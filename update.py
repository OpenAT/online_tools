# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
from time import sleep
import datetime
import ConfigParser
import psutil
import sys
import pwd

from tools_settings import Settings, set_arg
from tools_shell import find_file, shell
from tools_git import git_latest, get_sha1
from tools import prepare_repository, prepare_core, inifile_to_dict, send_email, find_addons_to_update, \
    service_control, service_exists, service_running
from backup import backup
from restore import restore


import logging
_log = logging.getLogger('fsonline')


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


def _prepare_update(instance_settings_obj, timeout=60*60*4):
    _log.info('Prepare the instance update!')
    # ATTENTION: Must raise an exception if anything goes wrong!
    assert instance_settings_obj, "Instance settings missing!"
    s = instance_settings_obj

    # Return dictionary format
    result = {'updated_to_commit': '',
              'pre_update_backup': '',
              'addons_to_update': '',
              'addons_string': ''}

    # Check/Reset the current instance odoo core
    # --------- --------------------------------
    _log.info('Prepare odoo core %s for current instance %s!' % (s.instance_core_dir, s.instance))
    prepare_core(s.instance_core_dir, tag=s.instance_core_tag, git_remote_url=s.core_remote_url, user=s.linux_user,
                 production_server=s.production_server)

    # Prepare the update_instance repository directory
    # ------------------------------------------------
    update_instance = s.instance + "_update"
    update_instance_dir = pj(s.instance_dir, 'update', update_instance)
    _log.info("Prepare the update_instance repository at directory: %s" % update_instance_dir)
    prepare_repository(repo_dir=update_instance_dir, service_name=update_instance,
                       git_remote_url=s.git_remote_url, branch=s.git_branch, user=s.linux_user)

    # Get update_instance settings
    # ----------------------------
    _log.info('Get update_instance settings after odoo core preparation for the update_instance!')
    s_upd = Settings(update_instance_dir, startup_args=s.startup_args, log_file=s.log_file, update_instance_mode=True)
    send_email(subject='FS-Online update started for instance %s to core %s and instance-commit %s'
                       '' % (s.instance.upper(), s_upd.core_tag, s_upd.git_commit))
    assert s.instance != s_upd.instance, "Instance '%s' and update_instance '%s' can not be the same!" % (
        s.instance, s_upd.instance)

    # Append update-commit-target commit to the result
    result['updated_to_commit'] = s_upd.git_commit

    # Check the git commits
    if s.git_commit == s_upd.git_commit:
        _log.warning("INSTANCE COMMIT DID NOT CHANGE! UPDATE IS NOT NECESSARY!")
        # HINT: This is an expected result and therefore should NOT raise an exception!
        return result

    # Prepare the update_instance odoo core (and therefore the core for the final update)
    # -----------------------------------------------------------------------------------
    prepare_core(s_upd.instance_core_dir, tag=s_upd.instance_core_tag, git_remote_url=s_upd.core_remote_url,
                 user=s_upd.linux_user, copy_core_dir=s.instance_core_dir,
                 production_server=s.production_server)

    # Update the update_instance settings (since the core exists now)
    # -----------------------------------
    s_upd = Settings(update_instance_dir, startup_args=s.startup_args, log_file=s.log_file, update_instance_mode=True)

    # Search for addons-to-update
    # ---------------------------
    addons_to_update = find_addons_to_update(s, s_upd)
    if not addons_to_update:
        _log.warning("NO ADDONS TO UPDATE FOUND! SKIPPING THE DRY-RUN UPDATE TEST AND THE PRE-UPDATE-BACKUP!")
        return result

    # Prepare the odoo startup arguments addons string
    addons_string = 'all' if len(addons_to_update) >= 6 else ','.join(addons_to_update)

    # Append addons-to-update to the result
    result['addons_to_update'] = addons_to_update
    result['addons_string'] = addons_string

    # Backup the current instance and restore it in the update_instance
    # -----------------------------------------------------------------
    # Backup
    _log.info('Creating pre-update-backup')
    pre_update_backup = backup(s.instance_dir, log_file=s_upd.log_file, settings=s)

    # Append pre_update_backup file to the result
    result['pre_update_backup'] = pre_update_backup

    # Restore
    _log.info('Pre-update-backup was created at %s' % pre_update_backup)
    _log.info('Restoring pre-update-backup "%s" for the update_instance %s' % (pre_update_backup, s_upd.instance))
    assert restore(s_upd.instance_dir, pre_update_backup,
                   log_file=s_upd.log_file, settings=s_upd,
                   backup_before_drop=False, start_after_restore=False
                   ), "Restore of pre-update backup %s failed!" % pre_update_backup
    _log.info('Pre-update-backup %s was restored for update_instance %s and db %s'
              '' % (pre_update_backup, s_upd.instance, s_upd.db_name))

    # Stop the update_instance service if any
    # ---------------------------------------
    if service_exists(s_upd.instance):
        service_control(s_upd.instance, 'stop')

    # Dry-Run/Test the update in the update_instance
    # ----------------------------------------------
    _log.info("Test (dry-run) the update in the update_instance!")
    python_exec = str(sys.executable)

    odoo_server = pj(s_upd.instance_core_dir, 'odoo/openerp-server')
    odoo_cwd = pj(s_upd.instance_core_dir, 'odoo')

    odoo_sargs = s_upd.startup_args[:]
    odoo_sargs = set_arg(odoo_sargs, key='-u', value=addons_string)
    odoo_sargs = set_arg(odoo_sargs, key='--stop-after-init')

    res = shell([python_exec]+[odoo_server]+odoo_sargs, cwd=odoo_cwd, user=s_upd.linux_user, timeout=timeout)
    if not s.log_file:
        _log.info('Dry-Run-Update log/result:\n\n---\n%s\n---\n' % str(res))

    # return addons_to_update
    _log.info('Dry-Run-Update was successfully!')
    return result


