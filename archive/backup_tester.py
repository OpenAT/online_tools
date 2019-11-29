# -*- coding: utf-'8' "-*-"

import os
from requests import Session, codes
from shell_tools import check_disk_space, test_zip

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


if __name__ == "__main__":
    backup('bsvw', '/Users/mkarrer/Entwicklung/github/online/online_tools/bsvw_test.zip',
           host="http://bsvw.datadialog.net", master_pwd='BSVWPWx3847#1')
