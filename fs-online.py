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
import argparse
import os
from os.path import join as pj
import sys
import logging
import ConfigParser
import pwd
import subprocess32
import shutil
import time
import zipfile
from xmlrpclib import ServerProxy
import base64


# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def excepthook(*eargs):
    logging.getLogger(__name__).critical('Uncaught exception:\n\n', exc_info=eargs)
    

def _production_server_check(instance_path):
    instance_path = os.path.abspath(instance_path)
    instance = os.path.basename(instance_path)
    return os.path.exists(pj('/etc/init.d', instance))


def _shell(cmd=list(), user=None, cwd=None, env=None, preexec_fn=None, **kwargs):
    assert isinstance(cmd, (list, tuple)), '_shell(cmd): cmd must be of type list or tuple!'
    # Working directory
    cwd = cwd or os.getcwd()

    # Linux User
    linux_user = pwd.getpwuid(os.getuid())
    # Switch user and environment if given
    if user:
        # Get linux user details from unix user account and password database
        # HINT: In case the user can not be found pwd will throw an KeyError exception.
        linux_user = pwd.getpwnam(user)
        # Create a new os environment
        env = os.environ.copy()
        # Set environment variables
        env['USER'] = user
        env['LOGNAME'] = linux_user.pw_name
        env['HOME'] = linux_user.pw_dir
        # Create a new function that will be called by subprocess32 before the shell command is executed
        preexec_fn = _switch_user_function(linux_user.pw_uid, linux_user.pw_gid)

    # Log user Current-Working-Directory and shell command to be executed
    logging.debug('[%s %s]$ %s' % (linux_user.pw_name, cwd, ' '.join(cmd)))

    # Execute shell command and return its output
    return subprocess32.check_output(cmd, cwd=cwd, env=env, preexec_fn=preexec_fn, **kwargs)


# TODO: Make this a bit smarter ;) !
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
    _shell(['service', service, state])

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


def _inifile_to_dict(inifile, section='options'):
    inifile = os.path.normpath(inifile)
    assert os.path.isfile(inifile), 'Config file %s not found!' % inifile
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


# Returns a function! Helper function for function "_shell()" to switch the user before shell command is executed
def _switch_user_function(user_uid, user_gid):
    def inner():
        logging.debug('Switch user from %s:%s to %s:%s.' % (os.getuid(), os.getgid(), user_uid, user_gid))
        # HINT: Will throw an exception if user or group can not be switched
        os.setresgid(user_gid, user_gid, user_gid)
        os.setresuid(user_uid, user_gid, user_gid)
    return inner


def _git_submodule_sha1(root_repo_path, submodule=str()):
    # HINT: Full submodule path needed!
    #       e.g.: 'fundraising_studio/online' for 'dadi/fundraising_studio/online'
    #       This allows that submodules of submodules will not get found if they have the same name!

    # Use git to get the list of submodules and their current commits SHA1
    submodules = _shell(['git', 'submodule', 'status', '--recursive'], cwd=root_repo_path)
    assert submodules, 'No submodules found in %s! Did you run "git submodule init"?' % root_repo_path

    # Create a dict out of the git output
    # e.g.: {'fundraising_studio/online': '-88b145319056b9d6feac9c86458371cd12a3960c'}
    # Example git-output line: "-88b145319056b9d6feac9c86458371cd12a3960c fundraising_studio/online "
    # HINT: [-40:] means use first 40 characters from right to left in the string (= removing the - if it exists)
    submodules = {line.split()[1].strip(): line.split()[0].strip()[-40:] for line in submodules.splitlines()}

    # Get SHA1 for submodule and check that it is 40 characters long!
    submodule_sha1 = submodules[submodule]
    assert len(submodule_sha1) == 40, 'Wrong or missing SHA1 (%s) for submodule %s in %s!' % (submodule_sha1,
                                                                                              submodule, root_repo_path)
    return submodule_sha1