def _update(instance_settings_obj, target_commit='', pre_update_backup='', addons_to_update=None, addons_string='',
            timeout=60*60*4, log_file=''):
    assert instance_settings_obj, "Instance settings missing!"
    assert len(target_commit) >= 2, "Update-target-commit seems incorrect! %s" % target_commit
    s = instance_settings_obj
    _log.info('Starting update of the production instance "%s" to commit "%s" with addon-updates for %s'
              '' % (s.instance, target_commit, str(addons_to_update)))
    if addons_to_update or addons_string:
        assert os.path.isfile(pre_update_backup), "Pre-Update-Backup file is missing at %s" % pre_update_backup
        assert addons_to_update and addons_string, "addons_to_update and addons_string must be given or none of them!"

    # Check the git commits
    # ---------------------
    if s.git_commit == target_commit:
        _log.warning("INSTANCE COMMIT DID NOT CHANGE! PRODUCTION UPDATE SKIPPED!")
        return True

    # Stop the odoo instance service
    # ------------------------------
    if service_exists(s.linux_instance_service):
        service_control(s.linux_instance_service, 'stop')
        assert not service_running(s.linux_instance_service), "Could not stop the instance service!"

    # Checkout the update-target-commit
    # ---------------------------------
    try:
        git_latest(s.instance_dir, commit=target_commit, user=s.linux_user)
        assert get_sha1(s.instance_dir, raise_exception=False) == target_commit, \
            "Instance-directory-sha1 does not match update-target-commit-sha1 after checkout!"

    # Restore in case of an error
    except Exception as e:
        _log.error('Could not checkout the update-target-commit! %s' % repr(e))

        # Restore original commit if needed
        if get_sha1(s.instance_dir, raise_exception=False) != s.git_commit:
            _log.info('Try to restore pre-update instance commit %s' % s.git_commit)
            try:
                git_latest(s.instance_dir, commit=s.git_commit, user=s.linux_user)
                assert get_sha1(s.instance_dir, raise_exception=False) == s.git_commit, \
                    "Instance-commit does not match pre-update commit after restore attempt!"
            except Exception as e2:
                _log.critical('Could not restore pre-update instance commit %s' % s.git_commit)
                raise e2

        # Restart the instance service
        if service_exists(s.linux_instance_service):
            service_control(s.linux_instance_service, 'start')
            assert service_running(s.linux_instance_service), "Could not start the instance service!"

        # If the restore of the original commit worked and the service could be started we can return 'False'
        _log.error('Update of the production database failed.')
        return False

    # Skipp addons update
    # -------------------
    if not addons_to_update or not addons_string:
        _log.warning("NO ADDONS TO UPDATE! SKIPPING THE -u ODOO UPDATE!")

        # Restart the instance service
        if service_exists(s.linux_instance_service):
            service_control(s.linux_instance_service, 'start')
            assert service_running(s.linux_instance_service), "Could not start the instance service!"

        _log.info('Update done and instance running!')
        return True

    # Run the addons update
    # ---------------------
    _log.info("Run the odoo addons update!")
    python_exec = str(sys.executable)

    odoo_server = pj(s.instance_core_dir, 'odoo/openerp-server')
    odoo_cwd = pj(s.instance_core_dir, 'odoo')

    odoo_sargs = s.startup_args[:]
    odoo_sargs = set_arg(odoo_sargs, key='-u', value=addons_string)
    odoo_sargs = set_arg(odoo_sargs, key='--stop-after-init')

    try:
        res = shell([python_exec]+[odoo_server]+odoo_sargs, cwd=odoo_cwd, user=s.linux_user, timeout=timeout)
        if not s.log_file:
            _log.info('Production instance odoo addons update log/result:\n\n---\n%s\n---\n' % str(res))

    # Restore in case of an error
    except Exception as e:
        _log.error('Update of the odoo addons failed in the production instance! %s' % repr(e))
        # Restore commit and pre-update-backup
        try:
            _log.warning("Try to restore pre-update-commit and backup after failed update!")
            git_latest(s.instance_dir, commit=s.git_commit, user=s.linux_user)
            assert get_sha1(s.instance_dir, raise_exception=False) == s.git_commit, \
                "Instance-commit does not match pre-update commit after restore attempt!"
            restore(s.instance_dir, pre_update_backup, log_file=log_file, start_after_restore=True)
            assert service_running(s.linux_instance_service)
        except Exception as e2:
            _log.critical("Restoring the instance to pre-update-backup failed! %s" % repr(e))
            raise e2
        _log.error('Update of the production database failed but pre-update restore was successful.')
        return False

    return True


