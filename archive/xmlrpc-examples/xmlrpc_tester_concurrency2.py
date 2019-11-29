# Small test Script to Show and Test XMLRPC calls to odoo
import xmlrpclib
import datetime
import time

# Connection parameters
url = 'http://demo.datadialog.net'
db = 'demo'
username = 'admin'
password = 'admin'


#url = 'http://127.0.0.1:8069'


# Start the connection
common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
print common.version()

# Get the User ID
uid = common.authenticate(db, username, password, {})

# Get the models env
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

# Run for two minutes
runtime_end = datetime.datetime.now() + datetime.timedelta(0, 240)

counter = 1

while datetime.datetime.now() < runtime_end:
    # Write one res.partner
    # #2/8/2017 09:39:11 AM#
    # print 'Write to res.partner 1577'
    firstname = "Speed-" + str(counter)
    start_time = time.time()
    try:
        print models.execute_kw(db,
                                uid,
                                password,
                                'res.partner',
                                'write',
                                [
                                    [76],
                                    {
                                        #"firstname": firstname,
                                        #"lastname": firstname,
                                        "street": firstname,
                                    }
                                ],
                                {'context': {'lang': 'de_DE'}},
                                )
    except Exception as e:
        print e
        pass
    print "Time for %s in seconds %.3f" % (firstname, (time.time() - start_time))
    counter += 1
