# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib
import time

# Connection parameters
url = 'http://localhost:8069'
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
fields = ['firstname', 'lastname', 'street']
i = 1000
partners = list()
while i > 0:
    partners += [['Firstname', 'Lastname'+str(i), 'Street '+str(i)]]
    i = i-1


# Test the speed of the load method:
# start_time = time.time()
# print models.execute_kw(db, uid, password, 'res.partner', 'load',
#                         [
#                           #Header
#                           fields,
#                           #Data
#                           partners
#                         ],
#                         {'context': {}})
#
#
# duration = time.time() - start_time
# print "LOAD speed:"
# print "Total time in seconds %.3f" % duration
# print "Time per record in seconds %.3f" % (duration/len(partners))
# print "==================\n"


# Test the speed of separate create calls
partners_as_dicts = [dict(zip(fields, p)) for p in partners]
start_time = time.time()
for partner in partners_as_dicts:
    models.execute_kw(db, uid, password, 'res.partner', 'create',
                      [partner],
                      {'context': {'lang': 'de_DE'}})
duration = time.time() - start_time
print "CREATE speed:"
print "Total time in seconds %.3f" % duration
print "Time per record in seconds %.3f" % (duration/len(partners_as_dicts))
print "==================\n"
