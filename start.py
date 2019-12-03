# -*- coding: utf-'8' "-*-"
import sys
import os
from os.path import join as pj
import pwd
import psutil

from tools_settings import Settings
from tools_shell import shell

import logging
_log = logging.getLogger()


def start(instance_dir, cmd_args=None, log_file=''):
    cmd_args = list() if not cmd_args else cmd_args

    instance_dir = os.path.abspath(instance_dir)
    instance = os.path.basename(instance_dir)
    _log.info('----------------------------------------')
    _log.info('START INSTANCE %s' % instance)
    _log.info('----------------------------------------')
    _log.info('pid: %s' % os.getpid())
    linux_user = pwd.getpwuid(os.getuid())
    _log.info('user: %s' % linux_user.pw_name)
    _log.info('process.name: %s' % psutil.Process(os.getpid()).name())
    _log.info('sys.executable: %s' % str(sys.executable))

    # Load configuration
    _log.info("Prepare instance settings")
    s = Settings(instance_dir, startup_args=cmd_args, log_file=log_file)

    # Change current working directory to the folder odoo_dir inside the repo online
    working_dir = pj(s.instance_core_dir, 'odoo')
    _log.info("Change working directory to 'odoo' folder of core dir: %s" % working_dir)
    os.chdir(working_dir)

    # Change the current python script working directory to folder odoo_dir inside the repo online
    _log.info("Set python working directory (sys.path[0] and sys.argv[0]) to 'odoo' folder: %s" % working_dir)
    sys.path[0] = sys.argv[0] = working_dir
    assert working_dir == os.getcwd() == sys.path[0], (
            'Could not change working directory to %s !' % working_dir)

    # Overwrite the original script cmd args with the odoo-only ones
    log_startup_args = s.startup_args[:]
    if '-w' in log_startup_args:
        log_startup_args[log_startup_args.index('-w')+1] = '******'
    _log.info("Set sys.argv: %s" % ' '.join(sys.argv[0:1]+log_startup_args))
    sys.argv = sys.argv[0:1] + s.startup_args

    # _log basic info
    _log.info('Production Server: %s' % s.production_server)
    _log.info('Instance: %s' % s.instance)
    _log.info('Instance core tag: %s' % s.instance_core_tag)
    _log.info('Instance core dir: %s' % s.instance_core_dir)
    _log.info('Instance data_dir: %s' % s.data_dir)
    _log.info('Instance addon_path: %s' % s.addons_path)

    # _log system environment information
    _log.info("Environment $PATH: %s" % os.getcwd())
    _log.info("Environment $WORKING_DIRECTORY: %s" % os.environ.get("WORKING_DIRECTORY", ""))
    _log.info("Environment $PYTHONPATH: %s" % os.environ.get("PYTHONPATH", ""))
    _log.info("Environment $REQUESTS_CA_BUNDLE: %s" % os.environ.get("REQUESTS_CA_BUNDLE", ""))
    _log.info('Environment "python -m requests.certs" >>> %s' % shell(['python', '-m', 'requests.certs'], log=False))

    # Run odoo
    # HINT: 'import odoo' works because we are now in the FS-Online core directory that contains the folder odoo
    # ATTENTION: To make this work openerp-gevent must be in some path that python can load!
    _log.info("Run odoo.main() from odoo.py")
    _log.info("---")

    # Reset logging module before we start odoo
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # ATTENTION: To make this work the file 'openerp-gevent' must be in some path that python can load! It is included
    #            in the odoo core!!!
    import odoo
    odoo.main()
