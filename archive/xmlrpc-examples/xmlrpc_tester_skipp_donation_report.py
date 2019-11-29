# -*- coding: utf-8 -*-
# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib
import time

# Connection parameters
#url = 'http://localhost:8069'
url = 'http://wrtv.datadialog.net'
db = 'wrtv'
username = 'admin'
password = ''

common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
print common.version()

# Get the User ID
uid = common.authenticate(db, username, password, {})

# Get the models env
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))


# Get the Spendenmeldung (can bes skipped if id is already knwon)
spendenmeldung = models.execute_kw(db, uid, password,
                                   'res.partner.donation_report', 'search_read',
                                   [
                                       [['id', '=', 123456789012345678901234567890]]
                                   ],
                                   {'fields': ['betrag',]
                                    })


# Manual force skipp the spendenmeldung
res = models.execute_kw(db, uid, password, 'res.partner.donation_report', 'manual_force_skipp',
                        [
                            [15957]
                        ],
                        {})
