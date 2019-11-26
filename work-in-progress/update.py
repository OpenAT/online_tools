# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
from time import sleep
import datetime
import ConfigParser
import psutil
from psutil import NoSuchProcess

from tools_settings import Settings
from tools_shell import find_file
from tools import prepare_repository, prepare_core, inifile_to_dict, send_email

import logging
_log = logging.getLogger()


def _update_checks(settings, parallel_updates=2):
    _log.info('Run update checks')
    s = settings

    # Early raise an exception if update_lock_file exists but there is no running update process
    if os.path.isfile(s.update_lock_file):
        try:
            update_lock = inifile_to_dict(s.update_lock_file, 'info')
            update_lock_pid = int(update_lock['pid'])
            if not psutil.pid_exists(update_lock_pid):
                raise EnvironmentError("Update-lock-file exists but the related update-process is not running! "
                                       "You may delete the update-lock-file and try again.")
        except EnvironmentError as e:
            raise e
        except Exception as e:
            _log.warning('Concurrent update-process-id could not be read from update_lock_file %s! %s'
                         '' % (s.update_lock_file, repr(e)))
            pass

    # Check for a concurrent update for this instance
    concurrent_lock_counter = 60*12
    while os.path.isfile(settings.update_lock_file) and concurrent_lock_counter > 0:
        _log.warning('Concurrent update for this instance running! Wait for %s minutes.' % concurrent_lock_counter)
        sleep(60)
        concurrent_lock_counter -= 1
        if concurrent_lock_counter <= 0:
            raise Exception('Concurrent update check timed out!')

    # Check parallel updates on this server (max 2)
    parallel_lock_counter = 60*12
    while len(find_file(settings.update_lock_file_name,
                        start_dir=os.path.dirname(settings.instance_dir),
                        max_finds=parallel_updates,
                        exclude_folders=['cores'])) >= parallel_updates and parallel_lock_counter > 0:
        _log.warning('At least %s other updates are running on this server! Wait for %s minutes.'
                     '' % (parallel_updates, parallel_lock_counter))
        sleep(60)
        parallel_lock_counter -= 1
        if parallel_lock_counter <= 0:
            raise Exception('Parallel update check timed out!')

    # This is mandatory (python will NOT return True by default but just return)
    return True


def _prepare_update(instance_settings_obj):
    assert instance_settings_obj, "Instance settings missing!"
    s = instance_settings_obj

    # TODO: return the addons-to-update or raise an exception.
    #       If there are no addons to update return an empty list

    # Prepare the update_instance repository directory
    # ------------------------------------------------
    update_instance = s.instance + "_update"
    update_instance_dir = pj(s.instance_dir, 'update', update_instance)
    _log.info("Prepare the update_instance repository at directory: %s" % update_instance_dir)
    prepare_repository(repo_dir=update_instance_dir, service_name=update_instance,
                       git_remote_url=s.git_remote_url, branch=s.git_branch, user=s.linux_user)

    # Get update_instance settings
    # ----------------------------
    s_upd = Settings(update_instance_dir, startup_args=s.startup_args, log_file=s.log_file, update_instance_mode=True)
    assert s.instance != s_upd.instance, "Instance '%s' and update_instance '%s' can not be the same!" % (
        s.instance, s_upd.instance)
    # Check the git commits
    if s.git_commit == s_upd.git_commit:
        _log.warning("Commit did not change! Update is not necessary!")
        return list()

    # Prepare the update_instance odoo core (and therefore the core for the final update)
    # -----------------------------------------------------------------------------------
    # TODO: Set correct user and user-rights for core preparation
    prepare_core(s_upd.instance_core_dir, tag=s_upd.instance_core_tag, git_remote_url=s_upd.core_remote_url,
                 user=s_upd.linux_user, copy_core_dir=s.instance_core_dir)

    # Update the update_instance settings (since the core exists now)
    # -----------------------------------
    s_upd = Settings(update_instance_dir, startup_args=s.startup_args, log_file=s.log_file, update_instance_mode=True)

    # Search for addons-to-update
    # ---------------------------
    # Search for changed core addons
    # Search for changed instance addons
    # use -u all if more than 6 addons have changed (maybe we need a way to force -u all )
    # Stop here if no addons to update are found
    # Search for changed core translations
    # Search for changed instance translations
    # Return an empty list if there are no addons to update!

    # Backup the instance and restore in the update_instance
    # ------------------------------------------------------

    # Dry-Run/Test the update in the update_instance
    # ----------------------------------------------
    # Backup the instance
    # Restore the backup to the dry-run update_instance
    # Test-Run the addon updates
    # Test-Run the language updates
    # return addons_to_update


def _update(instance_settings_obj, pre_update_backup, addons_to_update):
    assert instance_settings_obj, "Instance settings missing!"
    s = instance_settings_obj

    # Stop the service
    # Run the update
    # Restore pre update backup if the update fails
    # Send message to sysadmin

    return True


def update(instance_dir, cmd_args=None, log_file='', parallel_updates=2):
    logging.info('----------------------------------------')
    logging.info('UPDATE instance')
    logging.info('----------------------------------------')
    logging.info('pid: %s' % os.getpid())
    logging.info('process.name: %s' % psutil.Process(os.getpid()).name())
    
    now = datetime.datetime.now()
    datetime_fmt = '%Y-%m-%dT%H-%M-%S'
    start = now.strftime(datetime_fmt)

    # Get instance settings
    s = Settings(instance_dir, startup_args=cmd_args, log_file=log_file)

    subject_success = 'FS-Online update DONE for instance %s' % s.instance
    subject_error = 'FS-Online update FAILED for instance %s' % s.instance

    # Send update-start email
    send_email(subject='FS-Online update started for instance %s at %s' % (s.instance, start))

    # Pre update checks
    try:
        _update_checks(s, parallel_updates=parallel_updates)
    except Exception as e:
        msg = 'Pre-update checks failed! %s' % repr(e)
        _log.error(msg)
        send_email(subject=subject_error, body=msg)
        return False

    # Create the update-lock-file
    _log.info("Creating update.lock file at %s!" % s.update_lock_file)
    update_lock = ConfigParser.SafeConfigParser()
    update_lock.add_section('info')
    update_lock.set('info', 'pid', str(os.getpid()))
    update_lock.set('info', 'instance_dir', s.instance_dir)
    update_lock.set('info', 'starttime', start)
    with open(s.update_lock_file, 'w+') as update_lock_file:
        update_lock.write(update_lock_file)

    # Prepare the update
    try:
        _prepare_update(instance_settings_obj=s)
    except Exception as e:
        msg = "Pre-Update preparations failed! %s" % repr(e)
        _log.error(msg)
        os.unlink(s.update_lock_file)
        send_email(subject=subject_error, body=msg)
        return False

    # Update the production instance
    try:
        update_done = _update(instance_settings_obj=s)
    except Exception as e:
        msg = "Update failed with unexpected exception! %s" % repr(s)
        _log.critical(msg)
        # HINT: Do !NOT! remove the update_lock_file because an unexpected exception was raised in the final update!
        send_email(subject=subject_error+' with unexpected exception!!!', body=msg)
        return False

    # Finish the update
    msg = "Update successfully done!" if update_done else "Update failed! But service was successfully restored!"
    send_email(subject=subject_success if update_done else subject_error, body=msg)
    return update_done
