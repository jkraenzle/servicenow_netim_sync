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
import time
import yaml

from ServiceNowAPI.servicenow import ServiceNow

import steelscript
from steelscript.common.service import UserAuth, Auth
from steelscript.common.exceptions import RvbdHTTPException
from steelscript.netim.core import NetIM

logging.captureWarnings(True)
logger = logging.getLogger(__name__)

#logging.basicConfig(stream=sys.stdout, level=logging.INFO)
#logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


#----- Helper functions

CSV_ENCODING = 'utf-8-sig'

def read_from_csv(file_path):

	reader = None
	fields = []
	rows = []
	try:
		with open(file_path, encoding=CSV_ENCODING, errors='replace') as file:
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
		with open(file_path, encoding=CSV_ENCODING, errors='replace') as file:
			reader = csv.DictReader(file, skipinitialspace=True, quoting=csv.QUOTE_MINIMAL)
			rows = list(reader)
	except:
		logger.debug(f"Error reading file {file_path}")
		logger.debug("Unexpected error {}".format(sys.exc_info()[0]))

	return rows

def yamlread(filename):
	try:
		if filename != None:
			with open(filename) as filehandle:
				yamlresult = yaml.safe_load(filehandle)
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

def filter_name_value_pair_get(filter):
	if 'name' in filter:
		filter_name = filter['name']
	else:
		filter_name = None
	if 'value' in filter:
		filter_value = filter['value']
	else:
		filter_value = None

	# Handle boolean
	if filter_value == 'True' or filter_value == 'true':
		filter_value = True
	elif filter_value == 'False' or filter_value == 'false':
		filter_value = False

	return filter_name, filter_value

def filter_name_value_pair_create(filter_name, filter_value):
	filter = {}
	filter['name'] = filter_name
	filter['value'] = filter_value
	return filter

def filters_validate(filters):
	valid_filters = []
	for filter in filters:
		if 'name' not in filter:
			logger.info(f"Invalid filter {filter}. No 'name'.")
			continue
		if filter['name'] == '' or filter['name'] == None:
			logger.info(f"Invalid filter {filter}. Filter 'name' is empty.")
			continue
		if 'value' not in filter:
			logger.info(f"Invalid filter {filter}. No 'value'.")
			continue
		if filter['value'] == '' or filter['value'] == None:
			logger.info(f"Invalid filter {filter}. Filter 'value' is empty.")
			continue
		valid_filters.append(filter)
	return valid_filters

def clean(object):

	temp = object
	if type(object) is dict:
		if 'display_value' in object:
			temp = object['display_value']
		elif 'value' in object:
			temp = object['value']

	return temp.strip()

#----- ServiceNow import functions, from API or spreadsheet

def sync_servicenow_resource_value_get(resource):
	if type(resource) is dict and 'value' in resource:
		resource_value = resource['value']
	else:
		resource_value = None

	# Handle boolean
	if resource_value == 'True' or resource_value == 'true':
		resource_value = True
	elif resource_value == 'False' or resource_value == 'false':
		resource_value = False

	return resource_value

def sync_servicenow_resource_display_value_get(resource):
	if type(resource) is dict and 'display_value' in resource:
		resource_display_value = resource['display_value']
	else:
		resource_display_value = None

	# Handle boolean
	if resource_display_value == 'True' or resource_display_value == 'true':
		resource_display_value = True
	elif resource_display_value == 'False' or resource_display_value == 'false':
		resource_display_value = False

	return resource_display_value

def sync_servicenow_devices_filter(devices, include_filters=[], exclude_filters=[]):

	# Validate input
	valid_include_filters = filters_validate(include_filters)
	valid_exclude_filters = filters_validate(exclude_filters)
	logger.info("There are {} valid include filters".format(len(valid_include_filters)))
	logger.info("There are {} valid exclude filters".format(len(valid_exclude_filters)))

	# Filter by inclusion
	included_devices = []
	# If no inclusion filters, include everything
	if len(valid_include_filters) == 0:
		included_devices = devices
	# Otherwise, roll through the inclusion filters and only include things that match one of the filters
	for include_filter in valid_include_filters:
		filter_name, filter_value = filter_name_value_pair_get(include_filter)
		for device in devices:
			if filter_name in device:
				# Check both 'value' and 'display_value' for match
				device_value = sync_servicenow_resource_value_get(device[filter_name])
				if filter_value == device_value:
					included_devices.append(device)
					continue
				device_value = sync_servicenow_resource_display_value_get(device[filter_name])
				if filter_value == device_value:
					included_devices.append(device)
					continue

	# Filter by exclusion
	devices_after_exclusion = []
	# If no exclusion filters, include everything
	if len(valid_exclude_filters) == 0:
		devices_after_exclusion = devices
	# Otherwise, roll through the exclusion filters and exclude things that match any one of the filters
	excluded_devices = []
	for exclude_filter in valid_exclude_filters:
		filter_name, filter_value = filter_name_value_pair_get(exclude_filter)
		for device in devices:
			if filter_name in device:
				device_value = sync_servicenow_resource_value_get(device[filter_name])
				if filter_value == device_value:
					excluded_devices.append(device)
					continue
				device_value = sync_servicenow_resource_display_value_get(device[filter_name])
				if filter_value == device_value:
					excluded_devices.append(device)
					continue

	# Only return devices that are intersecting between the two sets; exclusion will take precedence	
	filtered_devices = [device for device in included_devices if device not in excluded_devices]
	return filtered_devices

def sync_servicenow_api_devices_import(servicenow, include_filters=[], exclude_filters=[]):

	# Get all configuration items from ServiceNow
	parameters = []
	parameters.append({'name':'sysparm_display_value', 'value':'all'})
	devices = servicenow.get_configuration_items(parameters=parameters)
	logger.info("There are {} configuration items from ServiceNow".format(len(devices)))

	filtered_devices = sync_servicenow_devices_filter(devices, include_filters=include_filters, 
		exclude_filters=exclude_filters)

	return filtered_devices

def sync_servicenow_api_locations_import(servicenow):

	locations = servicenow.get_locations()

	return locations

def sync_servicenow_configuration_read(servicenow_yml):

	servicenow_configuration = yamlread(servicenow_yml)

	return servicenow_configuration

def sync_servicenow_api_import(servicenow_yml):

	config = sync_servicenow_configuration_read(servicenow_yml)

	# Authenticate to ServiceNow
	hostname = config['hostname']
	username = config['username']
	password = config['password']

	try:
		servicenow = ServiceNow(hostname, username, password)
	except:
		logger.info(f"Failed to reach ServiceNow instance at {hostname} with {username}")
		raise

	servicenow_devices = sync_servicenow_api_devices_import(servicenow, config['include_filters'],
		config['exclude_filters'])
	servicenow_locations = sync_servicenow_api_locations_import(servicenow)

	return servicenow_devices, servicenow_locations

