# -*- coding: utf-'8' "-*-"
import os
from os.path import join as pj
import datetime

from tools_settings import Settings
import tools_odoo

import logging
_log = logging.getLogger()


# TODO
def update(instance_dir, cmd_args=None, log_file=''):
    logging.info('----------------------------------------')
    logging.info('UPDATE instance')
    logging.info('----------------------------------------')

    # Prepare the dry run update instance under .../update/[instance]_update
    # ----------------------------------------------------------------------
    # HINT: this is called the update_instance from now on
    #
    # Get latest instance repository (clone or git_get_latest)
    # Compare the commit id of the update_instance and the instance (stop if equal)
    # Try to start the update_instance because the restore is much faster

    # Prepare the odoo core based on the instance.ini of the update_instance
    # ----------------------------------------------------------------------
    # Prepare/Get odoo core for instance.ini release tag

    # Search for addons to update
    # ---------------------------
    # Search for changed core addons
    # Search for changed instance addons
    # use -u all if more than 6 addons have changed (maybe we need a way to force -u all )
    # Stop here if no addons to update are found
    # Search for changed core translations
    # Search for changed instance translations

    # Dry-Run/Test the update in the update_instance
    # ----------------------------------------------
    # Backup the instance
    # Restore the backup to the dry-run update_instance
    # Test-Run the addon updates
    # Test-Run the language updates

    # Update the production instance
    # ------------------------------
    # Stop the service
    # Run the update
    # Restore pre update backup if the update fails
    # Send message to sysadmin

    return True
