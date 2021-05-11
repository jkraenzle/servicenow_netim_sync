# Script for synchronization of ServiceNow CMDB to NetIM

# Devices in ServiceNow -> Devices in NetIM
# Locations in ServiceNow -> Sites / Locations in NetIM
# Create Custom Attributes for:
# * Date/time of synchronization

import argparse
import csv
import datetime
import getpass
import logging
import sys
import yaml

#from ServiceNowAPI.servicenow import servicenow_devices_get, \
#	servicenow_device_filter_create, \
#	servicenow_locations_get, \
#	servicenow_relationships_get

import steelscript
from steelscript.netim.core import NetIM
from steelscript.common.service import UserAuth, Auth

logging.captureWarnings(True)
logger = logging.getLogger(__name__)

# Uncomment to send logging to stdout (print)
#logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

SERVICENOW_NETIM_SYNC_CUSTOM_ATTRIBUTE_LASTSYNCED = 'Last Synchronized with CMDB'
SERVICENOW_NETIM_SYNC_CUSTOM_ATTRIBUTE_CMDBCI = 'Configuration ID in CMDB'

# Helper functions

def read_from_csv(file_path):

	reader = None
	fields = []
	rows = []
	try:
		with open(file_path, encoding='iso-8859-1', errors='replace') as file:
			reader = csv.reader(file, skipinitialspace=True, quoting=csv.QUOTE_MINIMAL)
			line_count = 0
			for row in reader:
				if line_count == 0:
					fields += row
				else:
					rows.append(row)
				line_count += 1
	except:
		logger.debug(f"Error reading file {file_path}")
		logger.debug("Unexpected error {}".format(sys.exc_info()[0]))

	return fields, rows

def dictionary_from_csv(file_path):

	reader = None
	fields = []
	rows = []
	try:
		with open(file_path, encoding='iso-8859-1', errors='replace') as file:
			reader = csv.DictReader(file, skipinitialspace=True, quoting=csv.QUOTE_MINIMAL)
			rows = list(reader)
	except:
		logger.debug(f"Error reading file {file_path}")

	return rows

def yamlread(filename):
	try:
		if filename != None:
			with open(filename) as filehandle:
				yamlresult = yaml.load(filehandle)
		else:
			yamlresult = None

	except FileNotFoundError:
		yamlresult = None
	except:
		yamlresult = None

	return yamlresult

def credentials_get(filename):

	credentials = yamlread(filename)
	if credentials == None:
		return None, None, None
	
	hostname = None
	if 'hostname' in credentials:
		hostname = credentials['hostname']
	username = None
	if 'username' in credentials:
		username = credentials['username']
	password = None
	if 'password' in credentials:
		password = credentials['password']

	return hostname, username, password

# ServiceNow / NetIM functions
	
def servicenow_to_netim_synchronization_time_update(netim, device_ids):

	# Add custom attribute to NetIM devices for synchronization time
	attribute_id = netim.get_custom_attribute_id_by_name(SERVICENOW_NETIM_SYNC_CUSTOM_ATTRIBUTE_LASTSYNCED)

	# If the synchronization custom attribute has not been added to NetIM, add it and find its newly
	# created attribute ID
	if attribute_id == -1:
		response = netim.add_custom_attribute(SERVICENOW_NETIM_SYNC_CUSTOM_ATTRIBUTE_LASTSYNCED, 
			"The timestamp of the last update of the device from a CMDB.")
		if response == None:
			logger.debug("Failed to create Custom Attribute for synchronization time in NetIM")

	# Get time stamp value
	current_time = datetime.datetime.now()
	current_time_str = current_time.strftime('%m/%d/%Y %H:%M:%S')
	logger.info(f"Setting synchronization timestamp in NetIM to {current_time_str}")

	response = None
	try:
		# Add time stamp value to NetIM
		response = netim.import_custom_attribute_values_for_devices(device_ids, 
			SERVICENOW_NETIM_SYNC_CUSTOM_ATTRIBUTE_LASTSYNCED, current_time_str) 
	except NameError as e:
		logger.debug(f"Name error: {e}")
	except:
		logger.debug("Exception when importing Custom Attribute values for devices")
		logger.debug("Unexpected error {}".format(sys.exc_info()[0]))

	return response


