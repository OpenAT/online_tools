# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
import time
import ConfigParser

from tools_shell import shell

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


