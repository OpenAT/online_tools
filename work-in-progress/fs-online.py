#!/usr/bin/env python
"""
This script can start, backup, restore or update FS-Online instances on production or development machines.

Order of Actions if multiple are given: Backup -> Restore -> Update -> Start

Conventions:
  - Instance folder name = Database name = Instance name = Linux user name (on prod machines)
  - server.conf is directly located in the instance directory (or missing on dev machines)
  - All paths are relative to the instance directory
  - All submodules are linked via ssh e.g.: git@github.com:OpenAT/fundraising_studio.git
  - online repository is either directly inside the instance e.g.:
    /opt/instances/[instance]/fundraising_studio/online
    or at the same level as the instance in folders like online_[SHA1] e.g.:
    /opt/instances/[instance]
    /opt/instances/online_88b145319056b9d6feac9c86458371cd12a3960c
  - Full online repo for pull and copy is located at the same level as the instance and called online e.g.:
    /opt/instances/online
  - online_tools repo is at the same level as the instances e.g.:
    /opt/instances/online_tools
  - status.ini was removed - all relevant info is logged to the update log file
  - if an update or restore fails a file called update_restore_failed is created -
    no further updates or restore will run by this script as long as this file exits except --force is set

HINT: This script has 4 main sections:
  - HELPER FUNCTIONS
  - SCRIPT MODES
  - MAIN ROUTINE
  - START
"""
from shell_tools import shell
import git_tools as git
import odoo_tools as ot
#
import argparse
import os
from os.path import join as pj
import sys
import ConfigParser
import pwd
import shutil
import time
import datetime
import zipfile
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from contextlib import closing
from xmlrpclib import ServerProxy

import logging

# Globally initialize the logging for this file
# Get a handle to the root logger (or instantiate it the first and only time)
# HINT: The root logger is a singleton so all calls to it will return the same object!
log = logging.getLogger()
log.setLevel(logging.DEBUG)

# Create a format object to be used in log handlers
log_formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Log in GMT time (instead of localtime)
log_formatter.converter = time.gmtime

# Start a log handler and add it to the logger
log_handler = logging.StreamHandler(sys.stdout)

# Configure the log format for the new handler
log_handler.setFormatter(log_formatter)

# Set log handler output level
log_handler.setLevel(logging.DEBUG)

# Add the handler to the root logger
log.addHandler(log_handler)


def excepthook(*eargs):
    # Get the root logger and log to CRITICAL
    logging.getLogger(__name__).critical('Uncaught exception:\n'
                                         '-------------------\n', exc_info=eargs)


# Redirect sys assertion outputs to the logger
sys.excepthook = excepthook


# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def _production_server_check(instance_dir):
    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    return os.path.exists(pj('/etc/init.d', instance))


def _service_exists(service_name):
    service_file = pj('/etc/init.d', service_name)
    if os.path.exists(service_file):
        return True
    return False


def _service_running(service):
    pidfile = pj('/var/run', service + '.pid')
    logging.debug("Check if service %s ist running by pidfile at %s" % (service, pidfile))
    if os.path.isfile(pidfile):
        with open(pidfile, 'r') as pidfile:
            pid = str(pidfile.readline()).rstrip('\n')
            proc_dir = pj('/proc', pid)
            logging.debug("Process ID from pidfile %s" % pid)
            logging.debug("Process directory to check for if service is running %s" % proc_dir)
            if os.path.exists(proc_dir):
                logging.debug("Service %s is running!" % service)
                return True
    logging.debug("Service %s is NOT running!" % service)
    return False


def _service_control(service, state, wait=10):
    logging.info("Service %s will be %sed" % (service, state))
    # Basic Checks
    assert state in ["start", "stop", "restart", "reload"], '_service_control(service, state, wait=10) ' \
                                                            '"state" must be start, stop, restart or reload'
    assert _service_exists(service), "Service %s not found at /etc/init.d/%s"
    # Service is already running and should be started
    if state == "start" and _service_running(service):
        logging.warn("Nothing to do! Service %s is already running." % service)
        return True
    # Service is already stopped and should be stopped
    if state == "stop" and not _service_running(service):
        logging.warn("Nothing to do! Service %s is already stopped." % service)
        return True

    # Set service state
    shell(['service', service, state])

    # Wait for service to change state
    logging.debug("Waiting %s seconds for service to change state")
    time.sleep(wait)

    # Return
    if (service in ["start", "restart", "reload"] and _service_running(service)) or \
       (service == "stop" and not _service_running(service)):
        logging.info("Service %s successfully changed state to %sed" % (service, state))
        return True
    else:
        logging.error('Service %s could not be %sed' % (service, state))
        return False


