This project contains examples showcasing NetIM SteelScript by synchronizing data with a ServiceNow instance.

Current script runs as follows:

python3 sync_servicenow.py --netim_yml netim_account_example.yaml --servicenow_yml servicenow_account_example.yaml [--summary True] [--reconcile True]

where:

netim_account.yaml follows the example format

servicenow_account_example.yml follows the example format

summary is optionally provided to reduce the output for some lists to top 10

reconcile adds new devices and related groups

OR

python3 sync_servicenow.py --netim_yml netim_account_example.yaml --servicenow_devices_csv devices.csv --servicenow_locations_csv locations.csv [--summary True] [--reconcile True]

where:

netim_account.yaml follows the example format

devices.csv has headers [Name, Location, IP Address, CI ID]

locations.csv has headers [Name, City, State / Province, Country, Longitude, Latitude]

summary is optionally provided to reduce the output for some lists to top 10

reconcile adds new devices and related groups
