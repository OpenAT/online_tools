# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
from os.path import dirname as dirname
import pwd
from pprint import pformat

import tools
import tools_git as git

import logging
_log = logging.getLogger()


class Settings:
    def __init__(self, instance_dir, startup_args=None, log_file='', update_instance_mode=False):
        _log.info('Get settings for %sinstance at %s' % ('update_' if update_instance_mode else '', instance_dir))
        startup_args = list() if not startup_args else startup_args

        instance_dir = os.path.abspath(instance_dir)
        assert os.path.isdir(instance_dir), "Instance directory not found at %s!" % instance_dir

        # Make sure there is an instance.ini file
        instance_ini_file = pj(instance_dir, 'instance.ini')
        assert os.path.isfile(instance_ini_file), "File 'instance.ini' not found at %s!" % instance_ini_file

        # Basics
        self.instance_dir = instance_dir
        self.startup_args = startup_args

        # Environment information
        self.production_server = tools.production_server_check(instance_dir)
        if not self.production_server:
            _log.warning("Development environment detected! May load development defaults!")

        # Instance Settings
        self.instance = os.path.basename(instance_dir)
        self.instance_ini_file = instance_ini_file
        self.instance_core_tag = tools.inifile_to_dict(instance_ini_file)['core']

        # Make sure 'update_instance_settings' is used correctly
        _update_test = bool('_update' in self.instance)
        assert update_instance_mode is _update_test, "'_update' is %s in instance name %s" % (
            'mandatory' if update_instance_mode else 'missing', self.instance)

        # Base directory (contains instance directories and the odoo cores directory)
        if update_instance_mode:
            self.base_dir = dirname(dirname(dirname(self.instance_dir)))
        else:
            self.base_dir = dirname(self.instance_dir)
        assert os.path.isdir(self.base_dir), "Base directory not found at %s" % self.cores_dir

        # Directory for odoo cores
        self.cores_dir = pj(self.base_dir, 'cores')
        assert os.path.isdir(self.cores_dir), "Directory for odoo cores not found at %s" % self.cores_dir

        # Instance odoo core directory
        self.instance_core_dir = pj(self.cores_dir, 'online_' + self.instance_core_tag)
        if not update_instance_mode:
            assert os.path.isdir(self.instance_core_dir), "Instance core dir not found at %s" % self.instance_core_dir

        # Instance odoo-core information
        self.core_remote_url = 'https://github.com/OpenAT/online.git'
        if not os.path.exists(self.instance_core_dir) and update_instance_mode:
            _log.warning('Odoo core of update_instance not found at %s' % self.instance_core_dir)
            self.core_commit = ''
            self.core_tag = ''
        else:
            # core_commit
            self.core_commit = git.get_sha1(self.instance_core_dir)

            # core_tag
            try:
                self.core_tag = git.get_tag(self.instance_core_dir)
            except Exception as e:
                core_tag_msg = "Could not get a tag for current commit %s of odoo core %s" % (
                    self.core_commit, self.instance_core_dir)

                # Production Server
                if self.production_server:
                    _log.error(core_tag_msg)
                    raise e

                # Development Server
                else:
                    self.core_tag = False
                    _log.warning(core_tag_msg)

        # Check that the odoo core release tag matches the instance.ini core tag
        if self.instance_core_tag != self.core_tag:
            msg = ("Core commit tag from instance.ini (%s) not matching core_tag (%s) for commit in core dir %s!"
                   "" % (self.instance_core_tag, self.core_tag, self.instance_core_dir))
            if self.production_server and not update_instance_mode:
                raise Exception(msg)
            else:
                _log.warning(msg)

        # git repository information
        self.git_remote_url = git.get_remote_url(self.instance_dir)
        self.git_branch = git.get_current_branch(self.instance_dir)
        self.git_commit = git.get_sha1(self.instance_dir)

        # Linux information
        # ATTENTION: We use the current linux user if we are not in an production environment?
        current_linux_user = pwd.getpwuid(os.getuid())
        self.linux_user = self.instance if self.production_server else current_linux_user.pw_name

        # Prepare a list from the startup_args where we split --name=value to ['--name', 'value']
        sargs = []
        for item in startup_args:
            sargs.extend(str(item).split('=', 1) if item.startswith('--') else [item])

        # To make it easier block some "long" options
        avoid_long_options = ['--config', '--database', '--db_user', '--db_password', '--data-dir']
        not_allowed_options = [a for a in sargs if a in avoid_long_options]
        assert not not_allowed_options, "You must use the short form for cmd options %s" % not_allowed_options

        # Try to set odoo server configuration file
        if '-c' in self.startup_args:
            server_conf_file = startup_args[startup_args.index('-c')+1]
            assert os.path.isfile(server_conf_file), "Server config file not found at %s" % server_conf_file
        else:
            server_conf_file = pj(instance_dir, 'server.conf')
            # ATTENTION: Add the default server.conf to the startup_args !
            if os.path.isfile(server_conf_file):
                self.startup_args.extend(['-c', server_conf_file])

        # Odoo server configuration file as dict
        self.server_conf = tools.inifile_to_dict(server_conf_file) if os.path.isfile(server_conf_file) else {}

        # Master password
        self.master_password = self.server_conf.get('admin_passwd') or 'admin'

        # Logging
        # Priority: 1.) from command line --logfile  2.) from server.conf  3.) from method interface log_file
        # TODO: It is really not good to have two variables with nearly the same name! Maybe one is enough!
        self.log_file = log_file
        self.logfile = (sargs[sargs.index('--logfile')+1] if '--logfile' in sargs else self.server_conf.get('logfile'))
        if not self.logfile and self.log_file:
            self.logfile = self.log_file
            self.startup_args.extend(['--logfile='+self.logfile])

        # XMLRPC PORTS
        self.xmlrpc_port = (sargs[sargs.index('--xmlrpc-port') + 1] if '--xmlrpc-port' in sargs
                            else self.server_conf.get('xmlrpc_port') or '8069')
        self.xmlrpcs_port = (sargs[sargs.index('--xmlrpcs-port') + 1] if '--xmlrpcs-port' in sargs
                             else self.server_conf.get('xmlrpcs_port'))
        if update_instance_mode:
            self.xmlrpc_port = str(int(self.xmlrpc_port) + 10)
            self.xmlrpcs_port = str(int(self.xmlrpcs_port + 10)) if self.xmlrpcs_port else self.xmlrpcs_port

        # Database
        self.db_name = sargs[sargs.index('-d')+1] if '-d' in sargs else self.server_conf.get('db_name')
        if not self.db_name:
            self.db_name = self.instance
            self.startup_args.extend(['-d', self.db_name])

        self.db_user = sargs[sargs.index('-r')+1] if '-r' in sargs else self.server_conf.get('db_user')
        # development default
        if not self.db_user and not self.production_server:
            self.db_user = 'vagrant'
            self.startup_args.extend(['-r', self.db_user])
        assert self.db_user != "postgres", "Database user can not be 'postgres' for security reasons!"

        self.db_password = sargs[sargs.index('-w')+1] if '-w' in sargs else self.server_conf.get('db_password')
        # development default
        if not self.db_password and not self.production_server:
            self.db_password = 'vagrant'
            self.startup_args.extend(['-w', self.db_password])

        self.db_host = sargs[sargs.index('--db_host')+1] if '--db_host' in sargs else self.server_conf.get('db_host')
        # development default
        if not self.db_host and not self.production_server:
            self.db_host = '127.0.0.1'
            self.startup_args.extend(['--db_host='+self.db_host])

        self.db_port = sargs[sargs.index('--db_port')+1] if '--db_port' in sargs else self.server_conf.get('db_port')
        # development default
        if not self.db_port and not self.production_server:
            self.db_port = '5432'
            self.startup_args.extend(['--db_port='+self.db_port])

        self.db_template = (sargs[sargs.index('--db-template')+1] if '--db-template' in sargs
                            else self.server_conf.get('db_template'))
        if not self.db_template:
            self.db_template = 'template0'
            self.startup_args.extend(['--db-template='+self.db_template])

        # addons_path
        self.addons_path = (sargs[sargs.index('--addons-path')+1] if '--addons-path' in sargs
                            else self.server_conf.get('addons_path'))
        if self.addons_path:
            logging.warning("The addons_path is set so it will NOT be computed! %s!" % self.addons_path)
        if not self.addons_path:
            self.addons_path = ','.join([pj(self.instance_core_dir, 'odoo/openerp/addons'),
                                         pj(self.instance_core_dir, 'odoo/addons'),
                                         pj(self.instance_core_dir, 'addons-loaded'),
                                         pj(instance_dir, 'addons')])
            # HINT: Only add the addons path to the command line if not in server conf or command line already
            self.startup_args.extend(['--addons-path='+self.addons_path])

        self.instance_addons_dirs = self.addons_path.split(',')
        for addon_dir in self.instance_addons_dirs:
            assert os.path.isdir(addon_dir), "Addon directory not found at %s!" % addon_dir

        # data_dir
        self.data_dir = sargs[sargs.index('-D')+1] if '-D' in sargs else self.server_conf.get('data_dir')
        if not self.data_dir:
            self.data_dir = pj(self.instance_dir, 'data_dir')
            self.startup_args.extend(['-D', self.data_dir])
        self.data_dir = os.path.abspath(self.data_dir)
        assert os.path.isdir(self.data_dir), "Odoo data directory not found at %s!" % self.data_dir

        # filestore
        filestore = os.path.join(self.data_dir, 'filestore', self.db_name)
        self.filestore = filestore if os.path.isdir(filestore) else ''
        assert filestore != '/', "Filestore path is '/'!"

        # Instance URL
        self.instance_local_url = 'http://127.0.0.1:'+self.xmlrpc_port

        # Database URL
        self.db_url = ('postgresql://' + self.db_user + ':' + self.db_password +
                       '@' + self.db_host + ':' + self.db_port + '/' + self.db_name)

        # Instance database connection string for psycopg2
        self.db_con_dict = {
            'dbname': self.db_name,
            'user': self.db_user,
            'password': self.db_password,
            'host': self.db_host,
            'port': self.db_port
        }
        self.db_con_string = " ".join(str(key)+"='"+str(value)+"'" for key, value in self.db_con_dict.iteritems())

        # System database 'postgres' connection string for psycopg2 (e.g.: for dropping the instance db)
        self.postgres_db_con_dict = {
            'dbname': 'postgres',
            'user': self.db_user,
            'password': self.db_password,
            'host': self.db_host,
            'port': self.db_port
        }
        self.postgres_db_con_string = " ".join(str(key)+"='"+str(value)+"'"
                                               for key, value in self.postgres_db_con_dict.iteritems())

        # Status and update information
        if not update_instance_mode:
            status_ini_file = pj(instance_dir, 'status.ini')
            self.status_ini_file = status_ini_file if os.path.isfile(status_ini_file) else ''
            self.status_ini_dict = tools.inifile_to_dict(instance_ini_file) if self.status_ini_file else dict()
            self.no_update = self.status_ini_dict.get('no_update', False)
            self.update_failed = self.status_ini_dict.get('update_failed', False)
            self.restore_failed = self.status_ini_dict.get('restore_failed', False)
            assert not self.restore_failed, "'restore_failed' is set in status.ini at %s" % self.status_ini_file
            self.update_lock_file_name = 'update.lock'
            self.update_lock_file = pj(instance_dir, self.update_lock_file_name)

        _log.debug("Instance Settings:\n%s" % pformat(self.__dict__))
