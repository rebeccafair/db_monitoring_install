Note: To export dashboards from the Grafana API in a format that can be imported again use
curl -XGET 'http://admin:admin@grafana.host:3000/api/dashboards/db/dashboard-name' | jq '{dashboard: .dashboard}'
May also have to change id to null if creating a new dashboard.
-api.json files have been exported in this way via the api, files without -api have been exported manually through the web interface.