SERVICENOW_NETIM_CSV_DEVICES_NAME = 'Name'
SERVICENOW_NETIM_CSV_DEVICES_CMDBCI = 'CI ID'
SERVICENOW_NETIM_CSV_DEVICES_ADDRESS = 'IP Address'
SERVICENOW_NETIM_CSV_DEVICES_LOCATION = 'Location'

SERVICENOW_NETIM_CSV_LOCATIONS_NAME = 'Name'
SERVICENOW_NETIM_CSV_LOCATIONS_CITY = 'City'
SERVICENOW_NETIM_CSV_LOCATIONS_REGION = 'State / Province'
SERVICENOW_NETIM_CSV_LOCATIONS_COUNTRY = 'Country'
SERVICENOW_NETIM_CSV_LOCATIONS_LATITUDE = 'Latitude'
SERVICENOW_NETIM_CSV_LOCATIONS_LONGITUDE = 'Longitude'

SERVICENOW_NETIM_SITE_NAME = 'name'
SERVICENOW_NETIM_SITE_COUNTRY = 'country'
SERVICENOW_NETIM_SITE_REGION = 'region'
SERVICENOW_NETIM_SITE_CITY = 'city'
SERVICENOW_NETIM_SITE_LATITUDE = 'latitude'
SERVICENOW_NETIM_SITE_LONGITUDE = 'longitude'

SERVICENOW_NETIM_COUNTRY_NAME = 'name'
SERVICENOW_NETIM_COUNTRY_ID = 'id'
SERVICENOW_NETIM_REGION_NAME = 'name'
SERVICENOW_NETIM_REGION_ID = 'id'
SERVICENOW_NETIM_CITY_NAME = 'name'

SERVICENOW_NETIM_DEVICE_NAME = 'name'
SERVICENOW_NETIM_DEVICE_PRIMARYADDRESS = 'primaryAddress'

def servicenow_netim_csv_import(devices_csv, locations_csv):

	# Read files and find required fields
	servicenow_devices = dictionary_from_csv('input/devices.csv')
	if servicenow_devices == None or len(servicenow_devices) == 0:
		logger.debug("Device CSV input did not include the expected fields. Please correct and re-run script.")
		return

	servicenow_locations = dictionary_from_csv('input/locations.csv')
	if servicenow_locations == None or len(servicenow_locations) == 0:
		logger.debug("Locations CSV input did not include the expected fields. Please correct and re-run script.")
		return

	return servicenow_devices, servicenow_locations	

SERVICENOW_NETIM_LOCATION_COMPARISON_MATCH = 'match_all'
SERVICENOW_NETIM_LOCATION_COMPARISON_COUNTRY_EMPTY = 'country_empty'
SERVICENOW_NETIM_LOCATION_COMPARISON_COUNTRY_NOT_FOUND = 'country_not_found'
SERVICENOW_NETIM_LOCATION_COMPARISON_REGION_EMPTY = 'region_empty'
SERVICENOW_NETIM_LOCATION_COMPARISON_REGION_NOT_FOUND = 'region_not_found'
SERVICENOW_NETIM_LOCATION_COMPARISON_CITY_EMPTY = 'city_empty'
SERVICENOW_NETIM_LOCATION_COMPARISON_CITY_NOT_FOUND = 'city_not_found'
SERVICENOW_NETIM_LOCATION_COMPARISON_COORDINATES_MISSING = 'coordinates_missing'

SERVICENOW_NETIM_COUNTRY_NAME = 'name'

