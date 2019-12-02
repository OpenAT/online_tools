# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
import time
from time import sleep
import ConfigParser
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from tools_shell import check_disk_space, disk_usage, shell, find_file
import tools_git as git

import logging
_log = logging.getLogger()


def production_server_check(instance_dir):
    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    return os.path.exists(pj('/etc/init.d', instance))


def service_exists(service_name):
    service_file = pj('/etc/init.d', service_name)
    if os.path.exists(service_file):
        return True
    return False


def service_running(service):
    pidfile = pj('/var/run', service + '.pid')
    _log.debug("Check if service %s ist running by pidfile at %s" % (service, pidfile))
    if os.path.isfile(pidfile):
        with open(pidfile, 'r') as pidfile:
            pid = str(pidfile.readline()).rstrip('\n')
            proc_dir = pj('/proc', pid)
            _log.debug("Process ID from pidfile %s" % pid)
            _log.debug("Process directory to check for if service is running %s" % proc_dir)
            if os.path.exists(proc_dir):
                _log.debug("Service %s is running!" % service)
                return True
    _log.debug("Service %s is NOT running!" % service)
    return False


def service_control(service, state, wait=10):
    _log.info("Service %s will be %sed" % (service, state))
    # Basic Checks
    assert state in ["start", "stop", "restart", "reload"], 'service_control(service, state, wait=10) ' \
                                                            '"state" must be start, stop, restart or reload'
    assert service_exists(service), "Service %s not found at /etc/init.d/%s"
    # Service is already running and should be started
    if state == "start" and service_running(service):
        _log.warn("Nothing to do! Service %s is already running." % service)
        return True
    # Service is already stopped and should be stopped
    if state == "stop" and not service_running(service):
        _log.warn("Nothing to do! Service %s is already stopped." % service)
        return True

    # Set service state
    shell(['service', service, state])

    # Wait for service to change state
    _log.debug("Waiting %s seconds for service to change state")
    time.sleep(wait)

    # Return
    if (service in ["start", "restart", "reload"] and service_running(service)) or \
       (service == "stop" and not service_running(service)):
        _log.info("Service %s successfully changed state to %sed" % (service, state))
        return True
    else:
        _log.error('Service %s could not be %sed' % (service, state))
        return False


def inifile_to_dict(inifile, section='options'):
    _log.info("Read and parse *.ini file %s" % inifile)
    inifile = os.path.normpath(inifile)
    assert os.path.isfile(inifile), 'File %s not found!' % inifile
    cparser = ConfigParser.SafeConfigParser()
    cparser.read(inifile)
    return dict(cparser.items(section))


def prepare_repository(repo_dir='', service_name='', git_remote_url='', branch='', user=''):
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
        if service_exists(service_name):
            service_control(service_name, 'stop')

        # Checkout latest version
        git.git_latest(repo_dir, commit=branch, user=user)


