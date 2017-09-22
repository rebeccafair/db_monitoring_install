# Installation Instructions for Scientific Linux 7
To get a fully working TICK stack to monitor a MySQL database there are several steps:

1. [Install InfluxDB](#1-install-influxdb)
2. [Get some data into InfluxDB](#2-get-some-data-into-influxdb)
    1. [Install MySQL](#i-install-mysql)
    2. [Install Telegraf on MySQL host](#ii-install-telegraf)
3. [Install Kapacitor](#3-install-kapacitor)
4. [Install a Web UI](#4-install-a-web-ui)
    * [Install Grafana](#install-grafana)
    * [Install Chronograf](#install-chronograf)

## 1. Install InfluxDB
Download and install desired version from https://repos.influxdata.com/rhel/6/x86_64/stable/ (recommended 1.3.5):
```
wget https://repos.influxdata.com/rhel/6/x86_64/stable/influxdb-1.3.5.x86_64.rpm`
sudo yum localinstall influxdb-1.3.5.x86_64.rpm
rm influxdb-1.3.5.x86_64.rpm
```


Now edit the configuration file at `/etc/influxdb/influxdb.conf` and make some configuration changes:  
In the main configuration set `reporting-disabled = true`  
In the `[http]` section set `auth-enabled = true`


Start the InfluxDB service:  
`sudo systemctl start influxdb`

Create an admin user:  
`influx -execute "create user admin with password 'admin' with all privileges"`

## 2. Get some data into InfluxDB
To get some data into InfluxDB we need a MySQL database that we want to
monitor. If you already have a MySQL instance installed skip to step ii. The
MySQL server should preferably be on a different host to InfluxDB.

### i. Install MySQL
Download and install RPM package
```
wget https://dev.mysql.com/get/mysql57-community-release-el7-11.noarch.rpm
sudo yum localinstall mysql57-community-release-el7-11.noarch.rpm
rm mysql57-community-release-el7-11.noarch.rpm
sudo yum install mysql-community-server
```

Start MySQL server:  
`sudo systemctl start mysqld`

Get the automatically generated root password:  
`sudo grep 'temporary password' /var/log/mysqld.log`

Log in using the password:  
`mysql -u root -p`

In MySQL shell, uninstall validate_password plugin (just for simplicity) and change root password:
```
alter user 'root'@'localhost' identified by 'Password!1';
uninstall plugin validate_password;
alter user 'root'@'localhost' identified by 'root';
```

Now set the long query time to some appropriate value (default 10.0s), change the slow query log file and switch slow query logging on
```
mysql -u root -proot -e "set global slow_query_log_file = "/var/lib/mysql/slow.log";"
mysql -u root -proot -e "set global long_query_time = 1.0;"
mysql -u root -proot -e "set global slow_query_log = 'ON';"
```

To get some dummy data into MySQL you can use the following GitHub repo:
```
git clone https://github.com/datacharmer/test_db.git
cd test_db
mysql -u root -proot < employees_partitioned.sql
```

To generate some random queries on this DB, first create a reader user:  
```
mysql -u root -proot -e "create user 'reader' identified by 'reader';"
mysql -u root -proot -e "grant select on employees.* to reader;"
```
Now install python MySQL module: `sudo yum install MySQL-python`  
Run the provided script `query.py` in the background to generate random queries every 0-60 seconds:  
`nohup python mysql/query.py > /dev/null 2>&1 &`  
To see the process again: `ps ax | grep query.py`

### ii. Install Telegraf
First on the InfluxDB host, create a telegraf DB (with retention policy) and user in InfluxDB to allow Telegraf to write metrics:
```
influx -username admin -password 'admin' -execute "create database telegraf"
influx -username admin -password 'admin' -execute "create retention policy '30_days' on 'telegraf' duration 30d replication 1 default"
influx -username admin -password 'admin' -execute "create user telegraf with password 'telegraf'"
influx -username admin -password 'admin' -execute "grant write on telegraf to telegraf"
```

Now on the MySQL host, create a user in MySQL to allow Telegraf to obtain MySQL metrics:
```
mysql -u root -proot -e "grant select, process, replication client on *.* to 'telegraf'@'localhost' identified by 'telegraf';"
```

On the MySQL host, download and install desired Telegraf version from https://repos.influxdata.com/rhel/6/x86_64/stable/ (recommended 1.3.5):
```
wget https://repos.influxdata.com/rhel/6/x86_64/stable/telegraf-1.3.5-1.x86_64.rpm
sudo yum localinstall telegraf-1.3.5-1.x86_64.rpm
rm telegraf-1.3.5-1.x86_64.rpm
```

To collect custom MySQL data/metrics, copy the python script provided to the Telegraf plugin directory:
```
sudo cp telegraf/query_mysql.py /etc/telegraf/telegraf.d/
```

Give Telegraf read access to any files that need to be monitored (such as the slow query log):
```
sudo setfacl -m 'user:telegraf:r' /tmp/slow.log
```

Edit the configuration file at `/etc/telegraf/telegraf.conf` and make the following configuration changes:  
In the `[agent]` section set `interval = "60s"`, `flush_interval = "60s"` and `precision = "1ms"`. Precision must be set as when collecting blocking sessions with the python script, 1ms is added to the timestamp for each session to avoid clashes.  
In the `[[outputs.influxdb]]` section set `urls` to the InfluxDB host and port (default 8086) and set `username = "telegraf"` and `password = "telegraf"`.  
Uncomment `[[inputs.mysql]]` to enable MySQL metric collection and set `servers` to the MySQL host with the telegraf user and password e.g. `servers = ["telegraf:telegraf@tcp(localhost:3306)/?tls=false"]`.  
In the `[[inputs.mysql]]` section set `gather_innodb_metrics = true` to collect lots of InnoDB metrics, these are collected by the command `SELECT NAME, COUNT FROM information_schema.INNODB_METRICS WHERE status='enabled';`. Many are enabled by default, but to get the full set of InnoDB metrics use `set global innodb_monitor_enable = 'all';` in the MySQL shell. These are required by many of the graphs in the 'InnoDB Metrics Advanced' Grafana dashboard.  
In the `[[inputs.mysql]]` section set `interval_slow` to a value higher than 0 to collect global status variables.  
In the `[[inputs.mysql]]` section set `gather_process_list = true` to collect information about thread activity.  
Uncomment any other desired MySQL metrics to be collected.  
In the `[[inputs.exec]]` section set `commands = ["python /etc/telegraf/telegraf.d/query_mysql.py"]` and `data_format = "influx"` to enable collection of custom MySQL data such as blocking sessions. Command-line arguments can also be used to change the script logging level etc., see the script for details.  

### Monitoring the slow log
First switch the MySQL slow log on and set the long_query_time to some appropriate value:
```
mysql -u root -proot -e "set global slow_query_log = 'ON';"
mysql -u root -proot -e "set global long_query_time = 1.0;"
```
As currently Telegraf can only read single-line log events, we need to merge the multi-line events in the slow log to one line. To do this run the transform_slowlog.sh script:
```
nohup sudo bash transform_slowlog.sh > /tmp/slow.log 2> /dev/null &
```
Now change the Telegraf configuration to read the newly formatted slow log. In the `[[inputs.logparser]]` section set `files = ["/tmp/slow.log"]` , `patterns = ["# Time: %{DATA:timestamp} # User@Host: %{NOTSPACE:query_user:string} @ %{NOTSPACE:query_host:string} %{GREEDYDATA} # Query_time: %{NUMBER:query_time:float}  Lock_time: %{NUMBER:lock_time:float} Rows_sent: %{INT:rows_sent:int}  Rows_examined: %{INT:rows_examined:int} SET timestamp=%{INT};%{GREEDYDATA:query:string};"]` and `measurement = "mysql_slow"`

Start Telegraf service: `sudo systemctl start telegraf`

## 3. Install Kapacitor
First create a Kapacitor user in InfluxDB. This must be an admin user to allow Kapacitor to subscribe to InfluxDB data:  
`influx -username admin -password 'admin' -execute "create user kapacitor with password 'kapacitor' with all privileges"`

On the InfluxDB host, download and install desired version from https://repos.influxdata.com/rhel/6/x86_64/stable/ (recommended 1.3.2):
```
wget https://repos.influxdata.com/rhel/6/x86_64/stable/kapacitor-1.3.2.x86_64.rpm
sudo yum localinstall kapacitor-1.3.2.x86_64.rpm
rm kapacitor-1.3.2.x86_64.rpm
```

Edit the configuration file at `/etc/kapacitor/kapacitor.conf`:  
In the main configuration set `hostname` to the Kapacitor host  
In the `[[influxdb]]` section set `urls` to the InfluxDB host and `username = "kapacitor"` and `password = "kapacitor"`  
In the `[[smtp]]` section fill in your SMTP server details to enable email alerting

Start the Kapacitor service: `sudo systemctl start kapacitor`

Add an example alert rule to Kapacitor: `kapacitor define load_alert -type stream -tick kapacitor/load_alert.tick -dbrp telegraf.autogen`  
Enable the rule: `kapacitor enable load_alert`  

## 4. Install a web UI
Install a tool to greate graphs and dashboards. Chronograf is specifically
designed for InfluxDB and can also be used to manage Kapacitor alerts but is
quite new so has fewer options when creating graphs/dashboards than Grafana.

### Install Grafana
Create a user in InfluxDB to read data
```
influx -username admin -password 'admin' -execute "create user grafana with password 'grafana'"
influx -username admin -password 'admin' -execute "grant read on telegraf to grafana"
```

Download and install desired version from https://s3-us-west-2.amazonaws.com/grafana-releases/ (recommended 4.4.3):
```
wget https://s3-us-west-2.amazonaws.com/grafana-releases/release/grafana-4.4.3-1.x86_64.rpm
sudo yum localinstall grafana-4.4.3-1.x86_64.rpm
rm grafana-4.4.3-1.x86_64.rpm
```

Start the Grafana service: `sudo systemctl start grafana-server`

Post the InfluxDB data source to grafana:  
`curl -XPOST 'http://admin:admin@vm19.nubes.stfc.ac.uk:3000/api/datasources' -H 'Content-Type: application/json' -d @grafana/data_sources/influxdb.json`

Change the default organisation name:  
`curl -XPUT 'http://admin:admin@vm19.nubes.stfc.ac.uk:3000/api/org' -H 'Content-Type: application/json' -d '{ "name":"STFC"}'`

In the Grafana configuration file at `/etc/grafana/grafana.ini`:  
Under `[analytics]` set `reporting_enabled = false`  
Under `[auth.anonymous]` set `enabled = true`,`org_name = STFC` and `org_role = Viewer`

Access the Grafana web interface on port 3000 and log in with username and password
'admin'. Click on the grafana symbol in the top-left and go to Dashboards >
Import and import the dashboards in the grafana_dashboards folder in this repo.
Hopefully you can see some data!

### Install Chronograf

Create a user in InfluxDB to read data and create/delete Kapacitor rules
```
influx -username admin -password 'admin' -execute "create user chronograf with password 'chronograf' with all privileges"
influx -username admin -password 'admin' -execute "grant read on telegraf to chronograf"
```

Download and install desired version from https://repos.influxdata.com/rhel/6/x86_64/stable/ (recommended 1.3.7.0):
```
wget https://repos.influxdata.com/rhel/6/x86_64/stable/chronograf-1.3.7.0.x86_64.rpm
sudo yum localinstall chronograf-1.3.7.0.x86_64.rpm
rm chronograf-1.3.7.0.x86_64.rpm
```

Start the Chronograf service: `sudo systemctl start chronograf`

Access the Chronograf web interface on port 8888 and enter the InfluxDB details, with the chronograf user/password. Click on the Host List on the left and you should be able to see your MySQL host. Click on the links under the Apps heading to see some pregenerated dashboards.