def sync_servicenow_csv_import(devices_csv, locations_csv):

	# Read files and find required fields
	servicenow_devices = dictionary_from_csv(devices_csv)
	if servicenow_devices == None or len(servicenow_devices) == 0:
		logger.debug("Device INPUT input did not include the expected fields. Please correct and re-run script.")
		return None, None

	servicenow_locations = dictionary_from_csv(locations_csv)
	if servicenow_locations == None or len(servicenow_locations) == 0:
		logger.debug("Locations INPUT input did not include the expected fields. Please correct and re-run script.")
		return None, None

	return servicenow_devices, servicenow_locations	

def sync_servicenow_import(servicenow_yml=None, servicenow_devices_csv=None, servicenow_locations_csv=None):

	if servicenow_yml != None:
		# Option 1: Pull devices directly from ServiceNow
		servicenow_devices, servicenow_locations = sync_servicenow_api_import(servicenow_yml)

	elif servicenow_devices_csv != None and servicenow_locations_csv != None:
		# Option 2: Pull devices and locations from CSV
		servicenow_devices, servicenow_locations = sync_servicenow_csv_import(servicenow_devices_csv,
			servicenow_locations_csv)
	else:
		# Notify user that information is missing
		logger.info("Provided input parameters do not specify complete ServiceNow parameters")
		return None, None

	return servicenow_devices, servicenow_locations

#----- ServiceNow report functions
### FOR NOW, USE PRINT()

# Constants to use for normalized input fields for devices and locations for both CSV and API
SYNC_SERVICENOW_LOOKUP_DEVICES_NAME = 'Name'
SYNC_SERVICENOW_LOOKUP_DEVICES_CLASS = 'Class'
SYNC_SERVICENOW_LOOKUP_DEVICES_LOCATION = 'Location'
SYNC_SERVICENOW_LOOKUP_DEVICES_ID = 'CI ID'
SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS = 'Address'
SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS_EMPTY = 'N/A'
SYNC_SERVICENOW_LOOKUP_DEVICES_STATUS = 'Status'
SYNC_SERVICENOW_LOOKUP_DEVICES_MANUFACTURER = 'Manufacturer'
SYNC_SERVICENOW_LOOKUP_DEVICES_MODEL = 'Model'
SYNC_SERVICENOW_LOOKUP_DEVICES_MONITOR = 'Monitor'

SYNC_SERVICENOW_LOOKUP_LOCATIONS_NAME = 'Name'
SYNC_SERVICENOW_LOOKUP_LOCATIONS_CITY = 'City'
SYNC_SERVICENOW_LOOKUP_LOCATIONS_REGION = 'Region'
SYNC_SERVICENOW_LOOKUP_LOCATIONS_COUNTRY = 'Country'
SYNC_SERVICENOW_LOOKUP_LOCATIONS_LATITUDE = 'Latitude'
SYNC_SERVICENOW_LOOKUP_LOCATIONS_LONGITUDE = 'Longitude'

def sync_servicenow_devices_multiple_addresses_report(devices_with_multiple_addresses, lookup_table, summary=True):
	devices_with_multiple_addresses_count = len(devices_with_multiple_addresses)
	if devices_with_multiple_addresses_count > 0:
		print("")
		print(f"There are {devices_with_multiple_addresses_count} devices that have multiple listed IP addresses.")
		if devices_with_multiple_addresses_count > 10 and summary == True:
			print("Displaying the first 10 devices with multiple IP addresses:")
			print(devices_with_multiple_addresses[:10])
		else:
			print(f"The following device names have multiple addresses:")
			print(devices_with_multiple_addresses)
			
		print("")

	return


def sync_servicenow_devices_empty_addresses_report(devices_with_empty_addresses, lookup_table, summary=True):
	devices_with_empty_addresses_count = len(devices_with_empty_addresses)
	if devices_with_empty_addresses_count > 0:
		print("")
		print(f"There are {devices_with_empty_addresses_count} devices without listed IP addresses.")
		if devices_with_empty_addresses_count > 10 and summary == True:
			print("Displaying the first 10 devices without IP addresses:")
			print(list(devices_with_empty_addresses.keys())[:10])
		else:
			print(f"The following devices have empty addresses:")
			for device_name, device_instances in devices_with_empty_addresses.items():
				for device in device_instances:
					cmdb_ci = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ID]])
					address = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS]])
					location = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_LOCATION]])
					print(f"  {device_name}, {cmdb_ci}, {address}, {location}")
		print("")

	return


def sync_servicenow_devices_invalid_addresses_report(devices_with_invalid_addresses, lookup_table, summary=True):
	devices_with_invalid_addresses_count = len(devices_with_invalid_addresses)
	if devices_with_invalid_addresses_count > 0:
		print("")
		print(f"There are {devices_with_invalid_addresses_count} devices that have invalid IP addresses.")
		if devices_with_invalid_addresses_count > 10 and summary == True:
			print("Displaying the first 10 devices with invalid IP addresses:")
			print(list(devices_with_invalid_addresses.keys())[:10])
		else:
			print(f"The following devices have invalid addresses:")
			for device_name, device_instances in devices_with_invalid_addresses.items():
				for device in device_instances:
					cmdb_ci = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ID]])
					address = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS]])
					location = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_LOCATION]])
					print(f"  {device_name}, {cmdb_ci}, {address}, {location}")
		print("")

	return

def sync_servicenow_netim_devices_comparison_report(device_comparison, summary=True):
	new_devices = device_comparison[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_NEW]

	new_devices_count = len(new_devices)
	print("")
	print(f"There are {new_devices_count} devices with IP addresses that do not exist in NetIM.")
	if new_devices_count > 10 and summary:
		print("Displaying the first 10 devices:")
		print(new_devices[:10])	
	else:
		print(new_devices)

	different_addresses = device_comparison[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_DIFFERENT]
	different_addresses_count = len(different_addresses)
	if different_addresses_count > 0:	
		print("")
		print(f"There are {different_addresses_count} device(s) that exist in NetIM, but have different access addresses.")
		if different_addresses_count > 10 and summary:
			print("Displaying the first 10 devices:")
			print(different_addresses[:10])
		else:
			print(different_addresses)
	
	devices_with_no_updates = device_comparison[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_NO_UPDATES]
	no_update_count = len(devices_with_no_updates)
	if no_update_count > 0:
		print("")
		print(f"There are {no_update_count} device(s) that have matching names and access addresses in NetIM.")
		if no_update_count > 10 and summary:
			print("Displaying the first 10 devices:")
			print(devices_with_no_updates[:10])
		else:
			print("The following ServiceNow devices have matching names and access IP addresses in NetIM:")
			print(devices_with_no_updates)
		print("")

	return

