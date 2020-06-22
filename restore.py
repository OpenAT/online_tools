# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
import shutil
import zipfile
import tempfile

from tools_settings import Settings
from tools_db import drop_db, connection_check, create_db
from tools_shell import shell
from tools import service_exists, service_control, service_running
import tools_odoo
from backup import backup

import logging
_log = logging.getLogger()


def restore(instance_dir, backup_zip_file, mode='manual', log_file='', cmd_args=None, settings=None,
            backup_before_drop=True, start_after_restore=False, timeout=60*60*3, development_mode=False):
    cmd_args = list() if not cmd_args else cmd_args
    mode_allowed = ('all', 'http', 'manual')
    assert mode in mode_allowed, "mode must be one of %s" % str(mode_allowed)

    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    backup_zip_file = os.path.abspath(backup_zip_file)

    # Start logging
    logging.info('----------------------------------------')
    logging.info('RESTORE instance %s' % instance)
    logging.info('----------------------------------------')
    assert os.path.isfile(pj(instance_dir, 'instance.ini')), 'Not an instance directory! %s' % instance_dir
    assert os.path.isfile(backup_zip_file), 'Backup zip file not found at %s' % backup_zip_file
    if not development_mode and not backup_before_drop:
        assert '_update' in instance, "'backup_before_drop' must be enabled for non update instances!"

    # Load instance configuration
    _log.info("Prepare settings")
    s = settings if settings else Settings(instance_dir, startup_args=cmd_args, log_file=log_file)
    assert s.filestore, "'filestore' directory is missing in odoo settings! %s" % str(s.filestore)

    # Connect to the instance database and set "db_exists"
    _log.info("Check if the database %s exists" % s.db_name)
    db_exists = connection_check(s.db_con_string)

    # Backup instance database before drop
    if db_exists and backup_before_drop:
        _log.info("Backup instance %s before we drop the database %s" % (s.instance, s.db_name))
        pre_drop_backup_file = backup(instance_dir, cmd_args=cmd_args, log_file=log_file)
        assert pre_drop_backup_file, "Could not create instance backup!"
        _log.info("Pre-restore instance backup created at %s" % pre_drop_backup_file)

    # Drop existing Database
    if db_exists:
        drop_db(db_name=s.db_name, postgres_db_con_string=s.postgres_db_con_string)

    # Remove 'filestore' directory
    if os.path.isdir(s.filestore):
        _log.warning("Remove existing filestore at %s" % s.filestore)
        shutil.rmtree(s.filestore)

    # Restore state for "multiple mode" attempts
    restore_done = False

    # mode http: Restore by odoo (via http connection)
    # ------------------------------------------------
    # ATTENTION: This will create the database
    if mode in ('all', 'http') and not restore_done:
        _log.info("Restore backup by odoo via http")
        try:
            restore_done = tools_odoo.odoo_restore(s.db_name, backup_zip_file, host=s.instance_local_url,
                                                   master_pwd=s.master_password)
        except Exception as e:
            _log.warning('Restore by odoo via http failed! %s' % repr(e))
            restore_done = False

    # mode manual: Manually restore database and 'filestore' folder
    # -------------------------------------------------------------
    if mode in ('all', 'manual') and not restore_done:
        _log.info("Restore backup manually by sql and file copy")

        # Stop the odoo service
        if service_exists(s.linux_instance_service):
            service_control(s.linux_instance_service, 'stop')
            assert not service_running(s.linux_instance_service), "Could not stop service %s" % s.linux_instance_service

        # Restore 'filestore' folder
        # ATTENTION: s.filestore INCLUDES the database name! e.d.: '.../dadi/data_dir/filestore/dadi'
        _log.info('Restore filestore from %s to %s' % (backup_zip_file, s.filestore))
        with zipfile.ZipFile(backup_zip_file) as archive:
            for f in archive.infolist():
                if f.filename.startswith('filestore/'):
                    _log.debug('filename: %s' % f.filename)
                    # Create the file target name
                    # E.g. source='filestore/dadi/01/file.txt' or 'filestore/01/file.txt' target='01/file.txt'
                    # ATTENTION: Do not use lstrip()! 'filestore/e0/'.lstrip('filestore/') results in '0/' ?!?
                    if f.filename.startswith('filestore/'+s.db_name+'/'):
                        target = f.filename.split('filestore/'+s.db_name+'/', 1)[1]
                    else:
                        target = f.filename.split('filestore/', 1)[1]
                    if target:
                        _log.debug('target: %s' % target)
                        f.filename = target
                        _log.debug('target filename: %s' % f.filename)
                        archive.extract(f, s.filestore)

        # Create and restore the database
        _log.info('Restore instance database %s from %s' % (s.db_name, backup_zip_file))

        # Create instance database
        create_db(db_name=s.db_name, db_user=s.db_user, postgres_db_con_string=s.postgres_db_con_string)

        # Unzip the dump.sql file
        _log.info("Unzip dump.sql from backup archive")
        temp_dump_sql_file = tempfile.NamedTemporaryFile(delete=False)
        try:
            # Open the Zip Archive
            with zipfile.ZipFile(backup_zip_file) as archive:
                # Open the file dump.sql from the zip archive as a file like object
                with archive.open('dump.sql') as dump_sql:
                    while True:
                        # Read 2048 bytes from the file
                        data = dump_sql.read(2048)
                        if not data:
                            break
                        # Write that bytes to the named temporary file
                        temp_dump_sql_file.write(data)
        except Exception as e:
            _log.error("Could not extract dump.sql from backup archive! %s" % repr(e))
            os.unlink(temp_dump_sql_file.name)
            raise e

        # Restore dump.sql
        _log.info("Restore dump.sql from backup archive with psql to database %s" % s.db_name)
        try:
            shell(['psql', '-d', s.db_url, '-f', temp_dump_sql_file.name], log=False, timeout=timeout)
            restore_done = True
        except Exception as e:
            _log.error("Restore dump.sql from backup archive with psql failed! %s" % repr(e))
            os.unlink(temp_dump_sql_file.name)
            raise e

        # Unlink the temp file
        _log.info("Unlink temp file for dump.sql")
        os.unlink(temp_dump_sql_file.name)

    # DISABLE all cron jobs and remove passwords and access data
    if development_mode:
        script_dir = os.path.split(os.path.realpath(__file__))[0]
        disable_for_development_file = pj(script_dir, 'sql', 'disable_for_development.sql')
        assert os.path.isfile(disable_for_development_file), "SQL file '%s' not found!" % disable_for_development_file
        shell(['psql', '-d', s.db_url, '-f', disable_for_development_file], log=False, timeout=timeout)

    # Start the odoo service
    if start_after_restore and service_exists(s.linux_instance_service):
        service_control(s.linux_instance_service, 'start')
        assert service_running(s.linux_instance_service), "Could not start service %s" % s.linux_instance_service

    if restore_done:
        _log.info('RESTORE OF INSTANCE %s FROM %s DONE!' % (s.instance, backup_zip_file))
    else:
        _log.error('RESTORE OF INSTANCE %s FROM %s FAILED!' % (s.instance, backup_zip_file))
    return restore_done
