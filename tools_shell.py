# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
import sys
import pwd
import subprocess32
import time
from functools import wraps

import zipfile
modes = {zipfile.ZIP_DEFLATED: 'deflated',
         zipfile.ZIP_STORED: 'stored',
         }
try:
    import zlib
    # Hack to force zipfile compression level
    zlib.Z_DEFAULT_COMPRESSION = 1
    compression = zipfile.ZIP_DEFLATED
except:
    compression = zipfile.ZIP_STORED
# TEST FOR SPEED
# compression = zipfile.ZIP_STORED

import logging
_log = logging.getLogger()

try:
    import scandir
except:
    _log.warning("python lib 'scandir' could not be imported!")


def retry(exception_to_check, tries=4, delay=3, backoff=2, logger=None):
    """Retry calling the decorated function using an exponential backoff.

    http://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param exception_to_check: the exception to check. may be a tuple of
        exceptions to check
    :type exception_to_check: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay: initial delay between retries in seconds
    :type delay: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
        each retry
    :type backoff: int
    :param logger: logger to use. If None, print
    :type logger: logging.Logger instance
    """

    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except exception_to_check, e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    if logger:
                        logger.warning(msg)
                    else:
                        print msg
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry


# Returns a function! Helper function for function "shell()" to switch the user before shell command is executed
def _switch_user_function(user_uid, user_gid):
    _log.debug('Change user to uid %s with gid %s' % (user_uid, user_gid))

    def inner():
        os.setregid(user_gid, user_gid)
        os.setreuid(user_uid, user_uid)

    return inner


# Linux-Shell wrapper
def shell(cmd=list(), user=None, cwd=None, env=None, preexec_fn=None, log=True, **kwargs):
    if log:
        _log.debug("Run shell command: %s" % cmd)
    assert isinstance(cmd, (list, tuple)), 'shell(cmd): cmd must be of type list or tuple!'

    # Working directory
    cwd = cwd or os.getcwd()

    # Linux User Object
    linux_user_obj = pwd.getpwuid(os.getuid())

    # If user is set switch the user and os environment by
    if user:
        # Get linux user details from unix user account and password database
        # HINT: In case the user can not be found pwd will throw an KeyError exception.
        linux_user_obj = pwd.getpwnam(user)

        # Create a new os environment
        env = os.environ.copy()

        # Set environment variables
        env['USER'] = user
        env['LOGNAME'] = linux_user_obj.pw_name
        env['HOME'] = linux_user_obj.pw_dir

        # Create a new function that will be called by subprocess32 before the shell command is executed
        preexec_fn = _switch_user_function(linux_user_obj.pw_uid, linux_user_obj.pw_gid)

    # Log user Current-Working-Directory and shell command to be executed
    if log:
        _log.info('[%s@%s]$ %s' % (linux_user_obj.pw_name, cwd, ' '.join(cmd)))

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
            _log.warning(std_err.rstrip('\n'))
        raise e
    except Exception as e:
        _log.error('Shell subprocess32 exception! %s' % repr(e))
        raise e


def disk_usage(folder):
    """

    :param folder: (str) path to folder
    :return: (int) Disk-Size of folder (recursively) in MB
    """
    folder = os.path.abspath(folder)
    _log.info("Check disk usage of folder at %s" % folder)
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
        _log.info("Check if %sMB disk space is left at %s" % (min_free_mb, folder))
    else:
        _log.info("Compute free disk space in MB for folder %s" % folder)
    assert os.path.isdir(folder), "Directory not found: %s" % folder

    statvfs = os.statvfs(folder)
    free_bytes = statvfs.f_frsize * statvfs.f_bavail
    free_mb = free_bytes / 1000000
    _log.info("%sMB free disk space at %s" % (free_mb, folder))

    result = free_mb >= min_free_mb if min_free_mb else free_mb
    return result


def test_zip(zip_file):
    zip_file = os.path.abspath(zip_file)
    _log.info("Verify zip archive at %s" % zip_file)
    assert os.path.isfile(zip_file), "File not found at %s" % zip_file
    try:
        zip_to_check = zipfile.ZipFile(zip_file)
        failed = zip_to_check.testzip()
        assert failed is None, "Damaged files in zip archive found! %s" % failed
    except Exception as e:
        _log.error("Zip archive damaged! %s" % repr(e))
        raise e