def sync_servicenow_netim_sites_comparison_report(site_comparison, summary=True):
	new_sites = site_comparison[SYNC_SERVICENOW_NETIM_COMPARISON_SITES_NEW]

	new_sites_count = len(new_sites)
	print(f"The following {new_sites_count} site(s) are associated with devices and are not defined in NetIM:")
	if new_sites_count > 10 and args.summary:
		print("Displaying first 10 sites:")
		print(new_sites[:10])
	else:
		print(new_sites)

	existing_sites = site_comparison[SYNC_SERVICENOW_NETIM_COMPARISON_SITES_EXISTING]
	print("")
	existing_site_count = len(existing_sites)
	if existing_site_count == 0:
		print("No sites to be imported matched existing names in NetIM database.")
	else:
		print(f"The following {existing_site_count} site(s) have already been defined in NetIM.")
		if existing_site_count > 10 and args.summary:
			print("Displaying the first 10 sites:")
			print(existing_sites[:10])
		else:
			print(existing_sites)

	return

def sync_servicenow_netim_location_validation_report(comparison_dict, summary=True):

	if len(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_MATCH]) > 0:
		print("The following sites had country, region, city that were found in NetIM database:")
		print(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_MATCH])
	if len(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_CITY_NOT_FOUND]) > 0:
		print("The following sites had country and region found in NetIM database, but the city is not in database:")
		print(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_CITY_NOT_FOUND])
	if len(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_CITY_EMPTY]) > 0:
		print("The following sites had country and region found in NetIM database, but city field is empty in input:")
		print(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_CITY_EMPTY])
	if len(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_REGION_NOT_FOUND]) > 0:
		print("The following sites had country found in NetIM database, but region is not in database:")
		print(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_REGION_NOT_FOUND])
	if len(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_REGION_EMPTY]) > 0:
		print("The following sites had country found in NetIM database, but region field is empty in input:")
		print(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_REGION_EMPTY])
	if len(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COUNTRY_NOT_FOUND]) > 0:
		print("The following sites had a country that does not match an entry in the NetIM database:")
		print(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COUNTRY_NOT_FOUND])
	if len(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COUNTRY_EMPTY]) > 0:
		print("The following sites had no country listed in input:")
		print(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COUNTRY_EMPTY])
	if len(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COORDINATES_MISSING]) > 0:
		print("The following sites had missing coordinates (latitude, longitude):")
		print(comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COORDINATES_MISSING])

	return

#----- ServiceNow input/lookup functions

SYNC_SERVICENOW_INPUT_API_DEVICES_NAME = 'name'
SYNC_SERVICENOW_INPUT_API_DEVICES_CLASS = 'sys_class_name'
SYNC_SERVICENOW_INPUT_API_DEVICES_LOCATION = 'location'
SYNC_SERVICENOW_INPUT_API_DEVICES_ADDRESS = 'ip_address'
SYNC_SERVICENOW_INPUT_API_DEVICES_ADDRESS_EMPTY = ''
SYNC_SERVICENOW_INPUT_API_DEVICES_ID = 'sys_id'
SYNC_SERVICENOW_INPUT_API_DEVICES_STATUS = 'operational_status'
SYNC_SERVICENOW_INPUT_API_DEVICES_MANUFACTURER = 'vendor'
SYNC_SERVICENOW_INPUT_API_DEVICES_MODEL = 'model_id'
SYNC_SERVICENOW_INPUT_API_DEVICES_MONITOR = 'monitor'

SYNC_SERVICENOW_INPUT_CSV_DEVICES_NAME = 'Name'
SYNC_SERVICENOW_INPUT_CSV_DEVICES_CLASS = 'Class'
SYNC_SERVICENOW_INPUT_CSV_DEVICES_LOCATION = 'Location'
SYNC_SERVICENOW_INPUT_CSV_DEVICES_ADDRESS = 'IP Address'
SYNC_SERVICENOW_INPUT_CSV_DEVICES_ADDRESS_EMPTY = '#N/A'
SYNC_SERVICENOW_INPUT_CSV_DEVICES_ID = 'CI ID'
SYNC_SERVICENOW_INPUT_CSV_DEVICES_STATUS = 'CI Status'
SYNC_SERVICENOW_INPUT_CSV_DEVICES_MANUFACTURER = 'Manufacturer'
SYNC_SERVICENOW_INPUT_CSV_DEVICES_MODEL = 'Model'
SYNC_SERVICENOW_INPUT_CSV_DEVICES_MONITOR = 'Monitor'
SYNC_SERVICENOW_INPUT_CSV_DEVICES_MONITOR_TYPE = 'Monitored Type'

SYNC_SERVICENOW_INPUT_API_LOCATIONS_NAME = 'name'
SYNC_SERVICENOW_INPUT_API_LOCATIONS_CITY = 'city'
SYNC_SERVICENOW_INPUT_API_LOCATIONS_REGION = 'state'
SYNC_SERVICENOW_INPUT_API_LOCATIONS_COUNTRY = 'country'
SYNC_SERVICENOW_INPUT_API_LOCATIONS_LATITUDE = 'latitude'
SYNC_SERVICENOW_INPUT_API_LOCATIONS_LONGITUDE = 'longitude'

SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_NAME = 'Name'
SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_CITY = 'City'
SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_REGION = 'State / Province'
SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_COUNTRY = 'Country'
SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_LATITUDE = 'Latitude'
SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_LONGITUDE = 'Longitude'