# TODO: user and user right for core preparation
# TODO: Do not reset the core on development machines
def prepare_core(core_dir, tag='', git_remote_url='', user='', copy_core_dir='', production_server=True):
    _log.info("Prepare odoo core %s (tag %s)" % (core_dir, tag))
    assert core_dir, "'core_dir' missing or none"
    assert core_dir != '/', "'core_dir' can not be '/'"
    assert tag, "'tag' missing!"
    assert core_dir != copy_core_dir, "core_dir and copy_core_dir can not be the same!"

    min_core_folder_size_mb = 3000

    core_name = os.path.basename(core_dir)
    cores_base_dir = os.path.dirname(core_dir)
    core_lock_file = pj(cores_base_dir, core_name+'.lock')

    # Check concurrent odoo core update
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
    core_tag = git.get_tag(core_dir, raise_exception=False)
    if os.path.exists(core_dir) and core_tag:
        _log.info("Checkout tag %s from %s for odoo core %s as linux user %s"
                  "" % (tag, git_remote_url, core_dir, user))
        if production_server:
            try:
                git.git_latest(core_dir, commit=tag, user=user)
            except Exception as e:
                os.unlink(core_lock_file)
                _log.error('Core Checkout failed! %s' % repr(e))
                raise e
        else:
            _log.warning('Skipping core checkout and reset on development server!')

    # Clone (create) odoo core from github
    else:
        _log.info("Clone core from %s with tag %s to %s as user %s" % (git_remote_url, tag, core_dir, user))
        if production_server or not os.path.exists(core_dir):
            try:
                # Unlink the core_dir folder if any exits (maybe just a leftover)
                if os.path.exists(core_dir):
                    _log.warning("Deleting faulty core_dir at %s" % core_dir)
                    assert len(core_dir.split('/')) > 4, "Stopped for safety reasons! Not enough Subfolders!"
                    shell(['rm', '-rf', core_dir], user=user, cwd=cores_base_dir)
                # HINT: branch can also take tags and detaches the HEAD at that commit in the resulting repository
                git.git_clone(git_remote_url, branch=tag, target_dir=core_dir, cwd=os.path.dirname(core_dir), user=user)
            except Exception as e:
                os.unlink(core_lock_file)
                _log.error("Could not clone core! %s" % repr(e))
                raise e
        else:
            _log.warning('Skipping core-cloning on development server!')

    # Core preparation successfully done
    os.unlink(core_lock_file)
    _log.info("Core %s was successfully prepared!" % core_dir)
    return True


def send_email(subject='', body='', sender='admin@datadialog.net', recipient='admin@datadialog.net',
               smtp_server='192.168.37.1', smtp_port='25', raise_exception=False, timeout=5):
    body = subject if not body else body
    _log.info('Send email to "%s" with subject: "%s"' % (recipient, subject))

    # prepare email message
    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = recipient
        body = msg['Subject']
        msg.attach(MIMEText(body, 'plain'))
    except Exception as e:
        _log.warning("Could not prepare email! %s" % repr(e))
        if raise_exception:
            raise e
        else:
            return False

    # send email
    server = None
    try:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=timeout)
        server.sendmail(sender, recipient, msg.as_string())
    except Exception as e:
        _log.warning("Could not send email! %s" % repr(e))
        if raise_exception:
            raise e
    finally:
        try:
            if server:
                server.quit()
        except Exception as e:
            _log.error("Could not quit smpt server session! %s" % repr(e))


def find_addons_to_update(instance_settings, update_instance_settings,
                          watched_extensions=('.py', '.xml', '.po', '.pot', '.csv')):
    s = instance_settings
    s_upd = update_instance_settings
    _log.info("Find addons with changes between %s and %s" % (s.instance_dir, s_upd.instance_dir))

    # All changed files
    core_changed_files = git.git_diff(s_upd.instance_core_dir, s.core_commit, s_upd.core_commit)
    inst_changed_files = git.git_diff(s_upd.instance_dir, s.git_commit, s_upd.git_commit)
    changed_files = core_changed_files+inst_changed_files
    _log.info("Found %s changed file(s)!" % len(changed_files))

    # Watched files
    watched_files = list()
    for cf in changed_files:
        cf_abs = os.path.abspath(cf)
        if os.path.splitext(cf_abs)[1].lower() in watched_extensions:
            if os.path.islink(cf_abs):
                watched_files.append(os.path.realpath(cf_abs))
            elif os.path.isfile(cf_abs):
                watched_files.append(cf_abs)
    _log.info("Found %s watched file(s)!" % len(watched_files))
    _log.info("Watched files: %s" % str(watched_files))

    # Addons with changes
    addons_to_update = list()
    remaining = set(watched_files)
    for addon_dir in s_upd.all_addon_directories:
        changes = [f for f in remaining if f.startswith(addon_dir)]
        if changes:
            _log.info("Addon at %s has changed files %s" % (addon_dir, changes))
            addons_to_update.append(os.path.basename(addon_dir))
            remaining = remaining - set(changes)

    _log.info("Addon(s) to update: %s" % str(addons_to_update))
    return addons_to_update
