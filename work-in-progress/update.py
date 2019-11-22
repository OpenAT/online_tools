# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
from time import sleep
import datetime

from tools_settings import Settings
import tools
import tools_git as git
from tools_shell import find_file, check_disk_space, disk_usage, shell

import logging
_log = logging.getLogger()


def _update_checks(settings, parallel=2):
    _log.info('Run update checks')

    # Check 'no_update' in status.ini
    if settings.no_update:
        _log.error("'no_update' is True in status.ini at %s" % settings.status_ini_file)
        return False

    # Check 'update_failed'
    if settings.update_failed:
        _log.error("'update_failed' is True in status.ini at %s" % settings.status_ini_file)
        return False

    # Check for a concurrent update for this instance
    concurrent_lock_counter = 60*12
    while os.path.exists(settings.update_lock_file) and concurrent_lock_counter > 0:
        _log.warning('Concurrent update for this instance running! Wait for %s minutes.' % concurrent_lock_counter)
        sleep(60)
        concurrent_lock_counter -= 1
        if concurrent_lock_counter <= 0:
            _log.error('Concurrent update check timed out!')
            return False

    # Check parallel updates on this server (max 2)
    parallel_lock_counter = 60*12
    while len(find_file(settings.update_lock_file_name,
                        start_dir=os.path.dirname(settings.instance_dir),
                        max_finds=parallel,
                        exclude_folders=['cores'])) >= parallel and parallel_lock_counter > 0:
        _log.warning('At least %s parallel updates are running on this server! Wait for %s minutes.'
                     '' % (parallel, parallel_lock_counter))
        sleep(60)
        parallel_lock_counter -= 1
        if parallel_lock_counter <= 0:
            _log.error('Parallel update check timed out!')
            return False

    # This is mandatory (python will NOT return True by default but just return)
    return True


def _prepare_repository(repo_dir='', service_name='', git_remote_url='', branch='', user=''):
    # Clone (create) repository
    if not os.path.exists(repo_dir):
        _log.info("Clone instance github repository %s with branch %s to %s as user %s"
                  "" % (git_remote_url, branch, repo_dir, user))
        git.git_clone(git_remote_url, branch=branch, target_dir=repo_dir,
                      cwd=os.path.dirname(repo_dir), user=user)

    # Update existing repository
    else:
        _log.info("Checkout latest commit of github repository %s for branch %s"
                  "" % (repo_dir, branch))

        # Stop the update instance service if running
        if tools.service_exists(service_name):
            tools.service_control(service_name, 'stop')

        # Checkout latest version
        git.git_latest(repo_dir, commit=branch, user=user)


# TODO: Correct user for cores
def prepare_core(core_dir, tag='', git_remote_url='', user='', copy_core_dir=''):
    _log.info("Prepare odoo core %s (tag %s)" % (core_dir, tag))
    assert core_dir, "'core_dir' missing or none"
    assert core_dir != '/', "'core_dir' can not be '/'"
    assert tag, "'tag' missing!"
    assert core_dir != copy_core_dir, "core_dir and copy_core_dir can not be the same!"

    min_core_folder_size_mb = 3000

    # Check concurrent odoo core update
    core_name = os.path.basename(core_dir)
    cores_base_dir = os.path.dirname(core_dir)
    core_lock_file = pj(cores_base_dir, core_name+'.lock')
    _log.info('Check for core lock file at %s' % core_lock_file)
    concurrent_lock_counter = 60*12
    while os.path.exists(core_lock_file) and concurrent_lock_counter > 0:
        _log.warning('Concurrent update for odoo core running! Wait for %s minutes.' % concurrent_lock_counter)
        sleep(60)
        concurrent_lock_counter -= 1
        if concurrent_lock_counter <= 0:
            _log.error('Concurrent update check timed out!')
            raise

    # Check if we may skipp the core update
    if os.path.exists(core_dir):
        _log.info('Check if we can skipp the core preparation')
        core_dir_tag = git.get_tag(core_dir, raise_exception=False)
        if tag == core_dir_tag and disk_usage(core_dir) > min_core_folder_size_mb:
            _log.info("Skipping core preparation! Tags %s match and folder size is above %sMb"
                      "" % (tag, min_core_folder_size_mb))
            return True

    # Check the free disk space
    _log.info("Check free disk space for core preparation")
    if not check_disk_space(os.path.dirname(core_dir), min_free_mb=10000):
        _log.error('Not enough free disk space!')
        raise

    # Create core update lock file in the cores base dir
    _log.info("Creating core-update-lock-file at %s!" % core_lock_file)
    with open(core_lock_file, 'a+') as core_lock_file_handle:
        core_lock_file_handle.write('core update to tag %s' % tag)

    # Copy existing core for speed optimization
    if os.path.exists(copy_core_dir) and not os.path.exists(core_dir):
        _log.info('Copy existing core %s to %s (performance optimization)' % (copy_core_dir, core_dir))
        try:
            _log.info('Clean core-to-copy at %s' % copy_core_dir)
            git.git_reset(copy_core_dir, user=user)
            _log.info('Copy core')
            # HINT: "/." is necessary to copy also all hidden files
            # HINT: abspath would remove a trailing '/' from the path if any
            shell(['cp', '-rpf', os.path.abspath(copy_core_dir)+'/.', core_dir])
        except Exception as e:
            os.unlink(core_lock_file)
            _log.warning('Copy of existing core failed! %s' % repr(e))
            raise e

    # Update existing odoo core
    if os.path.exists(core_dir) and git.get_tag(core_dir, raise_exception=False):
        _log.info("Checkout tag %s from %s for odoo core %s as linux user %s"
                  "" % (tag, git_remote_url, core_dir, user))
        try:
            git.git_latest(core_dir, commit=tag, user=user)
        except Exception as e:
            os.unlink(core_lock_file)
            _log.error('Core Checkout failed! %s' % repr(e))
            raise e

    # Clone (create) odoo core from github
    else:
        _log.info("Clone core from %s with tag %s to %s as user %s"
                  "" % (git_remote_url, tag, core_dir, user))
        try:
            # Unlink the core_dir folder if any exits (maybe just a leftover)
            if os.path.exists(core_dir):
                _log.warning("Deleting faulty core_dir at %s" % core_dir)
                assert len(core_dir.split('/') > 4), "Stopped for safety reasons! Not enough Subfolders!"
                shell(['rm', '-rf', core_dir], user=user, cwd=cores_base_dir)
            # HINT: branch can also take tags and detaches the HEAD at that commit in the resulting repository
            git.git_clone(git_remote_url, branch=tag, target_dir=core_dir, cwd=os.path.dirname(core_dir), user=user)
        except Exception as e:
            os.unlink(core_lock_file)
            _log.error("Could not clone core! %s" % repr(e))
            raise e

    _log.info("Core %s was successfully prepared!" % core_dir)
    return True


