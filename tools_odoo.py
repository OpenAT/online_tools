# -*- coding: utf-'8' "-*-"
import os
import shutil
from urlparse import urljoin
# from xmlrpclib import ServerProxy

from tools_shell import shell, check_disk_space, test_zip, make_zip_archive

import logging
_log = logging.getLogger()


# ATTENTION: Importing requests may lead to segmentation faults on odoo startup!!!
# from requests import Session, codes
# ATTENTION: Version 2.3 is so old that it will not even recognise the REQUESTS_CA_BUNDLE env variable :(
#            therefore we need to do it by saltstack with an symbolic link - check the o
_log.info('python -m requests.certs >>> %s' % shell(['python', '-m', 'requests.certs']))
ca_bundle = os.path.join('/etc/ssl/certs/', 'ca-certificates.crt')
if os.path.isfile(ca_bundle):
    os.environ['REQUESTS_CA_BUNDLE'] = ca_bundle
    _log.warning('Environment var REQUESTS_CA_BUNDLE set to %s for python request library' % ca_bundle)
    _log.info('python -m requests.certs >>> %s' % shell(['python', '-m', 'requests.certs']))
try:
    from requests import certs
    requests_ca_bundle_path = certs.where()
    _log.info('requests: python request library ca-bundle path: %s' % requests_ca_bundle_path)
except Exception as e:
    _log.error('requests: could not run certs.where() %s' % repr(e))
    pass
from requests import Session, codes


# Min free space for backup location
_min_odoo_backup_space_mb = 20000

# TODO
# def _odoo_access_check(instance_dir, odoo_config=None):
#     instance_dir = os.path.abspath(instance_dir)
#     instance = os.path.basename(instance_dir)
#     odoo_config = odoo_config or _odoo_config(instance_dir)
#
#     logging.debug('Checking odoo xmlrpc access for instance %s' % instance)
#
#     # Getting xmlrpc connection parameters
#     # Default Settings
#     xmlrpc_interface = "127.0.0.1"
#     xmlrpc_port = "8069"
#     # Overwrite with xmlrpcs or xmlrpc from server.conf
#     if odoo_config.get('xmlrpcs'):
#         xmlrpc_interface = odoo_config.get('xmlrpcs_interface') or xmlrpc_interface
#         xmlrpc_port = odoo_config.get('xmlrpcs_port') or xmlrpc_port
#     elif odoo_config.get('xmlrpc'):
#         xmlrpc_interface = odoo_config.get('xmlrpc_interface') or xmlrpc_interface
#         xmlrpc_port = odoo_config.get('xmlrpc_port') or xmlrpc_port
#
#     # Connect to odoo by xmlrpc
#     odoo = ServerProxy('http://'+xmlrpc_interface+'/xmlrpc/db')


def odoo_backup(database, backup_file, host='http://127.0.0.1:8069', master_pwd='admin', timeout=60 * 60 * 4):
    # TODO: Honour timeout
    backup_file = os.path.abspath(backup_file)
    _log.info("Start Odoo backup of database %s at host %s to %s" % (database, host, backup_file))
    assert os.access(os.path.dirname(backup_file), os.W_OK), 'Backup location %s not writeable!' % backup_file
    assert not os.path.exists(backup_file), "Backup file exists! (%s)" % backup_file

    backup_dir = os.path.dirname(backup_file)
    assert check_disk_space(backup_dir, min_free_mb=_min_odoo_backup_space_mb
                            ), "Less than %sMB free disk space at %s" % (_min_odoo_backup_space_mb, backup_dir)

    # Start a stream backup via http
    url = urljoin(host, '/web/database/backup')
    payload = {'backup_db': database,
               'backup_pwd': master_pwd,
               'token': ''}

    _log.info("Request backup from %s" % url)
    session = Session()
    session.verify = True
    db_backup = session.post(url, data=payload, stream=True)
    assert db_backup and db_backup.status_code == codes.ok, "Backup request failed!"

    # Stream backup to file
    _log.info("Write backup to file %s" % backup_file)
    with open(backup_file, 'wb') as bf:
        for chunk in db_backup.iter_content(chunk_size=128):
            bf.write(chunk)

    # Verify the backup zip
    test_zip(backup_file)

    _log.info("Backup successful!")
    return backup_file