def _odoo_config(instance_path, cmd_args=list()):
    """ Parse odoo configuration file and command line arguments

    :param instance_path: string
    :param cmd_args: list Optional CMD Arguments that will be passed on to odoo
    :return: dict Odoo configuration dictionary with odoo startup commandline arguments
    """
    # Check for production server
    production_server = _production_server_check(instance_path)
    
    # Assert instance_path
    instance_path = os.path.normpath(instance_path)
    assert os.path.exists(instance_path), 'Instance path %s not found!' % instance_path

    # Assert that no odoo cmd options are in cmd_args that will be set here
    _test_optional_odoo_args(cmd_args)

    # Odoo server config default development values
    # HINT: Will be overridden later on from values of the server.conf file if given
    instance = os.path.basename(instance_path)
    oc = {
        'db_name': instance,
        'db_user': 'vagrant',
        'db_password': 'vagrant',
        'db_host': '127.0.0.1',
        'db_port': '5432',
        'data_dir': pj(instance_path, 'data_dir'),
        'server_wide_modules': 'web,web_kanban,dbfilter_from_header',
        'workers':'0'
    }
    # Get server.conf path
    server_conf = None  # e.g.: /opt/instances/dadi/server.conf
    if '-c' in cmd_args:
        server_conf = cmd_args[cmd_args.index('-c') + 1]
        assert os.path.isfile(server_conf), "Odoo server.conf file %s set by -c is missing!" % server_conf
    else:
        server_conf = pj(instance_path, 'server.conf')

    # Overwrite settings by settings from server.conf ini file
    # HINT: This is only needed to get the values for "workers" and "server_wide_modules" because they are required
    #       in startup_args. odoo will always search for server.conf or it is given by -c
    if os.path.isfile(server_conf):
        logging.info('Read odoo server.conf from: %s' % server_conf)
        oc.update(_inifile_to_dict(server_conf))
    else:
        # HINT: On prod machines there has to be a server.conf!
        assert not production_server, "Odoo server.conf file %s missing on production machine!" % server_conf
        logging.warn('No server.conf found at %s! Using development defaults instead.' % server_conf)

    # Get online repo location
    if os.path.isfile(pj(instance_path, 'fundraising_studio/online/odoo/odoo.py')):
        oc['online_repo'] = pj(instance_path, 'fundraising_studio/online')
    else:
        # Get SHA1 of submodule repo "online"
        online_sha1 = _git_submodule_sha1(instance_path, submodule='fundraising_studio/online')
        oc['online_repo'] = pj(os.path.dirname(instance_path), 'online_' + online_sha1)
    assert os.path.exists(oc['online_repo']), 'Repository online not found at %s !' % oc['online_repo']
    logging.info('Repository online is located at %s' % oc['online_repo'])

    # odoo addons paths
    oc['addons'] = [pj(oc['online_repo'], 'odoo/openerp/addons'),
                    pj(oc['online_repo'], 'odoo/addons'),
                    pj(oc['online_repo'], 'addons-loaded')]

    # instance addons path
    instance_addons = pj(instance_path, 'addons')
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


def _odoo_access_check(instance_path, odoo_config=None):
    instance_path = os.path.abspath(instance_path)
    instance = os.path.basename(instance_path)
    odoo_config = odoo_config or _odoo_config(instance_path)

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
def backup(instance_path, backup_file=None, start_time=str(time.strftime('%Y-%m-%d_%H-%M-%S'))):
    begin_backup = time.time()
    instance_path = os.path.abspath(instance_path)
    instance = os.path.basename(instance_path)
    logging.info('----------------------------------------')
    logging.info('BACKUP instance %s' % instance)
    logging.info('----------------------------------------')
    if backup_file:
        backup_file = os.path.abspath(backup_file)

    # Backup File Name
    if not backup_file:
        fs_sha1 = _git_submodule_sha1(instance_path, submodule='fundraising_studio')
        filename = instance + '--' + start_time + '--' + fs_sha1
        backup_file = pj(instance_path, 'backup', filename)

    # Check backup_path
    backup_path = os.path.dirname(backup_file)
    assert os.path.exists(backup_path), 'Backup path %s not found!' % backup_path

    # Get odoo startup configuration (for data_dir location and db_name)
    oc = _odoo_config(instance_path)

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
    _shell(db_backup_cmd, timeout=1800)
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


def restore(instance_path, backup_to_restore):
    begin_restore = time.time()
    instance_path = os.path.abspath(instance_path)
    instance = os.path.basename(instance_path)
    backup_to_restore = os.path.abspath(backup_to_restore)
    logging.info('----------------------------------------')
    logging.info('RESTORE instance %s' % instance)
    logging.info('----------------------------------------')
    assert os.path.exists(instance_path), 'Instance not found at %s' % instance_path
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
    if not custom_backup and _odoo_access_check(instance_path):
        logging.info('Restoring native odoo backup by xmlrpc from %s' % backup_to_restore)
        _odoo_restore(instance_path, backup_to_restore)
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


