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


def set_arg(arglist=None, key='', value=''):
    key, value = (str(key), str(value))
    sargs = arglist[:]
    assert key.startswith('-'), "key %s must start with '-' or '--'!" % key
    assert '=' not in key, 'key %s must not contain "="!' % key

    if key.startswith('--'):
        # Replace
        for index, item in enumerate(sargs):
            if item.startswith(key + '='):
                sargs[index] = key + '=' + value if value else key
                return sargs
        # Append
        sargs.append(key + '=' + value if value else key)
        return sargs

    # Replace or append short options (e.g.: ['-d', 'pfot'])
    elif key.startswith('-'):
        # Replace
        if key in sargs:
            index = sargs.index(key) + 1
            next_item = sargs[index]
            if value:
                assert not next_item.startswith('-'), "This option is already set but without a value!"
                sargs[index] = value
            else:
                assert next_item.startswith('-'), "This option seems to require a value!"
            return sargs
        # Append
        else:
            sargs.extend([key, value] if value else [key])
            return sargs


class Settings:
    def __init__(self, instance_dir, startup_args=None, log_file='', update_instance_mode=False):
        _log.info('Get settings for %sinstance with startup_args "%s" from "%s"'
                  '' % ('update_' if update_instance_mode else '', str(startup_args), instance_dir))

        self.odoo_manifest = '__openerp__.py'

        # instance_dir
        # ------------
        instance_dir = os.path.abspath(instance_dir)
        assert os.path.isdir(instance_dir), "Instance directory not found at %s!" % instance_dir
        self.instance_dir = instance_dir

        # Instance basics
        # ---------------
        self.instance = os.path.basename(instance_dir)
        self.instance_ini_file = pj(instance_dir, 'instance.ini')
        self.instance_core_tag = tools.inifile_to_dict(self.instance_ini_file)['core']

        # Startup arguments
        # -----------------
        # Initial startup arguments
        self.original_startup_args = startup_args[:]
        # Computed startup arguments
        self.startup_args = startup_args[:]

        # To make it easier block some "long" optionsn and convert the arguments to a more accessible list
        sargs = list()
        for item in self.startup_args:
            # Prepare a list from the startup_args where we split --name=value to ['--name', 'value']
            sargs.extend(str(item).split('=', 1) if item.startswith('--') else [item])
        avoid_long_options = ['--config', '--database', '--db_user', '--db_password', '--data-dir']
        not_allowed_options = [a for a in sargs if a in avoid_long_options]
        assert not not_allowed_options, "You must use the short form for cmd options %s" % not_allowed_options

        # Environment information
        # -----------------------
        self.production_server = tools.production_server_check(instance_dir)
        if not self.production_server:
            _log.warning("Development environment detected! May load development defaults!")

        # Make sure 'update_instance_settings' is used correctly
        _update_test = bool('_update' in self.instance)
        assert update_instance_mode is _update_test, "'_update' is %s in instance name %s" % (
            'mandatory' if update_instance_mode else 'missing', self.instance)

        # Base directory (contains instance directories and the odoo cores directory)
        # --------------
        if update_instance_mode:
            self.base_dir = dirname(dirname(dirname(self.instance_dir)))
        else:
            self.base_dir = dirname(self.instance_dir)
        assert os.path.isdir(self.base_dir), "Base directory not found at %s" % self.cores_dir

        # Core directories
        # ----------------
        # Directory for odoo cores
        self.cores_dir = pj(self.base_dir, 'cores')
        assert os.path.isdir(self.cores_dir), "Directory for odoo cores not found at %s" % self.cores_dir

        # Instance odoo core directory
        self.instance_core_dir = pj(self.cores_dir, 'online_' + self.instance_core_tag)
        if not update_instance_mode:
            assert os.path.isdir(self.instance_core_dir), "Instance core dir not found at %s" % self.instance_core_dir

        # Instance odoo-core information
        # ------------------------------
        self.core_remote_url = 'https://github.com/OpenAT/online.git'
        if update_instance_mode:
            self.core_commit = git.get_sha1(self.instance_core_dir, raise_exception=False)
            self.core_tag = git.get_tag(self.instance_core_dir, raise_exception=False)
        else:
            # core_commit
            self.core_commit = git.get_sha1(self.instance_core_dir)

            # core_tagcomputed startup arguments
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
                    self.core_tag = ''
                    _log.warning(core_tag_msg)

        # Check that the odoo core release tag matches the instance.ini core tag
        if self.instance_core_tag != self.core_tag:
            msg = ("Core commit tag from instance.ini '%s' not matching core_tag '%s' for commit in core dir %s!"
                   "" % (self.instance_core_tag, self.core_tag, self.instance_core_dir))
            if self.production_server and not update_instance_mode:
                raise Exception(msg)
            else:
                _log.warning(msg)

        # git repository information
        # --------------------------
        self.git_remote_url = git.get_remote_url(self.instance_dir)
        self.git_branch = git.get_current_branch(self.instance_dir)
        self.git_commit = git.get_sha1(self.instance_dir)

        # Linux information
        # -----------------
        # linux_user
        self.linux_user = self.instance
        # update mode
        if update_instance_mode:
            self.linux_user = self.instance.rsplit('_update')[0]
        # Development machine
        if not self.production_server:
            self.linux_user = pwd.getpwuid(os.getuid()).pw_name

        # linux_instance_service
        self.linux_instance_service = self.instance

        # odoo server configuration file
        # ------------------------------
        # server_conf_file
        self.server_conf_file = (sargs[sargs.index('-c') + 1] if '-c' in sargs else pj(instance_dir, 'server.conf'))
        # update mode
        if update_instance_mode:
            self.server_conf_file = pj(instance_dir, 'server.conf')
        # Set to empty string if the file does not exist!
        self.server_conf_file = '' if not os.path.isfile(self.server_conf_file) else self.server_conf_file
        # startup args
        if self.server_conf_file:
            self.startup_args = set_arg(self.startup_args, '-c', self.server_conf_file)

        # server_conf (Odoo server configuration file as dict)
        self.server_conf = tools.inifile_to_dict(self.server_conf_file) if self.server_conf_file else {}

        # Master password
        # ---------------
        self.master_password = self.server_conf.get('admin_passwd', 'admin')

        # Logging
        # -------
        # startup logfile (fsonline.py logfile)
        self.log_file = log_file

        # odoo logfile
        if '--logfile' in sargs:
            self.logfile = sargs[sargs.index('--logfile')+1]
            _log.info('Get odoo-logfile from startup arguments: %s' % self.logfile)
        elif 'logfile' in self.server_conf:
            self.logfile = self.server_conf['logfile']
            _log.info('Get odoo-logfile from server.conf: %s' % self.logfile)
        else:
            self.logfile = self.log_file
            _log.info('Get odoo-logfile from fsonline.py cmd-option --log_file: %s' % self.logfile)
        # startup args
        if self.logfile:
            self.startup_args = set_arg(self.startup_args, '--logfile', self.logfile)

        # XMLRPC PORTS
        # ------------
        self.xmlrpc_port = (sargs[sargs.index('--xmlrpc-port') + 1] if '--xmlrpc-port' in sargs
                            else self.server_conf.get('xmlrpc_port', '8069'))
        self.xmlrpcs_port = (sargs[sargs.index('--xmlrpcs-port') + 1] if '--xmlrpcs-port' in sargs
                             else self.server_conf.get('xmlrpcs_port'))
        # update mode
        if update_instance_mode:
            self.xmlrpc_port = str(int(self.xmlrpc_port) + 10) if self.xmlrpc_port else self.xmlrpc_port
            self.xmlrpcs_port = str(int(self.xmlrpcs_port) + 10) if self.xmlrpcs_port else self.xmlrpcs_port
        # startup args
        if self.xmlrpc_port:
            self.startup_args = set_arg(self.startup_args, '--xmlrpc-port', self.xmlrpc_port)
        if self.xmlrpcs_port:
            self.startup_args = set_arg(self.startup_args, '--xmlrpcs-port', self.xmlrpcs_port)

        # Database
        # --------
        # db_name
        self.db_name = sargs[sargs.index('-d')+1] if '-d' in sargs else self.server_conf.get('db_name')
        if not self.db_name:
            self.db_name = self.instance
        # update mode
        if update_instance_mode:
            self.db_name = self.server_conf.get('db_name', self.instance)
        # startup args
        self.startup_args = set_arg(self.startup_args, '-d', self.db_name)

        # db_user
        self.db_user = sargs[sargs.index('-r')+1] if '-r' in sargs else self.server_conf.get('db_user')
        # development default
        if not self.db_user and not self.production_server:
            self.db_user = 'vagrant'
        # update mode
        if update_instance_mode:
            self.db_user = self.server_conf.get('db_user', self.db_user)
        # startup args
        self.startup_args = set_arg(self.startup_args, '-r', self.db_user)
        assert self.db_user != "postgres", "Database user can not be 'postgres' for security reasons!"

        # db_password
        self.db_password = sargs[sargs.index('-w')+1] if '-w' in sargs else self.server_conf.get('db_password')
        # development default
        if not self.db_password and not self.production_server:
            self.db_password = 'vagrant'
        # update mode
        if update_instance_mode:
            self.db_password = self.server_conf.get('db_password', self.db_password)
        # startup args
        self.startup_args = set_arg(self.startup_args, '-w', self.db_password)

        # db_host
        self.db_host = sargs[sargs.index('--db_host')+1] if '--db_host' in sargs else self.server_conf.get('db_host')
        # development default
        if not self.db_host and not self.production_server:
            self.db_host = '127.0.0.1'
        # update mode
        if update_instance_mode:
            self.db_host = self.server_conf.get('db_host', self.db_host)
        # startup args
        self.startup_args = set_arg(self.startup_args, '--db_host', self.db_host)

        # db_port
        self.db_port = sargs[sargs.index('--db_port')+1] if '--db_port' in sargs else self.server_conf.get('db_port')
        # development default
        if not self.db_port and not self.production_server:
            self.db_port = '5432'
        # update mode
        if update_instance_mode:
            self.db_port = self.server_conf.get('db_port', self.db_port)
        # startup args
        self.startup_args = set_arg(self.startup_args, '--db_port', self.db_port)

        # db_template
        self.db_template = (sargs[sargs.index('--db-template')+1] if '--db-template' in sargs
                            else self.server_conf.get('db_template'))
        if not self.db_template:
            self.db_template = 'template0'
        # update mode
        if update_instance_mode:
            self.db_template = self.server_conf.get('db_template', self.db_template)
        # startup args
        self.startup_args = set_arg(self.startup_args, '--db-template', self.db_template)



        # odoo addon paths
        # ----------------
        # addons_path
        self.addons_path = (sargs[sargs.index('--addons-path')+1] if '--addons-path' in sargs
                            else self.server_conf.get('addons_path'))
        # update mode
        if update_instance_mode:
            self.addons_path = self.server_conf.get('addons_path')
        # Default addon paths
        if not self.addons_path:
            _log.warning('No addon paths given! Using default addon paths')
            self.addons_path = ','.join([pj(self.instance_core_dir, 'odoo/openerp/addons'),
                                         pj(self.instance_core_dir, 'odoo/addons'),
                                         pj(self.instance_core_dir, 'addons-loaded'),
                                         pj(instance_dir, 'addons')])
        # startup args
        self.startup_args = set_arg(self.startup_args, '--addons-path', self.addons_path)

        # instance_addons_dirs
        self.instance_addons_dirs = self.addons_path.split(',')
        for addon_dir in self.instance_addons_dirs:
            assert os.path.isdir(addon_dir), "Addon directory not found at %s!" % addon_dir

        # all_addon_directories
        self.all_addon_directories = list()
        for d in self.instance_addons_dirs:
            d = os.path.abspath(d)
            for f in os.listdir(d):
                f_dir = pj(d, f)
                if os.path.islink(f_dir):
                    link_path = os.path.realpath(f_dir)
                    if os.path.isfile(pj(link_path, self.odoo_manifest)):
                        self.all_addon_directories.append(link_path)
                elif os.path.isdir(f_dir) and os.path.isfile(pj(f_dir, self.odoo_manifest)):
                    self.all_addon_directories.append(f_dir)

        # data_dir
        # --------
        self.data_dir = sargs[sargs.index('-D')+1] if '-D' in sargs else self.server_conf.get('data_dir')
        # update mode
        if update_instance_mode:
            self.data_dir = self.server_conf.get('data_dir')
        # default data_dir
        if not self.data_dir:
            self.data_dir = pj(self.instance_dir, 'data_dir')
        self.data_dir = os.path.abspath(self.data_dir)
        if not update_instance_mode:
            assert os.path.isdir(self.data_dir), "Odoo data directory not found at %s!" % self.data_dir
        # startup args
        self.startup_args = set_arg(self.startup_args, '-D', self.data_dir)

        # filestore
        # ---------
        self.filestore = os.path.join(self.data_dir, 'filestore', self.db_name)
        if not os.path.isdir(self.filestore):
            _log.warning("'filestore' directory does not exist at %s" % self.filestore)
        assert self.filestore != '/', "Filestore path is '/'!"

        # ----------------------------
        # DEFAULT ODOO STARTUP OPTIONS
        # ----------------------------

        # --db-filter
        if '--db-filter' not in sargs and 'dbfilter' not in self.server_conf:
            self.startup_args = set_arg(self.startup_args, '--db-filter', '^'+self.db_name+'$')

        # --no-database-list
        if '--no-database-list' not in sargs and 'list_db' not in self.server_conf:
            self.startup_args = set_arg(self.startup_args, '--no-database-list')

        # --proxy-mode
        if '--proxy-mode' not in sargs and 'proxy_mode' not in self.server_conf:
            self.startup_args = set_arg(self.startup_args, '--proxy-mode')

        # --load=SERVER_WIDE_MODULES (Comma-separated list of server-wide modules)
        if '--load' not in sargs and 'server_wide_modules' not in self.server_conf:
            self.startup_args = set_arg(self.startup_args, '--load', 'web,web_kanban,dbfilter_from_header,connector')

        # --without-demo=all
        if '--without-demo' not in sargs and 'without_demo' not in self.server_conf:
            self.startup_args = set_arg(self.startup_args, '--without-demo', 'all')

        # -----------
        # HELPER DATA
        # -----------

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

            # DEPRECATED: 'status.ini'
            # WARNING: status.ini is deprecated since the new logging is good enough!
            #          The update_lock_file must be used to suppress updates!
            self.status_ini_name = 'status.ini'
            status_ini_file = pj(instance_dir, self.status_ini_name)
            self.status_ini_file = status_ini_file if os.path.isfile(status_ini_file) else ''
            self.status_ini_dict = tools.inifile_to_dict(self.instance_ini_file) if self.status_ini_file else dict()
            self.no_update = self.status_ini_dict.get('no_update', False)
            self.update_failed = self.status_ini_dict.get('update_failed', False)
            self.restore_failed = self.status_ini_dict.get('restore_failed', False)
            assert not self.no_update, "no_update set in status.ini"
            assert not self.update_failed, "update_failed set in status.ini"
            assert not self.restore_failed, "restore_failed set in status.ini"
            if self.status_ini_file:
                _log.warning("status.ini is deprecated! Please delete the file at %s!" % self.status_ini_file)

            assert not self.restore_failed, "'restore_failed' is set in status.ini at %s" % self.status_ini_file
            # 'update.lock'
            self.update_lock_file_name = 'update.lock'
            self.update_lock_file = pj(instance_dir, self.update_lock_file_name)

        _log.info("Instance '%s' computed startup arguments: %s" % (self.instance, self.startup_args))
        _log.debug("Instance Settings:\n%s" % pformat(self.__dict__))
