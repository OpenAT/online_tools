# -*- coding: utf-'8' "-*-"

import logging
import os
import pwd
import subprocess32
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
def shell(cmd=list(), user=None, cwd=None, env=None, preexec_fn=None, **kwargs):
    log.info("Run shell command: %s" % cmd)
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
    log.info('[%s %s]$ %s' % (linux_user.pw_name, cwd, ' '.join(cmd)))

    # Execute shell command and return its output
    return subprocess32.check_output(cmd, cwd=cwd, env=env, preexec_fn=preexec_fn, **kwargs)
