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
Get and install desired version from https://repos.influxdata.com/rhel/6/x86_64/stable/ (recommended 1.3.5):
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
### i. Install MySQL
### ii. Install Telegraf on MySQL host

## 3. Install Kapacitor

## 4. Install a web UI
### Install Grafana
### Install Chronograf
