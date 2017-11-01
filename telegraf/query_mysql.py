"""
    A custom script to gather metrics from a MySQL instance. To be run by the Telegraf exec
    plugin, and prints metrics in Influx line protocol format. To add new metrics create
    a new function gather_* and call it from gather_metrics. The gather_* function must:
    1) Have at least the DB cursor as an argument to enable the DB to be called. It may also
       be helpful to have host as the argument, so the host can be used as a tag value and
       distinguish different DB instances once the metrics are in InfluxDB
    2) Have a query string
    3) Call execute_query to obtain the field values using the query string
    4) Have a measurement string to write the metrics to
    5) Have a list of tag keys and tag values
    6) Have a list of field keys and field values
    7) Call print_influx_line_protocol
"""

import MySQLdb
import warnings
import logging
import argparse
import sys
import os
import time
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
    """ Connect to the DB and gather the metrics specified by the gather_* functions, 
        then close the connection """
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
    """ This queries for slow queries that have finished within the last 2 minutes (although the Telegraf
        exec plugin runs every 1 minute, 2 minutes is chosen to avoid potentially missing any queries due
        to timing). To avoid queries being counted twice, the 'start_time' field is used as the timestamp
        in InfluxDB, so that even if any queries are submitted twice, they will be overwritten as they have
        the same timestamp. """
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

    logging.info('Successfully queried for slow queries')

def gather_query_response_time(cursor, host):
    """ Gathers query response time. Requires the query response time plugin
        which is only available in MariaDB and query_response_time_stats='ON' """
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
    """ Gathers user statistics, is only available in MariaDB and requires userstat ='ON' """
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
    """ Returns a dictionary describing the DB version. Useful for queries 
        that are only valid on certain DB versions """
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
    """ Returns a boolean describing whether a variable is on. Returns false 
        if the varaible doesn't exist. Useful for checking whether it is worth
        executing a query """
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
    """ Tries to execute the query on the DB and fetch the data. Returns an empty
        list in the case of error. Doesn't exit the script so that other metrics can
        be collected even if one query fails """
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
    """ Prints metrics in Influx line protocol format https://docs.influxdata.com/influxdb/v1.3/write_protocols/line_protocol_tutorial/
        for the Telegraf exec plugin to output to InfluxDB. Each line printed is a point to be written to InfluxDB.

        Arguments:
        measurement  -- the InfluxDB measurement to write to
        tag_keys     -- a list of strings of the field names to be used as tags, e.g. ['host','user']
        tag_values   -- a list containing either a single value or list of values for each tag key. There must either be a single tag
                        value for all points that will be written, or a value must be given for each point to be written i.e. the list
                        of values must be of the same length as the numbers of points to be written. e.g. if writing 3 points and using
                        the tag keys ['host','user'], tag_values could be ['vm.stfc.ac.uk',['reader','reader','writer']]
        field_keys   -- a list of strings of the field names to be used e.g. ['waiting_thread','waiting_query']
        field_values -- a 2D list of the field values to be written. The first index is the point to be written and the second index is
                        the field e.g. if writing 2 points and using the field_keys ['waiting_thread','waiting_query'], field_values could
                        be [[12001,'select * from *'],[12002,'select * from *']]
        field_types  -- a list of strings specifying the type of each field. Valid string values are 'string', 'integer' and 'float'
        ts_field     -- a string, if you want to use one of the fields returned by the query as the timestamp in InfluxDB, specify the field name here
        ts_format    -- a string, if the field specified by ts_field isn't a datetime object, ts_format specifies the format to use when converting it
                        into a datetime object. See https://docs.python.org/2/library/datetime.html#strftime-strptime-behavior
        increment_ts -- a boolean, if there are multiple measurements with the same name, tags, fields and timestamp they overwrite
                        each other in InfluxDB. This adds 1ms to the timestamp to avoid this. This is useful when collecting event-based metrics
                        e.g. blocking sessions. For this setting to work it requires precision = '1ms' in the Telegraf configuration """
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
    """ Joins tag keys and values together in Influx line protocol format. Handles both cases where there is
        one tag value for all points and where there is a tag value for each point """
    joined_tags = []
    for i, key in enumerate(keys):
        if isinstance(values[i], list):
            joined_tags.append(key + '=' + str(values[i][index]))
        else:
            joined_tags.append(key + '=' + str(values[i]))
    return joined_tags

def ilp_join_fields(keys, values, types):
    """ Joins field keys and values together in Influx line protocol format. Handles fields differently
        depending on their type"""
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