def sync_servicenow_input_globals(use_api=True):

	lookup_table = {}

	if use_api == True:
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_NAME] = SYNC_SERVICENOW_INPUT_API_DEVICES_NAME
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_CLASS] = SYNC_SERVICENOW_INPUT_API_DEVICES_CLASS
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_LOCATION] = SYNC_SERVICENOW_INPUT_API_DEVICES_LOCATION
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS] = SYNC_SERVICENOW_INPUT_API_DEVICES_ADDRESS
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ID] = SYNC_SERVICENOW_INPUT_API_DEVICES_ID
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_STATUS] = SYNC_SERVICENOW_INPUT_API_DEVICES_STATUS
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_MANUFACTURER] = SYNC_SERVICENOW_INPUT_API_DEVICES_MANUFACTURER
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_MODEL] = SYNC_SERVICENOW_INPUT_API_DEVICES_MODEL
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_MONITOR] = SYNC_SERVICENOW_INPUT_API_DEVICES_MONITOR

		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS_EMPTY] = SYNC_SERVICENOW_INPUT_API_DEVICES_ADDRESS_EMPTY

		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_NAME] = SYNC_SERVICENOW_INPUT_API_LOCATIONS_NAME
		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_CITY] = SYNC_SERVICENOW_INPUT_API_LOCATIONS_CITY
		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_REGION] = SYNC_SERVICENOW_INPUT_API_LOCATIONS_REGION
		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_COUNTRY] = SYNC_SERVICENOW_INPUT_API_LOCATIONS_COUNTRY
		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_LATITUDE] = SYNC_SERVICENOW_INPUT_API_LOCATIONS_LATITUDE
		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_LONGITUDE] = SYNC_SERVICENOW_INPUT_API_LOCATIONS_LONGITUDE
	else:
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_NAME] = SYNC_SERVICENOW_INPUT_CSV_DEVICES_NAME
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_CLASS] = SYNC_SERVICENOW_INPUT_CSV_DEVICES_CLASS
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_LOCATION] = SYNC_SERVICENOW_INPUT_CSV_DEVICES_LOCATION
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS] = SYNC_SERVICENOW_INPUT_CSV_DEVICES_ADDRESS
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ID] = SYNC_SERVICENOW_INPUT_CSV_DEVICES_ID
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_STATUS] = SYNC_SERVICENOW_INPUT_CSV_DEVICES_STATUS
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_MANUFACTURER] = SYNC_SERVICENOW_INPUT_CSV_DEVICES_MANUFACTURER
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_MODEL] = SYNC_SERVICENOW_INPUT_CSV_DEVICES_MODEL
		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_MONITOR] = SYNC_SERVICENOW_INPUT_CSV_DEVICES_MONITOR

		lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS_EMPTY] = SYNC_SERVICENOW_INPUT_CSV_DEVICES_ADDRESS_EMPTY

		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_NAME] = SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_NAME
		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_CITY] = SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_CITY
		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_REGION] = SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_REGION
		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_COUNTRY] = SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_COUNTRY
		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_LATITUDE] = SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_LATITUDE
		lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_LONGITUDE] = SYNC_SERVICENOW_INPUT_CSV_LOCATIONS_LONGITUDE

	return lookup_table

def sync_servicenow_input_ipaddress_valid(device_address):

	valid_ipv4_address = True
	if device_address.count('.') == 3:
		octets = device_address.split('.')
		for octet in octets:
			try:
				if str(int(octet)) != octet:
					valid_ipv4_address = False
				if int(octet) < 0 or int(octet) > 255:
					valid_ipv4_address = False
			except:
				valid_ipv4_address = False
		try:
			# If the last digit is a broadcast address, it can't be used for access
			if octets[3] == '255':
				valid_ipv4_address = False
		except:
			valid_ipv4_address = False
			
	else:
		valid_ipv4_address = False

	# Handle valid IP address formats that cannot be used for interfaces
	if valid_ipv4_address == True:
		if device_address == '0.0.0.0' or device_address == '127.0.0.1':
			valid_ipv4_address = False

	valid_ipv6_address = True
	if device_address.count(':') == 7:
		segments = device_address.split(':')
		for segment in segments:
			if segment == '':
				continue
			if len(segment) > 4:
				valid_ipv6_address = False
				continue
			try:
				if int(segment, 16) < 0 or segment[0] == '-':
					valid_ipv6_address = False
			except:
				valid_ipv6_address = False
	else:
		valid_ipv6_address = False

	return valid_ipv4_address or valid_ipv6_address

def sync_servicenow_input_validate(devices, locations, lookup_table, summary=True):

	# Check for duplicate names and valid IP addresses
	# In the process, build a dictionary to see which devices have multiple listed access addresses
	devices_with_empty_addresses = {}
	devices_with_invalid_addresses = {}
	devices_unique_by_name = {}
	multiple_addresses_set = set()

	for device in devices:
		device_name = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_NAME]])
		device_address = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS]])

		# If the device address is empty, NetIM cannot monitor the device, so track the list of devices that
		# do not have an IP address assigned
		if device_address == '' or device_address == lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS_EMPTY]:
			if device_name in devices_with_empty_addresses:
				devices_with_empty_addresses[device_name].append(device)
			else:
				devices_with_empty_addresses[device_name] = [device]
			continue

		# If the device address is invalid, NetIM cannot monitor the device
		if sync_servicenow_input_ipaddress_valid(device_address) == False:
			if device_name in devices_with_invalid_addresses:
				devices_with_invalid_addresses[device_name].append(device)
			else:
				devices_with_invalid_addresses[device_name] = [device]
			continue

		# If the device name is listed more than once in ServiceNow with more than one valid address, track it
		# Eventually, the device will need to be resolved to one access IP address range
		if device_name in devices_unique_by_name:
			multiple_addresses_set.update([device_name])
			devices_unique_by_name[device_name].append(device)
		else:
			devices_unique_by_name[device_name] = [device]

	# Report on findings of devices with empty and invalid addresses
	logger.info("There are {} devices in ServiceNow with no address".format(len(devices_with_empty_addresses)))
	sync_servicenow_devices_empty_addresses_report(devices_with_empty_addresses, lookup_table, summary)
	logger.info("There are {} devices in ServiceNow with invalid addresses".format(len(devices_with_invalid_addresses)))
	sync_servicenow_devices_invalid_addresses_report(devices_with_invalid_addresses, lookup_table, summary)

	# Report on findings of devices with multiple addresses
	devices_with_multiple_addresses = list(multiple_addresses_set)
	sync_servicenow_devices_multiple_addresses_report(devices_with_multiple_addresses, lookup_table, summary)

	# Without having other criteria, choose the first IP address for each device name as the primary access address
	# Also create the data set that matches all available access addresses to a device name for future selection purposes
	devices_to_import = []
	devices_with_access_addresses = {}
	for device_name in devices_unique_by_name:
		for device_instance in devices_unique_by_name[device_name]:
			access_address = clean(device_instance[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS]])
			if device_name not in devices_with_access_addresses:
				devices_to_import.append(device_instance)
				devices_with_access_addresses[device_name] = [access_address]
			else:
				devices_with_access_addresses[device_name].append(access_address)
	logger.info("There are {} unique devices with IP addresses from the ServiceNow data".format(len(devices_to_import)))

	# Get unique list of locations from the devices that may be imported
	devlocation_set = set()
	for device in devices_to_import:
		devlocation = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_LOCATION]])
		devlocation_set.update([devlocation])
	devlocations = list(devlocation_set)

	# Loop through locations in ServiceNow and import those that are associated with devices
	# Check for duplicate location names along the way
	locations_to_import = []
	location_tracker = {}
	duplicate_location_names = []

	for location in locations:
		location_name = clean(location[lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_NAME]])

		if location_name in location_tracker:
			location_tracker[location_name].append(location)
			duplicate_location_names.append(location_name)
			continue
		else:
			location_tracker[location_name] = [location]

		if location_name in devlocations:
			locations_to_import.append(location)

	# Report on duplicate location names

	return devices_to_import, locations_to_import, devices_with_access_addresses

