# -*- coding: utf-'8' "-*-"
import os
import sys
import shutil
import zipfile
from requests import Session, codes
import base64
from xmlrpclib import ServerProxy

from urlparse import urljoin
import logging

log = logging.getLogger()


def backup(database, backup_file, host='http://127.0.0.1:8069', master_pwd='admin'):
    backup_file = os.path.abspath(backup_file)
    log.info("Start Odoo backup of database %s at host %s to %s" % (database, host, backup_file))
    assert os.access(os.path.dirname(backup_file), os.W_OK), 'Backup location %s not writeable!' % backup_file
    assert not os.path.exists(backup_file), "Backup file exists! (%s)" % backup_file

    # TODO: Check free disk space

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
    log.info("Verify the zip archive at %s" % backup_file)
    try:
        backup_zip = zipfile.ZipFile(backup_file)
        failed = backup_zip.testzip()
        assert failed is None, "Damaged files in zip archive found! %s" % failed
    except Exception as e:
        log.error("Zip archive damaged!\n%s" % repr(e))
        raise e

    log.info("Backup successful!")
    return backup_file


def backup_manual(db_url='', filestore='', backup_file=''):
    database = db_url.rsplit('/', 1)[1]
    assert database, "Database name not found in db_url!"

    filestore = os.path.abspath(filestore)
    assert os.path.exists(filestore), "Filestore not found at %s" % filestore

    backup_file = os.path.abspath(backup_file)
    log.info("Start manual Odoo backup of database %s to %s" % (database, backup_file))

    backup_dir = os.path.dirname(backup_file)
    assert os.access(backup_dir, os.W_OK), 'Backup location %s not writeable!' % backup_file
    assert not os.path.exists(backup_file), "Backup file exists! (%s)" % backup_file

    # TODO: Check free disk space

    # Create temporary backup folder
    temp_dir_name = 'temp_' + os.path.splitext(os.path.basename(backup_file))[0]
    temp_dir = os.path.join(backup_dir, temp_dir_name)
    log.info("Create temporary backup folder at %s" % temp_dir)
    os.makedirs(temp_dir)

    # Backup data
    if os.path.isdir(os.path.join(filestore, database)):
        source_dir = os.path.join(filestore, database)
    else:
        source_dir = filestore
    target_dir = os.path.join(temp_dir, 'filestore')
    log.info("Copy data at %s to %s" % (source_dir, target_dir))
    shutil.copytree(source_dir, target_dir)

    # TODO: Backup database via pg_dump

    # TODO: ZIP data in temp_dir

    # TODO: Verify Zip Archive

    # TODO: Remove Temp folder

    # TODO: Log and return result






