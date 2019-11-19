# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
import tools
import tools_git as git

import logging
_log = logging.getLogger()


class Settings:
    def __init__(self, instance_dir, startup_args=None, log_file=''):
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

        # Instance Settings
        self.instance = os.path.basename(instance_dir)
        self.instance_ini_file = instance_ini_file
        self.instance_core_tag = tools.inifile_to_dict(instance_ini_file)['core']
        self.instance_core_dir = pj(os.path.dirname(instance_dir), 'cores', 'online_'+self.instance_core_tag)
        assert os.path.isdir(self.instance_core_dir), "Instance core dir not found at %s" % self.instance_core_dir

        # Odoo Core Information
        self.core_commit = git.get_sha1(self.instance_core_dir)
        try:
            self.core_tag = git.get_tag(self.instance_core_dir)
        except Exception as e:
            self.core_tag = False
            _log.warning("Could not get a tag for current commit %s of odoo core %s"
                         "" % (self.core_commit, self.instance_core_dir))

        # Check that the odoo core release tag matches the instance.ini core tag
        if self.instance_core_tag != self.core_tag:
            msg = ("Core commit tag from instance.ini (%s) not matching core_tag (%s) for commit in core dir %s!"
                   "" % (self.instance_core_tag, self.core_tag, self.instance_core_dir))
            if self.production_server:
                raise Exception(msg)
            else:
                _log.warning(msg)

        # Prepare a list from the startup_args where we split --name=value to ['--name', 'value']
        sa = []
        for item in startup_args:
            sa.extend(str(item).split('=', 1) if item.startswith('--') else [item])

        # To make it easier block some "long" options
        avoid_long_options = ['--config', '--database', '--db_user', '--db_password', '--data-dir']
        not_allowed_options = [a for a in sa if a in avoid_long_options]
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
        self.log_file = log_file
        self.logfile = (sa[sa.index('--logfile')+1] if '--logfile' in sa else self.server_conf.get('logfile'))
        if not self.logfile and self.log_file:
            self.logfile = self.log_file
            self.startup_args.extend(['--logfile='+self.logfile])

        # XMLRPC
        self.xmlrpc_port = (sa[sa.index('--xmlrpc-port') + 1] if '--xmlrpc-port' in sa
                            else self.server_conf.get('xmlrpc_port') or '8069')
        self.xmlrpcs_port = (sa[sa.index('--xmlrpcs-port') + 1] if '--xmlrpcs-port' in sa
                             else self.server_conf.get('xmlrpcs_port'))

        # Database
        self.db_name = sa[sa.index('-d')+1] if '-d' in sa else self.server_conf.get('db_name')
        if not self.db_name:
            self.db_name = self.instance
            self.startup_args.extend(['-d', self.db_name])

        self.db_user = sa[sa.index('-r')+1] if '-r' in sa else self.server_conf.get('db_user')
        if not self.db_user:
            self.db_user = 'vagrant'
            self.startup_args.extend(['-r', self.db_user])
        assert self.db_user != "postgres", "Database user can not be 'postgres' for security reasons!"

        self.db_password = sa[sa.index('-w')+1] if '-w' in sa else self.server_conf.get('db_password')
        if not self.db_password:
            self.db_password = 'vagrant'
            self.startup_args.extend(['-w', self.db_password])

        self.db_host = sa[sa.index('--db_host')+1] if '--db_host' in sa else self.server_conf.get('db_host')
        if not self.db_host:
            self.db_host = '127.0.0.1'
            self.startup_args.extend(['--db_host='+self.db_host])

        self.db_port = sa[sa.index('--db_port')+1] if '--db_port' in sa else self.server_conf.get('db_port')
        if not self.db_port:
            self.db_port = '5432'
            self.startup_args.extend(['--db_port='+self.db_port])

        self.db_template = (sa[sa.index('--db-template')+1] if '--db-template' in sa
                            else self.server_conf.get('db_template'))
        if not self.db_template:
            self.db_template = 'template0'
            self.startup_args.extend(['--db-template='+self.db_template])

        # addons_path
        self.addons_path = (sa[sa.index('--addons-path')+1] if '--addons-path' in sa
                            else self.server_conf.get('addons_path'))
        if self.addons_path:
            logging.warning("The addons_path is set so it will NOT be computed! %s!" % self.addons_path)
        if not self.addons_path:
            self.addons_path = ','.join([pj(self.instance_core_dir, 'odoo/openerp/addons'),
                                         pj(self.instance_core_dir, 'odoo/addons'),
                                         pj(self.instance_core_dir, 'addons-loaded'),
                                         pj(instance_dir, 'addons')])
            self.startup_args.extend(['--addons-path='+self.addons_path])

        self.instance_addons_dirs = self.addons_path.split(',')
        for addon_dir in self.instance_addons_dirs:
            assert os.path.isdir(addon_dir), "Addon directory not found at %s!" % addon_dir

        # data_dir
        self.data_dir = sa[sa.index('-D')+1] if '-D' in sa else self.server_conf.get('data_dir')
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

