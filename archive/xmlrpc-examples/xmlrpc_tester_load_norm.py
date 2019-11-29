# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib
import time

# Connection parameters
url = 'http://demo.datadialog.net'
db = 'demo'
username = 'admin'
password = 'hfjfk94l4mf#3'


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
i = 1000
tokens = list()
while i > 0:
    tokens += [['my_token_r.external_id'+str(i), '123456789r'+str(i), 'Administrator']]
    i = i-1

fields = ['id', 'name', 'partner_id']
#print tokens
# Test the speed of the load method:
start_time = time.time()

print models.execute_kw(db, uid, password, 'res.partner.fstoken', 'load',
                        [
                          #Header
                          fields,
                          #Data
                          tokens
                        ],
                        {'context': {}})


duration = time.time() - start_time
print "Total time in seconds %.3f" % duration
print "Time per record in seconds %.3f" % (duration/len(tokens))

print "==================\n"
start_time = time.time()
for token in tokens:
    token_dict = {'partner_id': 1, 'name': token[1]+'x'}
    #print token_dict
    models.execute_kw(db, uid, password, 'res.partner.fstoken', 'create',
                      [token_dict],
                      {'context': {}})
duration = time.time() - start_time
print "Total time in seconds %.3f" % duration
print "Time per record in seconds %.3f" % (duration/len(tokens))