#----- ServiceNow/NetIM conversion functions

# Constants to use for NetIM device attributes
NETIM_DEVICE_NAME = 'name'
NETIM_DEVICE_DEVICENAME = 'deviceName'
NETIM_DEVICE_DISPLAYNAME = 'displayName'
NETIM_DEVICE_ACCESSINFO = 'deviceAccessInfo'
NETIM_DEVICE_ACCESSADDRESS = 'accessAddress'
NETIM_DEVICE_GROUP = 'group'
NETIM_DEVICE_CMDB_ID = 'cmdb_ci'

# Constants to use for NetIM Site/Group fields
NETIM_SITE_NAME = 'name'
NETIM_SITE_COUNTRY = 'country'
NETIM_SITE_REGION = 'region'
NETIM_SITE_CITY = 'city'
NETIM_SITE_LATITUDE = 'latitude'
NETIM_SITE_LONGITUDE = 'longitude'
NETIM_SITE_CMDB_ID = 'cmdb_ci'

def sync_servicenow_to_netim_devices_convert(devices_to_import, lookup_table):
	converted_devices = []

	for device in devices_to_import:
		converted_device = {}
		device_name = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_NAME]])
		converted_device[NETIM_DEVICE_NAME] = device_name
		converted_device[NETIM_DEVICE_DEVICENAME] = device_name
		converted_device[NETIM_DEVICE_DISPLAYNAME] = device_name
		access_address = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ADDRESS]])
		converted_device[NETIM_DEVICE_ACCESSADDRESS] = access_address

		group = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_LOCATION]])
		converted_device[NETIM_DEVICE_GROUP] = group

		converted_device[NETIM_DEVICE_CMDB_ID] = clean(device[lookup_table[SYNC_SERVICENOW_LOOKUP_DEVICES_ID]])
		converted_devices.append(converted_device)
		
	return converted_devices

def sync_servicenow_to_netim_locations_convert(locations_to_import, lookup_table):
	converted_sites = []

	# Get the list of locations that are assigned to devices being imported into ServiceNow
	# and use them to pull the required information from the locations table
	for location in locations_to_import:
		converted_site = {}
		converted_site[NETIM_SITE_NAME] = clean(location[lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_NAME]])
		converted_site[NETIM_SITE_CITY] = clean(location[lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_CITY]])
		converted_site[NETIM_SITE_REGION] = clean(location[lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_REGION]])
		country = clean(location[lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_COUNTRY]])
		# Handle abbreviation of USA
		if country == 'USA':
			country = 'United States of America'
		converted_site[NETIM_SITE_COUNTRY] = country
		converted_site[NETIM_SITE_LATITUDE] = clean(location[lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_LATITUDE]])
		converted_site[NETIM_SITE_LONGITUDE] = clean(location[lookup_table[SYNC_SERVICENOW_LOOKUP_LOCATIONS_LONGITUDE]])
		converted_sites.append(converted_site)
	logger.info("Converted {} sites(s) from ServiceNow associated with polled devices".format(len(converted_sites)))

	return converted_sites


#----- ServiceNow/NetIM comparison functions

SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_NEW = 'new_device'
SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_DIFFERENT = 'different_address'
SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_NO_UPDATES = 'no_updates'

SYNC_SERVICENOW_NETIM_COMPARISON_SITES_NEW = 'new_site'
SYNC_SERVICENOW_NETIM_COMPARISON_SITES_EXISTING = 'existing_site'

# Constants to use for location comparison lists in comparison dictionary
SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_MATCH = 'match_all'
SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COUNTRY_EMPTY = 'country_empty'
SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COUNTRY_NOT_FOUND = 'country_not_found'
SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_REGION_EMPTY = 'region_empty'
SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_REGION_NOT_FOUND = 'region_not_found'
SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_CITY_EMPTY = 'city_empty'
SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_CITY_NOT_FOUND = 'city_not_found'
SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COORDINATES_MISSING = 'coordinates_missing'


def sync_servicenow_netim_device_name_comparison(servicenow_device, netim_device):
	if NETIM_DEVICE_NAME in servicenow_device:
		servicenow_device_name = servicenow_device[NETIM_DEVICE_NAME]
	else:
		logger.debug(f'Missing name in passed information from ServiceNow')
		return False

	if NETIM_DEVICE_NAME in netim_device:
		netim_device_name = netim_device[NETIM_DEVICE_NAME].strip()
	else:
		logger.debug(f'Missing name in passed information from NetIM')
		return False

	# If a device is an FQDN, then strip it down to the hostname
	if '.' in servicenow_device_name:
		servicenow_device_name = servicenow_device_name.split('.')[0]
	if '.' in netim_device_name:
		netim_device_name = netim_device_name.split('.')[0]
	netim_device_displayname = netim_device[NETIM_DEVICE_DISPLAYNAME].strip()
	if '.' in netim_device_displayname:
		netim_device_displayname = netim_device_displayname.split('.')[0]
	netim_device_devicename = netim_device[NETIM_DEVICE_DEVICENAME].strip()
	if '.' in netim_device_devicename:
		netim_device_devicename = netim_device_devicename.split('.')[0]

	if servicenow_device_name.lower() == netim_device_name.lower() \
		or servicenow_device_name.lower() == netim_device_displayname.lower() \
		or servicenow_device_name.lower() == netim_device_devicename.lower():
		return True
	else:
		return False

