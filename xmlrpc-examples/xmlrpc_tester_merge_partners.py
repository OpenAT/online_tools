# -*- coding: utf-8 -*-
# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib
import time

# Connection parameters
#url = 'http://localhost:8069'
url = 'http://demo.local.com'
db = 'demo'
username = 'admin'
password = ''

common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
print common.version()

# Get the User ID
uid = common.authenticate(db, username, password, {})

# Get the models env
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

# Test check_bpk
print models.execute_kw(db, uid, password, 'res.partner', 'merge_partner',
                        [],
                        {
                            'partner_to_remove_id': 101872,
                            'partner_to_keep_id':   101875,
                         })
