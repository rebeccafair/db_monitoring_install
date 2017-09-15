import MySQLdb
import warnings
import logging
import argparse
import sys
import os
import time
import gc

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--host',default='localhost')
    parser.add_argument('--port',default=3306,type=int)
    parser.add_argument('--user',default='telegraf')
    parser.add_argument('--password',default='telegraf')
    parser.add_argument('--loglevel',default='ERROR')
    parser.add_argument('--logfile',default='/var/log/telegraf/exec_mysql.log')
    args = parser.parse_args()

    warnings.simplefilter('error', MySQLdb.Warning)
    logging.basicConfig(filename=args.logfile, level=getattr(logging, args.loglevel.upper()),
                        format='%(asctime)s: %(levelname)s: %(message)s')
    gather_metrics(args.host, args.port, args.user, args.password)


def gather_metrics(db_host, db_port, db_user, db_pass):
    gc.collect() # Clean up any old DB connections
    try:
        db = MySQLdb.connect(host=db_host, port=db_port, user=db_user, passwd=db_pass)
        cursor = db.cursor()
    except MySQLdb.Warning as e:
        logging.warning(e[0])
    except MySQLdb.Error as e:
        print 'Couldn\'t connect to DB!'
        logging.error('Failed to connect to DB - ' + e[1] + '(' + str(e[0]) + ')')
        return

    v = get_version(cursor)
    host = os.uname()[1]

    gather_blocking_sessions(cursor, v, host)

    if (v['type'] == 'MariaDB'):
        gather_query_response_time(cursor, v, host)

    db.close()

    logging.info('Successfully gathered MySQL metrics')

def get_version(cursor):
    try:
        version = cursor.execute('SELECT VERSION()')
        version = cursor.fetchone()[0]
    except MySQLdb.Warning as e:
        logging.warning(e[0])
    except MySQLdb.Error as e:
        logging.error('Failed to get DB version - ' + e[1] + '(' + str(e[0]) + ')')
        sys.exit(0)

    versions = { 'major_version': int(version.split('.')[0]),
                 'minor_version': int(version.split('.')[1]),
                 'type': 'MariaDB' if 'MariaDB' in version.split('.')[2] else 'MySQL'
               }
    return versions

def gather_blocking_sessions(cursor, versions, host):
    query = ('SELECT r.trx_id waiting_trx_id, '
             'r.trx_mysql_thread_id waiting_thread, '
             'r.trx_query waiting_query, '
             'pw.user waiting_user, '
             'r.trx_wait_started waiting_since, '
             'b.trx_id blocking_trx_id, '
             'b.trx_mysql_thread_id blocking_thread, '
             'b.trx_query blocking_query, '
             'pb.user blocking_user '
             'FROM information_schema.innodb_lock_waits w '
             'INNER JOIN information_schema.innodb_trx b '
             'ON b.trx_id = w.blocking_trx_id '
             'INNER JOIN information_schema.innodb_trx r '
             'ON r.trx_id = w.requesting_trx_id '
             'INNER JOIN information_schema.processlist pb '
             'ON pb.ID = b.trx_mysql_thread_id '
             'INNER JOIN information_schema.processlist pw '
             'ON pw.ID = r.trx_mysql_thread_id;')
    measurement = 'mysql_blocking'
    tag_keys = ['host']
    tag_values = [host]
    field_keys = ['waiting_trx_id', 'waiting_thread', 'waiting_query', 'waiting_user', 'waiting_since',
                  'blocking_trx_id', 'blocking_thread', 'blocking_query', 'blocking_user']
    field_types = ['integer', 'integer', 'string', 'string', 'string',
                   'integer', 'integer', 'string', 'string']

    if (versions['type'] == 'MariaDB' or
       (versions['major_version'] == 5 and versions['minor_version'] >= 5)):

        try:
            cursor.execute(query)
        except MySQLdb.Warning as e:
            logging.warning(e[0])
        except MySQLdb.Error as e:
            logging.error('Failed to query for blocking sessions - ' + e[1] + '(' + str(e[0]) + ')')
            return

        try:
            data = cursor.fetchall()
        except MySQLdb.Warning as e:
            logging.warning(e[0])
        except MySQLdb.Error as e:
            logging.error('Failed to fetch blocking sessions - ' + e[1] + '(' + str(e[0]) + ')')
            return

        field_values = data
        print_influx_line_protocol(measurement, tag_keys, tag_values, field_keys, field_values, field_types)

    logging.info('Successfully queried for blocking sessions')