def servicenow_netim_location_comparison (netim, sites_to_import):

	comparison_dict = {}
	comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_MATCH] = []
	comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COUNTRY_EMPTY] = []
	comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COUNTRY_NOT_FOUND] = []
	comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_REGION_EMPTY] = []
	comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_REGION_NOT_FOUND] = []
	comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_CITY_EMPTY] = []
	comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_CITY_NOT_FOUND] = []
	comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COORDINATES_MISSING] = []

	region_cache = {}
	city_cache = {}

	countries_json = netim.get_all_countries()
	countries = []
	if 'items' in countries_json:
		countries = countries_json['items']

	for site in sites_to_import:
		# Do a quick check in this loop to see if coordinates are missing
		site_name = site[SERVICENOW_NETIM_SITE_NAME]
		if site[SERVICENOW_NETIM_SITE_LATITUDE] == "" or site[SERVICENOW_NETIM_SITE_LONGITUDE] == "":
			comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COORDINATES_MISSING].append(site_name)

		# Now, begin rest of data comparison to see what matches for this site that is being considered for import
		country_empty = country_found = region_empty = region_found = city_empty = city_found = False
	
		# Case: Country is empty
		site_country = site[SERVICENOW_NETIM_SITE_COUNTRY]
		if site_country  == "":
			country_empty = True
			pass	

		for country in countries:
			country_name = country[SERVICENOW_NETIM_COUNTRY_NAME]
			if site_country == country_name:
				# Case: Country is found, but region not specified
				site_region = site[SERVICENOW_NETIM_SITE_REGION]
				if site_region == None or site_region == "":
					country_found = region_empty = True
					break

				# Use caches so not requesting region or city data multiple times
				regions = []
				if country_name in region_cache:
					regions = region_cache[country_name]
				else:
					regions_json = netim.get_regions_by_country_id(country[SERVICENOW_NETIM_COUNTRY_ID])
					if regions_json != None and 'items' in regions_json:
						regions = regions_json['items']
						region_cache[country_name] = regions

				for region in regions:
					region_name = region[SERVICENOW_NETIM_REGION_NAME]
					if site_region == region_name:
						site_city = site[SERVICENOW_NETIM_SITE_CITY]
						if site_city == None or site_city == "":
							# Case: Country, region found; city empty
							country_found = region_found = city_empty = True
							break
						
						# Use cache
						cities = []
						if region_name in city_cache:
							cities = city_cache[region_name]
						else:
							cities_json = netim.get_cities_by_region_id(region[SERVICENOW_NETIM_REGION_ID])
							if cities_json != None and 'items' in cities_json:
								cities = cities_json['items']
								city_cache[region_name] = cities

						for city in cities:
							city_name = city[SERVICENOW_NETIM_CITY_NAME]
							if site['city'] == city_name:
								# Case: All match
								country_found = region_found = city_found = True
								break	
						# Case: Country and region match, but city not found
						country_found = region_found = True
						break
				# Case: Country found, but region not found; city requires region
				country_found = True
				break

		if country_found == True:
			if region_found == True:
				if city_found == True:
					comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_MATCH].append(site_name)
				elif city_empty == True:
					comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_CITY_EMPTY].append(site_name)
				else:
					comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_CITY_NOT_FOUND] = []
			elif region_empty == True:
				comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_REGION_EMPTY].append(site_name)
			else:
				comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_REGION_NOT_FOUND].append(site_name)
		elif country_empty == True:
			comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COUNTRY_EMPTY].append(site_name)
		else:
			comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COUNTRY_NOT_FOUND].append(site_name)

	return comparison_dict

