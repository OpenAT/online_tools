# -*- coding: utf-8 -*-
# Small test Script to Show and Test XMLRPC calls to odoo

import xmlrpclib
import time

# Connection parameters
#url = 'http://localhost:8069'
url = 'http://clic.datadialog.net'
db = 'clic'
username = 'admin'
password = ''

common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
print common.version()

# Get the User ID
uid = common.authenticate(db, username, password, {})

# Get the models env
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

# Test check_bpk
partner_to_delete = [47800, 47801, 47802, 47803, 47804, 47805, 47806, 47807, 47808, 47811, 47809, 47810, 47812, 47813, 47818, 47814, 47819, 47815, 47816, 47822, 47817, 47823, 47934, 47933, 47932, 47931, 47930, 47929, 47928, 47927, 47926, 47925, 47924, 47923, 47922, 47921, 47920, 47919, 47824, 47918, 47917, 47916, 47915, 47914, 47913, 47912, 47911, 47910, 47909, 47908, 47907, 47906, 47905, 47904, 47903, 47902, 47901, 47900, 47899, 47898, 47897, 47896, 47895, 47894, 47825, 47893, 47892, 47891, 47890, 47889, 47888, 47887, 47886, 47885, 47884, 47883, 47882, 47881, 47880, 47879, 47878, 47877, 47876, 47875, 47874, 47873, 47872, 47871, 47820, 47870, 47869, 47868, 47867, 47866, 47826, 47865, 47864, 47863, 47862, 47861, 47860, 47859, 47858, 47857, 47856, 47855, 47854, 47853, 47852, 47851, 47850, 47849, 47848, 47847, 47846, 47845, 47844, 47843, 47842, 47821, 47841, 47840, 47827, 47839, 47838, 47837, 47836, 47835, 47834, 47833, 47832, 47831, 47830, 47829]

for pid in partner_to_delete:

    partner = models.execute_kw(db, uid, password,
                                'res.partner', 'search_read',
                                [[['id', '=', pid]]],
                                {'fields': ['name', 'bpk_request_ids']})

    if partner:
        name = partner[0]['name']
        print "Deleting Partner %s" % name

        # Delete related bpks
        bpk_request_ids = partner[0].get('bpk_request_ids')
        for bpk_id in bpk_request_ids:
            print "Deleting bpk with id %s for partner %s" % (bpk_id, name)
            print models.execute_kw(db, uid, password, 'res.partner.bpk', 'unlink',
                                    [[bpk_id]],
                                    {})

        # Delete the partner
        print "Deleting partner with id %s and name %s" % (pid, name)
        print models.execute_kw(db, uid, password, 'res.partner', 'unlink',
                                [[pid]],
                                {})
