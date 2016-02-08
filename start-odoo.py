#!/usr/bin/env python

import sys
import os
from os.path import join as pj
import ConfigParser
import time
import shutil
import subprocess32
from subprocess32 import check_output as shell
from collections import OrderedDict


def _git_get_hash(path):
    assert os.path.exists(path), 'ERROR: Path not found: %s' % path
    try:
        hashid = shell(['git', 'log', '-n', '1', '--pretty=format:"%H"'], cwd=path)
        return str(hashid)
    except subprocess32.CalledProcessError as e:
        print 'CRITICAL: Get commit-hash failed with returncode %s !\n%s\n' % (e.returncode, e.output)
        raise


def _odoo_config(instance_path):
    cnf = {}

    # Get the configfile and set sys.argv
    configfile = False
    if '-c' in sys.argv:
        configfile = sys.argv[sys.argv.index('-c')+1]
        assert os.path.isfile(configfile), "CRITICAL: -c given but config file not found at: %s" % configfile
    elif os.path.isfile(pj(instance_path, 'server.conf')):
        print "Using default config file server.conf!"
        configfile = pj(instance_path, 'server.conf')
        sys.argv.append('-c')
        sys.argv.append(configfile)
    if configfile:
        cnf = ConfigParser.SafeConfigParser()
        cnf.read(configfile)
        cnf = dict(cnf.items('options'))
        cnf['config_file'] = configfile
    else:
        cnf['config_file'] = False
        print '\nWARNING: No config file found at: %s Using development defaults instead!' % configfile

    # ----- STATIC INFORMATION (WILL NOT BE CHANGED) START -----
    # Get the Database name from commandline > or configfile > or foldername
    cnf['db_name'] = sys.argv[sys.argv.index('-d')+1] if '-d' in sys.argv else \
        cnf.get('db_name', os.path.basename(instance_dir))    # cd ..
    cnf['db_user'] = cnf.get('db_user', 'vagrant')
    cnf['db_password'] = cnf.get('db_password', 'vagrant')
    cnf['db_host'] = cnf.get('db_host', '127.0.0.1')
    cnf['db_port'] = cnf.get('db_port', '5432')
    # Database URL
    cnf['db_url'] = 'postgresql://' + cnf['db_user'] + ':' + cnf['db_password'] + \
        '@' + cnf['db_host'] + ':' + cnf['db_port'] + '/' + cnf['db_name']
    # Add instance dir
    cnf['instance_dir'] = instance_dir
    # basic directory where everything is installed to
    cnf['root_dir'] = os.path.dirname(instance_dir)  # cd .. e.g.: /opt/online
    # backup base dir
    cnf['backup_base_dir'] = pj(cnf['instance_dir'], 'backup')
    assert os.path.exists(cnf['backup_base_dir']), "CRITICAL: backup directory missing: %s" % cnf['backup_base_dir']
    # Add data_dir !!! ATTENTION: (must be an absolute path!) !!!
    cnf['data_dir'] = cnf.get('data_dir', pj(instance_dir, 'data_dir'))
    assert os.path.exists(cnf['data_dir']), "CRITICAL: data_dir missing! Must be an absolute path: %s" % cnf['data_dir']
    # Addon locations relative to the odoo folder inside the odoo_core folder
    # Make sure addons-path is NOT! in the config file or command line since we calculate them.
    assert 'addons_path' not in cnf, "CRITICAL: addons_path found in config file! Please remove it!"
    assert '--addons_path' not in sys.argv, "CRITICAL: --addons_path found! Please remove it!"
    cnf['addons_reldirs'] = ['openerp/addons', 'addons', '../addons-loaded', ]
    cnf['addons_instance_dir'] = pj(instance_dir, 'addons')
    cnf['addons_path'] = list(cnf['addons_reldirs']) + [cnf['addons_instance_dir'], ]
    cnf['addons_path_csv'] = ",".join([str(item) for item in cnf['addons_path']])
    # Additional needed options
    cnf['server_wide_modules'] = cnf.get('server_wide_modules', 'web,web_kanban,dbfilter_from_header')
    cnf['workers'] = cnf.get('workers', '0')
    # Generate development startup options in case no config file was found
    # HINT: Add this to sys.argv of all odoo starts
    cnf['dev_startup_args'] = []
    if not cnf['config_file']:
        cnf['dev_startup_args'] = ['-d', cnf['db_name'],
                                   '-r', cnf['db_user'],
                                   '-w', cnf['db_password'],
                                   '--db_host', cnf['db_host'],
                                   '--db_port', cnf['db_port'],
                                   '-D', cnf['data_dir'],
                                   '--addons-path=' + cnf['addons_path_csv'],
                                   '--load', cnf['server_wide_modules'],
                                   '--db-template', 'template0',
                                   '--workers', cnf['workers'],
                                   ]
    else:
        cnf['dev_startup_args'] = ['--addons-path=' + cnf['addons_path_csv'], ]
    # ----- STATIC INFORMATION (WILL NOT BE CHANGED) END -----

    # ----- DYNAMIC INFORMATION (MAYBE WRITTEN AT UPDATE) START -----
    # Get the version.ini settings
    version_file = pj(instance_dir, 'version.ini')
    assert os.path.isfile(version_file), 'CRITICAL: No version file found at: %s' % configfile
    version = ConfigParser.SafeConfigParser()
    version.read(version_file)
    cnf.update(dict(version.items('options')))
    cnf['version_file'] = version_file
    # Add odoo sources path
    cnf['core_current_dir'] = pj(cnf['root_dir'], 'online_' + cnf['core_current'])
    cnf['core_target_dir'] = pj(cnf['root_dir'], 'online_' + cnf['core_target'])
    assert os.path.exists(cnf['core_current_dir']), 'CRITICAL: Current odoo core missing: %s' % cnf['core_current_dir']
    # Set instance addons last start commit hash
    if cnf.get('addons_last_update') == 'False':
        cnf['addons_last_update'] = _git_get_hash(instance_dir)
    # ----- DYNAMIC INFORMATION (MAYBE WRITTEN AT UPDATE) END -----

    cnf['start_time'] = str(time.strftime('-%Y-%m-%d_%H-%M-%S'))
    assert os.path.exists(pj(cnf['instance_dir'], 'log')), "CRITICAL: log folder missing!"
    cnf['update_log_file'] = pj(cnf['instance_dir'], 'log/' +
                                'update-' + cnf['db_name'] + '-' + cnf['core_target'] + cnf['start_time'] + '.log')
    return cnf


