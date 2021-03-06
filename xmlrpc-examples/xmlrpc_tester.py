# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib
import time

# Connection parameters
url = 'http://demo.datadialog.net'
db = 'demo'
username = 'admin'
password = 'admin'


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

# Create a test array of partner
i = 500
partners = list()
while i > 0:
    partners += [['my_partnerf.external_id'+str(i), 'Hulk'+str(i), 'Test']]
    i = i-1

print partners
# Test the speed of the load method:
start_time = time.time()

models.execute_kw(db, uid, password, 'res.partner', 'load',
                  [
                    #Header
                    ['id', 'firstname', 'lastname'],
                    #Data
                    partners
                  ],
                  {'context': {}})


duration = time.time() - start_time
print "Total time in seconds %.3f" % duration
print "Time per record in seconds %.3f" % (duration/len(partners))
