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
"""
import argparse
import os
from os.path import join as pj
import sys
import time
import textwrap
import logging

# Initialize the logging
# Get a handle to the root logger (or instantiate it the first and only time)
# HINT: The root logger is a singleton so all calls to it will return the same object!
#logging.basicConfig(format='%(asctime)s %(levelname)-8s %(module)-14s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
_log = logging.getLogger()
_log.setLevel(logging.DEBUG)
# Create a format object to be used in log handlers
log_formatter = logging.Formatter(fmt='%(asctime)s %(levelname)-8s %(module)-14s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
# Log in GMT time (instead of localtime) to have the same time than odoo logging
log_formatter.converter = time.gmtime
log_sys_handler = logging.StreamHandler(sys.stdout)
log_sys_handler.setFormatter(log_formatter)
log_sys_handler.setLevel(logging.DEBUG)

# Add the handler to the root logger
_log.addHandler(log_sys_handler)


# Redirect sys assertion outputs to the logger
def excepthook(*eargs):
    print "SYS excepthook() %s" % repr(eargs)
    # Get the root logger and log to CRITICAL
    logging.getLogger(__name__).critical('Uncaught exception:\n-------------------\n%s', eargs,
                                         exc_info=True)


sys.excepthook = excepthook


# ATTENTION: segfault warning! backup > tools_odoo ... import requests
#            Importing requests may lead to segmentation faults on odoo startup on the production servers!!!
#            The reason is totally unclear and is seems it depends on the import order as well!
#            There was some info in the old start.py that it is maybe related to the ssl certificate chain!?!
#            Therefore the request import was moved inside a function which may help or may just mask the problem!
#            Also the import order seems to help: backup should be imported first here
import backup
import restore
import update
import start


# -----------------------------
# COMMAND PARSER FUNCTION CALLS
# -----------------------------
def fson_start(known_args=None, unknown_args=None):
    # Make sure the instance path exits
    assert os.path.exists(known_args.instance_dir), 'Instance directory not found at %s!' % known_args.instance_dir

    # Make sure the instance.ini is available
    instance_ini_file = pj(known_args.instance_dir, 'instance.ini')
    assert os.path.isfile(instance_ini_file), 'File instance.ini not found at %s!' % instance_ini_file

    start.start(known_args.instance_dir, cmd_args=unknown_args, log_file=known_args.log_file)


def fson_backup(known_args=None, unknown_args=None):
    assert known_args.backup, "'backup' argument missing in known_args"
    result = backup.backup(known_args.instance_dir,
                           env=known_args.env,
                           backup_file=known_args.backup,
                           mode=known_args.backup_mode,
                           db_url=known_args.db_url,
                           data_dir=known_args.data_dir,
                           cmd_args=unknown_args,
                           log_file=known_args.log_file)
    if result:
        exit(0)
    else:
        exit(100)


def fson_restore(known_args=None, unknown_args=None):
    if known_args.restore:
        restore.restore(known_args.instance_dir,
                        backup_zip_file=known_args.restore,
                        development_mode=bool(known_args.env == 'development'),
                        cmd_args=unknown_args,
                        log_file=known_args.log_file)
        exit(0)


def fson_update(known_args=None, unknown_args=None):
    if known_args.update:
        update.update(known_args.instance_dir,
                      update_branch=known_args.update,
                      cmd_args=unknown_args,
                      log_file=known_args.log_file)
        exit(0)

# ----------------------------
# COMMAND PARSER
# ----------------------------
# Support the "old" commands format:
#    fsonline.py /path/to/instance --backup=/path/to/backup/file.zip
#    fsonline.py /path/to/instance --backup /path/to/backup/file.zip
#
# We redirect the parsing of the unknown_args to the 'parser_for_subcommands' for known subcommands
# This is kind of a hack to keep the old interface of fs-online.py. It is necessary because argparse is not
# supporting "optional" subcommands. Check the following URL for more information on this:
# https://stackoverflow.com/questions/46667843/how-to-set-a-default-subparser-using-argparse-module-with-python-2-7


# THE MAIN PARSER FOR A REGULAR ODOO START
# ----------------------------------------
# TODO: Add some help/hints to the parser_main for the available modes/subcommands and how to get help!
parser_main = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog=textwrap.dedent(
"""
---
Start, backup, restore or update an fs-online odoo instance.

Available subcommands are: 'backup', 'restore' and 'update'
You can get help for the subcommands like this: fsonline.py does_not_matter --backup -h

Example usages:
    
    fsonline.py /opt/online/dadi
    fsonline.py /opt/online/dadi -l /log/mylog.log
    fsonline.py /opt/online/dadi -l /log/mylog.log -u all --stop-after-init
    
    fsonline.py /opt/online/dadi --backup
    fsonline.py /opt/online/dadi --backup --mode=odoo
    fsonline.py dadi --backup=/path/to/backup_file.zip --db_url=*** --data_dir=/path/to/odoo/data_dir
    
    fsonline.py /opt/online/dadi --restore=/path/to/backup_file.zip
    fsonline.py /opt/online/dadi --env=development --restore=/path/to/backup_file.zip
    
    fsonline.py /opt/online/dadi --update=o8r356
    fsonline.py /opt/online/dadi --update=86a7ae75da902b3f46a0f808b348a38aed31c622
