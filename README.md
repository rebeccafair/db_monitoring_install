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
First on the InfluxDB host, create a telegraf DB and user in InfluxDB to allow Telegraf to write metrics:
```
influx -username admin -password 'admin' -execute "create database telegraf"
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

Edit the configuration file at `/etc/telegraf/telegraf.conf` and make the following configuration changes:  
In the `[agent]` section set `interval = "60s"` and `flush_interval = "60s"`  
In the `[[outputs.influxdb]]` section set `urls` to the InfluxDB host and port (default 8086) and set `username = "telegraf"` and `password = "telegraf"`  
Uncomment `[[inputs.mysql]]` to enable MySQL metric collection and set `servers` to the MySQL host with the telegraf user and password e.g. `servers = ["telegraf:telegraf@tcp(localhost:3306)/?tls=false"]`

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
In the `[[influxdb]]` set `urls` to the InfluxDB host and `username = "kapacitor"` and `password = "kapacitor"`  

Start the Kapacitor service: `sudo systemctl start kapacitor`

Add an example alert rule to Kapacitor: `kapacitor define load_alert -type stream -tick kapacitor/load_alert.tick -dbrp telegraf.autogen`

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

Access the Grafana interface on port 3000 and log in with username and password
'admin'. Click on the grafana symbol in the top-left and go to Dashboards >
Import and import the dashboards in the grafana_dashboards folder in this repo.
Hopefully you can see some data!

### Install Chronograf

