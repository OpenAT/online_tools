#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import select
import psycopg2
import psycopg2.extensions
import urllib
import urllib2
import logging
import time


# TODO: For security reasons it should be possible to read the data (pw, port ...) from server.conf
# TODO: This would avoid having the pw in any other file like init

def db_connection(parserargs):
    # Open database connection and start listening in channel
    try:
        logging.debug("Connect to database")
        dbc = psycopg2.connect(database=parserargs.database, user=parserargs.dbuser, password=parserargs.dbsecret,
                               host=parserargs.machine, port=parserargs.port)

        logging.debug("Set database connection to ISOLATION_LEVEL_AUTOCOMMIT")
        logging.debug(dbc.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT))

        logging.debug("Open Database cursor")
        cur = dbc.cursor()

        logging.debug("Open LISTEN channel: %s" % parserargs.channel)
        logging.debug(cur.execute('LISTEN ' + parserargs.channel))

        logging.info("Database %s connection established. Listening on channel %s." % (parserargs.database,
                                                                                       parserargs.channel))
        return dbc, cur
    except Exception as e:
        logging.warning("Could not open database cursor and start listening channel: %s." % repr(e))
        return False, False


# Webhook
def webhook(args):

    # Set default value for channel
    if args.channel is None:
        args.channel = args.database

    # Set Log Level
    logging.basicConfig(
            level=getattr(logging, args.verbose.upper()),
            format='%(asctime)s %(name)-8s %(levelname)-8s %(message)s',
            datefmt='%d-%m-%y %H:%M',
            filename=args.logfile,
    )
    # Start logging
    logging.info("Try listening on channel %s for database %s on server %s" % (args.channel, args.database,
                                                                                      args.machine))

    # Open Database Connection and Listening Channel
    dbc, cur = db_connection(args)

    # Start to permanently listening for events
    # HINT: This uses the native linux system cues
    while True:
        logging.debug("Service running!")
        try:
            # Check every 5 seconds if the "readable list" is ready for reading
            # HINT: The optional timeout argument specifies a time-out as a floating point number in seconds.
            #       When the timeout argument is omitted the function blocks until at least one file descriptor is
            #       ready. A time-out value of zero specifies a poll and never blocks.
            if not select.select([dbc], [], [], 10) == ([], [], []):
                logging.info("Message from database waiting. Polling from %s." % args.database)

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
            logging.info("KeyboardInterrupt or SystemExit.")
            try:
                logging.info("Try to close the Database Connection.")
                dbc.close()
            except:
                logging.error("Could not close database connection!")
                exit(200)
            logging.info("Regular script exit.")
            # Clean Exit
            exit(0)
        except Exception as e:
            logging.warning("Unexpected Error: %s\n Waiting 5 minutes before retry:" % repr(e))
            time.sleep(300)

            # Reconnect if database connection is broken
            try:
                dbc.isolation_level
            except:
                logging.error("Database connection is broken. Trying to reconnect:")
                dbc, cur = db_connection(args)


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