---
""")
                                      )
parser_main.set_defaults(func=fson_start)
parser_main.add_argument('instance_dir',
                    help="Path to instance directory or instance name for manual backups.")
parser_main.add_argument('-l', '--log_file',
                    metavar='/path/to/log_file.log (Will log to STDOUT if not set)',
                    help='Add "logfile = /path/too/odoo.log" to the odoo server.conf '
                         'if you want a separate log file for the odoo log messages.')
parser_main.add_argument('-v', '--verbose',
                    help='Log Level',
                    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                    default='INFO')
parser_main.add_argument('-e', '--env',
                    nargs='?',                  # ? means 0-or-1 argument values
                    default='production',       # Set this value when the argument is missing completely
                    const='production',         # Set this value when there is no value for the argument
                    choices=['production', 'development'],
                    help='In the development environment there will be additional cleanups for backup and restore! '
                         'NEVER use "development" on a production instance!')

# CREATE A SECOND PARSER FOR THE SUBCOMMANDS
# ------------------------------------------
parser_for_subcommands = argparse.ArgumentParser()
subparsers = parser_for_subcommands.add_subparsers(dest="subcommand_name", help='Extra Modes')

# BACKUP
subparser_backup = subparsers.add_parser("backup",
                                         help="Backup Instance")
subparser_backup.set_defaults(func=fson_backup)
subparser_backup.add_argument('--backup',
                              nargs='?',            # ? means 0-or-1 argument values
                              const='default',      # Set this default when there is no value for the argument
                              metavar='/path/to/backup/file.zip',
                              type=str,             # converts the argument to string
                              help='Will backup to default location /[instance_dir]/update/[backupname.zip] if no '
                                   'path is given!')
subparser_backup.add_argument('--backup_mode',
                              nargs='?',            # ? means 0-or-1 argument values
                              default='manual',     # Set this value when the argument is missing completely
                              choices=['manual', 'odoo'],
                              help='Mode manual will use file copy and pg_dump for the backup.\n'
                                   'Mode odoo will use odoo for the backup.\n'
                                   'HINT: The options db_url and data_dir only apply in manual mode!')
subparser_backup.add_argument('--db_url',
                              nargs='?',            # ? means 0-or-1 argument values
                              default='',
                              type=str,             # converts the argument to string
                              help='The postgresql database url in the format xxx. '
                                   'Only used for manual backups!')
subparser_backup.add_argument('--data_dir',
                              nargs='?',            # ? means 0-or-1 argument values
                              default='',           # Set this value when the argument is missing completely
                              type=str,             # converts the argument to string
                              help='The odoo data_dir location. e.g. /opt/online/dadi/data_dir. '
                                   'Only used for manual backups')


# RESTORE
subparser_restore = subparsers.add_parser("restore",
                                      help="Restore Instance")
subparser_restore.set_defaults(func=fson_restore)
subparser_restore.add_argument('--restore',
                               required=True,
                               type=str,
                               metavar='/path/to/backup/file.zip',
                               help='Restore from backup zip or from folder')

# UPDATE
subparser_update = subparsers.add_parser("update",
                                      help="Update Instance")
subparser_update.set_defaults(func=fson_update)
subparser_update.add_argument('--update',
                              nargs='?',    # ? means 0-or-1 argument values
                              const='o8',   # Set this default when there is no value for the argument
                              type=str,     # converts the argument to string
                              help='Update to branch or commit of the instance repository in github! Defaults to: "o8"')


# --------------------
# START
# --------------------
if __name__ == "__main__":
    # Globally available variables:
    # -------------------------------------------------------------------------------
    # known_args        (Namespace)                 CMD settings known to command parser
    # unknown_args      (list)                      CMD settings not set in command parser
    # _log              (logging instance)          Globally used logger __main__
    # -------------------------------------------------------------------------------

    # Preparations to redirect -h or --help to the correct parser
    cmd_args_no_help = [s for s in sys.argv[1:] if s not in ['-h', '--help']]
    help = bool(len(cmd_args_no_help) < len(sys.argv)-1)

    # Parse the arguments of the 'parser_main'
    known_args, unknown_args = parser_main.parse_known_args(cmd_args_no_help)

    # Make sure none or exactly one 'known subcommand' is given
    known_subcommands = ['backup', 'restore', 'update']
    subcommand_count = 0
    for unknown_arg in unknown_args:
        if any(unknown_arg.lstrip('--').split('=')[0] == known_sc for known_sc in known_subcommands):
            subcommand_count += 1
    assert subcommand_count <= 1, "Multiple subcommands are not supported!"

    # Parse subcommand arguments with the special parser 'parser_for_subcommands' AND redirect -h to the correct parser
    subcommand = unknown_args[0].split('=')[0].lstrip('--') if len(unknown_args) > 0 else None
    if subcommand and subcommand in known_subcommands:
        unknown_args.insert(0, subcommand)
        if help:
            parser_for_subcommands.parse_known_args([subcommand, '-h'], namespace=known_args)
            exit(0)
        else:
            known_args, unknown_args = parser_for_subcommands.parse_known_args(unknown_args, namespace=known_args)

    if help:
        known_args, unknown_args = parser_main.parse_known_args()
        exit(0)

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
    _log.info('known_args: %s' % known_args)
    _log.info('unknown_args: %s' % str(unknown_args))

    # START THE DEFAULT PARSER FUNCTION
    known_args.func(known_args=known_args, unknown_args=unknown_args)