def update(instance_dir, cmd_args=None, log_file='', parallel_updates=2):
    _log.info('----------------------------------------')
    _log.info('UPDATE instance')
    _log.info('----------------------------------------')
    _log.info('pid: %s' % os.getpid())
    _log.info('process.name: %s' % psutil.Process(os.getpid()).name())
    linux_user = pwd.getpwuid(os.getuid())
    _log.info('user: %s' % linux_user.pw_name)
    if linux_user.pw_name != 'root':
        _log.warning('Updates should always be run as a root user or core preparations may fail!')
    
    now = datetime.datetime.now()
    datetime_fmt = '%Y-%m-%dT%H-%M-%S'
    start = now.strftime(datetime_fmt)

    # Get instance settings
    s = Settings(instance_dir, startup_args=cmd_args, log_file=log_file)

    # Send update-start email
    send_email(subject='FS-Online update for instance %s was requested at %s' % (s.instance.upper(), start))

    # Prepare update-end email message subjects
    subject_success = 'FS-Online update for instance %s is DONE! ' % s.instance.upper()
    subject_error = 'FS-Online update for instance %s has FAILED! ' % s.instance.upper()

    # Pre update checks
    try:
        _update_checks(s, parallel_updates=parallel_updates)
    except Exception as e:
        msg = "FS-Online update for instance %s failed at pre-update-checks! %s" % (s.instance.upper(), repr(e))
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
        prepare_upd = _prepare_update(instance_settings_obj=s)

        # Check the result
        assert prepare_upd['updated_to_commit'], "'updated_to_commit' is missing in answer from _prepare_update()!"

        _test_vals = ('pre_update_backup', 'addons_to_update', 'addons_string')
        if any(v for k, v in prepare_upd.iteritems() if k in _test_vals):
            assert all(v for k, v in prepare_upd.iteritems() if k in _test_vals), \
                "Return information of _prepare_update() seems incorrect: %s" % prepare_upd

    except Exception as e:
        msg = "FS-Online update for instance %s failed at pre-update-preparations! %s" % (s.instance.upper(), repr(e))
        _log.error(msg)
        send_email(subject=subject_error, body=msg)
        # Cleanup and return
        os.unlink(s.update_lock_file)
        return False

    # Update the production instance
    try:
        update_done = _update(instance_settings_obj=s,
                              target_commit=prepare_upd['updated_to_commit'],
                              pre_update_backup=prepare_upd['pre_update_backup'],
                              addons_to_update=prepare_upd['addons_to_update'],
                              addons_string=prepare_upd['addons_string'],
                              log_file=log_file)
    except Exception as e:
        msg = "FS-Online update for instance %s failed with unexpected exception!\n\n%s" % (s.instance.upper(), repr(e))
        _log.critical(msg)
        # HINT: Do !NOT! remove the update_lock_file because an unexpected exception was raised in the final update!
        send_email(subject=subject_error+' WITH UNEXPECTED EXCEPTION!!!', body=msg)
        send_email(subject=subject_error + ' WITH UNEXPECTED EXCEPTION!!!', body=msg,
                   recipient='michael.karrer@datadialog.net')
        # Cleanup and return
        os.unlink(s.update_lock_file)
        return False

    # Update done
    if update_done:
        msg = "FS-Online update for instance %s successfully DONE!" % s.instance.upper()
        _log.info(msg)
    else:
        msg = "FS-Online update for instance %s FAILED! But service seems to be restored!" % s.instance.upper()
        _log.error(msg)
    send_email(subject=subject_success if update_done else subject_error, body=msg)

    # Cleanup and return
    os.unlink(s.update_lock_file)
    return update_done
