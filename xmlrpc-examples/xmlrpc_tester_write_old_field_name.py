# -*- coding: utf-8 -*-
# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib

# Connection parameters
url = 'http://demo.local.com'
db = 'demo'
username = 'admin'
password = 'admin'

common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
print common.version()

# Get the User ID
uid = common.authenticate(db, username, password, {})

# Get the models env
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

# Test check_bpk
print models.execute_kw(db, uid, password, 'res.partner', 'write',
                        [
                            [116355], {'glglglglgl': "BOB", 'muahhahha': 123}
                        ]
                        )