def gather_query_response_time(cursor, versions, host):
    query = 'SELECT count from information_schema.query_response_time order by time asc'
    avg_query = 'SELECT SUM(total)/SUM(count) from information_schema.query_response_time'
    measurement = 'mysql_query_response'
    tag_keys = ['host']
    tag_values = [host]
    field_keys = ['avg_response_time', '1us_count', '10us_count', '100us_count','1ms_count', '10ms_count', '100ms_count',
                  '1s_count', '10s_count', '100s_count', '1000s_count', '10000s_count', '100000s_count', '1000000s_count', 'too_long_count']
    field_types = ['float', 'integer', 'integer', 'integer', 'integer', 'integer', 'integer', 'integer',
                   'integer', 'integer', 'integer', 'integer', 'integer', 'integer', 'integer']

    try:
        cursor.execute(avg_query)
    except MySQLdb.Warning as e:
        logging.warning(e[0])
    except MySQLdb.Error as e:
        logging.error('Failed to query for average query response time - ' + e[1] + '(' + str(e[0]) + ')')
        return

    try:
        data = cursor.fetchall()
    except MySQLdb.Warning as e:
        logging.warning(e[0])
    except MySQLdb.Error as e:
        logging.error('Failed to fetch average query response time - ' + e[1] + '(' + str(e[0]) + ')')
        return
    avg_query_response_time = data[0][0]

    try:
        cursor.execute(query)
    except MySQLdb.Warning as e:
        logging.warning(e[0])
    except MySQLdb.Error as e:
        logging.error('Failed to query for query response time distribution - ' + e[1] + '(' + str(e[0]) + ')')
        return

    try:
        data = cursor.fetchall()
    except MySQLdb.Warning as e:
        logging.warning(e[0])
    except MySQLdb.Error as e:
        logging.error('Failed to fetch query response time distribution - ' + e[1] + '(' + str(e[0]) + ')')
        return

    field_values = [[avg_query_response_time] + [int(x[0]) for x in data]]
    print_influx_line_protocol(measurement, tag_keys, tag_values, field_keys, field_values, field_types)

    logging.info('Successfully queried for query response time')

def print_influx_line_protocol(measurement, tag_keys, tag_values, field_keys, field_values, field_types):
    tags = [key + '=' + tag_values[i] for i, key in enumerate(tag_keys)]
    timestamp = int(time.time())*(10**9)
    for i,vals in enumerate(field_values):
        fields = ilp_join_fields(field_keys, field_values[i], field_types)
        # If there are multiple measurements with the same name, tags, fields and timestamp they overwrite
        # each other in InfluxDB. Add 1ns to timestamp to avoid this. Requires precision = "1ns" in
        # Telegraf configuration
        print measurement + ',' + ','.join(tags) + ' ' + ','.join(fields) + ' ' + str(timestamp + i)

def ilp_join_fields(keys, values, types):
    joined_fields = []
    for i, val in enumerate(keys):
        if types[i] == 'integer':
            joined_fields.append(keys[i] + '=' + str(values[i]) + 'i')
        elif types[i] == 'string':
            joined_fields.append(keys[i] + '=' + '"' + str(values[i]) + '"')
        else:
            joined_fields.append(keys[i] + '=' + str(values[i]))
    return joined_fields  

main()
