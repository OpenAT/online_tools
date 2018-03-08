# -*- coding: utf-'8' "-*-"
import os
import sys
import pwd
import subprocess32
import zipfile

import logging
log = logging.getLogger()


# Returns a function! Helper function for function "shell()" to switch the user before shell command is executed
def _switch_user_function(user_uid, user_gid):
    def inner():
        log.debug('Switch user from %s:%s to %s:%s.' % (os.getuid(), os.getgid(), user_uid, user_gid))
        # HINT: Will throw an exception if user or group can not be switched
        os.setresgid(user_gid, user_gid, user_gid)
        os.setresuid(user_uid, user_gid, user_gid)
    return inner


# Linux-Shell wrapper
def shell(cmd=list(), user=None, cwd=None, env=None, preexec_fn=None, log_info=True, **kwargs):
    log.debug("Run shell command: %s" % cmd)
    assert isinstance(cmd, (list, tuple)), 'shell(cmd): cmd must be of type list or tuple!'

    # Working directory
    cwd = cwd or os.getcwd()

    # Linux User
    linux_user = pwd.getpwuid(os.getuid())

    # Switch user and environment if given
    if user:
        # Get linux user details from unix user account and password database
        # HINT: In case the user can not be found pwd will throw an KeyError exception.
        linux_user = pwd.getpwnam(user)

        # Create a new os environment
        env = os.environ.copy()

        # Set environment variables
        env['USER'] = user
        env['LOGNAME'] = linux_user.pw_name
        env['HOME'] = linux_user.pw_dir

        # Create a new function that will be called by subprocess32 before the shell command is executed
        preexec_fn = _switch_user_function(linux_user.pw_uid, linux_user.pw_gid)

    # Log user Current-Working-Directory and shell command to be executed
    if log_info:
        log.info('[%s %s]$ %s' % (linux_user.pw_name, cwd, ' '.join(cmd)))

    # Execute shell command and return its output
    # HINT: this was the original solution but this will not log errors but send it to sys.stderr
    #return subprocess32.check_output(cmd, cwd=cwd, env=env, preexec_fn=preexec_fn, **kwargs)

    # Log Error output also
    # https://stackoverflow.com/questions/16198546/get-exit-code-and-stderr-from-subprocess-call
    try:
        result = subprocess32.check_output(cmd, cwd=cwd, env=env, preexec_fn=preexec_fn,
                                           stderr=subprocess32.STDOUT, **kwargs)
        return result
    except subprocess32.CalledProcessError as e:
        std_err = '{}'.format(e.output.decode(sys.getfilesystemencoding()))
        if std_err:
            log.warning(std_err.rstrip('\n'))
        raise e


def disk_usage(folder):
    """

    :param folder: (str) path to folder
    :return: (int) Disk-Size of folder (recursively) in MB
    """
    folder = os.path.abspath(folder)
    log.info("Check disk usage of folder at %s" % folder)
    assert os.path.isdir(folder), "Directory not found: %s" % folder

    size = shell(['du', '-sm', folder])
    size = int(size.split()[0])

    return size


def check_disk_space(folder, min_free_mb=0):
    """

    :param folder: (str) path to folder to check free disk space in
    :param min_free_mb: (int) minimum free disk space at folder to return True
    :return: (boolean) if min_free_mb is set or (int) free disk space in MB
    """
    folder = os.path.abspath(folder)
    if min_free_mb:
        log.info("Check if %sMB disk space is left at %s" % (min_free_mb, folder))
    else:
        log.info("Compute free disk space in MB for folder %s" % folder)
    assert os.path.isdir(folder), "Directory not found: %s" % folder

    statvfs = os.statvfs(folder)
    free_bytes = statvfs.f_frsize * statvfs.f_bavail
    free_mb = free_bytes / 1000000
    log.info("%sMB free disk space at %s" % (free_mb, folder))

    result = free_mb >= min_free_mb if min_free_mb else free_mb
    return result


def test_zip(zip_file):
    zip_file = os.path.abspath(zip_file)
    log.info("Verify zip archive at %s" % zip_file)
    assert os.path.isfile(zip_file), "File not found at %s" % zip_file
    try:
        zip_to_check = zipfile.ZipFile(zip_file)
        failed = zip_to_check.testzip()
        assert failed is None, "Damaged files in zip archive found! %s" % failed
    except Exception as e:
        log.error("Zip archive damaged! %s" % repr(e))
        raise e
