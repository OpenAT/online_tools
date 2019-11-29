#!/usr/bin/env python
# We are talking to the running odoo server through xmlrpc
#
# look at "odoo/openerp/service/db.py" or common.py or modules.py and search for "def dispatch(...)" : there you can
# find all the available xmlrpc methods
#
# ATTENTION: be aware that for most db.py methods the fist argument is always the SUPER_PASSWORD
#            look at: passwd = params[0] and params = params[1:]
import sys
import zipfile
from requests import Session, codes
import argparse
import base64
from xmlrpclib import ServerProxy


# Create database
def newdb(args):
    # Create the Database
    # service/db.py:   def exp_create_database(db_name, demo, lang, user_password='admin'):
    print 'Creating Database: %s' % args.database
    if server.create_database(args.superpwd, args.database, False, 'de_DE', args.password):
        sys.exit(0)
    else:
        sys.exit(2)


# Duplicate Database:
def dupdb(args):
    # Duplicate the Database
    # service/db.py:   def exp_duplicate_database(db_original_name, db_name):
    print 'Duplicate Database: %s' % args.database
    if server.duplicate_database(args.superpwd, args.database, args.template):
        sys.exit(0)
    else:
        sys.exit(2)


# Backup DB
# service/db.py:   def exp_dump(db_name) -> NOT USED ANYMORE BECAUSE OF MEMORY PROBLEMS!
def backup(args):
    # Request data
    url = "http://%s/web/database/backup" % args.hostserver
    payload = {'backup_db': args.database,
               'backup_pwd': args.superpwd,
               'token': ''}
    backupfile = args.filedump

    # Backup request
    # HINT: must be done as a POST request with stream=True to avoid memory overflows
    print 'Request database backup for db %s at %s' % (args.database, url)
    session = Session()
    session.verify = True
    db_backup = session.post(url, data=payload, stream=True)
    if not db_backup or db_backup.status_code != codes.ok:
        print 'ERROR: Database backup for db %s FAILED!' % args.database
        sys.exit(2)

    # Write content to file
    print 'Write Database Backup to file %s' % backupfile
    with open(backupfile, 'wb') as bf:
        for chunk in db_backup.iter_content(chunk_size=128):
            bf.write(chunk)

    # Verify zip file
    try:
        backupzip = zipfile.ZipFile(backupfile)
        failed = backupzip.testzip()
        if failed is not None:
            raise Exception
    except Exception as e:
        print "ERROR: Backup zip file validation failed!"
        sys.exit(2)

    # Backup done
    print 'Database backup for db %s to %s finished successfully!' % (args.database, backupfile)
    sys.exit(0)


# Restore DB
# service/db.py:   def exp_restore(db_name, data, copy=False):
def restore(args):
    print 'Restore Database: %s' % args.database
    with open(args.filedump, 'rb') as dump_file:
        if server.restore(args.superpwd, args.database, base64.b64encode(dump_file.read())):
            sys.exit(0)
        else:
            sys.exit(2)


# ----------------------------
# Create the command parser
# ----------------------------
parser = argparse.ArgumentParser()
parser.add_argument('-b', '--baseport', required='True', help='XMLRPC Port')
parser.add_argument('-s', '--superpwd', required='True', help='Super Password')
parser.add_argument('-x', '--hostserver', required='True', help='Server Address')
subparsers = parser.add_subparsers(title='subcommands',
                                   description='available subcommands',
                                   help='')

# SubParser for newdb
parser_newdb = subparsers.add_parser('newdb', help='Create a new DB or duplicate existing if -t given.')
parser_newdb.add_argument('-d', '--database', required='True', help='Name of new database')
parser_newdb.add_argument('-p', '--password', required='True', help='Password for user "admin"')
parser_newdb.set_defaults(func=newdb)

# SubParser for dubdb
parser_dupdb = subparsers.add_parser('dupdb', help='Create a new DB or duplicate existing if -t given.')
parser_dupdb.add_argument('-d', '--database', required='True', help='Name of new database')
parser_dupdb.add_argument('-t', '--template', help='Existing database to duplicate')
parser_dupdb.set_defaults(func=dupdb)

# SubParser for backup
parser_backup = subparsers.add_parser('backup', help='Backup database with data-dir as zip file.')
parser_backup.add_argument('-d', '--database', required='True', help='Database to backup')
parser_backup.add_argument('-f', '--filedump', required='False', help='Backupfile')
parser_backup.set_defaults(func=backup)

# SubParser for restore
parser_restore = subparsers.add_parser('restore', help='restore database with data-dir as zip file.')
parser_restore.add_argument('-d', '--database', required='True', help='Name of new database')
parser_restore.add_argument('-f', '--filedump', required='True', help='Backupfile to restore')
parser_restore.set_defaults(func=restore)

# --------------------
# START
# --------------------
args = parser.parse_args()
print 'DEBUG: args: %s' % args

# XMLRPC Proxy Connection
server = ServerProxy('http://' + str(args.hostserver) + '/xmlrpc/db')
print "server: %s" % server

# Call method argparse.ArgumentParser.parse_args.func() of object parser
args.func(args)