def make_zip_archive(output_filename=None, source_dir=None, verify_archive=False, prefix_source_folder=False):
    """
    Will create a zip archive with relative file paths
    :param output_filename: Path and name of the zip archive file to create
    :param source_dir: Folder that should be zipped
    :return:
    """
    if prefix_source_folder:
        # HINT: os.pardir = '..' so this is like 'cd..'
        relroot = os.path.abspath(os.path.join(source_dir, os.pardir))
    else:
        relroot = os.path.abspath(source_dir)

    # Open the zip archive
    with zipfile.ZipFile(output_filename, "w", compression, allowZip64=True) as archive_file:

        # Walk through all the files and folders
        for root, dirs, files in os.walk(source_dir):
            relpath = os.path.relpath(root, relroot)
            relpath = '' if relpath == '.' else relpath

            # Add directory (needed for empty dirs)
            archive_file.write(root, relpath)

            # Add regular files
            for f in files:
                filename = os.path.join(root, f)
                if os.path.isfile(filename):
                    archive_name = os.path.join(relpath, f)
                    archive_file.write(filename, archive_name)

    # Test the zip archive
    if verify_archive:
        test_zip(output_filename)


def find_file(file_name, start_dir='/', max_finds=0, exclude_folders=tuple(), walk_method=None, topdown=True):
    start = time.time()
    exclude_folders = list(set(exclude_folders))

    _log.info("Search recursively for file '%s' in directory '%s' for %s occurrences with excluded directories %s!"
              "" % (file_name, start_dir,
                    max_finds if max_finds else 'unlimited',
                    str(exclude_folders) if exclude_folders else 'no'))

    # Select walk method
    if not walk_method:
        try:
            walk_method = scandir.walk
        except:
            walk_method = os.walk

    res = []
    for root_folder, sub_folders, files in walk_method(start_dir, topdown=topdown):

        # Exclude unwanted folders
        if exclude_folders:
            sub_folders_start = sub_folders[:]
            # Modify sub_folders in-place
            # HINT: Modifying sub_folders in-place will prune the (subsequent) files and directories visited by os.walk
            sub_folders[:] = [d for d in sub_folders if d not in exclude_folders]
            sub_folders_removed = [r for r in sub_folders_start if r not in sub_folders]
            if sub_folders_removed:
                _log.debug("Subfolder(s) %s removed!" % str(sub_folders_removed))

        # Search for the file
        if file_name in files:
            res.append(pj(root_folder, file_name))

        # Stop the for loop if file was found 'max_finds' times
        if 0 < max_finds <= len(res):
            _log.info("File %s found %s times! Stopping the search!" % (file_name, len(res)))
            break

    _log.info("File %s was %sfound at %s in %s seconds with method '%s'"
              "" % (file_name,
                    str(len(res))+' times ' if res else 'NOT ',
                    start_dir,
                    time.time() - start,
                    walk_method.__name__))

    return res


# Yeuk Hon Wong
# https://gist.github.com/amitsaha/5990310
def tail(filename, n):
    stat = os.stat(filename)
    if stat.st_size == 0 or n == 0:
        yield ''
        return

    page_size = 5
    offsets = []
    count = _n = n if n >= 0 else -n

    last_byte_read = last_nl_byte = starting_offset = stat.st_size - 1

    with open(filename, 'r') as f:
        while count > 0:
            starting_byte = last_byte_read - page_size
            if last_byte_read == 0:
                offsets.append(0)
                break
            elif starting_byte < 0:
                f.seek(0)
                text = f.read(last_byte_read)
            else:
                f.seek(starting_byte)
                text = f.read(page_size)

            for i in range(-1, -1*len(text)-1, -1):
                last_byte_read -= 1
                if text[i] == '\n':
                    last_nl_byte = last_byte_read
                    starting_offset = last_nl_byte + 1
                    offsets.append(starting_offset)
            count -= 1

    offsets = offsets[len(offsets)-_n:]
    offsets.reverse()

    with open(filename, 'r') as f:
        for i, offset in enumerate(offsets):
            f.seek(offset)

            if i == len(offsets) - 1:
                yield f.read()
            else:
                bytes_to_read = offsets[i+1] - offset
                yield f.read(bytes_to_read)


def tail_no_exception(filename, n):
    try:
        res = tail(filename, n)
        return res
    except Exception as e:
        _log.warning('tail() failed: %s' % repr(e))
        return None

