#!/usr/bin/env python
import sys
import os
from os.path import join as pj
import subprocess32
from subprocess32 import check_output as shell
import ConfigParser
import shutil


# Update script run by instance github webhooks and in saltstack ONLINE.sls formula

instance_path = sys.argv[sys.argv.index('--instance-dir')+1]
assert os.path.exists(instance_path), 'CRITICAL: Instance path not found: %s' % instance_path

root_path = os.path.dirname(instance_path)
instance = os.path.basename(instance_path)

# Stop Service
# Todo: better detection if service is really stopped
if '--service-restart' in sys.argv:
    try:
        print "\nStopping Service: %s" % instance
        shell(['service', instance, 'stop'], timeout=60)
    except (subprocess32.CalledProcessError, subprocess32.TimeoutExpired) as e:
        print 'ERROR: Stopping service failed with retcode %s !\nOutput:\n\n%s\n' % (e.returncode, e.output)
        raise

# Update Instance Repo
try:
    print '\nUpdate from github of instance %s' % instance_path
    shell(['git', 'fetch'], cwd=instance_path, timeout=300)
    shell(['git', 'pull'], cwd=instance_path, timeout=300)
    print 'Update of instance successful!'
except (subprocess32.CalledProcessError, subprocess32.TimeoutExpired) as e:
    print 'ERROR: Update of instance %s failed with retcode %s !\nOutput:\n\n%s\n' % (instance, e.returncode, e.output)
    raise

# Create set of odoo cores in core_current and core_target
print '\nCloning FS-Online cores from github:'
version_files = list()
# http://stackoverflow.com/questions/1724693/find-a-file-in-python
for dirname, folders, files in os.walk(root_path, followlinks=True):
    for folder in folders:
        if 'online_' not in folder:
            inifile = pj(pj(dirname, folder), 'version.ini')
            if os.path.isfile(inifile):
                version_files.append(inifile)
odoo_cores = list()
if version_files:
    for version_file in version_files:
        config = ConfigParser.SafeConfigParser()
        config.read(version_file)
        config = dict(config.items('options'))
        if config.get('core_current') and config.get('core_current') not in odoo_cores:
            odoo_cores.append(config.get('core_current'))
        if config.get('core_target') and config.get('core_target') not in odoo_cores:
            odoo_cores.append(config.get('core_target'))
print 'FS-Online Cores found: %s' % odoo_cores

# git clone all missing sources and prevent others to write to the core
odoo_core_paths = []
for core in odoo_cores:
    # TODO: find a way to give username with @ and password for git clone
    url = 'https://github.com/OpenAT/online.git'
    path = pj(root_path, 'online_' + core)
    odoo_core_paths.append(path)
    if os.path.exists(path):
        print "\nCore %s already exists: %s" % (core, path)
    else:
        try:
            print "\nCloning core %s from github to %s" % (core, path)
            shell(['git', 'clone', '-b', core, '--recurse-submodules', url, path], cwd=root_path, timeout=1200)
        except (subprocess32.CalledProcessError, subprocess32.TimeoutExpired) as e:
            print 'ERROR: Cloning of core failed with retcode %s !\nOutput:\n\n%s\n' % (e.returncode, e.output)
            raise
    try:
        print 'Set user and group to root for core %s' % core
        shell(['chown', '-R', 'root:root', path], cwd=path, timeout=60)
        print 'Set files and directories to read only for all others.'
        shell(['chmod', '-R', 'o+rX-w', path], cwd=path, timeout=60)
    except:
        print "WARNING: Could not set user, group or rights for core! Maybe you are not root?"

# remove unnecessary sources
cmd = ['find', root_path, '-type', 'd', '-maxdepth', '1', '-iname', 'online_o*']
found_cores = [line for line in subprocess32.check_output(cmd).splitlines()]
print "\nSearching for obsolete cores."
print "Cores found in version.ini files: %s" % odoo_core_paths
print "Cores found on on host: %s" % found_cores
for found_core_path in found_cores:
    if found_core_path not in odoo_core_paths and os.path.exists(pj(found_core_path, 'addons-loaded')):
        shutil.rmtree(found_core_path)
        print 'Core was deleted since not needed by any version.ini file: %s' % found_core_path

# Start Service
if '--service-restart' in sys.argv:
    try:
        print "\nStarting Service: %s" % instance
        shell(['service', instance, 'start'], timeout=60)
    except (subprocess32.CalledProcessError, subprocess32.TimeoutExpired) as e:
        print 'ERROR: Starting service failed with retcode %s !\nOutput:\n\n%s\n' % (e.returncode, e.output)
        raise
