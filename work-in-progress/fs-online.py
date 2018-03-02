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
#
import argparse
import os
from os.path import join as pj
import sys
import logging
import ConfigParser
import pwd
import shutil
import time
import zipfile
from xmlrpclib import ServerProxy


# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def excepthook(*eargs):
    # Get the root logger and log to CRITICAL
    logging.getLogger(__name__).critical('Uncaught exception:\n'
                                         '-------------------\n', exc_info=eargs)
    

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


def _test_optional_odoo_args(optional_args=list()):
    # HINT: These settings should NOT be assigned by command line!
    #       For development use a local server.conf if you need to overwrite any of these settings!
    # HINT: -D = data_dir
    unsupported_options = [
        '-d', '--database',
        '-r', '--db_user',
        '-w', '--db_password',
        '--db_host',
        '--db_port',
        '--pg_path',
        '--addons-path',
        '-D',
        '--load',
        '--workers',
        '--db-template',
    ]
    # Cleanup: remove white space and option values
    optional_args_clean = [x.strip().split('=')[0] for x in optional_args if x.strip()[0] == '-']
    for option in optional_args_clean:
        assert option not in unsupported_options, \
            'Odoo option %s not supported on command line! Use local server.conf instead.' % option
    return True


def _odoo_config(instance_dir, cmd_args=list()):
    """ Parse odoo configuration file and command line arguments

    :param instance_dir: string
    :param cmd_args: list Optional CMD Arguments that will be passed on to odoo
    :return: dict Odoo configuration dictionary with odoo startup commandline arguments
    """
    # Check for production server
    production_server = _production_server_check(instance_dir)
    
    # Assert instance_dir
    instance_dir = os.path.normpath(instance_dir)
    assert os.path.exists(instance_dir), 'Instance path %s not found!' % instance_dir

    # Assert that no odoo cmd options are in cmd_args that will be set here
    _test_optional_odoo_args(cmd_args)

    # Odoo server config default development values
    # HINT: Will be overridden later on from values of the server.conf file if given
    instance = os.path.basename(instance_dir)
    oc = {
        'db_name': instance,
        'db_user': 'vagrant',
        'db_password': 'vagrant',
        'db_host': '127.0.0.1',
        'db_port': '5432',
        'data_dir': pj(instance_dir, 'data_dir'),
        'server_wide_modules': 'web,web_kanban,dbfilter_from_header',
        'workers':'0'
    }
    # Get server.conf path
    server_conf = None  # e.g.: /opt/instances/dadi/server.conf
    if '-c' in cmd_args:
        server_conf = cmd_args[cmd_args.index('-c') + 1]
        assert os.path.isfile(server_conf), "Odoo server.conf file %s set by -c is missing!" % server_conf
    else:
        server_conf = pj(instance_dir, 'server.conf')

    # Overwrite settings by settings from server.conf ini file
    # HINT: This is only needed to get the values for "workers" and "server_wide_modules" because they are required
    #       in startup_args. odoo will always search for server.conf or it is given by -c
    if os.path.isfile(server_conf):
        logging.info('Read odoo server.conf from: %s' % server_conf)
        oc.update(inifile_to_dict(server_conf))
    else:
        # HINT: On prod machines there has to be a server.conf!
        assert not production_server, "Odoo server.conf file %s missing on production machine!" % server_conf
        logging.warn('No server.conf found at %s! Using development defaults instead.' % server_conf)

    # Get online repo location
    if os.path.isfile(pj(instance_dir, 'fundraising_studio/online/odoo/odoo.py')):
        oc['online_repo'] = pj(instance_dir, 'fundraising_studio/online')
    else:
        # Get SHA1 of submodule repo "online"
        online_sha1 = git.submodule_sha1(instance_dir, submodule='fundraising_studio/online')
        oc['online_repo'] = pj(os.path.dirname(instance_dir), 'online_' + online_sha1)
    assert os.path.exists(oc['online_repo']), 'Repository online not found at %s !' % oc['online_repo']
    logging.info('Repository online is located at %s' % oc['online_repo'])

    # odoo addons paths
    oc['addons'] = [pj(oc['online_repo'], 'odoo/openerp/addons'),
                    pj(oc['online_repo'], 'odoo/addons'),
                    pj(oc['online_repo'], 'addons-loaded')]

    # instance addons path
    instance_addons = pj(instance_dir, 'addons')
    for dirpath, dirnames, files in os.walk(instance_addons):
        if dirnames:
            # TODO better check if addons are in the addons folder (search for __openerp.py__)
            logging.info('Instance addons found at %s .' % instance_addons)
            oc['addons'].append(instance_addons)
        else:
            logging.warning('No instance addons found at %s !' % instance_addons)

    # Database URL for backup and restore modes
    # Example: 'postgresql://vagrant:vagrant@127.0.0.1:5432/dadi'
    oc['db_url'] = 'postgresql://' + oc['db_user'] + ':' + oc['db_password'] \
                   + '@' + oc['db_host'] + ':' + oc['db_port'] + '/' + oc['db_name']

    # Create the Startup Arguments for ../odoo/openerp/cli method main
    oc['startup_args'] = ['-d', oc['db_name'],
                          '-r', oc['db_user'],
                          '-w', oc['db_password'],
                          '--db_host', oc['db_host'],
                          '--db_port', oc['db_port'],
                          '--addons-path', ','.join(oc['addons']),
                          '-D', oc['data_dir'],
                          '--load', oc['server_wide_modules'],
                          '--workers', oc['workers'],
                          '--db-template', oc.get('db-template', 'template0')
                          ]
    return oc