def inifile_to_dict(inifile, section='options'):
    log.info("Read and parse *.ini file %s" % inifile)
    inifile = os.path.normpath(inifile)
    assert os.path.isfile(inifile), 'File %s not found!' % inifile
    cparser = ConfigParser.SafeConfigParser()
    cparser.read(inifile)
    return dict(cparser.items(section))


class Settings:
    def __init__(self, instance_dir, startup_args=[], log_file=''):
        instance_dir = os.path.abspath(instance_dir)
        assert os.path.isdir(instance_dir), "Instance directory not found at %s!" % instance_dir

        # Make sure there is an instance.ini file
        instance_ini_file = pj(known_args.instance_dir, 'instance.ini')
        assert os.path.isfile(instance_ini_file), "File 'instance.ini' not found at %s!" % instance_ini_file

        # Basics
        self.instance_dir = instance_dir
        self.startup_args = startup_args

        # Environment information
        self.production_server = _production_server_check(instance_dir)

        # Instance Settings
        self.instance = os.path.basename(instance_dir)
        self.instance_ini_file = instance_ini_file
        self.instance_core_tag = inifile_to_dict(instance_ini_file)['core']
        self.instance_core_dir = pj(os.path.dirname(instance_dir), 'online_'+self.instance_core_tag)
        assert os.path.isdir(self.instance_core_dir), "Instance core dir not found at %s" % self.instance_core_dir

        # Odoo Core Information
        self.core_commit = git.get_sha1(self.instance_core_dir)
        try:
            self.core_tag = git.get_tag(self.instance_core_dir)
        except Exception as e:
            self.core_tag = False
            log.warning("Could not get a tag for current commit %s of odoo core %s"
                        "" % (self.core_commit, self.instance_core_dir))

        # Check that the odoo core release tag matches the instance.ini core tag
        if self.instance_core_tag != self.core_tag:
            msg = ("Core commit tag from instance.ini (%s) not matching core_tag (%s) for commit in core dir %s!"
                   "" % (self.instance_core_tag, self.core_tag, self.instance_core_dir))
            if self.production_server:
                raise Exception(msg)
            else:
                log.warning(msg)

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
        self.server_conf = inifile_to_dict(server_conf_file) if os.path.isfile(server_conf_file) else {}

        # Master password
        self.master_password = self.server_conf.get('admin_passwd') or 'admin'

        # Logging
        self.log_file = log_file
        self.logfile = (sa[sa.index('--logfile')+1] if '--logfile' in sa else self.server_conf.get('logfile'))
        if not self.logfile and self.log_file:
            self.logfile = self.log_file
            self.startup_args.extend(['--logfile='+self.logfile])

        # XMLRPC
        self.xmlrpc_port = (sa[sa.index('--xmlrpc-port')+1] if '--xmlrpc-port' in sa
                            else self.server_conf.get('xmlrpc_port') or '8069')
        self.xmlrpcs_port = (sa[sa.index('--xmlrpcs-port')+1] if '--xmlrpcs-port' in sa
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
        db_con_string = {
            'dbname': self.db_name,
            'user': self.db_user,
            'password': self.db_password,
            'host': self.db_host,
            'port': self.db_port
        }
        self.db_con_string = " ".join(str(key)+"='"+str(value)+"'" for key, value in db_con_string.iteritems())

        # postgres database connection string for psycopg2 (for dropping the instance db)
        postgres_db_con_string = db_con_string
        postgres_db_con_string['dbname'] = 'postgres'
        self.postgres_db_con_string = " ".join(str(key)+"='"+str(value)+"'"
                                               for key, value in postgres_db_con_string.iteritems())


def _odoo_access_check(instance_dir, odoo_config=None):
    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    odoo_config = odoo_config or _odoo_config(instance_dir)

    logging.debug('Checking odoo xmlrpc access for instance %s' % instance)

    # Getting xmlrpc connection parameters
    # Default Settings
    xmlrpc_interface = "127.0.0.1"
    xmlrpc_port = "8069"
    # Overwrite with xmlrpcs or xmlrpc from server.conf
    if odoo_config.get('xmlrpcs'):
        xmlrpc_interface = odoo_config.get('xmlrpcs_interface') or xmlrpc_interface
        xmlrpc_port = odoo_config.get('xmlrpcs_port') or xmlrpc_port
    elif odoo_config.get('xmlrpc'):
        xmlrpc_interface = odoo_config.get('xmlrpc_interface') or xmlrpc_interface
        xmlrpc_port = odoo_config.get('xmlrpc_port') or xmlrpc_port

    # Connect to odoo by xmlrpc
    odoo = ServerProxy('http://'+xmlrpc_interface+'/xmlrpc/db')


# ----------------------------
# SCRIPT MODES
# ----------------------------
def backup(instance_dir, backup_file='', odoo_cmd_startup_args=[], log_file=''):
    """
    Backup an FS-Online instance

    :param instance_dir: (str) Directory of the instance to backup
    :param backup_file: (str) Full Path and file name
    :param odoo_cmd_startup_args: (list) with cmd options
    :param log_file: (str) Full Path and file name
    :return: (str) 'backup_file' if backup worked or (boolean) 'False' if backup failed
    """
    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    log.info('----------------------------------------')
    log.info('BACKUP instance %s' % instance)
    log.info('----------------------------------------')

    # Get odoo settings
    log.info("Get instance settings from %s" % instance_dir)
    s = Settings(instance_dir, startup_args=odoo_cmd_startup_args, log_file=log_file)

    # Default backup file name
    if not backup_file:
        core_id = s.core_tag or s.core_commit
        start_str = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%S')
        assert core_id, "No commit tag or commit id found for odoo core at %s" % s.instance_core_dir
        backup_name = instance + '_' + start_str + '_' + core_id + '.zip'
        backup_file = pj(known_args.instance_dir, 'update', backup_name)

    # Clean backup_file path
    backup_file = os.path.abspath(backup_file)

    # Try a backup via http post request (= streaming)
    log.info("Try regular backup via http connection to odoo")
    try:
        result = ot.backup(s.db_name, backup_file, host=s.instance_local_url, master_pwd=s.master_password)
    except Exception as e:
        result = False
        log.warning("Http streaming backup failed! %s" % repr(e))

    # Try an alternative manual backup via file copy and pg_dump
    if not result:
        log.info("Try manual backup via database url and data_dir copy")
        try:
            result = ot.backup_manual(db_url=s.db_url, data_dir=s.data_dir, backup_file=backup_file)
        except Exception as e:
            result = False
            log.error("Manual backup failed! %s" % repr(e))

    # Log result
    if result:
        log.info("Backup of instance %s to %s done!" % (s.instance, result))
    else:
        log.critical("Backup of instance %s to %s FAILED!" % (s.instance, backup_file))
        return False

    # Return 'path to backup file' or False
    return result


def restore(instance_dir, backup_zip_file, odoo_cmd_startup_args=[], log_file='', backup_before_drop=False):
    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    backup_zip_file = os.path.abspath(backup_zip_file)
    logging.info('----------------------------------------')
    logging.info('RESTORE instance %s' % instance)
    logging.info('----------------------------------------')
    assert os.path.isdir(instance_dir), 'Instance directory not found at %s' % instance_dir
    assert os.path.isfile(backup_zip_file), 'Backup zip file not found at %s' % backup_zip_file

    # Load configuration
    log.info("Prepare settings")
    s = Settings(instance_dir, startup_args=odoo_cmd_startup_args, log_file=log_file)

    # Check if the database exists
    log.info("Check if the database %s exists" % s.db_name)
    try:
        conn_instance_db = psycopg2.connect(s.db_con_string)
        # Close the cursor again because we don't need it anymore
        conn_instance_db.close()
        db_exists = True
        log.warning("Database %s exists already!" % s.db_name)
    except Exception as e:
        log.info("Could not connect to the postgresql database %s: %s" % (s.db_name, repr(e)))
        db_exists = False

    # TODO: After debug set default value for backup_before_drop to True again: Backup before drop
    # TODO: Only run if the database is not empty!
    if db_exists and backup_before_drop:
        log.info("Backup instance %s before we drop the database %s" % (s.instance, s.db_name))
        pre_drop_backup_file = backup(instance_dir, odoo_cmd_startup_args=odoo_cmd_startup_args, log_file=log_file)
        assert pre_drop_backup_file, "Could not create instance backup!"
        log.info("Pre-restore instance backup created at %s" % pre_drop_backup_file)

    # Connect to 'postgres' database (should always exist!)
    try:
        conn_postgres_db = psycopg2.connect(s.postgres_db_con_string)
    except Exception as e:
        log.critical("Could not connect to the 'postgres' database!")
        raise e

    # Drop or create the instance database
    with closing(conn_postgres_db.cursor()) as cr:
        # Set the isolation level to ISOLATION_LEVEL_AUTOCOMMIT before DROP/CREATE
        # HINT: This is the same as: conn.autocommit = True
        log.info("Set the database isolation level to ISOLATION_LEVEL_AUTOCOMMIT before drop")
        conn_postgres_db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        # Drop instance database first
        if db_exists:
            log.info("Try to drop database %s" % s.db_name)
            # Drop other database connections
            log.info("Try to quit all other connections to the database %s before drop" % s.db_name)
            try:
                cr.execute("""SELECT pg_terminate_backend(pid)
                              FROM pg_stat_activity
                              WHERE pg_stat_activity.datname = '%s'
                              AND pid != pg_backend_pid()""" % s.db_name)
            except Exception as e:
                log.warning("Dropping connections to database %s failed! %s" % (s.db_name, repr(e)))

            # Drop database
            log.warning("Dropping database %s" % s.db_name)
            try:
                cr.execute('DROP DATABASE "%s"' % s.db_name)
            except Exception as e:
                log.critical("Could not drop database %s! %s" % (s.db_name, repr(e)))
                raise e

        # Create instance database
        # log.info("Try to create the database %s" % s.db_name)
        # try:
        #     cr.execute("""CREATE DATABASE %s
        #                   WITH OWNER %s
        #                   TEMPLATE template0
        #                   ENCODING 'UTF8'""" % (s.db_name, s.db_user))
        # except Exception as e:
        #     log.critical("Could not create database %s!" % s.db_name)
        #     raise e

    # Remove old filestore directory
    if os.path.isdir(s.filestore):
        log.warning("Remove existing filestore at %s" % s.filestore)
        shutil.rmtree(s.filestore)

    # Restore via odoo (http connection)
    log.info("Restore odoo backup by http request")
    ot.restore(s.db_name, backup_zip_file, host=s.instance_local_url, master_pwd=s.master_password)

    # TODO: Manual restore via pg_dump and file copy

    # Return result
    return True


def update(settings=None):
    logging.info('----------------------------------------')
    logging.info('UPDATE instance')
    logging.info('----------------------------------------')
    exit(0)


def start(instance_dir, cmd_args=[], log_file=''):
    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    log.info('START INSTANCE %s' % instance)
    log.info('---')

    # Load configuration
    log.info("Prepare settings")
    s = Settings(instance_dir, startup_args=cmd_args, log_file=log_file)

    # Change current working directory to the folder odoo_dir inside the repo online
    working_dir = pj(s.instance_core_dir, 'odoo')
    log.info("Change working directory to 'odoo' folder of core dir %s" % working_dir)
    os.chdir(working_dir)

    # Change the current python script working directory to folder odoo_dir inside the repo online
    log.info("Set python working directory (sys.path[0] and sys.argv[0]) to 'odoo' folder %s" % working_dir)
    sys.path[0] = sys.argv[0] = working_dir
    assert working_dir == os.getcwd() == sys.path[0], (
            'Could not change working directory to %s !' % working_dir)

    # Overwrite the original script cmd args with the odoo-only ones
    user = pwd.getpwuid(os.getuid())
    log.info("Set sys.argv: %s" % ' '.join(s.startup_args))
    sys.argv = sys.argv[0:1] + s.startup_args

    # Log basic info
    logging.info('Production Server: %s' % s.production_server)
    logging.info('Instance: %s' % s.instance)
    logging.info('Instance core tag: %s' % s.instance_core_tag)
    logging.info('Instance core dir: %s' % s.instance_core_dir)
    logging.info('Instance data_dir: %s' % s.data_dir)
    logging.info('Instance addon_path: %s' % s.addons_path)

    # Log system environment information
    log.info("Environment current system user: %s" % user)
    log.info("Environment $PATH: %s" % os.getcwd())
    log.info("Environment $WORKING_DIRECTORY: %s" % os.environ.get("WORKING_DIRECTORY", ""))
    log.info("Environment $PYTHONPATH: %s" % os.environ.get("PYTHONPATH", ""))

    # Run odoo
    # HINT: 'import odoo' works because we are now in the FS-Online core directory that contains the folder odoo
    # ATTENTION: To make this work openerp-gevent must be in some path that python can load!
    log.info("Run odoo.main() from odoo.py")
    log.info("---")

    # Reset logging
    # logging.shutdown()
    reload(logging)

    import odoo
    odoo.main()


# ------------------------------------
# COMMAND PARSER DEFAULT FUNCTION CALL
# ------------------------------------
def fs_online():
    # BACKUP
    if known_args.backup:
        # If backup files is not set set it to an empty string
        if known_args.backup is True:
            known_args.backup = ''

        result = backup(known_args.instance_dir, backup_file=known_args.backup,
                        odoo_cmd_startup_args=unknown_args, log_file=known_args.log_file)
        if result:
            exit(0)
        else:
            exit(100)

    # RESTORE
    if known_args.restore:
        assert known_args.restore, "No backup file given!"
        restore(known_args.instance_dir, backup_zip_file=known_args.restore,
                odoo_cmd_startup_args=unknown_args, log_file=known_args.log_file)
        exit(0)

    # UPDATE
    if known_args.update or known_args.update_to_rev:
        # TODO
        exit(0)

    # START
    return start(known_args.instance_dir, cmd_args=unknown_args, log_file=known_args.log_file)


# ----------------------------
# COMMAND PARSER
# ----------------------------
# Create a new argument-parser object
parser = argparse.ArgumentParser()

# Add Arguments
parser.add_argument('instance_dir', help="Instance directory")
parser.add_argument('--log_file',
                    metavar='Not set for STDOUT or /path/log_file.log',
                    help='Log file for this script and odoo. Emtpy for stdout. '
                         'Add "--logfile=/path/too/odoo.log" or add "logfile = /path/too/odoo.log" to server.conf '
                         'if you want a separate log-file for the odoo log messages.')
parser.add_argument('--verbose', help='Log Level',
                    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                    default='INFO')

# Additional modes for this script
parser.add_argument('--backup',
                    action='store_true',
                    #default='',
                    #metavar='EMTPY or /path/to/backup.zip',
                    help='Create a backup at the given file name! Will backup to default location '
                         '/[instance_dir]/update/[backupname.zip] if no backupfile is given!')

parser.add_argument('--restore',
                    metavar='/path/to/backup/backup.zip',
                    help='Restore from backup zip or from folder')

parser.add_argument('--update',
                    action='store_true',
                    #default='',
                    #metavar='EMPTY for latest commit OR Branch, Tag or SHA1 e.g.: --update=o8r168',
                    help='Update the instance to latest commit of the instance repository on github.')

# Set a default function to be called after the initialization of the parser object
parser.set_defaults(func=fs_online)


# --------------------
# START
# --------------------
if __name__ == "__main__":
    # Globally available data stores (vars):
    # -------------------------------------------------------------------------------
    # known_args        (Namespace)                 CMD settings known to command parser
    # unknown_args      (list)                      CMD settings not set in command parser
    # log               (logging instance)          Globally used logger __main__
    # -------------------------------------------------------------------------------

    # Get the command line arguments
    known_args, unknown_args = parser.parse_known_args()

    # Make sure the instance path exits
    assert os.path.exists(known_args.instance_dir), 'Instance directory not found at %s!' % known_args.instance_dir

    # Make sure the instance.ini is available
    instance_ini_file = pj(known_args.instance_dir, 'instance.ini')
    assert os.path.isfile(instance_ini_file), 'File instance.ini not found at %s!' % instance_ini_file

    # START LOGGING
    # -------------

    # Set the log Level
    log_level = logging.getLevelName(known_args.verbose)
    log.setLevel(log_level)

    # Start logging to file
    if known_args.log_file:
        known_args.log_file = os.path.abspath(known_args.log_file)
        assert os.access(os.path.dirname(known_args.log_file), os.W_OK), 'Logfile location %s not writeable!' \
                                                                         '' % known_args.log_file

        # Rest the log handler(s)
        for handler in log.handlers[:]:
            log.removeHandler(handler)

        # Add the file handler
        log_handler = logging.FileHandler(filename=known_args.log_file)
        log_handler.setFormatter(log_formatter)
        log_handler.setLevel(log_level)

        # Add the log handler to the root logger
        log.addHandler(log_handler)

    # Log script start
    log.info('================================================================================')
    log.info('fs-online.py %s' % ' '.join(sys.argv))
    log.info('================================================================================')

    # START fs_online()
    # -----------------
    # HINT: See "parser.set_defaults(func=fs_online)" above
    known_args.func()