def _odoo_backup(conf, backup_base_dir=False):
    if not backup_base_dir:
        backup_base_dir = conf['backup_base_dir']
    assert os.path.exists(backup_base_dir), "ERROR: Backup directory missing: %s" % backup_base_dir
    backup_dir = pj(backup_base_dir,
                    conf['db_name'] + '-' + conf['core_current'] + conf['start_time'])
    os.makedirs(backup_dir)
    # Backup data_dir
    print '\nBackup of data_dir at %s to %s' % (conf['data_dir'], backup_dir)
    shutil.copytree(conf['data_dir'], pj(backup_dir, 'data_dir'))
    # Backup database
    try:
        cmd = ['pg_dump', '--format=c', '--no-owner', '--dbname='+conf['db_url'], '--file='+pj(backup_dir, 'db.dump')]
        print 'Backup of database at %s to %s' % (conf['db_name'], backup_dir)
        shell(cmd, timeout=300)
    except subprocess32.CalledProcessError as e:
        print 'CRITICAL: Backup failed with returncode %s !\n%s\n' % (e.returncode, e.output)
        raise
    print 'Backup was successful!'
    return backup_dir


def _odoo_restore(backup_dir, conf):
    # Todo: Check for a odoo backup
    restore_data_dir = str()
    restore_target_dir = str()
    restoredb = []
    if os.path.exists(pj(backup_dir, 'filestore')):
        print '\nOdoo backup detected!'
        restore_data_dir = pj(backup_dir, 'filestore')
        restore_target_dir = pj(conf['data_dir'], 'filestore')
        assert os.path.exists(restore_data_dir), "ERROR: Restore filestore directory is missing: %s" % restore_data_dir
        restore_database = pj(backup_dir, 'dump.sql')
        assert os.path.exists(restore_database), "ERROR: Restore database file is missing: %s" % restore_database
        restoredb = ['psql', '--dbname='+conf['db_url'], '-f', restore_database, ]
    else:
        restore_data_dir = pj(backup_dir, 'data_dir')
        restore_target_dir = conf['data_dir']
        assert os.path.exists(restore_data_dir), "ERROR: Restore data_dir directory is missing: %s" % restore_data_dir
        restore_database = pj(backup_dir, 'db.dump')
        assert os.path.exists(restore_database), "ERROR: Restore database file is missing: %s" % restore_database
        restoredb = ['pg_restore', '--format=c', '--no-owner', '--dbname='+conf['db_url'], restore_database, ]

    # Restore data_dir
    print '\nRestore of data_dir at %s to %s' % (backup_dir, conf['data_dir'])
    shutil.rmtree(conf['data_dir'])
    shutil.copytree(restore_data_dir, restore_target_dir)

    # Restore database
    try:
        # Drop the Database first (max_locks_per_transaction = 256 or higher is required for this to work!)
        print 'Restore of database at %s to %s' % (backup_dir, conf['db_name'])
        sqldrop = 'DROP schema public CASCADE;CREATE schema public;'
        dropdb = ['psql', '-q', '--command='+sqldrop, '--dbname='+conf['db_url'], ]
        devnull = open(os.devnull, 'w')
        shell(dropdb, timeout=120, stderr=devnull)
    except subprocess32.CalledProcessError as e:
        print 'CRITICAL: Drop database failed with returncode %s !\n%s\n' % (e.returncode, e.output)
        raise
    try:
        # Restore the database (HINT: Don't use --clean!)
        shell(restoredb, timeout=600)
    except (subprocess32.CalledProcessError, subprocess32.TimeoutExpired) as e:
        print 'CRITICAL: Restore database failed with returncode %s ! Output:\n%s\n' % (e.returncode, e.output)
        raise

    print 'Restore was successful!'
    return True