class Settings:
    def __init__(self, instance_dir, startup_args=[], log_level='INFO', log_file=''):
        instance_dir = os.path.abspath(instance_dir)
        assert os.path.isdir(instance_dir), "Instance directory not found at %s!" % instance_dir

        instance_ini_file = pj(known_args.instance_dir, 'instance.ini')
        assert os.path.isfile(instance_ini_file), "File 'instance.ini' not found at %s!" % instance_ini_file

        # Basics
        self.instance_dir = instance_dir
        self.startup_args = startup_args

        # Logging
        self.log_file = log_file
        self.log_level = log_level

        # Environment information
        self.production_server = _production_server_check(instance_dir)

        # Instance Settings
        self.instance = os.path.basename(instance_dir)
        self.instance_ini_file = instance_ini_file
        self.instance_core_tag = inifile_to_dict(S.instance_ini_file)['core']
        self.instance_core_dir = pj(instance_dir, 'online_'+self.instance_core_tag)
        icd_tag = git.get_tag(self.instance_core_dir)
        assert self.instance_core_tag == icd_tag, (
                "Core from instance.ini is %s not matching tag in core dir %s!" % (self.instance_core_tag, icd_tag))

        # odoo startup configuration
        # TODO: Make sure none of the long versions (-d = --database) are in startup_args
        if '-c' in self.startup_args:
            server_conf_file = startup_args[startup_args.index('-c')+1]
        else:
            server_conf_file = pj(instance_dir, 'server.conf')
        self.server_conf = inifile_to_dict(server_conf_file) if os.path.isfile(server_conf_file) else {}

        sa = [i for i in item.split('=') for item in startup_args]
        self.db_name = sa[sa.index('-d')+1] if '-d' in sa else self.server_conf.get('db_name')
        self.db_user = sa[sa.index('-r')+1] if '-r' in sa else self.server_conf.get('db_user')
        self.db_password = sa[sa.index('-w')+1] if '-w' in sa else self.server_conf.get('db_password')
        self.db_host = sa[sa.index('--db_host')+1] if '--db_host' in sa else self.server_conf.get('db_host')
        self.db_port = sa[sa.index('--db_port')+1] if '--db_port' in sa else self.server_conf.get('db_port')
        self.db_template = (sa[sa.index('--db-template')+1] if '--db-template' in sa
                            else self.server_conf.get('db_template'))
        self.addons_path = (sa[sa.index('--addons-path')+1] if '--addons-path' in sa
                            else self.server_conf.get('addons_path'))

        # Set default startup values if not set by command line or server.conf
        if not self.db_name:
            self.startup_args.extend(['-d', self.instance])
        if not self.db_user:
            self.startup_args.extend(['-r', 'vagrant'])
        if not self.db_password:
            self.startup_args.extend(['-w', 'vagrant'])
        if not self.db_host:
            self.startup_args.extend(['--db_host=127.0.0.1'])
        if not self.db_port:
            self.startup_args.extend(['--db_port=5432'])
        if not self.db_template:
            self.startup_args.extend(['--db-template=template0'])
        if not self.addons_path:
            addons_dirs = ','.join([pj(self.instance_core_dir, 'odoo/openerp/addons'),
                                    pj(self.instance_core_dir, 'odoo/addons'),
                                    pj(self.instance_core_dir, 'addons-loaded'),
                                    pj(instance_dir, 'addons')])
            self.addons_path.extend(['--addons-path='+addons_dirs])

        # Set instance addons dirs based on addons_path
        self.instance_addons_dirs = self.addons_path.split(',')


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
def backup(instance_dir, backup_file=None, start_time=str(time.strftime('%Y-%m-%d_%H-%M-%S'))):
    begin_backup = time.time()
    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    logging.info('----------------------------------------')
    logging.info('BACKUP instance %s' % instance)
    logging.info('----------------------------------------')
    if backup_file:
        backup_file = os.path.abspath(backup_file)

    # Backup File Name
    if not backup_file:
        fs_sha1 = git.submodule_sha1(instance_dir, submodule='fundraising_studio')
        filename = instance + '--' + start_time + '--' + fs_sha1
        backup_file = pj(instance_dir, 'backup', filename)

    # Check backup_path
    backup_path = os.path.dirname(backup_file)
    assert os.path.exists(backup_path), 'Backup path %s not found!' % backup_path

    # Get odoo startup configuration (for data_dir location and db_name)
    oc = _odoo_config(instance_dir)

    # TODO: Create backup by xmlrpc/odoo if instance is running

    # Create temporary backup folder
    tmp_folder = pj(backup_path, instance + '--' + start_time)
    logging.info('Creating temporary backup folder at %s' % tmp_folder)
    os.makedirs(tmp_folder)
    assert os.path.exists(tmp_folder), 'Could not create temporary backup folder %s' % tmp_folder

    # BACKUP instance files (if any)
    files = pj(oc['data_dir'], 'filestore', oc['db_name'])
    files_target = pj(tmp_folder, 'filestore')
    if os.path.exists(files):
        logging.info('Backup instance files from %s to temporary folder %s' % (files, files_target))
        shutil.copytree(files, files_target)
    else:
        logging.warn('Files to backup not found at %s' % files)

    # BACKUP instance database (max time 30 minutes = 1800 seconds)
    db_target = pj(tmp_folder, 'db.dump')
    db_backup_cmd = ['pg_dump',
                     '--format=c', '--no-owner', '--dbname='+oc['db_url'], '--file='+db_target]
    logging.info('Backup instance database %s to temporary folder %s' % (oc['db_name'], db_target))
    shell(db_backup_cmd, timeout=1800)
    assert os.path.getsize(db_target) >= 10000, 'Database backup inaccessible or smaller than 10KB at %s' % db_target

    # Create backup zip file from temporary folder and delete temp folder
    # HINT: ".zip" is added by shutil.make_archive
    logging.info('Create zip file %s from temporary folder %s' % (backup_file, tmp_folder))
    backup_file = shutil.make_archive(backup_file, 'zip', tmp_folder)
    if os.path.exists(backup_file):
        logging.info('Removing temporary folder %s' % tmp_folder)
        shutil.rmtree(tmp_folder)

    # Log backup info
    size_in_mb = str("{0:.2f}".format(float(os.path.getsize(backup_file) / 1000 / 1000)))
    backup_time = time.time() - begin_backup
    logging.debug('Backup size %s MB' % size_in_mb)
    logging.debug('Backup time %s seconds (%s minutes)' % ("{0:.0f}".format(backup_time),
                                                           "{0:.1f}".format(backup_time/60)))
    logging.debug('Backup file %s' % backup_file)
    logging.info('Backup finished successfully!')
    return str(backup_file)


