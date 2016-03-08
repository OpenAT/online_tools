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
    print "\nStarting listening on channel %s for database %s on server %s" % (args.channel, args.database, args.machine)

    dbc = psycopg2.connect(database=args.database, user=args.dbuser, password=args.dbsecret,
                           host=args.machine, port=args.port)
    dbc.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = dbc.cursor()
    cur.execute('LISTEN %s' % args.channel)

    retry = False
    while True:
        try:
            if retry:
                print "Retry in 10 seconds!"
                sleep(10)
                retry = False
            if not select.select([dbc], [], [], 5) == ([], [], []):
                print "Listening (polling) at database %s." % args.database
                dbc.poll()
                while dbc.notifies:
                    print "Got notify from database %s at channel %s." % (args.channel, args.database)
                    notify = dbc.notifies.pop()
                    print "DEBUG: notify.payload %s, notify.pid: %d" % (notify.payload, notify.pid)
                    print "Fire webhook. Http GET URL: %s" % args.targeturl
                    urllib2.urlopen(args.targeturl).read()
        except (KeyboardInterrupt, SystemExit):
            print "CRITICAL: KeyboardInterrupt or SystemExit!"
            raise
        except Exception as e:
            print "ERROR: %s" % e
            retry = True


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
