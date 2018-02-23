# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib


# Connection parameters
url = 'http://127.0.0.1:8069'
db = 'demo'
username = 'sosync'
password = 'sosync'


common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
print common.version()

# Get the User ID
uid = common.authenticate(db, username, password, {})

# Get the models env
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))


# Search for the sosync user
sosync_user_id = models.execute_kw(db, uid, password, 'res.users', 'search',
                                   [[['login', '=', 'sosync']]],                    # Positional args of method search
                                   {'limit': 1})                                    # kwargs of method search
print sosync_user_id
sosync_user = models.execute_kw(db, uid, password, 'res.users', 'browse',
                                   [[1]],                                           # Positional args of method search
                                   )

# Update the sosync user password
if sosync_user_id:
    print models.execute_kw(db, uid, password, 'res.users', 'write',
                            [sosync_user_id, {'password': 'bob'}],                  # Positional args of method write
                            )

