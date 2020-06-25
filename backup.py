# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
import datetime

from tools_settings import Settings
import tools_odoo

import logging
_log = logging.getLogger()


class BackupSettings:
    def __init__(self, instance_dir, env=None, backup_file=None, mode=None, db_url=None, data_dir=None, cmd_args=None,
                 settings=None, log_file=None, ):

        # Pass-Through variables
        self.instance_dir = instance_dir
        self.backup_file = backup_file

        # Computed variables
        self.odoo_db_name = None
        self.odoo_db_url = None
        self.odoo_host = None
        self.odoo_data_dir = None
        self.odoo_master_pwd = None

        # LOW LEVEL BACKUP WITHOUT ODOO / ODOO SETTINGS
        if db_url or data_dir:
            assert not settings, "settings must be empty when db_url or data_dir is given"
            assert backup_file != 'default', "backup_file missing"
            backup_dir = os.path.dirname(backup_file)
            assert os.access(backup_dir, os.R_OK), "Backup directory not writeable at %s" % backup_dir
            assert mode == 'manual', "mode must be 'manual' if db_url or data_dir is given!"
            assert db_url, "db_url missing"
            assert os.path.exists(data_dir), "data_dir not found at %s" % data_dir

            self.odoo_db_name = db_url.rsplit('/', 1)[1]
            self.odoo_db_url = db_url
            self.odoo_host = None
            self.odoo_data_dir = data_dir
            self.odoo_master_pwd = None

        # BACKUP WITH ODOO SETTINGS ON ODOO SERVICE HOST
        else:
            # Cleanup for instance_dir
            self.instance_dir = os.path.abspath(instance_dir)

            # Get odoo settings
            if not settings:
                _log.info("Get instance settings from %s" % instance_dir)
                s = Settings(instance_dir, startup_args=cmd_args, log_file=log_file)
            else:
                s = settings

            # Default backup_file name
            if not backup_file or backup_file == 'default':
                core_id = s.core_tag or s.core_commit
                start_str = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%S')
                assert core_id, "No commit tag or commit id found for odoo core at %s" % s.instance_core_dir
                backup_name = s.instance + '__' + start_str + '__' + core_id + '.zip'
                self.backup_file = pj(instance_dir, 'update', backup_name)
                _log.info("No backup file name specified. Using default name and location: %s" % self.backup_file)

            self.odoo_db_name = s.db_name
            self.odoo_db_url = s.db_url
            self.odoo_host = s.instance_local_url
            self.odoo_data_dir = s.data_dir
            self.odoo_master_pwd = s.master_password


def backup(instance_dir, env=None, backup_file='', mode='manual', db_url=None, data_dir=None,
           log_file='', cmd_args=None, settings=None,  timeout=60*60*4):
    """
    Backup an FS-Online instance

    HINT: manual mode seems to be much faster and less cpu intensive therefore it is the default

    :param timeout: (int) timeout in seconds
    :param settings: odoo instance settings object
    :param mode: (str) backup mode
    :param instance_dir: (str) Directory of the instance to backup
                               or just the instance name for manual backups on remote servers
    :param backup_file: (str) Full Path and file name
    :param cmd_args: (list) with cmd options
    :param log_file: (str) Full Path and file name
    :return: (str) 'backup_file' if backup worked or (boolean) 'False' if backup failed
    """
    cmd_args = list() if not cmd_args else cmd_args
    mode_allowed = ('manual', 'odoo')
    assert mode in mode_allowed, "mode must be one of %s" % str(mode_allowed)

    # COMPUTE SETTINGS FOR BACKUP
    # ---------------------------
    bse = BackupSettings(instance_dir, env=env, backup_file=backup_file, mode=mode, db_url=db_url,
                         data_dir=data_dir, cmd_args=cmd_args, settings=settings, log_file=log_file)

    # START BACKUP
    # ------------
    _log.info('--------------------------------------------------------------------------------')
    _log.info('BACKUP (db: %s, instance %s)' % (bse.odoo_db_name, bse.instance_dir))
    _log.info('--------------------------------------------------------------------------------')

    # Backup via odoo post request (= streaming by odoo)
    if mode == 'odoo':
        _log.info("Try odoo backup via odoo service")
        try:
            backup_archive = tools_odoo.odoo_backup(bse.odoo_db_name,
                                                    bse.backup_file,
                                                    host=bse.odoo_host,
                                                    master_pwd=bse.odoo_master_pwd,
                                                    timeout=timeout)
        except Exception as e:
            _log.warning("Odoo backup failed! %s" % repr(e))
            raise e

    # Manual backup via file copy and pg_dump
    if mode == 'manual':
        _log.info("Try manual odoo backup via database dump and data_dir copy")
        try:
            backup_archive = tools_odoo.odoo_backup_manual(db_url=bse.odoo_db_url,
                                                           data_dir=bse.odoo_data_dir,
                                                           backup_file=bse.backup_file,
                                                           timeout=timeout)
        except Exception as e:
            _log.error("Manual odoo backup failed! %s" % repr(e))
            raise e

    assert backup_archive, "BACKUP OF INSTANCE %s TO %s FAILED!" % (bse.instance_dir, bse.backup_file)

    # _log result
    _log.info("BACKUP OF INSTANCE %s TO %s DONE!" % (bse.instance_dir, backup_archive))

    # Return 'path to backup file' or False
    return backup_archive