def restore(instance_dir, backup_to_restore):
    begin_restore = time.time()
    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    backup_to_restore = os.path.abspath(backup_to_restore)
    logging.info('----------------------------------------')
    logging.info('RESTORE instance %s' % instance)
    logging.info('----------------------------------------')
    assert os.path.exists(instance_dir), 'Instance not found at %s' % instance_dir
    assert os.path.exists(backup_to_restore), 'Backup to restore not found at %s' % backup_to_restore

    # TODO: Test this code extensively
    # Check if backup_to_restore is a custom backup
    # HINT: If it is a folder it is always a custom backup
    custom_backup = backup_to_restore if os.path.isdir(backup_to_restore) else None
    if os.path.isfile(backup_to_restore):
        assert zipfile.is_zipfile(backup_to_restore), 'Backup file must be a zip archive!'
        with zipfile.ZipFile(backup_to_restore, "r") as archive:
            # Check if the backup zip file is a custom backup
            if 'dump.sql' not in archive.namelist():
                # Extract custom backup zip file to temporary folder
                custom_backup = os.path.splitext(backup_to_restore)[0]
                logging.info('UnZipping custom backup to temporary folder %s' % custom_backup)
                assert not os.path.exists(
                    custom_backup), 'Folder to unzip custom backup already exists at %s' % custom_backup
                archive.extractall(custom_backup)

    # TODO: Restore through xmlrpc/odoo if odoo is accessible by xmlrpc and we have a native odoo backup
    if not custom_backup and _odoo_access_check(instance_dir):
        logging.info('Restoring native odoo backup by xmlrpc from %s' % backup_to_restore)
        _odoo_restore(instance_dir, backup_to_restore)
        return True

    # TODO: Else manually restore
    logging.info('Restoring custom backup from %s' % custom_backup)
    # Stop Instance
    # Restore Files
    # Restore DB
    # Start Instance
    # Remove custom_backup folder if backup_to_restore is a file

    return True