def sync_servicenow_netim_devices_comparison(devices_to_import, netim, devices_with_access_addresses=None):

	comparison_dict = {}	
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_NEW] = []
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_DIFFERENT] = []
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_NO_UPDATES] = []

	# Get devices from NetIM
	netim_devices = sync_netim_devices_import(netim)

	# Iterate over devices from ServiceNow, comparing name and address to what is already in NetIM
	for device_under_consideration in devices_to_import:
		found_device = False
		found_address = False

		for netim_device in netim_devices:
			# Compare by device name
			if NETIM_DEVICE_NAME not in netim_device:
				logger.debug(f"Skipping device with no field {NETIM_DEVICE_NAME}")
				continue
			
			if sync_servicenow_netim_device_name_comparison(device_under_consideration, netim_device) == True:
				found_device = True

				# Find address in the data from NetIM
				netim_device_address = None
				if NETIM_DEVICE_ACCESSADDRESS in netim_device:
					netim_device_address = netim_device[NETIM_DEVICE_ACCESSADDRESS].strip()

				# If address has not changed and was not found in the first location, continue searching
				if netim_device_address == None or netim_device_address == "":
					if NETIM_DEVICE_ACCESSINFO in netim_device and \
						NETIM_DEVICE_ACCESSADDRESS in netim_device[NETIM_DEVICE_ACCESSINFO]:
						netim_device_address = netim_device[NETIM_DEVICE_ACCESSINFO][NETIM_DEVICE_ACCESSADDRESS].strip()

				# Compare ServiceNow address for device with NetIM's address
				if devices_with_access_addresses == None:
					if NETIM_DEVICE_ACCESSADDRESS in servicenow_device:
						servicenow_device_address = servicenow_device[NETIM_DEVICE_ACCESSADDRESS]
						if servicenow_address == netim_device_address:
							found_address = True
				# If available, use the original device address dictionary to get full list of available access addresses
				else:
					servicenow_device_name = device_under_consideration[NETIM_DEVICE_NAME]
					servicenow_device_address_list = []
					if servicenow_device_name in devices_with_access_addresses:
						servicenow_device_address_list = devices_with_access_addresses[servicenow_device_name]
				
					for servicenow_device_address in servicenow_device_address_list:
						if servicenow_device_address == netim_device_address:
							found_address = True
							break
				break

		if NETIM_DEVICE_NAME in device_under_consideration:
			servicenow_device_name = device_under_consideration[NETIM_DEVICE_NAME]
		else:
			servicenow_device_name = 'Unknown'
		if found_device == True:
			logger.info(f"Found device {servicenow_device_name}")
			if found_address == True:
				comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_NO_UPDATES].append(servicenow_device_name)
			else:
				comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_DIFFERENT].append(servicenow_device_name)
		else:
			logger.info(f"Did not find device {servicenow_device_name}")
			comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_NEW].append(servicenow_device_name)
	
	return comparison_dict

def sync_servicenow_netim_sites_comparison(sites_to_import, netim, summary):
	comparison_dict = {}
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_SITES_EXISTING] = []
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_SITES_NEW] = []

	groups_json = netim.get_all_groups()
	groups = []
	if 'items' in groups_json:
		groups = groups_json['items']
	if len(groups) == 0:
		logger.info('The list of groups/sites returned from NetIM was empty.')

	# Compare locations to import with existing locations
	existing_sites = []
	new_sites = []
	for site in sites_to_import:
		found_site = False
		for group in groups:
			site_name = site[NETIM_SITE_NAME].strip()
			if site_name == group[NETIM_SITE_NAME].strip():
				existing_sites.append(site_name)
				found_site = True
				break
		if found_site == False:
			new_sites.append(site_name)

	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_SITES_EXISTING] = existing_sites
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_SITES_NEW] = new_sites

	return comparison_dict

def sync_servicenow_netim_location_validation(sites_to_import, netim):

	comparison_dict = {}
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_MATCH] = []
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COUNTRY_EMPTY] = []
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COUNTRY_NOT_FOUND] = []
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_REGION_EMPTY] = []
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_REGION_NOT_FOUND] = []
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_CITY_EMPTY] = []
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_CITY_NOT_FOUND] = []
	comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COORDINATES_MISSING] = []

	region_cache = {}
	city_cache = {}

	countries_json = netim.get_all_countries()
	countries = []
	if 'items' in countries_json:
		countries = countries_json['items']

	for site in sites_to_import:
		# Do a quick check in this loop to see if coordinates are missing
		site_name = site[NETIM_SITE_NAME]
		if site[NETIM_SITE_LATITUDE] == "" or site[NETIM_SITE_LONGITUDE] == "":
			comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COORDINATES_MISSING].append(site_name)

		# Now, begin rest of data comparison to see what matches for this site that is being considered for import
		country_empty = country_found = region_empty = region_found = city_empty = city_found = False
	
		# Case: Country is empty
		site_country = site[NETIM_SITE_COUNTRY]
		if site_country  == "":
			country_empty = True
			continue

		for country in countries:
			country_name = country[NETIM_COUNTRY_NAME]
			if site_country == country_name:
				# Case: Country is found, but region not specified
				site_region = site[NETIM_SITE_REGION]
				if site_region == None or site_region == "":
					country_found = region_empty = True
					break

				# Use caches so not requesting region or city data multiple times
				regions = []
				if country_name in region_cache:
					regions = region_cache[country_name]
				else:
					regions_json = netim.get_regions_by_country_id(country[NETIM_COUNTRY_ID])
					if regions_json != None and 'items' in regions_json:
						regions = regions_json['items']
						region_cache[country_name] = regions

				for region in regions:
					region_name = region[NETIM_REGION_NAME]
					if site_region == region_name:
						site_city = site[NETIM_SITE_CITY]
						if site_city == None or site_city == "":
							# Case: Country, region found; city empty
							country_found = region_found = city_empty = True
							break
						
						# Use cache
						cities = []
						if region_name in city_cache:
							cities = city_cache[region_name]
						else:
							cities_json = netim.get_cities_by_region_id(region[NETIM_REGION_ID])
							if cities_json != None and 'items' in cities_json:
								cities = cities_json['items']
								city_cache[region_name] = cities

						for city in cities:
							city_name = city[NETIM_CITY_NAME]
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
					comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_MATCH].append(site_name)
				elif city_empty == True:
					comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_CITY_EMPTY].append(site_name)
				else:
					comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_CITY_NOT_FOUND] = []
			elif region_empty == True:
				comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_REGION_EMPTY].append(site_name)
			else:
				comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_REGION_NOT_FOUND].append(site_name)
		elif country_empty == True:
			comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COUNTRY_EMPTY].append(site_name)
		else:
			comparison_dict[SYNC_SERVICENOW_NETIM_COMPARISON_LOCATION_COUNTRY_NOT_FOUND].append(site_name)

	return comparison_dict

#----- NetIM Functions

NETIM_CUSTOM_ATTRIBUTE_LASTSYNCED = 'Timestamp Synchronized with CMDB'
NETIM_CUSTOM_ATTRIBUTE_LASTSYNCED_DESCRIPTION = 'Human readable value of when device was created from ServiceNow sync'
NETIM_CUSTOM_ATTRIBUTE_CMDB_ID = 'CI ID'
NETIM_CUSTOM_ATTRIBUTE_CMDB_ID_DESCRIPTION = 'ServiceNow CMDB Configuration Item (CI) Identifier'

# Constants to use for NetIM country, region, and city searches
NETIM_COUNTRY_NAME = 'name'
NETIM_COUNTRY_ID = 'id'
NETIM_REGION_NAME = 'name'
NETIM_REGION_ID = 'id'
NETIM_CITY_NAME = 'name'

