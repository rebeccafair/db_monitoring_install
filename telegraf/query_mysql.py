import MySQLdb
import warnings
import logging
import argparse
import sys
import os
import time
import gc
import datetime

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
        logging.error('Failed to connect to DB - ' + e[1] + '(' + str(e[0]) + ')')
        sys.exit(0)

    v = get_version(cursor)
    host = os.uname()[1]

    gather_blocking_sessions(cursor, host, v)
    gather_slow_queries(cursor, host)
    gather_query_response_time(cursor, host)
    gather_userstats(cursor, host, v)

    db.close()

    logging.info('Successfully gathered MySQL metrics')

def gather_blocking_sessions(cursor, host, versions):
    query = ('SELECT r.trx_id waiting_trx_id, '
             'r.trx_mysql_thread_id waiting_thread, '
             'r.trx_query waiting_query, '
             'pw.user waiting_user, '
             'pw.host waiting_host, '
             'r.trx_wait_started waiting_since, '
             'b.trx_id blocking_trx_id, '
             'b.trx_mysql_thread_id blocking_thread, '
             'b.trx_query blocking_query, '
             'pb.user blocking_user, '
             'pb.host blocking_host '
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
    field_keys = ['waiting_trx_id', 'waiting_thread', 'waiting_query', 'waiting_user', 'waiting_host', 'waiting_since',
                  'blocking_trx_id', 'blocking_thread', 'blocking_query', 'blocking_user', 'blocking_host']
    field_types = ['integer', 'integer', 'string', 'string', 'string', 'string',
                   'integer', 'integer', 'string', 'string', 'string']

    if (versions['type'] == 'MariaDB' or
       (versions['major_version'] == 5 and versions['minor_version'] >= 5)):

        field_values = execute_query(cursor, query)
        print_influx_line_protocol(measurement, tag_keys, tag_values, field_keys, field_values, field_types, increment_ts=True)

    logging.info('Successfully queried for blocking sessions')

def gather_slow_queries(cursor, host):
    query = ('select start_time, user_host, query_time, lock_time, rows_sent, rows_examined, db, '
             'last_insert_id, insert_id, server_id, sql_text, thread_id from mysql.slow_log '
             'where addtime(start_time,query_time) > date_sub(now(), interval 2 minute);')

    measurement = 'mysql_slow'
    tag_keys = ['host']
    tag_values = [host]
    field_keys = ['start_time', 'user_host', 'query_time', 'lock_time', 'rows_sent', 'rows_examined', 'db',
                  'last_insert_id', 'insert_id', 'server_id', 'sql_text', 'thread_id']
    field_types = ['string', 'string', 'string', 'string', 'integer', 'integer', 'string',
                  'integer', 'integer', 'integer', 'string', 'integer']

    if variable_is_on(cursor,'slow_query_log'):
        field_values = execute_query(cursor, query)
        print_influx_line_protocol(measurement, tag_keys, tag_values, field_keys, field_values, field_types, ts_field='start_time')

    logging.info('Successfully queried for blocking sessions')

def gather_query_response_time(cursor, host):
    count_query = 'SELECT count from information_schema.query_response_time order by time asc'
    sum_query = 'SELECT SUM(total), SUM(count) from information_schema.query_response_time'
    measurement = 'mysql_query_response'
    tag_keys = ['host']
    tag_values = [host]
    field_keys = ['sum_total', 'sum_count', '1us_count', '10us_count', '100us_count','1ms_count', '10ms_count', '100ms_count',
                  '1s_count', '10s_count', '100s_count', '1000s_count', '10000s_count', '100000s_count', '1000000s_count', 'too_long_count']
    field_types = ['float', 'integer', 'integer', 'integer', 'integer', 'integer', 'integer', 'integer', 'integer',
                   'integer', 'integer', 'integer', 'integer', 'integer', 'integer', 'integer']

    if variable_is_on(cursor,'query_response_time_stats'):
        try:
            data = execute_query(cursor, sum_query)
            sum_query_response = [float(data[0][0]), int(data[0][1])]

            data = execute_query(cursor, count_query)
            field_values = [[x for x in sum_query_response] + [int(x[0]) for x in data]]
        except IndexError:
            return

        print_influx_line_protocol(measurement, tag_keys, tag_values, field_keys, field_values, field_types)

        logging.info('Successfully queried for query response time')

def gather_userstats(cursor, host, versions):
    query = 'show user_statistics'
    measurement = 'mysql_userstat'
    tag_keys = ['host','user']
    field_keys = ['total_connections', 'concurrent_connections', 'connected_time', 'busy_time', 'cpu_time', 'bytes_received', 'bytes_sent',
                  'binlog_bytes_written', 'rows_read', 'rows_sent', 'rows_deleted', 'rows_inserted', 'rows_updated', 'select_commands',
                  'update_commands', 'other_commands', 'commit_transactions', 'rollback_transactions', 'denied_connections', 'lost_connections',
                  'access_denied', 'empty_queries', 'total_ssl_connections', 'max_statement_time_exceeded']
    field_types = ['integer', 'integer', 'integer', 'float', 'float', 'integer', 'integer',
                   'integer', 'integer', 'integer', 'integer', 'integer', 'integer', 'integer',
                   'integer', 'integer', 'integer', 'integer', 'integer', 'integer',
                   'integer', 'integer', 'integer', 'integer']

    if variable_is_on(cursor,'userstat'):
        # total_ssl_connections and max_statement_time_exceeded not available in MariaDB < 10.1.1
        if (versions['major_version'] < 10 or
           (versions['major_version'] == 10 and versions['minor_version'] == 1 and versions['patch_number'] < 1)):
            field_keys = field_keys[:-2]
            field_types = field_types[:-2]
        data = execute_query(cursor, query)
        field_values = [x[1:] for x in data]
        tag_values = [host, [x[0] for x in data]]
        print_influx_line_protocol(measurement, tag_keys, tag_values, field_keys, field_values, field_types)
        logging.info('Successfully queried for user statistics')

def get_version(cursor):
    try:
        version = cursor.execute('SELECT VERSION()')
        version = cursor.fetchone()[0]
    except MySQLdb.Warning as e:
        logging.warning(e[0])
    except MySQLdb.Error as e:
        logging.error('Failed to get DB version - ' + e[1] + '(' + str(e[0]) + ')')
        sys.exit(0)

    version_number = version.split('-')[0]
    versions = { 'major_version': int(version_number.split('.')[0]),
                 'minor_version': int(version_number.split('.')[1]),
                 'patch_number': int(version_number.split('.')[2]),
                 'type': 'MariaDB' if 'MariaDB' in version.split('.')[2] else 'MySQL'
               }
    return versions

def variable_is_on(cursor, variable):
    query = 'show variables like \'' + variable + '\''
    data = execute_query(cursor, query)

    try:
        value = data[0][1]
    except IndexError:
        value = None

    if value == 'ON':
        return True
    else:
        return False

def execute_query(cursor, query):
    try:
        cursor.execute(query)
    except MySQLdb.Warning as e:
        logging.warning(e[0])
    except MySQLdb.Error as e:
        logging.error('Failed to execute query [' + query + '] - ' + e[1] + '(' + str(e[0]) + ')')
        return []

    try:
        data = cursor.fetchall()
    except MySQLdb.Warning as e:
        logging.warning(e[0])
    except MySQLdb.Error as e:
        logging.error('Failed to fetch data for query [' + query + '] - ' + e[1] + '(' + str(e[0]) + ')')
        return []

    return data

def print_influx_line_protocol(measurement, tag_keys, tag_values, field_keys, field_values, field_types, ts_field=None, ts_format=None, increment_ts=False):
    # If there are multiple measurements with the same name, tags, fields and timestamp they overwrite
    # each other in InfluxDB. Add 1ms to timestamp to avoid this. Requires precision = "1ms" in
    # Telegraf configuration
    timestamp = int(time.time())*(10**9)
    epoch = datetime.datetime.utcfromtimestamp(0)
    if ts_field != None:
        ts_index = field_keys.index(ts_field)

    for i,val in enumerate(field_values):
        if ts_format != None:
            ts_datetime = datetime.strptime(field_values[i][ts_index], ts_format)
            timestamp = int((ts_datetime - epoch).total_seconds()*(10**9))
        elif ts_field != None:
            timestamp = int((field_values[i][ts_index] - epoch).total_seconds()*(10**9))
        if increment_ts:
            timestamp = timestamp + i*(10**6)
        tags = ilp_join_tags(tag_keys, tag_values, i)
        fields = ilp_join_fields(field_keys, field_values[i], field_types)
        print measurement + ',' + ','.join(tags) + ' ' + ','.join(fields) + ' ' + str(timestamp)

def ilp_join_tags(keys, values, index):
    joined_tags = []
    for i, key in enumerate(keys):
        if isinstance(values[i], list):
            joined_tags.append(key + '=' + str(values[i][index]))
        else:
            joined_tags.append(key + '=' + str(values[i]))
    return joined_tags

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

if __name__ == "__main__":
    main()