def update(settings=None):
    logging.info('----------------------------------------')
    logging.info('UPDATE instance')
    logging.info('----------------------------------------')
    exit(0)


def start(instance_dir, startup_args=[]):
    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    log.info('----------------------------------------')
    log.info('START instance %s' % instance)
    log.info('----------------------------------------')
    assert os.path.exists(instance_dir), 'Instance path %s not found!' % known_args.instance_dir

    # Check odoo directory
    odoo_dir = pj(S.core_dir, 'odoo_dir')
    assert os.path.exists(instance_dir), "Directory odoo not found at %s!" % odoo_dir

    # Change current working directory to the folder odoo_dir inside the repo online
    log.info("Change working directory to %s" % odoo_dir)
    os.chdir(odoo_dir)

    # Change the current python script working directory to folder odoo_dir inside the repo online
    log.info("Set python working directory (sys.path[0] and sys.argv[0]) to %s" % odoo_dir)
    sys.path[0] = sys.argv[0] = odoo_dir
    assert odoo_dir == os.getcwd() == sys.path[0], 'Could not change working directory to %s !' % odoo_dir

    # Compute the odoo startup arguments (odoo startup configuration)
    log.info("Compute final odoo startup arguments based on script command line options and server.conf")
    odoo_cmd_args = odoo_startup_options(S.instance_dir, startup_args)

    # Overwrite the original script cmd args with the odoo-only ones
    user = pwd.getpwuid(os.getuid())
    log.info("Set sys.argv to %s" % ' '.join(odoo_cmd_args))
    sys.argv = sys.argv[0:1] + odoo_cmd_args
    log.info("%s$ %s", (user, ' '.join(sys.argv)))

    # Log system environment information
    log.info("Environment current system user: %s" % user)
    log.info("Environment $PATH: %s" % os.getcwd())
    log.info("Environment $WORKING_DIRECTORY: %s" % os.environ.get("WORKING_DIRECTORY", ""))
    log.info("Environment $PYTHONPATH: %s" % os.environ.get("PYTHONPATH", ""))

    # Run odoo
    # HINT: 'import odoo' works because we are now in the FS-Online core directory that contains the folder odoo
    # ATTENTION: To make this work openerp-gevent must be in some path that python can load!
    log.info("Run odoo.main() from odoo.py")
    import odoo
    odoo.main()


# ----------------------------
# MAIN ROUTINE
# ----------------------------
def fs_online():
    # HINT: We use three global data stores:
    #         - "known_args",
    #         - "unknown_args" and the
    #         - settings dict "s"
    #       Further we use the global var "log" for the logger in all functions in this script
    #       For this script it seems too much overhead too pass these to all functions - no benefit but more text

    # Log basic info
    logging.info('Instance: %s' % S.instance)
    logging.info('Production Server: %s' % S.production_server)
    logging.info('Logfile: %s.' % S.log_file)
    logging.debug('CMD Script Arguments: %s' % known_args)
    logging.debug('CMD Optional Arguments passed on to odoo: %s' % unknown_args)
    
    # BACKUP
    if known_args.backup or known_args.backup_to_file:
        backup(instance_dir=S.instance_dir, backup_file=known_args.backup_to_file, start_time=S.start_time)
        exit(0)

    # RESTORE
    if known_args.restore:
        restore(S.instance_dir, known_args.restore)
        exit(0)

    # UPDATE
    if known_args.update or known_args.update_to_rev:
        update(settings=S)
        exit(0)

    # START
    return start(S.instance_dir, startup_args=unknown_args)


