# -*- coding: utf-8 -*-
# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib

# Connection parameters
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
print models.execute_kw(db, uid, password, 'res.partner.donation_report', 'create',
                        [
                            {'submission_env': "P",
                             'partner_id': 946,
                             'bpk_company_id': 1,
                             'anlage_am_um': '2018-03-09 09:12:36',
                             'ze_datum_von': '2017-01-01 00:00:01',
                             'ze_datum_bis': '2017-12-31 23:59:59',
                             'meldungs_jahr': '2017',
                             'betrag': 22,
                             }
                        ]
                        )
