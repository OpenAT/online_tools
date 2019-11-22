# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj

from tools_shell import shell
from tools import retry

import logging
_log = logging.getLogger()


def get_sha1(path):
    _log.info("Get SHA1 of git repo at %s" % path)
    assert os.path.isdir(path), "Repository path not found at %s" % path

    # sha1 = shell(['git', 'rev-parse', 'HEAD'], cwd=path)
    sha1 = shell(['git', 'log', '-1', '--pretty="%H"'], cwd=path)
    sha1 = sha1.strip().replace('"', '').replace("'", "")

    assert len(sha1) == 40, 'Wrong or missing SHA1 (%s) for git repo at %s!' % (sha1, path)
    return sha1


def get_submodule_sha1(path, submodule=str()):
    _log.info("Get SHA1 of submodule %s at %s" % (submodule, path))
    assert os.path.isdir(path), "Repository path not found at %s" % path

    # HINT: Full submodule path needed!
    #       e.g.: 'fundraising_studio/online' for 'dadi/fundraising_studio/online'
    #       This allows that submodules of submodules will not get found if they have the same name!

    # Use git to get the list of submodules and their current commits SHA1
    submodules = shell(['git', 'submodule', 'status', '--recursive'], cwd=path)
    assert submodules, 'No submodules found in %s! Did you run "git submodule init"?' % path

    # Create a dict out of the git output
    # e.g.: {'fundraising_studio/online': '-88b145319056b9d6feac9c86458371cd12a3960c'}
    # Example git-output line: "-88b145319056b9d6feac9c86458371cd12a3960c fundraising_studio/online "
    # HINT: [-40:] means use first 40 characters from right to left in the string (= removing the - if it exists)
    submodules = {line.split()[1].strip(): line.split()[0].strip()[-40:] for line in submodules.splitlines()}

    # Get SHA1 for submodule and check that it is 40 characters long!
    sha1 = submodules[submodule]
    sha1 = sha1.strip()
    assert len(sha1) == 40, 'Wrong or missing SHA1 (%s) for submodule %s in %s!' % (sha1, submodule, path)
    return sha1


def get_tag(path, match='o8r*', raise_exception=True):
    _log.info("Get 'tag' from git repo at %s" % path)
    try:
        assert os.path.isdir(path), "Repository path not found at %s" % path

        # HINT: -C and cwd=path are redundant (one would be enough) but kept here for reference
        # HINT: Will only return a tag if the current commit matches (a) tag(s) exactly (may return multiple tags!)
        cmd = ['git', '-C', path, 'describe', '--tags', '--exact-match']
        if match:
            cmd.append('--match='+match)
        tag = shell(cmd, cwd=path)
    except Exception as e:
        _log.error('Could not get tag! %s' % repr(e))
        if raise_exception:
            raise e
        else:
            return False

    return tag


