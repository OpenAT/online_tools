# -*- coding: utf-'8' "-*-"
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from contextlib import closing

import logging
_log = logging.getLogger()


def _connection_string_to_dict(db_con_string):
    # Parse the database connection string
    db_con_dict = dict()
    for item in db_con_string.split(" "):
        param = item.split("=")
        key = str(param[0]).strip("'").strip('"')
        val = str(param[1]).strip("'").strip('"')
        db_con_dict[key] = val

    # Check if any key or value is missing
    required = ('dbname', 'user', 'password', 'host', 'port')
    missing = [param for param in required if not db_con_dict.get(param, None)]
    assert not missing, "Parameter(s) %s missing in db_con_string" % str(missing)

    return db_con_dict


def connection_check(db_con_string=None):
    assert db_con_string, "Database connection string is missing"

    # Parse the connection string
    db_con_dict = _connection_string_to_dict(db_con_string)

    # Get the connection values
    dbname = db_con_dict['dbname']
    user = db_con_dict['user']
    host = db_con_dict['host']
    port = db_con_dict['port']

    _log.info("Check connection to database %s as user %s on host %s:%s " % (dbname, user, host, port))
    try:
        conn_instance_db = psycopg2.connect(db_con_string)
        # Close the cursor again because we don't need it anymore
        conn_instance_db.close()
        _log.info("Connection successfully established to database %s " % dbname)
        return True
    except Exception as e:
        _log.warning("Could not connect to database %s: %s" % (dbname, repr(e)))
        return False


def create_db(db_name=None, db_user=None, postgres_db_con_string=None):
    assert db_name and 'postgres' not in db_name, "db_name missing or contains 'postgres'"
    assert db_user and 'postgres' not in db_user, "db_user missing or contains 'postgres'"
    assert postgres_db_con_string, "Connection string for database 'postgres' is missing"
    postgres_db_con_dict = _connection_string_to_dict(postgres_db_con_string)
    assert postgres_db_con_dict['dbname'] == 'postgres', "Database in postgres_db_con_string must be 'postgres'!"

    _log.info('Try to create database %s' % db_name)

    # Connect to the system database 'postgres' (must always exist!)
    try:
        conn_postgres_db = psycopg2.connect(postgres_db_con_string)
    except Exception as e:
        _log.critical("Could not connect to the 'postgres' database!")
        raise e

    with closing(conn_postgres_db.cursor()) as cr:
        # Set the isolation level to ISOLATION_LEVEL_AUTOCOMMIT before DROP/CREATE
        # HINT: This is the same as: conn.autocommit = True
        _log.info("Set the isolation level to ISOLATION_LEVEL_AUTOCOMMIT before create")
        conn_postgres_db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        try:
            _log.info('Create the database %s with owner %s and UTF8 encoding' % (db_name, db_user))
            cr.execute("""CREATE DATABASE %s 
                     WITH OWNER %s 
                     TEMPLATE template0 
                     ENCODING 'UTF8' ;""" % (db_name, db_user))
        except Exception as e:
            _log.error("Creation of database %s failed! %s" % (db_name, repr(e)))
            raise e


def drop_db(db_name=None, postgres_db_con_string=None):
    assert db_name and 'postgres' not in db_name, "db_name missing or contains 'postgres'"
    assert postgres_db_con_string, "Connection string for database 'postgres' is missing"
    postgres_db_con_dict = _connection_string_to_dict(postgres_db_con_string)
    assert postgres_db_con_dict['dbname'] == 'postgres', "Database in postgres_db_con_string must be 'postgres'!"

    _log.info('Try to drop database %s' % db_name)

    # Connect to the system database 'postgres' (must always exist!)
    try:
        conn_postgres_db = psycopg2.connect(postgres_db_con_string)
    except Exception as e:
        _log.critical("Could not connect to the 'postgres' database!")
        raise e

    # Drop the instance database
    with closing(conn_postgres_db.cursor()) as cr:
        # Set the isolation level to ISOLATION_LEVEL_AUTOCOMMIT before DROP/CREATE
        # HINT: This is the same as: conn.autocommit = True
        _log.info("Set the isolation level to ISOLATION_LEVEL_AUTOCOMMIT before drop")
        conn_postgres_db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        # Drop database connections
        _log.info("Try to quit all other connections to the database %s before drop" % db_name)
        try:
            cr.execute("""SELECT pg_terminate_backend(pid)
                          FROM pg_stat_activity
                          WHERE pg_stat_activity.datname = '%s'
                          AND pid != pg_backend_pid()""" % db_name)
        except Exception as e:
            _log.warning("Dropping connections to database %s failed! %s" % (db_name, repr(e)))

        # Drop database
        _log.warning("Dropping database %s" % db_name)
        try:
            cr.execute('DROP DATABASE "%s"' % db_name)
        except Exception as e:
            _log.critical("Could not drop database %s! %s" % (db_name, repr(e)))
            raise e