def sync_netim_custom_attribute_devices_cmdb_id(netim, device_names, devices):
	# Add custom attribute to NetIM devices for CMDB CI
	devices_to_update = [device for device in devices if device[NETIM_DEVICE_NAME] in device_names]
	
	# Find if the attribute has already been added to NetIM
	attribute_id = netim.get_custom_attribute_id_by_name(NETIM_CUSTOM_ATTRIBUTE_CMDB_ID)

	# If the custom attribute has not been added to NetIM, add it and find its newly created attribute ID
	response = None
	if attribute_id == -1:
		try:
			response = netim.add_custom_attribute(NETIM_CUSTOM_ATTRIBUTE_CMDB_ID,
				NETIM_CUSTOM_ATTRIBUTE_CMDB_ID_DESCRIPTION)
			if response == None:
				logger.info("Failed to create Custom Attribute '{}' in NetIM".format(NETIM_CUSTOM_ATTRIBUTE_CMDB_ID))
				return
		except:
			logger.debug("Exception when adding Custom Attribute to NetIM.")
			raise

	# Provide time for the attribute to be processed
	time.sleep(2)

	# Now add Custom Attribute Value for each device
	response = None
	for device in devices_to_update:
		try:
			device_id = netim.get_device_id_by_device_name(device[NETIM_DEVICE_NAME])
			if device_id != -1:
				response = netim.add_custom_attribute_values(NETIM_CUSTOM_ATTRIBUTE_CMDB_ID, 
					device[NETIM_DEVICE_CMDB_ID], device_ids=[device_id])
				if response == None:
					logger.debug("Unable to add Custom Attribute Value for device")

		except NameError as e:
			logger.debug(f"Name error: {e}")
		except TypeError as e:
			logger.debug(f"Type error: {e}")
		except:
			logger.debug("Exception when importing Custom Attribute values for devices")
			logger.debug("Unexpected error {}".format(sys.exc_info()[0]))

	return 

def sync_netim_custom_attribute_devices_timestamp(netim, devices):

	# Add custom attribute to NetIM devices for synchronization time
	attribute_id = netim.get_custom_attribute_id_by_name(NETIM_CUSTOM_ATTRIBUTE_LASTSYNCED)

	# If the synchronization custom attribute has not been added to NetIM, add it and find its newly
	# created attribute ID
	response = None
	if attribute_id == -1:
		response = netim.add_custom_attribute(NETIM_CUSTOM_ATTRIBUTE_LASTSYNCED,
			NETIM_CUSTOM_ATTRIBUTE_LASTSYNCED_DESCRIPTION)
		if response == None:
			logger.debug("Failed to create Custom Attribute for synchronization time in NetIM")

	# Provide time for the attribute to be processed
	time.sleep(2)

	# Get time stamp value
	current_time = datetime.datetime.now()
	current_time_str = current_time.strftime('%m/%d/%Y %H:%M:%S')
	logger.info(f"Setting synchronization timestamp in NetIM to {current_time_str}")

	response = None
	try:
		# Loop over the devices, and if the device already has a value, update it
		for device in devices:
			device_id = netim.get_device_id_by_device_name(device[NETIM_DEVICE_NAME])
			if device_id != -1:
				values = netim.get_custom_attribute_values_for_device_by_attribute_name(device_id, NETIM_CUSTOM_ATTRIBUTE_LASTSYNCED)
			else:
				continue

			response = None
			if len(values) == 0:
				# Add time stamp value to NetIM
				response = netim.add_custom_attribute_values(NETIM_CUSTOM_ATTRIBUTE_LASTSYNCED, current_time_str, device_ids=[device_id]) 
			elif len(values) > 0:
				if 'id' in values[0]:
					value_id = values[0]['id']
					response = netim.update_custom_attribute_value_from_id(NETIM_CUSTOM_ATTRIBUTE_LASTSYNCED, value_id, current_time_str)
				if len(values) > 1:
					logger.debug(f"More than one Custom Attribute Value found for {NETIM_CUSTOM_ATTRIBUTE_LASTSYNCED}")
					logger.debug(f"Only one value is expected.")
	except NameError as e:
		logger.debug(f"Name error: {e}")
	except:
		logger.debug("Exception when importing Custom Attribute values for devices")
		logger.debug("Unexpected error {}".format(sys.exc_info()[0]))

	return

def sync_netim_sites_create(netim, site_names, sites):

	created_sites_ids = []
	sites_to_add = [site for site in sites if site[NETIM_SITE_NAME] in site_names]

	for site_to_add in sites_to_add:
		try:
			response = netim.add_group(site_to_add[NETIM_SITE_NAME])
			time.sleep(2)
			site_id = netim.get_group_id_by_group_name(site_to_add[NETIM_SITE_NAME])
			created_sites_ids.append(site_id)
		except:
			logger.info("Failed to add group {}".format(site_to_add[NETIM_SITE_NAME]))
			logger.debug("Unexpected error {}".format(sys.exc_info()[0]))

	return created_sites_ids

def sync_netim_sites_devices_add(netim, devices_to_add):

	for device in devices_to_add:
		try:
			# If the device has a group, add the device to the group that should have been created in NetIM
			group_name = device[NETIM_DEVICE_GROUP]
			if group_name == '':
				continue
			device_id = netim.get_device_id_by_device_name(device[NETIM_DEVICE_NAME])
			netim.add_devices_to_group(group_name, [device_id])
			time.sleep(2)
		except:
			logger.info("Failed to add device {} to group {}".format(device[NETIM_DEVICE_NAME], \
				device[NETIM_DEVICE_GROUP]))
			logger.debug("Unexpected error {}".format(sys.exc_info()[0]))
	return

def sync_netim_devices_create(netim, device_names, devices):

	created_devices_ids = []
	devices_to_add = [device for device in devices if device[NETIM_DEVICE_NAME] in device_names]

	for device_to_add in devices_to_add:
		try:
			response = netim.add_device_without_detail(device_to_add[NETIM_DEVICE_NAME], 
				device_to_add[NETIM_DEVICE_ACCESSADDRESS])
			time.sleep(2)
			device_id = netim.get_device_id_by_device_name(device_to_add[NETIM_DEVICE_NAME])
			created_devices_ids.append(device_id)
		except NameError as e:
			logger.info("Failed to add device {}".format(device_to_add[NETIM_DEVICE_NAME]))
			logger.debug(f"NameError: {e}")
		except:
			logger.info("Failed to add device {}".format(device_to_add[NETIM_DEVICE_NAME]))
			logger.debug("Unexpected error {}".format(sys.exc_info()[0]))

	return created_devices_ids

