#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import select
import psycopg2
import psycopg2.extensions
import urllib
import urllib2
import logging


# Webhook
def webhook(args):

    # Set Log Level
    logging.basicConfig(
            level=getattr(logging, args.verbose.upper()),
            format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
            datefmt='%d-%m-%y %H:%M',
    )
    # Log To File
    if args.logfile is not None:
        logging.basicConfig(filename=args.logfile)
    # Start logging
    logging.info("\nStarting listening on channel %s for database %s on server %s" % (args.channel, args.database,
                                                                                      args.machine))

    # Set default value for channel
    if args.channel is None:
        args.channel = args.database

    # Open Database Connection
    try:
        logging.debug("Connect to database")
        dbc = psycopg2.connect(database=args.database, user=args.dbuser, password=args.dbsecret,
                               host=args.machine, port=args.port)

        logging.debug("Set database connection to ISOLATION_LEVEL_AUTOCOMMIT")
        logging.debug(dbc.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT))

        logging.debug("Create Database cursor")
        cur = dbc.cursor()

        logging.debug("LISTEN on channel %s" % args.channel)
        logging.debug(cur.execute('LISTEN ' + args.channel))
    except:
        logging.critical("Could not open database cursor and start listening channel!\n Exiting script!")
        exit(100)

    # Start to permanently listening for events
    # HINT: This uses the native linux system cues
    while True:
        logging.debug("Service running!")
        try:
            # Check every 5 seconds if the "readable list" is ready for reading
            # HINT: The optional timeout argument specifies a time-out as a floating point number in seconds.
            #       When the timeout argument is omitted the function blocks until at least one file descriptor is
            #       ready. A time-out value of zero specifies a poll and never blocks.
            if not select.select([dbc], [], [], 5) == ([], [], []):
                logging.info("Message from database waiting. Polling from %s" % args.database)
                dbc.poll()
                while dbc.notifies:
                    logging.info("Popping notify from database %s at channel %s." % (args.channel, args.database))
                    notify = dbc.notifies.pop()
                    logging.debug("notify.payload %s, notify.pid: %d" % (notify.payload, notify.pid))
                    # Fire Request
                    # HINT: http://www.pythonforbeginners.com/python-on-the-web/how-to-use-urllib2-in-python/
                    logging.info("POST request to URL: %s" % args.targeturl)
                    post_data = urllib.urlencode({'instance': args.channel})
                    request = urllib2.Request(args.targeturl, post_data)
                    response = urllib2.urlopen(request)
                    logging.info(response.read())
                    response.close()
        except (KeyboardInterrupt, SystemExit):
            logging.info("KeyboardInterrupt or SystemExit!\n Normal Exiting script.")
            try:
                dbc.close()
            except:
                logging.warning("Could not close database connection!")
                exit(200)
            exit(0)
        except Exception as e:
            logging.error("ERROR: %s" % repr(e))


# ----------------------------
# Create the command parser
# ----------------------------
parser = argparse.ArgumentParser()
parser.add_argument('-d', '--database', required=True, help='Database Name')
parser.add_argument('-m', '--machine', required=True, help='Database Host-IP or DNS')
parser.add_argument('-p', '--port', required=True, help='Database Port')
parser.add_argument('-u', '--dbuser', required=True, help='Database User')
parser.add_argument('-s', '--dbsecret', required=True, help='Database Password')
parser.add_argument('-l', '--logfile', required=False, help='Log File')
parser.add_argument('-v', '--verbose', required=False,
                    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                    default='INFO',
                    help='Log Level (Default: INFO)')
parser.add_argument('-c', '--channel', required=False,
                    help='LISTEN Channel Name (Default: -d = database name!)')
parser.add_argument('-t', '--targeturl', required=False,
                    default='https://salt.datadialog.net:8000/hook/sosync/sync',
                    help='Target URL (Default: https://salt.datadialog.net:8000/hook/sosync/sync)')
parser.set_defaults(func=webhook)

# --------------------
# START
# --------------------
args = parser.parse_args()
# HINT do not user logging here already!
print 'DEBUG: args: %s' % args

# Call method argparse.ArgumentParser.parse_args.func() of object parser
args.func(args)