def get_current_branch(path):
    _log.info('Get current branch from git repot at %s' % path)
    # HINT: 'git branch' would be to cumbersome because it may list all branches and mark the current one with *
    branch = shell(['git', '-C', path, 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=path)
    branch = branch.strip('\n')
    return branch


def get_remote_url(path):
    _log.info('Get remote url from git repot at %s' % path)
    remote_url = shell(['git', '-C', path, 'config', '--get', 'remote.origin.url'], cwd=path)
    remote_url = remote_url.strip('\n')
    return remote_url


@retry(Exception, tries=3)
def git_submodule(path, user=None, timeout=60*60*2):
    _log.info("Git: Recursively init and update all submodules in directory %s as user %s" % (path, user))
    assert os.path.exists(path), 'Directory %s not found!' % path

    try:
        _log.debug("Sync submodules from .gitmodules to .git/config")
        shell(['git', 'submodule', 'sync'], cwd=path, timeout=60*5, user=user)

        _log.debug("Update and init submodules recursively")
        shell(['git', 'submodule', 'update', '--init', '--recursive'], cwd=path, timeout=timeout, user=user)

    except Exception as e:
        _log.error('Git submodule update for directory %s failed! %s' % (path, repr(e)))
        raise e

    return True


@retry(Exception, tries=3)
def git_clone(repo_remote_url, branch='o8', target_dir='', cwd='', user=None, timeout=60*60*2):
    # HINT: Target dir must either not exist or must be an empty directory.
    #       Will be used instead of the repository name!
    _log.info('Git: Clone repository %s to %s' % (repo_remote_url, target_dir))

    try:
        # Clone the repository
        # HINT: -b can also take tags and detaches the HEAD at that commit in the resulting repository
        shell(['git', 'clone', '-b', branch, repo_remote_url, target_dir],
              cwd=cwd, timeout=timeout, user=user)

        # Initialize and update all submodules
        git_submodule(target_dir, user=user)

    except Exception as e:
        _log.error('Git: Clone failed! %s' % repr(e))
        raise e

    return True


@retry(Exception, tries=3)
def git_checkout(path, commit='o8', user=None, timeout=60*90):
    _log.info("Git: Checkout commit or branch %s for git repository in %s." % (commit, path))
    assert os.path.exists(path), 'Path not found: %s' % path

    try:
        _log.debug('Fetch data from remote url before checkout')
        shell(['git', 'fetch'], cwd=path, timeout=60*5, user=user)
        shell(['git', 'fetch', '--tags'], cwd=path, timeout=60*5, user=user)

    except Exception as e:
        _log.error('Fetch data from remote url before checkout failed! %s' % repr(e))
        raise e

    try:
        shell(['git', 'checkout', commit], cwd=path, timeout=timeout, user=user)
        git_submodule(path, user=user)

    except Exception as e:
        _log.error('CRITICAL: Git checkout failed! %s' % repr(e))
        raise e

    return True


@retry(Exception, tries=3)
def git_reset(path, user=None):
    _log.info("Git: Reset repo and submodules at %s" % path)
    assert os.path.exists(path), 'Path not found: %s' % path

    # Default timeout for shell commands
    _timeout = 60*5

    try:
        # Fetch latest data and tags
        shell(['git', 'fetch', '--tags'], cwd=path, timeout=_timeout, user=user)

        # Force clean the repository
        shell(['git', 'clean', '-fdf'], cwd=path, timeout=_timeout, user=user)

        # Force clean the submodules
        shell(['git', 'submodule', 'foreach', '--recursive', 'git', 'clean', '-fdf'],
              cwd=path, timeout=_timeout, user=user)

        # Hard reset the repository
        shell(['git', 'reset', '--hard'], cwd=path, timeout=_timeout, user=user)

        # Sync the submodules from .gitmodules to .git/config
        shell(['git', 'submodule', 'sync'], cwd=path, timeout=_timeout, user=user)

        # Hard reset the submodules recursively
        shell(['git', 'submodule', 'foreach', '--recursive', 'git', 'reset', '--hard'],
              cwd=path, timeout=_timeout, user=user)

        # Update the submodules recursively
        shell(['git', 'submodule', 'update', '--init', '--recursive'],
              cwd=path, timeout=_timeout, user=user)

        # Force update the submodules recursively
        shell(['git', 'submodule', 'update', '-f'],
              cwd=path, timeout=_timeout, user=user)

    except Exception as e:
        _log.error('Cleanup of repository failed! %s' % repr(e))
        raise e


@retry(Exception, tries=3)
def git_latest(path, commit='o8', user=None, pull=False):
    _log.info("Git: Update repo %s to commit or branch %s" % (path, commit))
    assert os.path.exists(path), 'Path not found: %s' % path

    # Default timeout
    _timeout = 60*5

    # Reset the repository
    _log.info('Cleanup and reset the repository at %s' % path)
    git_reset(path, user=user)

    # Checkout the branch/commit
    _log.info("Checkout commit or branch %s for repository %s" % (commit, path))
    try:
        git_checkout(path, commit=commit, user=user)
    except Exception as e:
        _log.error('Git checkout failed! %s' % repr(e))
        raise e

    # Do an extra pull (should not be necessary?!?)
    if pull:
        try:
            shell(['git', 'pull'], cwd=path, timeout=_timeout, user=user)
        except Exception as e:
            _log.error('Git pull failed! %s' % repr(e))
            raise e

    return True