def start(instance_path, cmd_args=list()):
    instance_path = os.path.abspath(instance_path)
    instance = os.path.basename(instance_path)
    logging.info('----------------------------------------')
    logging.info('START instance %s' % instance)
    logging.info('----------------------------------------')
    assert os.path.exists(instance_path), 'Instance path %s not found!' % known_args.instance_path

    # TODO: Check if instance service is already running?

    # odoo startup configuration
    oc = _odoo_config(instance_path, cmd_args=cmd_args)

    # odoo location
    odoo = pj(oc['online_repo'], 'odoo')
    assert os.path.exists(instance_path), 'Odoo at path %s not found!' % odoo

    # Change current working directory to the folder odoo inside the repo online
    os.chdir(odoo)

    # Change the current python script working directory to folder odoo inside the repo online
    sys.path[0] = sys.argv[0] = odoo

    # Assert the script path and current working directory are correct
    assert odoo == os.getcwd() == sys.path[0], 'Could not change path to %s !' % odoo

    # Overwrite the the script cmd args with the ones we created for odoo
    # HINT: [0:1] returns a list with the first item of the former list whereas [0] would just return the value
    # TODO: Assert that there are no options from startup args in cmd_args
    sys.argv = sys.argv[0:1] + oc['startup_args'] + cmd_args

    # Start FS-Online
    current_user = pwd.getpwuid(os.getuid())
    logging.info('[%s %s]$ %s %s' % (current_user.pw_name, os.getcwd(), 'cli/server.py ', ' '.join(sys.argv)))
    # Multi-Threaded odoo start
    if oc['workers'] != '0':
        logging.warn('Gevented mode enabled because workers = %s' % oc['workers'])
        assert not sys.gettrace(), 'Multi threaded mode is not supported when debugging the script!'
        import gevent.monkey
        gevent.monkey.patch_all()
        import psycogreen.gevent
        psycogreen.gevent.patch_psycopg()
        # Start odoo (and reset logging before)
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        import openerp
        openerp.cli.main()
    # Single-Threaded odoo start
    else:
        if sys.gettrace():
            logging.warn('Script started by debugger!')
        logging.info('Disabling evented mode because workers = 0')
        # Start odoo (and reset logging before)
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        import openerp
        openerp.evented = False
        openerp.cli.main()


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
    logging.info('================================================================================')
    logging.info('fs-online.py %s' % ' '.join(sys.argv))
    logging.info('================================================================================')
    logging.info('Production Server: %s' % s['production_server'])
    logging.info('Logfile is located at %s.' % s['logfile'])
    logging.debug('CMD Script Arguments: %s' % known_args)
    logging.debug('CMD Optional Arguments passed on to odoo: %s' % unknown_args)

    # BACKUP
    if known_args.backup or known_args.backup_to_file:
        backup(instance_path=s['instance_path'], backup_file=known_args.backup_to_file, start_time=s['start_time'])
        exit(0)

    # RESTORE
    if known_args.restore:
        restore(s['instance_path'], known_args.restore)
        exit(0)

    # UPDATE
    if known_args.update or known_args.update_to_rev:
        update(settings=s)
        exit(0)

    # START
    return start(s['instance_path'], cmd_args=unknown_args)


# ----------------------------
# COMMAND PARSER
# ----------------------------
# Create a new argument-parser object
parser = argparse.ArgumentParser()
# Add Arguments
parser.add_argument('instance_path', help="Instance directory")
parser.add_argument('--logfile', metavar='/path/logfile.log', help='Log File')
parser.add_argument('--verbose', help='Log Level',
                    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                    default='DEBUG')
parser.add_argument('--backup',
                    action='store_true',
                    help='Create a backup at the default location /[instance_path]/backups/[backup_name]')
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
    # Prerequisites:
    #     - Set globally available variables
    #     - Check instance path
    #     - Setup logging
    #
    # Globally available data stores (vars):
    # -------------------------------------------------------------------------------
    # known_args        (Namespace)         CMD settings known to command parser
    # unknown_args      (list)              CMD settings not set in command parser
    # s                 (dict)              Settings dictionary
    # logging           (logging instance)  Globally used logger __main__
    # -------------------------------------------------------------------------------

    # Get the cmd args from argparse
    known_args, unknown_args = parser.parse_known_args()

    # SETTINGS DICTIONARY (globally accessible)
    s = dict()
    # Instance name and instance path
    s['instance_path'] = os.path.abspath(known_args.instance_path)
    s['instance'] = os.path.basename(s['instance_path'])
    # Start Time, logfile with path (or None), production server check
    s.update({
        'start_time': str(time.strftime('%Y-%m-%d_%H-%M-%S')),
        'logfile': os.path.abspath(known_args.logfile) if known_args.logfile else known_args.logfile,
        'production_server': _production_server_check(s['instance_path']),
    })
    # Check instance path
    assert os.path.exists(s['instance_path']), 'Instance path %s not found!' % known_args.instance_path

    # LOGGING
    if s['production_server'] and not s['logfile']:
        # Default logfile name and path for production servers (if None given)
        if known_args.update:
            s['logfile'] = pj(s['instance_path'], 'log/' + s['instance'] + '--update.log')
        else:
            s['logfile'] = pj(s['instance_path'], 'log/' + s['instance'] + '.log')
    # If a logfile was set either by cmd or by defaults check that we could access the file
    if s['logfile']:
        assert os.access(os.path.dirname(s['logfile']), os.W_OK), 'Logfile location %s not writeable!' % s['logfile']
    # Start logging
    # HINT: https://docs.python.org/2/howto/logging-cookbook.html
    # HINT: If you ever need to reconfigure logging later on you have to reset the handlers first.
    #       http://stackoverflow.com/questions/12158048/changing-loggings-basicconfig-which-is-already-set
    logging.basicConfig(
        filename=s['logfile'],
        level=getattr(logging, known_args.verbose.upper()),
        datefmt='%Y-%m-%d %H:%M:%S',
        format='%(asctime)s %(levelname)-8s %(message)s')

    # Redirect sys assertion outputs to the logger (by the helper function excepthook)
    sys.excepthook = excepthook
    # TODO: Redirect all stdout output to the logger ?!?

    # Start the function fs_online
    # HINT: See "parser.set_defaults(func=fs_online)" above
    known_args.func()
