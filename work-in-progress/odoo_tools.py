# -*- coding: utf-'8' "-*-"
import os
import sys
import shutil
import zipfile
from requests import Session, codes
import base64
from xmlrpclib import ServerProxy
import zipfile

from shell_tools import shell, check_disk_space, test_zip

from urlparse import urljoin
import logging

log = logging.getLogger()


def backup(database, backup_file, host='http://127.0.0.1:8069', master_pwd='admin'):
    backup_file = os.path.abspath(backup_file)
    log.info("Start Odoo backup of database %s at host %s to %s" % (database, host, backup_file))
    assert os.access(os.path.dirname(backup_file), os.W_OK), 'Backup location %s not writeable!' % backup_file
    assert not os.path.exists(backup_file), "Backup file exists! (%s)" % backup_file

    backup_dir = os.path.dirname(backup_file)
    assert check_disk_space(backup_dir, min_free_mb=3000), "Less than 3GB free disk space at %s" % backup_dir

    # Start a stream backup via http
    url = urljoin(host, '/web/database/backup')
    payload = {'backup_db': database,
               'backup_pwd': master_pwd,
               'token': ''}

    log.info("Request backup from %s" % url)
    session = Session()
    session.verify = True
    db_backup = session.post(url, data=payload, stream=True)
    assert db_backup and db_backup.status_code == codes.ok, "Backup request failed!"

    # Stream backup to file
    log.info("Write backup to file %s" % backup_file)
    with open(backup_file, 'wb') as bf:
        for chunk in db_backup.iter_content(chunk_size=128):
            bf.write(chunk)

    # Verify the backup zip
    test_zip(backup_file)

    log.info("Backup successful!")
    return backup_file


def restore(database, backup_zip_file, host='http://127.0.0.1:8069', master_pwd='admin'):
    backup_zip_file = os.path.abspath(backup_zip_file)
    log.info("Restore odoo backup from %s" % backup_zip_file)
    assert os.path.isfile(backup_zip_file), "Backup zip file not found at %s" % backup_zip_file

    # Verify the backup zip
    test_zip(backup_zip_file)

    # Try a http restore
    # Start a stream backup via http
    url = urljoin(host, '/web/database/restore')
    payload = {'restore_pwd': master_pwd,
               'new_db': database,
               'mode': False}

    log.info("Start restore POST request to %s" % url)
    session = Session()
    session.verify = True
    try:
        files = {'db_file': (backup_zip_file, open(backup_zip_file, 'rb'))}
        response = session.post(url, data=payload, files=files, stream=True)
        assert response and response.status_code == codes.ok, "Restore-response http status code != %s!" % codes.ok
    except Exception as e:
        log.error("Restore request failed! %s" % repr(e))
        raise e

    # Return True or False
    return True


def backup_manual(db_url='', data_dir='', backup_file=''):
    database = db_url.rsplit('/', 1)[1]
    assert database, "Database name not found in db_url!"

    data_dir = os.path.abspath(data_dir)
    assert os.path.exists(data_dir), "Folder data_dir not found at %s" % data_dir

    backup_file = os.path.abspath(backup_file)
    log.info("Start manual Odoo backup of database %s to %s" % (database, backup_file))

    backup_dir = os.path.dirname(backup_file)
    assert os.access(backup_dir, os.W_OK), 'Backup location %s not writeable!' % backup_file
    assert not os.path.exists(backup_file), "Backup file exists! (%s)" % backup_file

    assert check_disk_space(backup_dir, min_free_mb=3000), "Less than 3GB free disk space at %s" % backup_dir

    # Create temporary backup folder
    backup_file_name = os.path.basename(backup_file)
    temp_dir_name = 'temp_' + os.path.splitext(backup_file_name)[0]
    assert len(temp_dir_name) > 5, "Temp backup directory name too short %s" % temp_dir_name
    temp_dir = os.path.join(backup_dir, temp_dir_name)
    log.info("Create temporary backup folder at %s" % temp_dir)
    os.makedirs(temp_dir)

    # Backup file data (filestore of odoo)
    source_dir = os.path.join(data_dir, 'filestore', database)
    assert os.path.isdir(source_dir), "Files source directory not found at %s" % source_dir

    target_dir = os.path.join(temp_dir, 'filestore')
    log.info("Copy data at %s to %s" % (source_dir, target_dir))
    shutil.copytree(source_dir, target_dir)

    # Backup database via pg_dump
    db_file = os.path.join(temp_dir, 'dump.sql')
    log.info("Backup database %s via pg_dump to %s" % (database, db_file))
    try:
        shell(['pg_dump', '--format=p', '--no-owner', '--dbname=' + db_url, '--file=' + db_file],
              log_info=False, timeout=60*30)
    except Exception as e:
        log.error("Database backup via pg_dump failed! %s" % repr(e))
        raise e

    # ZIP data in temp_dir
    if backup_file.endswith('.zip'):
        backup_file = backup_file.rsplit('.zip', 1)[0]
    log.info("Create a zip archive at %s from temporary backup folder %s" % (backup_file, temp_dir))
    backup_zip_file = shutil.make_archive(backup_file, 'zip', root_dir=temp_dir)

    # Verify Zip Archive
    test_zip(backup_zip_file)

    # Remove Temp folder
    assert len(temp_dir) >= 12, "Temp directory seems to be wrong? %s" % temp_dir
    log.info("Remove temp dir %s" % temp_dir)
    shutil.rmtree(temp_dir)

    # Log and return result
    log.info("Manual Odoo backup of database %s to %s done!" % (database, backup_zip_file))
    return backup_zip_file



