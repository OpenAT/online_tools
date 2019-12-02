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
"""
import argparse
import os
from os.path import join as pj
import sys
import time

from start import start
from backup import backup
from restore import restore
from update import update

import logging
#import logging.handlers

# Globally initialize the logging for this file
# Get a handle to the root logger (or instantiate it the first and only time)
# HINT: The root logger is a singleton so all calls to it will return the same object!
_log = logging.getLogger()
_log.setLevel(logging.DEBUG)
# Create a format object to be used in log handlers
log_formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(module)-14s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
# Log in GMT time (instead of localtime)
log_formatter.converter = time.gmtime
# Start a log handler and add it to the logger
log_sys_handler = logging.StreamHandler(sys.stdout)
# Configure the log format for the new handler
log_sys_handler.setFormatter(log_formatter)
# Set log handler output level
log_sys_handler.setLevel(logging.DEBUG)
# Add the handler to the root logger
_log.addHandler(log_sys_handler)


def excepthook(*eargs):
    # Get the root logger and log to CRITICAL
    logging.getLogger(__name__).critical('Uncaught exception:\n'
                                         '-------------------\n', exc_info=eargs)


# Redirect sys assertion outputs to the logger
sys.excepthook = excepthook


# ------------------------------------
# COMMAND PARSER DEFAULT FUNCTION CALL
# ------------------------------------
def fs_online():
    # BACKUP
    if known_args.backup:
        result = backup(known_args.instance_dir, backup_file=known_args.backup,
                        cmd_args=unknown_args, log_file=known_args.log_file)
        if result:
            exit(0)
        else:
            exit(100)

    # RESTORE
    if known_args.restore:
        restore(known_args.instance_dir, backup_zip_file=known_args.restore,
                cmd_args=unknown_args, log_file=known_args.log_file)
        exit(0)

    # UPDATE
    if known_args.update:
        update(known_args.instance_dir, cmd_args=unknown_args, log_file=known_args.log_file)
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
    _log.setLevel(log_level)

    # Start logging to file
    if known_args.log_file:
        known_args.log_file = os.path.abspath(known_args.log_file)
        assert os.access(os.path.dirname(known_args.log_file), os.W_OK), 'Logfile location %s not writeable!' \
                                                                         '' % known_args.log_file

        # Remove the syslog handler as we log to file from now on
        _log.removeHandler(log_sys_handler)

        # Create the file log handler
        log_file_handler = logging.FileHandler(filename=known_args.log_file)
        log_file_handler.setFormatter(log_formatter)
        log_file_handler.setLevel(log_level)

        # Add the file log handler to the root logger
        _log.addHandler(log_file_handler)

    # Log script start
    _log.info('================================================================================')
    _log.info('fs-online.py %s' % ' '.join(sys.argv))
    _log.info('================================================================================')

    # START fs_online()
    # -----------------
    # HINT: See "parser.set_defaults(func=fs_online)" above
    known_args.func()