def odoo_backup_manual(db_url='', data_dir='', backup_file='', timeout=60 * 60 * 4):
    database = db_url.rsplit('/', 1)[1]
    assert database, "Database name not found in db_url!"

    _log.info("Start manual Odoo backup of database %s to %s" % (database, backup_file))

    # odoo data_dir
    data_dir = os.path.abspath(data_dir)
    assert os.path.exists(data_dir), "odoo directory 'data_dir' not found at %s" % data_dir

    # Archive file and location
    backup_file = os.path.abspath(backup_file)
    backup_dir = os.path.dirname(backup_file)
    assert os.access(backup_dir, os.W_OK), 'Backup location %s not writeable!' % backup_file
    assert not os.path.exists(backup_file), "Backup file exists! (%s)" % backup_file

    # Check disk space
    assert check_disk_space(backup_dir, min_free_mb=_min_odoo_backup_space_mb
                            ), "Less than %sMB free disk space at %s" % (_min_odoo_backup_space_mb, backup_dir)

    # Create temporary backup folder
    backup_file_name = os.path.basename(backup_file)
    temp_dir_name = 'temp_' + os.path.splitext(backup_file_name)[0]
    assert len(temp_dir_name) > 5, "Temp backup directory name too short %s" % temp_dir_name
    temp_dir = os.path.join(backup_dir, temp_dir_name)
    _log.info("Create temporary backup folder at %s" % temp_dir)
    os.makedirs(temp_dir)

    # Backup file data (filestore of odoo)
    source_dir = os.path.join(data_dir, 'filestore', database)
    assert os.path.isdir(source_dir), "Files source directory not found at %s" % source_dir

    target_dir = os.path.join(temp_dir, 'filestore')
    _log.info("Copy data at %s to %s" % (source_dir, target_dir))
    shutil.copytree(source_dir, target_dir)

    # Backup database via pg_dump
    db_file = os.path.join(temp_dir, 'dump.sql')
    _log.info("Backup database %s via pg_dump to %s" % (database, db_file))
    try:
        shell(['pg_dump', '--format=p', '--no-owner', '--dbname=' + db_url, '--file=' + db_file],
              log=False, timeout=timeout)
    except Exception as e:
        _log.error("Database backup via pg_dump failed! %s" % repr(e))
        raise e

    # Create (and test) zip archive from the temp folder
    _log.info("Create a zip archive at %s from temporary backup folder %s" % (backup_file, temp_dir))
    # if backup_file.endswith('.zip'):
    #     backup_file = backup_file.rsplit('.zip', 1)[0]
    # backup_zip_file = shutil.make_archive(backup_file, 'zip', root_dir=temp_dir)
    if not backup_file.endswith('.zip'):
        _log.warning('Backup-file should end with .zip! %s' % backup_file)
    make_zip_archive(output_filename=backup_file, source_dir=temp_dir, verify_archive=True)

    # Remove Temp folder
    assert len(temp_dir) >= 12, "Temp directory seems to be wrong? %s" % temp_dir
    _log.info("Remove temp dir %s" % temp_dir)
    shutil.rmtree(temp_dir)

    # Log and return result
    _log.info("Manual Odoo backup of database %s to %s done!" % (database, backup_file))
    return backup_file


def odoo_restore(database, backup_zip_file, host='http://127.0.0.1:8069', master_pwd='admin'):
    backup_zip_file = os.path.abspath(backup_zip_file)
    _log.info("Restore by odoo via http from file %s" % backup_zip_file)
    assert os.path.isfile(backup_zip_file), "Backup zip file not found at %s" % backup_zip_file

    # Verify the backup zip
    test_zip(backup_zip_file)

    # Try a http restore
    # Start a stream backup via http
    url = urljoin(host, '/web/database/restore')
    payload = {'restore_pwd': master_pwd,
               'new_db': database,
               'mode': False}

    _log.info("Start restore POST request to %s" % url)
    session = Session()
    session.verify = True
    try:
        files = {'db_file': (backup_zip_file, open(backup_zip_file, 'rb'))}
        response = session.post(url, data=payload, files=files, stream=True)
        assert response and response.status_code == codes.ok, "Restore-response http status code != %s!" % codes.ok
        _log.info('Restore by odoo via http done!')
    except Exception as e:
        _log.error("Restore by odoo via http failed! %s" % repr(e))
        raise e

    return True
