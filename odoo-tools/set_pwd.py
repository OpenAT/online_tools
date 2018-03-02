#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import os
import logging
import xmlrpclib


# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def excepthook(*eargs):
    logging.getLogger(__name__).critical('Uncaught exception:\n\n', exc_info=eargs)


# ----------------------------
# Create the command parser
# ----------------------------
# https://docs.python.org/3/library/argparse.html#default
# https://docs.python.org/2/howto/argparse.html
parser = argparse.ArgumentParser()
# Positional Arguments
parser.add_argument('login', help='The login of the odoo user to set the password for')
parser.add_argument('password', help='The unencrypted user password')


# Optional Arguments
parser.add_argument('-u', '--url',
                    default='http://demo.local.com',
                    help='Instance URL')
parser.add_argument('-d', '--db',
                    default='demo',
                    help='Instances Database')

parser.add_argument('-a', '--admin_user',
                    default='admin',
                    help='admin login')
parser.add_argument('-s', '--admin_secret',
                    default='admin',
                    help='admin password')

parser.add_argument('-l', '--log_file', metavar='/path/to/log_file.log', help='Log file')
parser.add_argument('-v', '--verbose', help='Log level',
                    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                    default='INFO')


# ----------------------------
# Start
# ----------------------------
a = parser.parse_args()

# Start logging
if a.logfile:
    assert os.access(os.path.dirname(a.logfile), os.W_OK), \
        "Logfile location '%s' not writeable!" % a.logfile
logging.basicConfig(
    filename=a.logfile,
    datefmt='%Y-%m-%d %H:%M:%S',
    format='set_pwd ' + ' %(asctime)s %(levelname)-7s %(message)s')
log = logging.getLogger('set_pwd')
log.setLevel(a.verbose.upper())

# Connection parameters
url = a.url
db = a.db
username = a.admin_user
password = a.admin_secret

# Connect to server
log.info("Connect to server %s as user %s" % (url, username))
common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
log.info(common.version())

# Login to odoo with an admin user
log.info("Login as admin-user %s" % username)
uid = common.authenticate(db, username, password, {})
assert uid, "Login as admin-user %s failed!" % username
log.info("Login as admin-user %s successful! UID: %s" % (username, uid))

# Change user password
# --------------------
log.info("Set new password for user with login %s" % a.login)

# Find the user id
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))
usr_ids = models.execute_kw(db, uid, password, 'res.users', 'search',
                            [[['login', '=', a.login]]],                        # Positional args of method search
                            {'limit': 1})                                       # kwargs of method search
assert usr_ids, "User with login %s not found!" % a.login
assert usr_ids != 1, "User 'admin' password change is not allowed!"

# Update the user record
res = models.execute_kw(db, uid, password, 'res.users', 'write',
                        [usr_ids, {'password': a.password}],                    # Positional args of method write
                        )
assert res, "Password for user with login %s could not be changed!" % a.login
log.info("New password for user with login %s set!")