def sync_netim_devices_import(netim):
	netim_devices_json = netim.get_all_devices()
	netim_devices = []
	if netim_devices_json != None and 'items' in netim_devices_json:
		netim_devices = netim_devices_json['items']
	logger.info("Retrieved {} device(s) from NetIM".format(len(netim_devices)))
	return netim_devices

def sync_netim_authenticate(netim_yml):
	netim_hostname, netim_username, netim_password = credentials_get(netim_yml)
	if netim_password == None or netim_password == "":
		print(f"Please provide password for user {netim_username} on NetIM {netim_hostname}")
		netim_password = getpass.getpass()

	netim = None
	# Authentication to NetIM
	try:
		auth = UserAuth(netim_username, netim_password, method=Auth.BASIC)
		netim = NetIM(netim_hostname, auth)
	except RvbdHTTPException as e:
		logger.debug(f"RvbdHTTPException: {e}")
		raise
	except NameError as e:
		logger.debug(f"NameError: {e}")
		raise
	except TypeError as e:
		logger.debug(f"TypeError: {e}")
		raise
	except:
		logger.debug("Unexpected error {}".format(sys.exc_info()[0]))
		raise	

	return netim

def main ():

	parser = argparse.ArgumentParser(description="Python utility to compare data from ServiceNow to \
		data in NetIM")
	parser.add_argument('--servicenow_yml', help='ServiceNow account credentials')
	parser.add_argument('--netim_yml', help='NetIM account credentials')
	parser.add_argument('--servicenow_devices_csv', help='Export of INPUT devices from ServiceNow')
	parser.add_argument('--servicenow_locations_csv', help='Export of INPUT devices from ServiceNow')
	parser.add_argument('--summary', type=bool, help='Print summary or full report detail')
	parser.add_argument('--reconcile', type=bool, help='Create devices/groups in NetIM for missing objects')
	args = parser.parse_args()

	print("")
	print("ServiceNow and NetIM Comparison Report")
	print("---------------------------------------------------------------------------------------------------")

	# Get device and location import from API (or after export from CSV)
	if args.servicenow_yml != None and args.servicenow_yml != "":
		use_api = True
		text = 'API'
	else:
		use_api = False
		text = 'spreadsheets'
	print("")
	print(f"Step 1 of 7: Getting device and location information from ServiceNow {text}")

	servicenow_devices, servicenow_locations = sync_servicenow_import(args.servicenow_yml, 
		args.servicenow_devices_csv, args.servicenow_locations_csv)
	logger.info("There are {} ServiceNow devices".format(len(servicenow_devices)))
	logger.info("There are {} ServiceNow locations".format(len(servicenow_locations)))

	print("Step 2 of 7: Validating input from ServiceNow")
	lookup_table = sync_servicenow_input_globals(use_api)
	devices_to_import, locations_to_import, devices_with_access_addresses = \
		sync_servicenow_input_validate(servicenow_devices, servicenow_locations, lookup_table, args.summary)

	logger.info("After validation, there are {} devices to import from ServiceNow".format(len(devices_to_import)))
	logger.info("After validation, there are {} locations to import from ServiceNow".format(len(locations_to_import)))

	print("Step 3 of 7: Converting input from ServiceNow into NetIM structures")
	converted_devices = sync_servicenow_to_netim_devices_convert(devices_to_import, lookup_table)
	converted_sites = sync_servicenow_to_netim_locations_convert(locations_to_import, lookup_table)
	
	logger.info("After conversion, there are {} devices for NetIM to compare".format(len(converted_devices)))
	logger.info("After conversion, there are {} sites for NetIM to compare".format(len(converted_sites)))

	#---- NetIM API -----

	print(f"Step 4 of 7: Authenticating with NetIM")
	netim = sync_netim_authenticate(args.netim_yml)

	print("Step 5 of 7: Comparing devices in NetIM with the inputs from ServiceNow")
	device_comparison = sync_servicenow_netim_devices_comparison(converted_devices, netim, devices_with_access_addresses)
	sync_servicenow_netim_devices_comparison_report(device_comparison, args.summary)

	#----- Code that compares existing groups/sites to those in file -----

	print("")
	print("Step 6 of 7: Comparing site and groups in NetIM with the inputs from ServiceNow")
	print("")
	site_comparison = sync_servicenow_netim_sites_comparison(converted_sites, netim, args.summary)
	sync_servicenow_netim_sites_comparison_report(site_comparison, args.summary)

	#----- Code to compare geographical information -----

	print("")
	print("Step 7 of 7: Comparing location information in NetIM with the inputs from ServiceNow")
	print("")

	location_validation = sync_servicenow_netim_location_validation(converted_sites, netim)
	sync_servicenow_netim_location_validation_report(location_validation, args.summary)

	#-----
	print("")
	print("End of Comparison Report")
	print("---------------------------------------------------------------------------------------------------")

	if args.reconcile == True:
		print("")
		print("ServiceNow to NetIM Reconciliation Report")
		print("---------------------------------------------------------------------------------------------------")
		print("")
		print("Step 1 of 4: Reconciling devices in NetIM")
		print("")
		# Sync list of devices to NetIM
		# existing_devices?
		# different_devices?
		new_devices = device_comparison[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_NEW]
		new_device_ids = sync_netim_devices_create(netim, new_devices, converted_devices)	
		print("Created {} out of {} found new, valid devices in NetIM".format(len(new_device_ids), len(new_devices)))
		### For now, don't update different devices
		#updated_device_ids = sync_netim_devices_update(netim, \
		#	device_comparison[SYNC_SERVICENOW_NETIM_COMPARISON_DEVICES_DIFFERENT])

		print("")
		print("Step 2 of 4: Reconciling sites in NetIM")
		print("")
		# Sync list of locations to NetIM
		new_sites = site_comparison[SYNC_SERVICENOW_NETIM_COMPARISON_SITES_NEW]
		new_sites_ids = sync_netim_sites_create(netim, new_sites, converted_sites)
		print("Created {} out of {} found new, valid sites in NetIM".format(len(new_sites_ids), len(new_sites)))

		print("")
		print("Step 3 of 4: Adding devices to sites in NetIM")
		print("")
		# Add devices to sites in NetIM
		sync_netim_sites_devices_add(netim, converted_devices)

		print("")
		print("Step 4 of 4: Adding custom attributes in NetIM")
		print("")
		# Set up a process to track when devices were last synchronized with the CMDB. This allows an
		# automated way to determine if a device should be aged out because it is no longer tracked in
		# the CMDB
		sync_netim_custom_attribute_devices_cmdb_id(netim, new_devices, converted_devices)
		sync_netim_custom_attribute_devices_timestamp(netim, converted_devices)
		

		print("")
		print("End of Reconciliation Report")
		print("---------------------------------------------------------------------------------------------------")

	return

if __name__ == "__main__":
	main ()
