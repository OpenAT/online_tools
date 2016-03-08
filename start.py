#!/usr/bin/env python

# TODO: Make sure every commit betwenn latest commit and current commit is used for update since we have to make
#       every intermediate update also!
# HINT: Should be no real problem now since every push triggers an update

import sys
import os
from os.path import join as pj
import ConfigParser
import time
import shutil
import subprocess32
from collections import OrderedDict
import pwd
from time import sleep
import urllib2
import difflib
from functools import wraps


def retry(ExceptionToCheck, tries=4, delay=3, backoff=2, logger=None):
    """Retry calling the decorated function using an exponential backoff.

    http://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param ExceptionToCheck: the exception to check. may be a tuple of
        exceptions to check
    :type ExceptionToCheck: Exception or tuple
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
                except ExceptionToCheck, e:
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


def pp(e):
    output = '\n\n'+str(e)+'\n'
    if hasattr(e, 'output'):
        output += str(e.output)+'\n'
    # print output
    return output


def _change_user(user_uid, user_gid):
    def inner():
        try:
            print "Before shell command user_id %s group_id %s" % (os.getuid(), os.getgid())
            # os.setegid(user_gid)
            # os.seteuid(user_uid)
            os.setresgid(user_gid, user_gid, user_gid)
            os.setresuid(user_uid, user_gid, user_gid)
            print "Changed to user_id %s group_id %s" % (os.getuid(), os.getgid())
        except Exception as e:
            print 'WARNING: Could not change user_id and group_id!%s' % pp(e)
            return True
    # ATTENTION: not inner() because we want to return the function and not the result!
    return inner


def shell(*args, **kwargs):
    # Remove None of False user names
    if not kwargs.get('user_name', True):
        kwargs.pop('user_name')

    # give the possibility to run shell as a different user
    if 'user_name' in kwargs:
        try:
            user = pwd.getpwnam(kwargs.get('user_name'))
            env = os.environ.copy()
            env.update({
                'HOME': user.pw_dir,
                'LOGNAME': user.pw_name,
                'USER': kwargs.get('user_name'),
            })
            kwargs.update({
                'preexec_fn': _change_user(user.pw_uid, user.pw_gid),
                'env': env,
                # 'shell': True,
            })
            kwargs.pop('user_name')
            print "Shell user name: %s pid: %s gid: %s" % (user.pw_name, user.pw_uid, user.pw_gid)
            # print "ENV: %s" % env
        except Exception as e:
            print "WARNING: User %s not found on this machine! " \
                  "Will run as %s.\n%s\n" % (kwargs.get('user_name'), pwd.getpwuid(os.getuid())[0], pp(e))
            kwargs.pop('user_name')
        print "Shell Command: %s" % args[0]
        print "Shell CWD: %s" % kwargs.get('cwd', os.getcwd())
    return subprocess32.check_output(*args, **kwargs)


@retry(Exception, tries=3)
def _git_get_hash(path):
    print "\nGit get commit id %s." % path
    assert os.path.exists(path), 'CRITICAL: Path not found: %s' % path
    try:
        hashid = shell(['git', 'log', '-n', '1', '--pretty=format:%H'], cwd=path)
        return hashid
    except Exception as e:
        raise Exception('CRITICAL: Get commit-hash failed!%s' % pp(e))


@retry(Exception, tries=3)
def _git_submodule(path, user_name=None):
    print "Git update submodule --init --recursive in %s." % path
    assert os.path.exists(path), 'CRITICAL: Path not found: %s' % path
    try:
        shell(['git', 'submodule', 'update', '--init', '--recursive'], cwd=path, timeout=1200,
              user_name=user_name)
    except Exception as e:
        raise Exception('CRITICAL: Git submodule update %s failed!%s' % (path, pp(e)))
    return True


@retry(Exception, tries=3)
def _git_clone(repo, branch='o8', cwd='', target='', user_name=None):
    cwd = cwd or os.getcwd()
    target = target or repo.rsplit('/', 1)[-1].replace('.git', '', 1)
    target_dir = pj(cwd, target)
    print "Git clone %s to %s." % (repo, target_dir)
    assert not os.path.exists(target_dir), 'CRITICAL: Target path exists: %s' % target_dir
    devnull = open(os.devnull, 'w')
    try:
        shell(['git', 'clone', '-b', branch, repo, target], cwd=cwd, timeout=600, user_name=user_name)
        _git_submodule(target_dir, user_name=user_name)
    except Exception as e:
        raise Exception('CRITICAL: Git clone %s failed!%s' % (repo, pp(e)))
    devnull.close()
    return True


@retry(Exception, tries=3)
def _git_checkout(path, commit='o8', user_name=None):
    print "Git checkout %s in %s." % (commit, path)
    assert os.path.exists(path), 'CRITICAL: Path not found: %s' % path
    try:
        print "Git fetch before checkout %s" % path
        shell(['git', 'fetch'], cwd=path, timeout=120, user_name=user_name)
        shell(['git', 'fetch', '--tags'], cwd=path, timeout=120, user_name=user_name)
    except Exception as e:
        print 'ERROR: git fetch failed before checkout!%s' % pp(e)
    try:
        shell(['git', 'checkout', commit], cwd=path, timeout=60, user_name=user_name)
        _git_submodule(path, user_name=user_name)
    except Exception as e:
        raise Exception('CRITICAL: Git checkout %s failed!%s' % (commit, pp(e)))
    return True


@retry(Exception, tries=3)
def _git_latest(target_path, repo, commit='o8', user_name=None, pull=False):
    print "Get latest git repository %s -b %s in %s." % (repo, commit, target_path)
    # HINT: 'target_path' is the full path where the repo should be cloned to
    if os.path.exists(target_path):
        # Git repo exists already
        devnull = open(os.devnull, 'w')
        try:
            print "Reset git repo and submodules in %s, " % target_path
            shell(['git', 'reset', '--hard'],
                  cwd=target_path, timeout=120, stderr=devnull, user_name=user_name)
            shell(['git', 'submodule', 'update', '-f'],
                  cwd=target_path, timeout=120, stderr=devnull, user_name=user_name)
        except Exception as e:
            print 'ERROR: Reset git repo and submodules failed!%s' % pp(e)
        try:
            _git_checkout(target_path, commit=commit, user_name=user_name)
        except Exception as e:
            raise Exception('CRITICAL: git checkout failed!%s' % pp(e))
        try:
            if pull:
                shell(['git', 'pull'], cwd=target_path, timeout=120, stderr=devnull, user_name=user_name)
        except Exception as e:
            raise Exception('CRITICAL: git pull failed!%s' % pp(e))
        devnull.close()
    else:
        # Git repo does not exist
        _git_clone(repo, branch=commit, cwd=os.path.dirname(target_path), target=os.path.basename(target_path),
                   user_name=user_name)
    print "Get latest git repository done."
    return True


def _service_exists(service_name):
    service_file = pj('/etc/init.d', service_name)
    print "Check if service exists at %s" % service_file
    if os.path.exists(service_file):
        return True
    return False


def _service_running(service_name):
    pidfile = pj('/var/run', service_name + '.pid')
    print "Check if service %s ist running with pidfile %s" % (service_name, pidfile)
    if os.path.isfile(pidfile):
        with open(pidfile, 'r') as pidfile:
            pid = str(pidfile.readline()).rstrip('\n')
            proc_dir = pj('/proc', pid)
            print "Service pidfile contents %s. proc_dir %s" % (pid, proc_dir)
            if os.path.exists(proc_dir):
                print "Service is running!"
                return True
    return False


def _service_control(service_name, running, wait=10):
    print "Set service %s to state running %s" % (service_name, str(running))
    assert running in [True, False], 'CRITICAL: Running can only be True or False %s!' % running

    if not _service_exists(service_name):
        print 'WARNING: No init script found for service %s. Maybe on development server?' % service_name
        return True

    status = 'start' if running else 'stop'
    try:
        shell(['service', service_name, status])
        sleep(wait)
        print "Running %s and _service_running(service_name) %s " % (running, _service_running(service_name))
        if running != _service_running(service_name):
            print 'ERROR: Could not set service %s to %s' % (service_name, status)
            raise Exception('ERROR: Could not set service %s to %s' % (service_name, status))
        return True
    except:
        return False


def _find_root_dir(path, tools_folder_name='online_tools', stop='/'):
    while path not in ['/', stop, ]:
        if tools_folder_name in os.listdir(path):
            return path
        path = os.path.dirname(path)
    return False


def _odoo_config(instance_path):
    cnf = dict()
    cnf['instance'] = os.path.basename(instance_path)
    cnf['start_time'] = str(time.strftime('%Y-%m-%d_%H-%M-%S'))
    # Production Server?
    cnf['production_server'] = False
    if _service_exists(cnf['instance']):
        cnf['production_server'] = True

    # Log to File!
    if cnf['production_server']:
        cnf['update_log_file'] = '/var/log/online/'+cnf['instance']+'/'+cnf['instance']+'--update.log'
        if os.path.isfile(cnf['update_log_file']):
            shell(['chown', cnf['instance']+':'+cnf['instance'], cnf['update_log_file']])
        sys.stdout = open(cnf['update_log_file'], 'a+', buffering=1)
        sys.stderr = open(cnf['update_log_file'], 'a+', buffering=1)

    # server.conf (or -c)
    print "\nReading config file."
    configfile = False

    if '-c' in sys.argv:
        configfile = sys.argv[sys.argv.index('-c')+1]
    elif os.path.isfile(pj(instance_path, 'server.conf')):
        print "Using default config file server.conf!"
        configfile = pj(instance_path, 'server.conf')
        sys.argv.append('-c')
        sys.argv.append(configfile)

    if configfile:
        assert os.path.isfile(configfile), "CRITICAL: Config file not found at: %s" % configfile
        print "Read configfile server.conf from: %s" % configfile
        config = ConfigParser.SafeConfigParser()
        config.read(configfile)
        cnf.update(dict(config.items('options')))
        cnf['config_file'] = configfile
    else:
        cnf['config_file'] = False
        print 'WARNING: No config file found at: %s Using development defaults instead!' % instance_path

    # status.ini
    cnf['status_file'] = pj(instance_path, 'status.ini')
    status_file = dict()
    if os.path.isfile(cnf['status_file']):
        try:
            print "Read status.ini from: %s" % cnf['status_file']
            status_file = ConfigParser.SafeConfigParser()
            status_file.read(cnf['status_file'])
            status_file = dict(status_file.items('options'))
        except:
            status_file = dict()
            print "ERROR: Could not read status.ini from: %s" % cnf['status_file']
    cnf['restore_failed'] = status_file.get('restore_failed', 'False')
    cnf['update_failed'] = status_file.get('update_failed', 'False')
    cnf['no_update'] = status_file.get('no_update', 'False')
    assert cnf['restore_failed'] == 'False', 'CRITICAL: Restore failed set in status.ini!'

    # instance.ini
    assert os.path.isfile(pj(instance_path, 'instance.ini')), 'CRITICAL: instance.ini missing!'
    core = ConfigParser.SafeConfigParser()
    core.read(pj(instance_path, 'instance.ini'))
    core = dict(core.items('options'))
    cnf['core'] = core.get('core')

    # ----- REGULAR START -----
    if cnf['production_server']:
        cnf['root_dir'] = '/opt/online'
    else:
        cnf['root_dir'] = _find_root_dir(instance_path)
    assert os.path.exists(cnf['root_dir']), 'CRITICAL: root_dir not found! %s ' % cnf['root_dir']

    # Directories
    cnf['core_dir'] = pj(cnf['root_dir'], 'online_'+cnf['core'])
    cnf['instance_dir'] = instance_path
    cnf['data_dir'] = cnf.get('data_dir', pj(cnf['instance_dir'], 'data_dir'))
    cnf['backup_dir'] = pj(cnf['instance_dir'], 'update')
    if _service_exists(cnf['instance']) and '_update' not in cnf.get('db_name', cnf['instance']):
        assert os.path.exists(cnf['backup_dir']), "CRITICAL: Backup directory is missing! %s" % cnf['backup_dir']

    # Repository URLs
    cnf['instance_repo'] = 'git@github.com:OpenAT/' + cnf['instance'] + '.git'
    cnf['core_repo'] = 'https://github.com/OpenAT/online.git'

    # Service
    cnf['service'] = False
    cnf['pid_file'] = pj('/var/run', cnf['instance'] + '.pid')
    if os.path.isfile(cnf['pid_file']):
        with open(cnf['pid_file'], 'r') as pidfile:
            cnf['service'] = os.path.isfile(str(pidfile.readline()))

    # Database  (commandline > or configfile > or foldername)
    cnf['db_name'] = sys.argv[sys.argv.index('-d')+1] if '-d' in sys.argv else \
        cnf.get('db_name', cnf['instance'])
    cnf['db_user'] = cnf.get('db_user', 'vagrant')
    cnf['db_password'] = cnf.get('db_password', 'vagrant')
    cnf['db_host'] = cnf.get('db_host', '127.0.0.1')
    cnf['db_port'] = cnf.get('db_port', '5432')
    cnf['db_url'] = 'postgresql://' + cnf['db_user'] + ':' + cnf['db_password'] + \
        '@' + cnf['db_host'] + ':' + cnf['db_port'] + '/' + cnf['db_name']

    # Check root access
    try:
        testdir = pj(cnf['root_dir'], cnf['start_time'])
        os.makedirs(testdir)
        shutil.rmtree(testdir)
        cnf['root_rights'] = True
    except:
        cnf['root_rights'] = False

    # Addons Paths (relative to the odoo folder inside the odoo_core folder)
    # Make sure addons-path is NOT! in the config file or command line since we calculate them.
    assert 'addons_path' not in cnf, "CRITICAL: addons_path found in config file! Please remove it!"
    assert '--addons_path' not in sys.argv, "CRITICAL: --addons_path found! Please remove it!"
    cnf['addons_reldirs'] = ['openerp/addons', 'addons', '../addons-loaded', ]
    cnf['addons_instance_dir'] = pj(cnf['instance_dir'], 'addons')
    cnf['addons_path'] = list(cnf['addons_reldirs']) + [cnf['addons_instance_dir'], ]
    cnf['addons_path_csv'] = ",".join([str(item) for item in cnf['addons_path']])

    # Additional needed options
    cnf['server_wide_modules'] = cnf.get('server_wide_modules', 'web,web_kanban,dbfilter_from_header')
    cnf['workers'] = cnf.get('workers', '0')

    # Commit Hash
    cnf['commit'] = _git_get_hash(cnf['instance_dir'])

    # Startup Args
    cnf['startup_args'] = ['--addons-path=' + cnf['addons_path_csv'], ]

    # Development Start (config file not found)
    if not cnf['config_file']:
        cnf['startup_args'] += ['-d', cnf['db_name'],
                                '-r', cnf['db_user'],
                                '-w', cnf['db_password'],
                                '--db_host', cnf['db_host'],
                                '--db_port', cnf['db_port'],
                                '-D', cnf['data_dir'],
                                '--load', cnf['server_wide_modules'],
                                '--db-template', 'template0',
                                '--workers', cnf['workers'],
                                ]
    # ----- REGULAR START END -----
    return cnf


def _odoo_update_config(cnf):
    # ----- UPDATE CHECK -----
    if '--update' in sys.argv:
        assert cnf['root_rights'], 'CRITICAL: --update given but not a root user!'
        assert os.path.exists(pj(cnf['instance_dir'], 'update')), 'CRITICAL: "update" Directory missing!'
        cnf['latest_instance'] = cnf['instance'] + '_update'

        # Backup (folder for his run of the script)
        cnf['backup'] = pj(cnf['backup_dir'], cnf['db_name']+'-pre-update_backup-'+cnf['start_time'])

        # Check if an update is already running
        cnf['update_lock_file'] = pj(cnf['instance_dir'], 'update.lock')
        counter = 0
        while os.path.isfile(cnf['update_lock_file']):
            print "WARNING: Concurrent update running. Recheck in 10 seconds."
            sleep(10)
            counter += 1
            assert counter < 60, 'CRITICAL: Concurrent update still running after 10 min! Please check %s .' \
                                 % cnf['update_lock_file']

        # Stop update if ...
        if cnf['update_failed'] != 'False' or cnf['no_update'] != 'False' \
                or any(x in ['--addons-path', '-u', '-i'] for x in sys.argv):
            print '\nUPDATE SKIPPED! Check "update_failed", "no_update", "-u", "-i" or "--addons-path".'
            cnf['run_update'] = False
            return cnf
        cnf['run_update'] = True

        # Create update lock file (Starting Update now)
        with open(cnf['update_lock_file'], 'a+'):
            assert os.path.isfile(cnf['update_lock_file']), 'CRITICAL: Could not create update_lock_file %s' \
                                                            % cnf['update_lock_file']
        if cnf['production_server']:
            shell(['chmod', 'o=', cnf['update_lock_file']])
            shell(['chown', cnf['instance']+':'+cnf['instance'], cnf['update_lock_file']])

        # Database
        cnf['latest_db_name'] = cnf['db_name'] + '_update'
        cnf['latest_db_url'] = 'postgresql://' + cnf['db_user'] + ':' + cnf['db_password'] + \
            '@' + cnf['db_host'] + ':' + cnf['db_port'] + '/' + cnf['latest_db_name']

        # Directories
        cnf['latest_inst_dir'] = pj(cnf['instance_dir'], 'update/' + cnf['latest_db_name'])
        cnf['latest_data_dir'] = pj(cnf['latest_inst_dir'], 'data_dir')

        # Addons paths
        cnf['latest_addons_instance_dir'] = pj(cnf['latest_inst_dir'], 'addons')
        cnf['latest_addons_path'] = list(cnf['addons_reldirs']) + [cnf['latest_addons_instance_dir'], ]
        cnf['latest_addons_path_csv'] = ",".join([str(item) for item in cnf['latest_addons_path']])

        # Get latest version of the instance repo
        # HINT: Must be run as the instance user because of git ssh!
        print "\n---- Get latest %s repository for update check." % cnf['instance']
        if cnf['production_server'] or not os.path.exists(cnf['latest_inst_dir']):
            _git_latest(cnf['latest_inst_dir'], cnf['instance_repo'], user_name=cnf['instance'], pull=True)
        else:
            print "WARNING: Development server found! Get latest repository for update check skipped!"
        print "---- Get latest %s repository done" % cnf['instance']

        # Commit Hash
        cnf['latest_commit'] = _git_get_hash(cnf['latest_inst_dir'])

        # latest instance.ini
        assert os.path.isfile(pj(cnf['latest_inst_dir'], 'instance.ini')), \
            'CRITICAL: instance.ini missing for latest repo!'
        instance_latest = ConfigParser.SafeConfigParser()
        instance_latest.read(pj(cnf['latest_inst_dir'], 'instance.ini'))
        instance_latest = dict(instance_latest.items('options'))
        cnf['latest_core'] = instance_latest.get('core')
        cnf['latest_core_dir'] = pj(cnf['root_dir'], 'online_' + cnf['latest_core'])

        # Forced addons to install or update for the INSTANCE
        cnf['latest_install_addons'] = []
        cnf['latest_update_addons'] = []
        if cnf['commit'] != cnf['latest_commit']:
            try:
                if instance_latest.get('install_addons') != 'False':
                    cnf['latest_install_addons'] = filter(None, instance_latest.get('install_addons', '').split(','))
                if instance_latest.get('update_addons') != 'False':
                    cnf['latest_update_addons'] = filter(None, instance_latest.get('update_addons', '').split(','))
            except Exception as e:
                _finish_update(cnf, error="CRITICAL: Could not set latest_[install/update]_addons!"+pp(e))

        # Get cores before we load core.ini
        try:
            _get_cores(cnf)
        except Exception as e:
            _finish_update(cnf, error="CRITICAL: Could not get cores!"+pp(e))

        # latest core.ini (core.ini is optional!)
        core_update = dict()
        if os.path.exists(pj(cnf['latest_core_dir'], 'core.ini')):
            try:
                core_update = ConfigParser.SafeConfigParser()
                core_update.read(pj(cnf['latest_core_dir'], 'core.ini'))
                core_update = dict(core_update.items('options'))
            except Exception as e:
                _finish_update(cnf, error="CRITICAL: Could not read core.ini!"+pp(e))

        # Forced addons to install or update for the CORE
        cnf['latest_core_install_addons'] = []
        cnf['latest_core_update_addons'] = []
        if cnf['core'] != cnf['latest_core']:
            try:
                if core_update.get('install_addons') != 'False':
                    cnf['latest_core_install_addons'] = filter(None, core_update.get('install_addons', '').split(','))
                if core_update.get('update_addons') != 'False':
                    cnf['latest_core_update_addons'] = filter(None, core_update.get('update_addons', '').split(','))
            except Exception as e:
                _finish_update(cnf, error="CRITICAL: Could not set latest_core_[install/update]_addons!"+pp(e))

        # All forced addons to update and install
        cnf['addons_to_install'] = cnf['latest_core_install_addons'] + cnf['latest_install_addons']
        cnf['addons_to_install_csv'] = ",".join([str(item) for item in cnf['addons_to_install']])
        cnf['addons_to_update'] = cnf['latest_core_update_addons'] + cnf['latest_update_addons']
        cnf['addons_to_update_csv'] = ",".join([str(item) for item in cnf['addons_to_update']])

        # Startup Args
        cnf['latest_startup_args'] = ['-d', cnf['latest_db_name'],
                                      '-r', cnf['db_user'],
                                      '-w', cnf['db_password'],
                                      '--db_host', cnf['db_host'],
                                      '--db_port', cnf['db_port'],
                                      '-D', cnf['latest_data_dir'],
                                      '--addons-path=' + cnf['latest_addons_path_csv'],
                                      '--load', cnf['server_wide_modules'],
                                      '--db-template', 'template0',
                                      '--workers', '0',
                                      '--xmlrpc-port', str(int(cnf.get('xmlrpc_port', 8000))+10)
                                      ]

        # server.conf file
        try:
            latest_server_conf = ConfigParser.SafeConfigParser()
            latest_server_conf.add_section('options')
            values = {
                'db_name': cnf['latest_db_name'],
                'db_user': cnf['db_user'],
                'db_password': cnf['db_password'],
                'db_host': cnf['db_host'],
                'db_port': cnf['db_port'],
                'db_template': 'template0',
                'data_dir': cnf['latest_data_dir'],
                'server_wide_modules': cnf['server_wide_modules'],
                'xmlrpc': 'True',
                'xmlrpc_port': str(int(cnf.get('xmlrpc_port', 8000))+10),
                'xmlrpcs': 'True',
                'xmlrpcs_port': str(int(cnf.get('xmlrpcs_port', 8001))+10),
            }
            if cnf['production_server']:
                values.update({'logfile': '/var/log/online/' + cnf['instance'] + '/' + cnf['latest_instance'] + '.log'})
            for key, value in values.iteritems():
                latest_server_conf.set('options', str(key), str(value))
            with open(pj(cnf['latest_inst_dir'], 'server.conf'), 'w+') as writefile:
                latest_server_conf.write(writefile)
        except Exception as e:
            print 'ERROR: Could not update %s\n%s\n' % (pj(cnf['latest_inst_dir'], 'server.conf'), pp(e))
    # ----- UPDATE CHECK END -----

    return cnf


@retry(Exception, tries=4)
def _get_cores(conf):
    print "\n---- GET CORES (should be run as a root user)"
    paths = list()
    paths.append(conf['core_dir'])

    # get current core
    if os.path.exists(conf['core_dir']) and not conf['production_server']:
        print 'WARNING: Development server found! Skipping %s clone or checkout' % conf['core_dir']
    else:
        _git_latest(conf['core_dir'], conf['core_repo'], commit=conf['core'])

    # get or create latest core
    if conf.get('latest_core_dir', False):
        if conf.get('latest_core_dir') != conf['core_dir']:

            if os.path.exists(conf['latest_core_dir']) and not conf['production_server']:
                print 'WARNING: Development server found! Skipping %s clone or checkout' % conf['latest_core_dir']
            else:
                # Optimization to save time for download
                if not os.path.exists(conf['latest_core_dir']):
                    shutil.copytree(conf['core_dir'], conf['latest_core_dir'])
                # get latest core
                _git_latest(conf['latest_core_dir'], conf['core_repo'], commit=conf['latest_core'])
            paths.append(conf['latest_core_dir'])
    else:
        print "ERROR: latest_core_dir not in configuration!"

    # Set correct rights
    if conf['production_server']:
        for path in paths:
            path = str(path)
            if conf['root_dir'] in path:
                try:
                    print "Set correct user and rights for core in path %s" % path
                    shell(['chown', '-R', 'root:root', path], cwd=path, timeout=60)
                    # Make sure others can read(use) the core and its files too
                    # HINT: This should be ok already in the core in Github!
                    shell(['chmod', '-R', 'o=rX', path], cwd=path, timeout=60)
                except (Exception, subprocess32.TimeoutExpired) as e:
                    print 'ERROR: Set user and rights failed! Retcode %s !' % pp(e)
    print "---- GET CORES done\n"
    return True


def _odoo_backup(conf, backup_target=None):
    print "\nBACKUP"
    # Create folder to backup into
    backup_target = backup_target or conf['backup']
    try:
        os.makedirs(backup_target)
    except Exception as e:
        raise Exception('CRITICAL: Can not create backup dir %s%s' % (os.makedirs(backup_target), pp(e)))

    # Backup filestore from data_dir for instance database
    source_filestore = pj(conf['data_dir'], 'filestore/'+conf['db_name'])
    print 'Backup of filestore for db %s at %s to %s' % (conf['db_name'], source_filestore, backup_target)
    assert os.path.exists(source_filestore), 'CRITICAL: Source filestore not found for database! %s' % source_filestore
    shutil.copytree(source_filestore, pj(backup_target, 'filestore'))

    # Backup database
    try:
        print 'Backup of database at %s to %s' % (conf['db_name'], backup_target)
        cmd = ['pg_dump', '--format=c', '--no-owner',
               '--dbname='+conf['db_url'], '--file='+pj(backup_target, 'db.dump')]
        shell(cmd, timeout=300)
    except Exception as e:
        raise Exception('CRITICAL: Backup of database failed!%s' % pp(e))

    print 'BACKUP done!\n'
    return backup_target


@retry(Exception, tries=3)
def _odoo_restore(backup_dir, conf, data_dir_target='', database_target_url=''):
    # database
    database_source = pj(backup_dir, 'db.dump')
    database_target_url = database_target_url or conf['db_url']

    database_name = database_target_url.rsplit('/', 1)[-1]
    database_restore_cmd = ['pg_restore', '--format=c', '--no-owner', '-n', 'public', '--dbname='+database_target_url, database_source]

    # data_dir
    data_dir_source = pj(backup_dir, 'filestore')
    data_dir_target = data_dir_target or conf['data_dir']
    data_dir_target = pj(data_dir_target, 'filestore/'+database_name)

    # odoo backup format detection
    if os.path.exists(pj(backup_dir, 'dump.sql')):
        # database
        database_source = pj(backup_dir, 'dump.sql')
        database_restore_cmd = ['psql', '-d', database_target_url, '-f', database_source]

    print "\nRESTORE of %s to data_dir_target %s and db_target %s " % (backup_dir, data_dir_target, database_target_url)
    assert os.path.exists(data_dir_source), "ERROR: Restore directory is missing: %s" % data_dir_source
    assert os.path.exists(database_source), "ERROR: Restore database file is missing: %s" % database_source

    # Restore data_dir
    print 'Restore of data_dir at %s to %s' % (backup_dir, data_dir_target)
    try:
        if os.path.exists(data_dir_target):
            shutil.rmtree(data_dir_target)
        shutil.copytree(data_dir_source, data_dir_target)
    except Exception as e:
        raise Exception('CRITICAL: Restore of data_dir failed!%s' % pp(e))

    # Restore database
    print 'Restore of database at %s to %s' % (backup_dir, database_target_url)
    try:
        datname = "'%s'" % database_name
        postgres_db_url = database_target_url.rsplit('/', 1)[-2] + '/postgres'
        # Drop Connections
        sql_drop_conn = "SELECT pg_terminate_backend(pid) \
                         FROM pg_stat_activity \
                         WHERE pg_stat_activity.datname = %s \
                         AND pid <> pg_backend_pid() ;" % datname
        cmd_drop_conn = ['psql', '-q', '-c', sql_drop_conn, '-d', database_target_url]
        # Drop DB
        sql_drop_db = "DROP DATABASE %s ;" % database_name
        cmd_drop_db = ['psql', '-q', '-c', sql_drop_db, '-d', postgres_db_url]
        # Create DB
        sql_create_db = "CREATE DATABASE %s \
                         WITH OWNER %s \
                         TEMPLATE template0 \
                         ENCODING 'UTF8' ;" % (database_name, conf['db_user'])
        cmd_create_db = ['psql', '-q', '-c', sql_create_db, '-d', postgres_db_url]
        try:
            shell(cmd_drop_conn, timeout=240)
        except:
            print "WARNING: could not drop connections to database %s" % database_name
        try:
            shell(cmd_drop_db, timeout=240)
        except:
            print "WARNING: could not drop database %s" % database_name
        shell(cmd_create_db, timeout=240)
    except Exception as e:
        raise Exception('CRITICAL: Drop (and create) database failed!%s' % pp(e))
    try:
        # Restore the database (HINT: Don't use --clean!)
        shell(database_restore_cmd, timeout=600)
    except (Exception, subprocess32.TimeoutExpired) as e:
        raise Exception('CRITICAL: Restore database failed!%s' % pp(e))

    print 'RESTORE done!\n'
    return True


def _changed_files(gitrepo_path, current, target='Latest'):
    print "Searching for changed files in %s" % gitrepo_path
    if current == target:
        print "WARNING: Current and target commit are the same!"
        return []
    changed_files = []
    gitdiff = ['git', 'diff', '--name-only', '--ignore-submodules=all', '--diff-filter=ACMR']

    # Find regular changed files
    for f in shell(gitdiff + [current, target], cwd=gitrepo_path).splitlines():
        changed_files.append(pj(gitrepo_path, f))

    # Find changed files of submodules
    for subm in shell(['git', 'submodule'], cwd=gitrepo_path).splitlines():
        relative_path = subm.strip().split()[1]
        absolute_path = pj(gitrepo_path, relative_path)
        current_rev = shell(['git', 'ls-tree', current, relative_path], cwd=gitrepo_path).strip().split()[2]
        target_rev = shell(['git', 'ls-tree', target, relative_path], cwd=gitrepo_path).strip().split()[2]
        for f in shell(gitdiff + [current_rev, target_rev], cwd=absolute_path).splitlines():
            changed_files.append(pj(absolute_path, f))

    print "Changed files found: %s\n" % changed_files
    return changed_files


def _find_addons_byfile(changed_files, stop=[]):
    print "Find addons by file. Stop at dir / or %s" % stop
    updates = langupdates = []
    for f in changed_files:
        filetype = os.path.splitext(f)[1]
        if filetype in ('.py', '.xml', '.po', '.pot'):
            path = os.path.dirname(f)
            #print "DEBUG: path %s filetype %s isfile %s %s" % (path, filetype, pj(path, '__openerp__.py'), os.path.isfile(pj(path, '__openerp__.py')))
            while path not in ['/', ] + stop:
                if os.path.isfile(pj(path, '__openerp__.py')):
                    if filetype in ('.py', '.xml', '.po'):
                        updates.append(os.path.basename(path))
                    elif filetype in ('.po', '.pot'):
                        langupdates.append(os.path.basename(path))
                    break
                path = os.path.dirname(path)  # cd ..
    print "Found addons: %s\n" % list(OrderedDict.fromkeys(updates))
    return list(OrderedDict.fromkeys(updates)), list(OrderedDict.fromkeys(langupdates))


def _find_addons_inpaths(addons_paths):
    addons = []
    for addons_path in addons_paths:
        assert os.path.exists(addons_path), "ERROR: Addons path is missing: %s" % addons_path
        for dirname, folders, files in os.walk(addons_path, followlinks=True):
            for folder in folders:
                if os.path.isfile(pj(pj(dirname, folder), '__openerp__.py')):
                    addons.append(folder)
    return list(OrderedDict.fromkeys(addons))


def _addons_to_update(conf):
    # core
    langupdates = []
    core_updates = []
    if conf['core'] != conf['latest_core']:
        odoo_base_addons = pj(conf['latest_core_dir'], 'odoo/openerp/addons')
        odoo_addons = pj(conf['latest_core_dir'], 'odoo/addons')
        loaded_addons = pj(conf['latest_core_dir'], 'addons-loaded')
        changed_files = _changed_files(conf['latest_core_dir'], conf['core'], conf['latest_core'])
        updates, langupdates = _find_addons_byfile(changed_files, stop=[conf['latest_core_dir'], ])
        for addon in _find_addons_inpaths([odoo_base_addons, odoo_addons, loaded_addons]):
            if addon in updates:
                core_updates.append(addon)
    if core_updates:
        print 'Updates for the odoo core found: %s' % core_updates
    else:
        print 'No Updates for the odoo core found!'

    # instance-addons
    changed_files = _changed_files(conf['latest_inst_dir'], conf['commit'], conf['latest_commit'])
    instance_updates, instance_langupdates = _find_addons_byfile(changed_files, stop=[conf['latest_inst_dir'], ])
    if instance_updates:
        print 'Updates for the instance addons found: %s' % instance_updates
    else:
        print 'No Updates for the instance addons found!'

    # addons to update
    addons_to_update = core_updates + instance_updates
    languages_to_update = langupdates + instance_langupdates
    return addons_to_update, languages_to_update


def _finish_update(conf, success=str(), error=str(), restore_failed='False'):
    assert success != error, 'CRITICAL: error and success given for the update?!?'

    # Write status.ini file
    try:
        status_ini = ConfigParser.SafeConfigParser()

        # add update options
        status_ini.add_section('options')
        values = {
            'update_failed': conf['start_time'] if error else 'False',
            'restore_failed': restore_failed,
            'no_update': conf['no_update'],
        }
        for key, value in values.iteritems():
            status_ini.set('options', str(key), str(value))

        # Write config for debugging
        status_ini.add_section('config')
        for key, value in conf.iteritems():
            status_ini.set('config', str(key), str(value))

        with open(conf['status_file'], 'w+') as writefile:
            status_ini.write(writefile)
        if conf['production_server']:
            shell(['chmod', 'o=', conf['status_file']])
            shell(['chown', conf['instance']+':'+conf['instance'], conf['status_file']])
    except Exception as e:
        print 'ERROR: Could not update %s%s' % (conf['status_file'], pp(e))

    # Remove update.lock file
    try:
        if os.path.isfile(conf['update_lock_file']):
            os.remove(conf['update_lock_file'])
    except Exception as e:
        print 'ERROR: Could not remove update lock file! %s%s' % (conf['update_lock_file'], pp(e))

    # TODO: remove old temp backups (if more than 3)
        # get dirs and sort by date
        # remove all but the last three

    # Print final message
    if success:
        print "%s\n---------- UDPATE DONE! ----------" % success
    if error:
        print "%s\n---------- ERROR: UPDATE FAILED! ----------" % error

    # Close conf['update_log_file']
    if conf['production_server']:
        sys.stderr.close()
        sys.stdout.close()

    # Exit --update process
    if success:
        exit(0)
    if error:
        exit(1)


def _compare_urls(url1, url2, wanted_simmilarity=1.0):
    try:
        url1 = urllib2.urlopen(url1)
        url1_content = url1.read()
        url2 = urllib2.urlopen(url2)
        url2_content = url2.read()
        simmilarity = difflib.SequenceMatcher(None, url1_content, url2_content).ratio()
        print "Websites match to %s percent." % simmilarity*100
        if wanted_simmilarity >= simmilarity:
            return True
    except Exception as e:
        print "ERROR: Could not compare websites:%s" % pp(e)
    return False


def _odoo_update(conf):
    print '\n---------- UPDATE START %s ----------' % conf['start_time']

    # 1.) No Changes at all
    if conf['commit'] == conf['latest_commit']:
        return _finish_update(conf, success="No Update necessary.")

    # Search for addons to update
    try:
        print 'Search for addons to update.'
        addons_to_update = _addons_to_update(conf)[0]
        if addons_to_update:
            conf['addons_to_update_csv'] = ",".join([str(item) for item in conf['addons_to_update'] + addons_to_update])
    except Exception as e:
        return _finish_update(conf, error='CRITICAL: Search for addons to update failed!'+pp(e))

    # 2.) No addons to install or update found and cores are the same
    if not conf['addons_to_install_csv'] and not conf['addons_to_update_csv'] and conf['core'] == conf['latest_core']:
        print '\nUpdate instance repo without restart!'
        try:
            _git_checkout(conf['instance_dir'], commit=conf['latest_commit'], user_name=conf['instance'])
            return _finish_update(conf, success='Pulled instance repo '+conf['latest_commit']+' without restart!')
        except Exception as e:
            return _finish_update(conf, error='CRITICAL: Checkout '+conf['latest_commit']+' failed!'+pp(e))

    # 3.) Update is required
    print '\nUpdate is required!'

    # Backup
    try:
        print 'Backup before update: %s' % conf['backup']
        backup = _odoo_backup(conf, backup_target=conf['backup'])
    except Exception as e:
        _finish_update(conf, error='CRITICAL: Backup before update failed. Skipping update.'+pp(e))
        return False

    # TODO: Run language Updates
    # 3.1) Dry-Run the update
    print "-- Dry-Run the update."
    try:
        # Stop Service
        print "Stopping service %s." % conf['latest_instance']
        if conf['production_server']:
            if not _service_control(conf['latest_instance'], running=False):
                raise Exception('ERROR: Could not stop service %s' % conf['latest_instance'])
        else:
            print "WARNING: Development server found! Stopping the service skipped!"

        # Restore backup
        _odoo_restore(backup, conf, data_dir_target=conf['latest_data_dir'], database_target_url=conf['latest_db_url'])


        # Server Script and command working directory
        odoo_server = [pj(conf['latest_core_dir'], 'odoo/openerp-server'), ]
        odoo_cwd = pj(conf['latest_core_dir'], 'odoo')

        # Update addons in the dry-run instance
        if conf['addons_to_update_csv']:
            print '\n-- Updating the dry-run database. (Please be patient)'
            print '%s%s' % ('Addons to update: ', conf['addons_to_update_csv'])
            args = ['--stop-after-init', ]
            args += ['-u', conf['addons_to_update_csv']]
            shell(odoo_server + conf['latest_startup_args'] + args, cwd=odoo_cwd, timeout=600,
                  user_name=conf['instance'])

        # Install addons in the dry-run instance
        if conf['addons_to_install_csv']:
            print '\n-- Install addons in the dry-run database. (Please be patient)'
            print '%s%s' % ('Addons to install: ', conf['addons_to_install_csv'])
            args = ['--stop-after-init', ]
            args += ['-i', conf['addons_to_install_csv']]
            shell(odoo_server + conf['latest_startup_args'] + args, cwd=odoo_cwd, timeout=600,
                  user_name=conf['instance'])
    except Exception as e:
        return _finish_update(conf, error='CRITICAL: Update dry-run failed!'+pp(e))

    # 3.1.1) Compare webpages (and permanently Start the Dry-Run Instance).
    # print "\n-- Start the Dry-Run instance service permanently and check webpages for any changes."
    # if conf['production_server']:
    #     # Start latest instance
    #     if _service_control(conf['latest_instance'], running=True):
    #         url = 'http://'+conf['instance']+'.datadialgo.net'
    #         latest_url = 'http://'+conf['latest_instance']+'.datadialgo.net'
    #         if not _compare_urls(url, latest_url, wanted_simmilarity=0.8):
    #             print "WARNING: Webpages seem to be different!"
    #             # return _finish_update(conf, error='CRITICAL: Websites are different!\n')
    # else:
    #     print "WARNING: Development server found! Compare Webpages skipped!"

    # TODO: Run language Updates
    # 3.2) Update of production instance
    print "\n-- Run the final update on production instance. Service will be stopped!"
    if conf['production_server']:
        try:
            # Stop service
            print "\nStop service %s." % conf['instance']
            if not _service_control(conf['instance'], running=False):
                raise Exception('ERROR: Could not stop service %s' % conf['instance'])

            # Get correct instance commit
            print '\nCheckout the correct commit ID for instance repo %s' % conf['latest_commit']
            _git_checkout(conf['instance_dir'], conf['latest_commit'], user_name=conf['instance'])

            # Startup Args
            args = ['-c', conf['config_file'], '--stop-after-init', ]
            args += conf['startup_args']

            # Update addons in productive instance
            if conf['addons_to_update_csv']:
                print '\n-- Updating the production database. (Please be patient)'
                print '%s%s' % ('Addons to update: ', conf['addons_to_update_csv'])
                shell(odoo_server + ['-u', conf['addons_to_update_csv']] + args, cwd=odoo_cwd, timeout=600,
                      user_name=conf['instance'])

            # Install addons in productive instance
            if conf['addons_to_install_csv']:
                print '\n-- Install addons in the production database. (Please be patient)'
                print '%s%s' % ('Addons to install: ', conf['addons_to_install_csv'])
                shell(odoo_server + ['-i', conf['addons_to_install_csv']] + args, cwd=odoo_cwd, timeout=600,
                      user_name=conf['instance'])

            # Update successful
            print "\nUpdate successful!\nStart service %s" % conf['instance']
            if _service_control(conf['instance'], running=True):
                _finish_update(conf, success='Final update successful and instance UP!\n')
            else:
                _finish_update(conf, success='WARNING: Final update successful but instance DOWN!\n')

        except Exception as e:
            print "\nCRITICAL: Final update on production instance failed! %s" % pp(e)
            # Update failed - try to restore backup
            try:
                # Restore correct commit
                print "\n-- Restore pre-update instance commit."
                _git_checkout(conf['instance_dir'], conf['commit'], user_name=conf['instance'])

                # Restore database and data_dir
                print "\n -- Restore pre-update database and filestore."
                _odoo_restore(backup, conf, data_dir_target=conf['data_dir'], database_target_url=conf['db_url'])

            except Exception as e:
                # RESTORE FAILED!
                return _finish_update(conf, error='CRITICAL: Update failed! DATABASE NOT RESTORED!'+pp(e),
                                      restore_failed='True')

            # Restore successful after failed update
            print "\nStart service %s" % conf['instance']
            if _service_control(conf['instance'], running=True):
                _finish_update(conf, success='ERROR: UPDATE failed! Restore successful! Instance UP!\n')
            else:
                _finish_update(conf, error='CRITICAL: UPDATE failed! Restore successful! Instance DOWN!\n')

    else:
        print "WARNING: Development server found! Run the final update skipped!"
        _finish_update(conf, success='Development server found! Only Dry-Run update done!\n')


# ----- START MAIN ROUTINE -----
if __name__ == "__main__":

    # Make sure there is no = used for sys args
    #assert any("=" in s for s in sys.argv[1:]) == False, 'ERROR: Do not use = in startup arguments!\n' \
    #                                                     'Wrong: --instance_dir=/odoo/dadi\n' \
    #                                                     'Correct: --instance_dir /odoo/dadi'
    # TODO: Check if --addons sys.argv

    # Get the instance_dir
    instance_dir = sys.argv[sys.argv.index('--instance-dir')+1]
    assert os.path.exists(instance_dir), 'CRITICAL: --instance_dir directory not found or set: %s' % instance_dir

    # Get the odoo configuration and/or defaults
    odoo_config = _odoo_config(instance_dir)

    # Create a backup
    if '--backup' in sys.argv:
        print '\n---- Starting backup (--backup given)'
        try:
            _odoo_backup(odoo_config)
        except:
            print 'ERROR: --backup given but could not create the backup!'
        sys.argv.remove('--backup')

    # Restore a backup from folder (expects "data_dir" folder and "db.dump" file inside restore folder)
    if '--restore' in sys.argv:
        print '\n---- Starting restore (--restore given)'
        if odoo_config['production_server']:
            try:
                _service_control(odoo_config['instance'], running=False)
                _odoo_restore(sys.argv[sys.argv.index('--restore')+1], odoo_config)
            except:
                print "ERROR: Could not stop service before restore!"
        else:
            print "WARNING: Development server found! Stopping the service skipped!"
            _odoo_restore(sys.argv[sys.argv.index('--restore')+1], odoo_config)
        sys.argv.pop(sys.argv.index('--restore')+1)
        sys.argv.remove('--restore')

    # Update FS-Online
    if '--update' in sys.argv:
        print '\n---- Starting update check (--update given)'
        # Add additional update configuration
        odoo_config.update(_odoo_update_config(odoo_config))
        if odoo_config['run_update']:
            _odoo_update(odoo_config)
        else:
            _finish_update(odoo_config, success='WARNING: run_update is set to False!\n')

    # Start FS-Online
    else:
        print '\n---------- REGULAR START %s ----------' % odoo_config['start_time']
        sys.argv.pop(sys.argv.index('--instance-dir')+1)
        sys.argv.remove('--instance-dir')
        if '--update' in sys.argv:
            sys.argv.remove('--update')

        # Change path to correct core and folder odoo
        sys.path[0] = sys.argv[0] = pj(odoo_config['core_dir'], 'odoo')
        os.chdir(sys.path[0])
        print 'sys.path[0] and sys.argv[0] set to: %s' % sys.path[0]
        print 'Working directory set to: %s' % os.getcwd()

        # Set Startup Args (--addons-path for regular start or dev defaults)
        sys.argv += odoo_config['startup_args']
        print "Start odoo with sys.argv: %s" % sys.argv

        # for gevented mode
        if odoo_config['workers'] != str(0):
            print "INFO: Evented mode enabled! workers: %s" % odoo_config['workers']
            import gevent.monkey
            gevent.monkey.patch_all()
            import psycogreen.gevent
            psycogreen.gevent.patch_psycopg()

        # Load openerp
        if sys.gettrace() or odoo_config['workers'] == str(0):
            # we are in debug mode ensure that odoo don't try to start in gevented mode
            print 'INFO: Evented mode disabled! workers = 0 or sys.gettrace() found.\n'
            import openerp
            openerp.evented = False
        else:
            print "WARNING: Evented mode enabled! workers: %s\n" % odoo_config['workers']
            import gevent.monkey
            gevent.monkey.patch_all()
            import psycogreen.gevent
            psycogreen.gevent.patch_psycopg()
            import openerp

        # Start odoo
        openerp.cli.main()