def _changed_files(gitrepo_path, current, target='Latest'):
    if current == target:
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

    return changed_files


def _find_addons_byfile(changed_files, stop=[]):
    updates = langupdates = []
    for f in changed_files:
        filetype = os.path.splitext(f)[1]
        if filetype in ('.py', '.xml', '.po', '.pot'):
            path = os.path.dirname(f)
            while path not in ['/', ] + stop:
                if os.path.isfile(pj(path, '__openerp__.py')):
                    if filetype in ('.py', '.xml'):
                        updates.append(os.path.basename(path))
                    else:
                        langupdates.append(os.path.basename(path))
                    break
                path = os.path.dirname(path)  # cd ..
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


def _update_config(configfile, conf, settings={}, section='options'):
    config = ConfigParser.SafeConfigParser()
    config.read(configfile)
    for key, value in settings.iteritems():
        conf[key] = value
        config.set(section, key, value)
    with open(configfile, 'w+') as writefile:
        config.write(writefile)
    return True


def _odoo_update(conf):
    print '\nStart update check!'
    # Do not start if the instance addon version will not fit the targeted core
    # HINT: String splicing starts at 1 ant not at 0 (so we skip 3 chars e.g.: o8r)
    assert int(conf['addons_minimum_core'][3:]) <= int(conf['core_target'][3:]), "CRITICAL:" \
        "Instance-addons addons_minimum_core is greater than the core_target version in version.ini!"

    if conf['update_failed'] != 'False' or conf['no_update'] != 'False' \
            or any(x in ['--addons-path', '-u'] for x in sys.argv)\
            or not os.path.exists(conf['core_target_dir']):

        if not os.path.exists(conf['core_target_dir']):
            print "ERROR: Odoo target core is missing: %s" % os.path.exists(conf['core_target_dir'])
        print "Updates skipped!\nCheck update_failed or no_update in version.ini or --addons-path or -u was set."
        return False

    # addons to update for odoo-core and thirdparty-addons
    core_updates = []
    if conf['core_current'] != conf['core_target']:
        odoo_base_addons = pj(conf['core_target_dir'], 'odoo/openerp/addons')
        odoo_addons = pj(conf['core_target_dir'], 'odoo/addons')
        loaded_addons = pj(conf['core_target_dir'], 'addons-loaded')
        changed_files = _changed_files(conf['core_target_dir'], conf['core_current'], conf['core_target'])
        updates, langupdates = _find_addons_byfile(changed_files, stop=[conf['root_dir'], ])
        for addon in _find_addons_inpaths([odoo_base_addons, odoo_addons, loaded_addons]):
            if addon in updates:
                core_updates.append(addon)
    if core_updates:
        print 'Updates for the odoo core found: %s' % core_updates

    # addons to update for instance addons
    changed_files = _changed_files(conf['addons_instance_dir'],
                                   conf['addons_last_update'],
                                   _git_get_hash(conf['instance_dir']))
    # HINT: all addons in addons_instance_dir can be installed so no for loop needed
    instance_updates, instance_langupdates = _find_addons_byfile(changed_files, stop=[conf['instance_dir'], ])
    if instance_updates:
        print 'Updates for the instance addons found: %s' % instance_updates

    all_updates = core_updates + instance_updates
    # Update - If any addons to update are found
    if all_updates:
        # Backup first
        try:
            backup = _odoo_backup(conf)
            print 'Backup before update done: %s' % backup
            print 'Please remember that pre-update backups will not be automatically deleted!'
        except:
            print 'ERROR: Backup before update failed. Skipping update.'
            return False

        # Update Database
        try:
            all_updates_csv = ",".join([str(item) for item in all_updates])
            args = list(sys.argv[1:]) + conf['dev_startup_args']
            args += ['-u', all_updates_csv, '--stop-after-init']
            command = [pj(conf['core_target_dir'], 'odoo/openerp-server'), ] + args
            print '\nStarting update of database. Please be patient!\nAddons to update: %s' % all_updates_csv
            #print 'Updating odoo with: %s' % command
            # Todo: http://blog.endpoint.com/2015/01/getting-realtime-output-using-python.html
            #       http://eyalarubas.com/python-subproc-nonblock.html
            # HINT: Correct Path is set by cwd
            update = shell(command, cwd=pj(conf['core_target_dir'], 'odoo'), timeout=600)
            # Write log file
            try:
                with open(conf['update_log_file'], 'w+') as writefile:
                    writefile.write(update)
            except:
                print "ERROR: Could not write update log: %s" % conf['update_log_file']
        except (subprocess32.CalledProcessError, subprocess32.TimeoutExpired) as e:

            # Update failed
            _update_config(conf['version_file'], conf, settings={'update_failed': conf['core_target']})
            # Write log file
            try:
                with open(conf['update_log_file'], 'w+') as writefile:
                    writefile.write(update)
            except:
                print "ERROR: Could not write update log: %s" % conf['update_log_file']
            print 'ERROR: Update failed with returncode %s !\nOutput:\n\n%s\n' % (e.returncode, e.output)
            try:
                # Restore pre-update backup
                _odoo_restore(backup, conf)
                return False
            except:

                # Update Failed and Restore Failed - Raise Exception
                _update_config(conf['version_file'], conf, settings={'restore_failed': conf['core_target']})
                print 'CRITICAL: Could not restore db and data_dir after failed-update!'
                raise

    # Update was successful (or no addons to update found)
    _update_config(conf['version_file'], conf, 
                   settings={'core_current': conf['core_target'],
                             'addons_last_update': _git_get_hash(conf['instance_dir'])
                             })

    # Todo: make sure instance_dir will be pushed back to github
    #       Some problems arise if we are on the developement servers ...
    #       Therefore the update should only happen if no config file is found!
    if not all_updates:
        print 'No addons needed to be updated!'
    print 'Update was successful!'
    return True

