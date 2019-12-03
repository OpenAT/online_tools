# Usage of fsonline.py
Start an instance: 

```fsonline.py [instance-folder]```

Start an instance with log file: 

```fsonline.py [[instance-folder] --log_file=[path-to-log-file]```

Backup an instance to the default location: 

```fsonline.py [instance-folder] --backup```

Backup to specific file with logging: 

```fsonline.py [instance-folder] --backup [backup-zip-archive] --log_file=[path-to-log-file]```

Restore an instance: 

```fsonline.py [instance-folder] --restore [backup-zip-archive]```

Restore to specific file with logging to file: 

```fsonline.py [instance-folder] --restore [backup-zip-archive] --log_file=[path-to-log-file]```

# Info

- All relevant odoo startup options will be added automatically e.g.: like '--db-filter=^pfot$ --no-database-list'. Check *sys.argv:* in the log.
- Startup option priority: *Command line* > *server.conf* > *Defaults in tools_settings.py*
- It is no longer needed to create the update_instance in the [instance-dir]/update folder. Will be created automatically at --update
- Is is no longer needed to create a linux service for the update_instance. (You still can create one if you want to. 
  Start and Stop are handled correctly as long as the service is named as the instance name e.g.: dadi_update)
- Logging of updates will go into the update_instance log file (e.g.: dadi_update.log) The file dadi--update.log is no longer needed!
- The file status.ini is no longer needed and can be removed. But it will be checked if available!
- In case of an unexpected error the update.lock file will be left in the instance directory
- The update.lock file contains the process id (pid). Therefore we can check if an update is still running or died unexpectedly!
- Core-update-lock-files are now created in the *cores* folder and contain the full name of the core - therefore individual core updated may run in parallel
- Timeouts for updates are pretty long now - in the hours area - to enable backup and restore of big databases
- Backup is no always a Zip archive in the standard odoo format. The restore expect a zip archive too! Can be restored by odoo database manager!
- Backups are always performed manually by default (pgdump and file copy) because it is faster and more stable than the odoo web-backup
- Logfile of fsonline.py can be different from the odoo logfile if really needed! 
  --log_file is for fsonline.py and will be taken for odoo. To use a different logfile for odoo you can use --logfile or set a logfile in odoos server.conf
- On development machines the odoo cores are not reseted and updated by --update
- The update instance folder is now also called like the update database e.g.: dadi_update instead of just like the instance (dadi)! 
  Therefore: 'instance name' = 'database name' = 'service name' = 'instance folder name'! 
  The only exception is the linux and database user of the update_instance which is the user of the instance e.g.: dadi to avoid too many linux and postgres users.
- Two E-Mails are send to indicate the update start! One when the update is requested and one when the update really starts after successful pre-update-checks!
  But be aware that they may not come to the e-mail inbox in the expected order because of how the mail delivery works!

# Using python methods on the command line
Full git reset inlcuding submodules:

``` python -c "import tools_git as git; git.git_reset('/Users/michaelkarrer/pycharm_projects/fsonline/cores/online_o8r321')"```

Reset repo and force checkout of commit:

```python -c "import tools_git as git; git.git_latest('/Users/michaelkarrer/pycharm_projects/fsonline/cores/online_o8r321', commit='o8r321')"```
