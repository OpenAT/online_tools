# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib


# Connection parameters
url = 'http://localhost:8069'
db = 'dadi'
username = 'admin'
password = 'admin'


common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
print common.version()

# Get the User ID
uid = common.authenticate(db, username, password, {})

# Get the models env
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

# Write one res.partner
# #2/8/2017 09:39:11 AM#
print 'Write to res.partner 1577'
print models.execute_kw(db, uid, password,
                  'res.partner',
                  'write',
                  [[1577],
                   {
                    "anrede_individuell": False,
                    "birthdate_web": "06.01.1983",
                    "city": "Wien",
                    "company_name_web": False,
                    #"create_date": "###",
                    "donation_deduction_optout_web": False,
                    "donation_receipt_web": False,
                    "email": "a.briones.rojas@gmail.com",
                    "firstname": "Agnes",
                    "fstoken_update": "H05EYTJ1ZWG7",
                    #2/8/2017 09:39:11 AM#
                    "fstoken_update_date": "2017-02-08T09:39:11Z",
                    "gender": "female",
                    "is_company": False,
                    "lastname": "Briones Rojas",
                    "name_zwei": False,
                    "newsletter_web": True,
                    "street": "Rautenkranzgasse",
                    "street_number_web": "46/110",
                    "street2": False,
                    "title_web": False,
                    "zip": "1210",
                   }],
                   {'context': {'lang': 'de_DE'}}
                  )