# ----- START MAIN ROUTINE -----
if __name__ == "__main__":

    # Make sure there is no = used for sys args
    assert any("=" in s for s in sys.argv[1:]) == False, 'ERROR: Do not use = in startup arguments!\n' \
                                                         'Wrong: --instance_dir=/odoo/dadi\n' \
                                                         'Correct: --instance_dir /odoo/dadi'
    # Get the instance_dir and set it as the script path
    instance_dir = sys.argv[sys.argv.index('--instance-dir')+1]
    assert os.path.exists(instance_dir), 'CRITICAL: --instance_dir directory not found or set: %s' % instance_dir
    sys.argv.pop(sys.argv.index('--instance-dir')+1)
    sys.argv.remove('--instance-dir')
    sys.path[0] = instance_dir

    # Todo: make sure instance_dir is up to date with github?!?
    #       Some problems arise if we are on the developement servers ...
    #       Therefore the update should only happen if no config file is found!

    # Get the odoo configuration and/or defaults
    odoo_config = _odoo_config(instance_dir)

    # Do not start if there was failed restore attempt after an update
    assert odoo_config['restore_failed'] == 'False', 'CRITICAL: "restore_failed" is set in version.ini!'

    # Create a backup
    if '--backup' in sys.argv:
        _odoo_backup(odoo_config)
        sys.argv.remove('--restore')

    # Restore a backup from folder (must use "data_dir" and "db.dump" inside restore folder)
    if '--restore' in sys.argv:
        _odoo_restore(sys.argv[sys.argv.index('--restore')+1], odoo_config)
        sys.argv.pop(sys.argv.index('--restore')+1)
        sys.argv.remove('--restore')

    # Update Database if pre-requisites are met
    # HINT: Updates will only be done if -c is found and --addons-path or -u is not found in sys.argv
    _odoo_update(odoo_config)

    # Start odoo
    print '\n\n---------- START ----------'
    # Switch path to current odoo_core
    sys.path[0] = pj(odoo_config['core_current_dir'], 'odoo')
    sys.argv[0] = sys.path[0]
    sys.path.append(sys.path[0])
    print 'sys.path[0] and sys.argv[0] set to: %s' % sys.path[0]
    os.chdir(sys.path[0])
    print 'Working directory set to: %s' % os.getcwd()
    # Use development defaults for startup. (ONLY if no config file was found else dev_startup_args are empty!)
    sys.argv += odoo_config['dev_startup_args']
    print "Start odoo with sys.argv: %s" % sys.argv

    # for gevented mode
    if odoo_config['workers'] != str(0):
        print "workers: %s" % odoo_config['workers']
        import gevent.monkey
        gevent.monkey.patch_all()
        import psycogreen.gevent
        psycogreen.gevent.patch_psycopg()

    # load openerp
    import openerp
    if sys.gettrace() is None and odoo_config['workers'] == str(0):
        # we are in debug mode ensure that odoo don't try to start in gevented mode
        print 'Odoo started in debug mode. Set openerp.evented to False!'
        openerp.evented = False
    openerp.cli.main()
