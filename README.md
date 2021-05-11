This project contains examples showcasing NetIM SteelScript by synchronizing data with a ServiceNow instance.

Current script runs as follows:

python3 servicenow_to_netim.py --netim_yml netim_account.yaml --servicenow_devices_csv devices.csv --servicenow_locations_csv locations.csv [--summary True]

where:

netim_account.yaml
follows the format of example_account.yaml

devices.csv
has headers [Name, Location, IP Address, CI ID]

locations.csv
has headers [Name, City, State / Province, Country, Longitude, Latitude]

summary 
is optionally provided to reduce the output for some lists to top 10
