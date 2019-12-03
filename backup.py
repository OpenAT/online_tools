# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
import datetime

from tools_settings import Settings
import tools_odoo

import logging
_log = logging.getLogger()


def backup(instance_dir, backup_file='', mode='manual', log_file='', cmd_args=None, settings=None, timeout=60*60*4):
    """
    Backup an FS-Online instance

    HINT: manual mode seems to be much faster and less cpu intensive therefore it is the default

    :param timeout: (int) timeout in seconds
    :param settings: instance settings object
    :param mode: (str) backup mode
    :param instance_dir: (str) Directory of the instance to backup
    :param backup_file: (str) Full Path and file name
    :param cmd_args: (list) with cmd options
    :param log_file: (str) Full Path and file name
    :return: (str) 'backup_file' if backup worked or (boolean) 'False' if backup failed
    """
    cmd_args = list() if not cmd_args else cmd_args
    mode_allowed = ('all', 'http', 'manual')
    assert mode in mode_allowed, "mode must be one of %s" % str(mode_allowed)
    
    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    _log.info('----------------------------------------')
    _log.info('BACKUP instance %s' % instance)
    _log.info('----------------------------------------')

    # Get odoo settings
    _log.info("Get instance settings from %s" % instance_dir)
    s = settings if settings else Settings(instance_dir, startup_args=cmd_args, log_file=log_file)

    # Default backup file name
    if not backup_file or backup_file == 'default':
        core_id = s.core_tag or s.core_commit
        start_str = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%S')
        assert core_id, "No commit tag or commit id found for odoo core at %s" % s.instance_core_dir
        backup_name = instance + '__' + start_str + '__' + core_id + '.zip'
        backup_file = pj(instance_dir, 'update', backup_name)
        _log.info("No backup file name specified. Using default name and location: %s" % backup_file)

    # Clean backup_file path
    backup_file = os.path.abspath(backup_file)
    backup_archive = None

    # Backup via http post request (= streaming by odoo)
    # --------------------------------------------------
    if mode in ('all', 'http') and not backup_archive:
        _log.info("Try regular backup via http connection to odoo")
        try:
            backup_archive = tools_odoo.odoo_backup(s.db_name, backup_file, host=s.instance_local_url,
                                                    master_pwd=s.master_password, timeout=timeout)
        except Exception as e:
            backup_archive = False
            _log.warning("Http streaming backup failed! %s" % repr(e))

    # Manual backup via file copy and pg_dump
    # ---------------------------------------
    if mode in ('all', 'manual') and not backup_archive:
        _log.info("Try manual backup via database url and data_dir copy")
        try:
            backup_archive = tools_odoo.odoo_backup_manual(db_url=s.db_url, data_dir=s.data_dir, backup_file=backup_file,
                                                           timeout=timeout)
        except Exception as e:
            backup_archive = False
            _log.error("Manual backup failed! %s" % repr(e))

    # _log result
    if backup_archive:
        _log.info("BACKUP OF INSTANCE %s TO %s DONE!" % (s.instance, backup_archive))
    else:
        _log.critical("BACKUP OF INSTANCE %s TO %s FAILED!" % (s.instance, backup_file))
        return False

    # Return 'path to backup file' or False
    return backup_archive
