# Installation Instructions for Scientific Linux 7
To get a fully working TICK stack to monitor a MySQL database there are several steps:

1. [Install InfluxDB](#1-install-influxdb)
2. [Get some data into InfluxDB](#2-get-some-data-into-influxdb)
    1. [Install MySQL](#i-install-mysql)
    2. [Install Telegraf on MySQL host](#ii-install-telegraf-on-mysql-host)
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
First on the InfluxDB host, create a user in InfluxDB to allow Telegraf to write metrics:
```
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

## 4. Install a web UI
### Install Grafana
### Install Chronograf
