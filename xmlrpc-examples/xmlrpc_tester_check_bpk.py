# -*- coding: utf-8 -*-
# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib
import time

# Connection parameters
#url = 'http://localhost:8069'
url = 'http://demo.local.com'
db = 'demo'
username = 'admin'
password = 'hfjfk94l4mf#3'

common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
print common.version()

# Get the User ID
uid = common.authenticate(db, username, password, {})

# Get the models env
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

# Test check_bpk
print models.execute_kw(db, uid, password, 'res.partner', 'check_bpk',
                        [],
                        {
                            'firstname': 'Rene',
                            'lastname': 'Mattes',
                            'birthdate': '1986-03-18',
                            'zipcode': '1234',
                            'context': {},
                         })
