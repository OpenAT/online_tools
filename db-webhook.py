#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import select
import psycopg2
import psycopg2.extensions
import urllib2
from time import sleep


# Webhook
def webhook(args):
    print "\nStarting listening on channel %s for database %s on server %s" % \
          (args.channel, args.database, args.machine)

    print "Connect to database"
    dbc = psycopg2.connect(database=args.database, user=args.dbuser, password=args.dbsecret,
                           host=args.machine, port=args.port)

    print "Set database connection to ISOLATION_LEVEL_AUTOCOMMIT"
    dbc.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

    print "Create Database cursor"
    cur = dbc.cursor()

    print "LISTEN on channel %s" % args.channel
    cur.execute('LISTEN ' + args.channel)

    while True:
        print "Service running! %s" % repr(select.select([dbc], [], [], 5))
        try:
            # Check every 5 seconds if the "readable list" is ready for reading
            # HINT: The optional timeout argument specifies a time-out as a floating point number in seconds.
            #       When the timeout argument is omitted the function blocks until at least one file descriptor is
            #       ready. A time-out value of zero specifies a poll and never blocks.
            if not select.select([dbc], [], [], 5) == ([], [], []):
                print "Message from database waiting. Polling from %s" % args.database
                dbc.poll()
                while dbc.notifies:
                    print "Popping notify from database %s at channel %s." % (args.channel, args.database)
                    notify = dbc.notifies.pop()
                    print "DEBUG: notify.payload %s, notify.pid: %d" % (notify.payload, notify.pid)
                    print "Fire webhook. Http-GET URL: %s" % args.targeturl
                    urllib2.urlopen(args.targeturl).read()
        except (KeyboardInterrupt, SystemExit):
            print "STOP SCRIPT: KeyboardInterrupt or SystemExit!"
            try:
                dbc.close()
            except:
                "ERROR: Could not close database connection!"
            # Stop Script
            exit(0)
        except Exception as e:
            print "ERROR: %s" % repr(e)


# ----------------------------
# Create the command parser
# ----------------------------
parser = argparse.ArgumentParser()
parser.add_argument('-d', '--database', required='True', help='Database Name')
parser.add_argument('-m', '--machine', required='True', help='Database Host-IP or DNS')
parser.add_argument('-p', '--port', required='True', help='Database Port')
parser.add_argument('-u', '--dbuser', required='True', help='Database User')
parser.add_argument('-s', '--dbsecret', required='True', help='Database Password')
subparsers = parser.add_subparsers(title='subcommands',
                                   description='available commands',
                                   help='')

# SubParser for webhook
parser_webhook = subparsers.add_parser('webhook', help='Generate Listener for webhook!')
parser_webhook.add_argument('-c', '--channel', required='True', help='LISTEN Channel Name')
parser_webhook.add_argument('-t', '--targeturl', required='True', help='Target URL')
parser_webhook.set_defaults(func=webhook)

# --------------------
# START
# --------------------
args = parser.parse_args()
print 'DEBUG: args: %s' % args

# Call method argparse.ArgumentParser.parse_args.func() of object parser
args.func(args)