# ----------------------------
# COMMAND PARSER
# ----------------------------
# Create a new argument-parser object
parser = argparse.ArgumentParser()
# Add Arguments
parser.add_argument('instance_dir', help="Instance directory")
parser.add_argument('--log_file', metavar='/path/log_file.log', help='Log File')
parser.add_argument('--verbose', help='Log Level',
                    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                    default='DEBUG')
parser.add_argument('--backup',
                    action='store_true',
                    help='Create a backup at the default location /[instance_dir]/backups/[backup_name]')
parser.add_argument('--backup-to-file',
                    metavar='/path/backup.zip',
                    help='Filename with full path to output the backup.')
parser.add_argument('--restore',
                    metavar='/path/to/backup',
                    help='Restore from backup folder or file')
parser.add_argument('--update',
                    action='store_true',
                    help='Update the instance to latest commit of the instance branch master on github.')
parser.add_argument('--update-to-rev',
                    metavar='Branch, Tag or SHA1',
                    help='Update the instance to the given rev (rev = Branch, Tag or SHA1).')
# Set a default function to call after the initialization of the parser object
parser.set_defaults(func=fs_online)


# --------------------
# START
# --------------------
if __name__ == "__main__":
    # Globally available data stores (vars):
    # -------------------------------------------------------------------------------
    # known_args        (Namespace)                 CMD settings known to command parser
    # unknown_args      (list)                      CMD settings not set in command parser
    # S                 (Class/Namespace Object)    Settings dictionary
    # log               (logging instance)          Globally used logger __main__
    # -------------------------------------------------------------------------------
    script_start_time = str(time.strftime('%Y-%m-%d_%H-%M-%S'))

    # Get the command line arguments
    known_args, unknown_args = parser.parse_known_args()

    # Create a new namespace object for the settings
    class S:
        pass

    # START LOGGING
    # -------------
    # Set and check log_file
    S.log_file = known_args.logfile if known_args.logfile else False
    if S.log_file:
        assert os.access(os.path.dirname(S.log_file), os.W_OK), 'Logfile location %s not writeable!' % S.log_file

    # Get a handle to the root logger (or instantiate it the first and only time)
    # HINT: The root logger is a singleton so all calls to it will return the same object!
    log = logging.getLogger()

    # Create a format object to be used in log handlers
    log_formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')

    # Create a log handler
    if S.log_file:
        log_handler = logging.FileHandler(filename=S.log_file)
    else:
        log_handler = logging.StreamHandler(sys.stdout)

    # Configure the log format for the new handler
    log_handler.setFormatter(log_formatter)

    # Add the handler to the root logger
    log.addHandler(log_handler)

    # Redirect sys assertion outputs to the logger
    sys.excepthook = excepthook

    # Log script start
    logging.info('================================================================================')
    logging.info('fs-online.py %s' % ' '.join(sys.argv))
    logging.info('================================================================================')

    # SETTINGS (globally accessible)
    # ------------------------------
    # Make sure the instance path exits
    assert os.path.exists(known_args.instance_dir), 'Instance directory not found at %s!' % known_args.instance_dir

    # Make sure the instance.ini is available
    instance_ini_file = pj(known_args.instance_dir, 'instance.ini')
    assert os.path.isfile(instance_ini_file), 'File instance.ini not found at %s!' % instance_ini_file

    # Instance
    S.instance_dir = os.path.abspath(known_args.instance_dir)
    S.instance = os.path.basename(S.instance_dir)
    S.instance_ini_file = instance_ini_file
    S.instance_core = inifile_to_dict(S.instance_ini_file)['core']
    # Global
    S.start_time = str(time.strftime('%Y-%m-%d_%H-%M-%S'))
    S.production_server = _production_server_check(S.instance_dir)
    # FS-Online Core (from instance.ini)
    S.core_dir = pj(os.path.dirname(S.instance_dir), 'online_'+S.instance_core)
    S.core_tag = git.get_tag(S.core_dir)
    # Startup Config

    # Check that the core dir name and the core tag and the instance_core matches
    assert S.instance_core == S.core_tag, "Core from instance.ini is %s not matching core_tag %s!" \
                                          "" % (S.instance_core, S.core_tag)

    # START fs_online()
    # -----------------
    # HINT: See "parser.set_defaults(func=fs_online)" above
    known_args.func()