def update(instance_dir, cmd_args=None, log_file='', parallel=2):
    logging.info('----------------------------------------')
    logging.info('UPDATE instance')
    logging.info('----------------------------------------')
    
    start = datetime.datetime.now()
    datetime_fmt = '%Y-%m-%dT%H-%M-%S'

    # TODO: Send Info E-Mail - maybe this is done in fs-online.py only? OR i rename this function to '_update' and do
    #       another 'update' function that sends e-mails and captures exceptions and writes the status.ini!!!

    # Get instance settings
    s = Settings(instance_dir, startup_args=cmd_args, log_file=log_file)

    # Pre update checks
    if not _update_checks(s, parallel=parallel):
        _log.error('Update check failed!')
        return False
    
    # START THE UPDATE
    # ----------------
    # Create an update lock file
    _log.info("Creating update.lock file at %s!" % s.update_lock_file)
    with open(s.update_lock_file, 'a+') as update_lock_file:
        update_lock_file.write('%s update start at %s' % (s.instance, start.strftime(datetime_fmt)))
    
    # Prepare the update_instance repository directory
    # ------------------------------------------------
    update_instance = s.instance+"_update"
    update_instance_dir = pj(instance_dir, 'update', update_instance)
    _log.info("Prepare the update_instance repository at directory: %s" % update_instance_dir)
    _prepare_repository(repo_dir=update_instance_dir, service_name=update_instance,
                        git_remote_url=s.git_remote_url, branch=s.git_branch, user=s.linux_user)

    # Get update_instance settings
    # ----------------------------
    s_upd = Settings(update_instance_dir, startup_args=cmd_args, log_file=log_file, update_instance_mode=True)
    assert s.instance != s_upd.instance, "Instance '%s' and update_instance '%s' can not be the same!" % (
        s.instance, s_upd.instance)

    # Prepare the update_instance odoo core
    # -------------------------------------
    prepare_core(s_upd.instance_core_dir, tag=s_upd.instance_core_tag, git_remote_url=s_upd.core_remote_url,
                 user=s_upd.linux_user, copy_core_dir=s.instance_core_dir)

    # Update the update_instance settings (since the core exists now)

    # Backup and restore to the update_instance the

    # Compare the commit id of the update_instance and the instance (stop if equal)

    # Prepare the odoo core based on the instance.ini of the update_instance

    # Search for addons to update
    # ---------------------------
    # Search for changed core addons
    # Search for changed instance addons
    # use -u all if more than 6 addons have changed (maybe we need a way to force -u all )
    # Stop here if no addons to update are found
    # Search for changed core translations
    # Search for changed instance translations

    # Dry-Run/Test the update in the update_instance
    # ----------------------------------------------
    # Backup the instance
    # Restore the backup to the dry-run update_instance
    # Test-Run the addon updates
    # Test-Run the language updates

    # Update the production instance
    # ------------------------------
    # Stop the service
    # Run the update
    # Restore pre update backup if the update fails
    # Send message to sysadmin

    return True