def main ():

	parser = argparse.ArgumentParser(description="Python utility to compare data from ServiceNow to \
		data in NetIM")
	parser.add_argument('--servicenow_yml', help='ServiceNow account credentials')
	parser.add_argument('--netim_yml', help='NetIM account credentials')
	parser.add_argument('--servicenow_devices_csv', help='Export of CSV devices from ServiceNow')
	parser.add_argument('--servicenow_locations_csv', help='Export of CSV devices from ServiceNow')
	parser.add_argument('--summary', type=bool, help='Print summary or full report detail')
	args = parser.parse_args()

	print("")
	print("NetIM to ServiceNow Comparison Report")
	print("---------------------------------------------------------------------------------------------------")

	if args.servicenow_yml == None or args.servicenow_yml == "":
		text = 'spreadsheets'
	else:
		text = 'API'
	print("")
	print(f"Step 1 of 6: Getting device and location information from ServiceNow {text}")
	if args.servicenow_yml != None:
		# Pull devices and locations from ServiceNow
		servicenow_devices = None
		servicenow_locations = None
	elif args.servicenow_devices_csv != None and args.servicenow_locations_csv != None:
		# Pull devices and locations from CSV spreadsheets
		servicenow_devices, servicenow_locations = servicenow_netim_csv_import(args.servicenow_devices_csv,
			args.servicenow_locations_csv)
	else:
		# Notify user that information is missing
		pass

	# Get unique list of locations from the devices that may be imported	
	devlocation_set = set()
	for device in servicenow_devices:
		devlocation = device[SERVICENOW_NETIM_CSV_DEVICES_LOCATION]
		devlocation_set.update([devlocation.strip()])
	servicenow_devlocations = list(devlocation_set)

	print("Step 2 of 6: Identifying sites that have actively polled devices")
	# Get the list of locations that are assigned to devices being imported into ServiceNow
	# and use them to pull the required information from the locations table
	sites_to_import = []
	for devlocation_name in servicenow_devlocations:
		if devlocation_name == "":
			pass
		for location in servicenow_locations:
			if devlocation_name == location[SERVICENOW_NETIM_CSV_LOCATIONS_NAME].strip():
				site_to_import = \
					{SERVICENOW_NETIM_SITE_NAME:location[SERVICENOW_NETIM_CSV_LOCATIONS_NAME],
					SERVICENOW_NETIM_SITE_CITY:location[SERVICENOW_NETIM_CSV_LOCATIONS_CITY],
					SERVICENOW_NETIM_SITE_REGION:location[SERVICENOW_NETIM_CSV_LOCATIONS_REGION],
					SERVICENOW_NETIM_SITE_COUNTRY:location[SERVICENOW_NETIM_CSV_LOCATIONS_COUNTRY],
					SERVICENOW_NETIM_SITE_LONGITUDE:location[SERVICENOW_NETIM_CSV_LOCATIONS_LONGITUDE],
					SERVICENOW_NETIM_SITE_LATITUDE:location[SERVICENOW_NETIM_CSV_LOCATIONS_LATITUDE]}
				sites_to_import.append(site_to_import)

	#---- NetIM API -----

	netim_hostname, netim_username, netim_password = credentials_get(args.netim_yml)
	print(f"Step 3 of 6: Authenticating with NetIM {netim_hostname}")
	# Authentication to NetIM

	try:
		auth = UserAuth(netim_username, netim_password, method=Auth.BASIC)
		netim = NetIM(netim_hostname, auth)
	except:
		logger.debug("Unexpected error {}".format(sys.exc_info()[0]))
		return

	#----- Pull devices to being comparisons -----
	print("Step 4 of 6: Comparing devices in NetIM with the spreadsheets from ServiceNow")
	# Check device name, access address, CMDB CI
	netim_devices_json = netim.get_all_devices()
	netim_devices = []
	if 'items' in netim_devices_json:
		netim_devices = netim_devices_json['items']

	new_devices = []
	devices_with_no_updates = []
	different_addresses = []

	for servicenow_device in servicenow_devices:
		found_device = found_address = False
		servicenow_device_name = servicenow_device[SERVICENOW_NETIM_CSV_DEVICES_NAME]
		for netim_device in netim_devices:
			netim_device_name = netim_device[SERVICENOW_NETIM_DEVICE_NAME]
			if servicenow_device_name == netim_device_name:
				netim_device_address = netim_device[SERVICENOW_NETIM_DEVICE_PRIMARYADDRESS]
				if servicenow_device[SERVICENOW_NETIM_CSV_DEVICES_ADDRESS] != netim_device_address:
					found_device = found_address = True
					break
				found_device = True
				break

		if found_device == True:
			if different_addresses == True:
				devices_with_no_updates.append(servicenow_device_name)
			else:
				different_addresses.append(servicenow_device_name)
		else:
			new_devices.append(servicenow_device_name)

	# Report output
	new_devices_count = len(new_devices)
	print("")
	print(f"There are {new_devices_count} devices that do not exist in NetIM.")
	if new_devices_count > 10 and args.summary:
		print("Displaying the first 10 devices:")
		print(new_devices[:10])	
	else:
		print(new_devices)

	different_addresses_count = len(different_addresses)
	if different_addresses_count > 0:	
		print("")
		print(f"There are {different_addresses_count} device(s) that exist in NetIM, but have different access addresses.")
		if different_addresses_count > 10 and args.summary:
			print("Displaying the first 10 devices:")
			print(different_addresses[:10])
		else:
			print(different_addresses)
	
	no_update_count = len(devices_with_no_updates)
	if no_update_count > 0:
		print("")
		print(f"There are {no_update_count} device(s) that have matching names and access addresses in NetIM.")
		if no_update_count > 10 and args.summary:
			print("Displaying the first 10 devices:")
			print(devices_with_no_updates[:10])
		else:
			print("The following ServiceNow devices have matching names and access IP addresses in NetIM:")
			print(devices_with_no_updates)
		print("")

	#----- Code that compares existing groups/sites to those in file -----

	print("")
	print("Step 5 of 6: Comparing site and groups in NetIM with the spreadsheets from ServiceNow")
	print("")
	groups_json = netim.get_all_groups()
	groups = []
	if 'items' in groups_json:
		groups = groups_json['items']

	# Compare locations to import with existing locations
	existing_sites = []
	new_sites = []
	for site in sites_to_import:
		for group in groups:
			site_name = site[SERVICENOW_NETIM_SITE_NAME]
			if site_name == group[SERVICENOW_NETIM_SITE_NAME]:
				existing_sites.append(site_name)
				break

		new_sites.append(site_name)

	new_sites_count = len(new_sites)
	print(f"The following {new_sites_count} site(s) are associated with devices and are not defined in NetIM:")
	if new_sites_count > 10 and args.summary:
		print("Displaying first 10 sites:")
		print(new_sites[:10])
	else:
		print(new_sites)

	print("")
	existing_site_count = len(existing_sites)
	if existing_site_count == 0:
		print("No existing sites matched in NetIM database.")
	elif existing_site_count > 10 and args.summary:
		print("Displaying the first 10 sites:")
		print("The following {existing_site_count} site(s) have been defined in NetIM:")
	else:
		print(existing_sites)
	print("")

	#----- Code to compare geographical information -----

	print("")
	print("Step 6 of 6: Comparing location information in NetIM with the spreadsheets from ServiceNow")
	print("")


	comparison_dict = servicenow_netim_location_comparison(netim, sites_to_import)

	if len(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_MATCH]) > 0:
		print("The following sites had country, region, city that were found in NetIM database:")
		print(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_MATCH])
	if len(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_CITY_NOT_FOUND]) > 0:
		print("The following sites had country and region found in NetIM database, but the city is not in database:")
		print(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_CITY_NOT_FOUND])
	if len(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_CITY_EMPTY]) > 0:
		print("The following sites had country and region found in NetIM database, but city field is empty in input:")
		print(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_CITY_EMPTY])
	if len(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_REGION_NOT_FOUND]) > 0:
		print("The following sites had country found in NetIM database, but region is not in database:")
		print(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_REGION_NOT_FOUND])
	if len(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_REGION_EMPTY]) > 0:
		print("The following sites had country found in NetIM database, but region field is empty in input:")
		print(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_REGION_EMPTY])
	if len(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COUNTRY_NOT_FOUND]) > 0:
		print("The following sites had a country that does not match an entry in the NetIM database:")
		print(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COUNTRY_NOT_FOUND])
	if len(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COUNTRY_EMPTY]) > 0:
		print("The following sites had no country listed in input:")
		print(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COUNTRY_EMPTY])

	print("")
	if len(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COORDINATES_MISSING]) > 0:
		print("The following sites had missing coordinates (latitude, longitude):")
		print(comparison_dict[SERVICENOW_NETIM_LOCATION_COMPARISON_COORDINATES_MISSING])

	#-----
	# Sync list of devices to NetIM
	#netim_devices_import(netim_credentials, servicenow_devices)

	# Sync list of locations to NetIM
	#netim_locations_import(netim_credentials, servicenow_locations)

	# Set up a process to track when devices were last synchronized with the CMDB. This allows an
	# automated way to determine if a device should be aged out because it is no longer tracked in
	# the CMDB
	#response = servicenow_to_netim_synchronization_time_update(netim, updated_device_ids)
	#print(response)	

	return

if __name__ == "__main__":
	main ()
