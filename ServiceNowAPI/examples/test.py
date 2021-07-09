from servicenow import ServiceNow

import argparse
import getpass

def validate_filters(filters):
	valid_filters = []
	for filter in filters:
		if 'name' not in filter:
			logger.info(f"Invalid filter {filter}. No attribute 'name'")
			continue
		if 'value' not in filter:
			logger.info(f"Invalid filter {filter}. No attribute 'value'")
			continue
		valid_filters.append(filter)

	return valid_filters

def get_filter_name_value_pair(filter):
	filter_name = filter['name']
	filter_value = filter['value']
	return filter_name, filter_value

def set_filter_name_value_pair(filter_name, filter_value):
	filter = {}
	filter['name'] = filter_name
	filter['value'] = filter_value
	return filter

def filter_cis(cis, include_filters=[], exclude_filters=[]):
	filtered_cis = []

	# Validate filters
	valid_include_filters = validate_filters(include_filters)
	valid_exclude_filters = validate_filters(exclude_filters)

	# Filter by inclusion
	included_cis = []
	# If no inclusion filters, include everything
	if len(valid_include_filters) == 0:
		included_cis = cis
	# Otherwise, roll through the inclusion filters and only include things that match
	for include_filter in valid_include_filters:
		filter_name, filter_value = get_filter_name_value_pair(include_filter)
		for ci in cis:
			if filter_name in ci:
				ci_value = None
				if 'value' in ci[filter_name]:
					ci_value = ci[filter_name]['value']
				if filter_value == ci_value:
					included_cis.append(ci)
				if 'display_value' in ci[filter_name]:
					ci_value = ci[filter_name]['display_value']
				if filter_value == ci_value:
					included_cis.append(ci)

	# Filter by exclusion
	cis_after_exclusion = []
	# If no exclusion filters, include everything
	if len(valid_exclude_filters) == 0:
		cis_after_exclusion = cis
	# Otherwise, roll through the exclusion filters and only include things that don't match
	for exclude_filter in valid_exclude_filters:
		filter_name, filter_value = get_filter_name_value_pair(exclude_filter)
		for ci in cis:
			if filter_name in ci:
				ci_value = None
				if 'value' in ci[filter_name]:
					ci_value = ci[filter_name]['value']
				if filter_value != ci_value:
					cis_after_exclusion.append(ci)
				if 'display_value' in ci[filter_name]:
					ci_value = ci[filter_name]['display_value']
				if filter_value != ci_value:
					cis_after_exclusion.append(ci)

	filtered_cis = [ci for ci in included_cis if ci in cis_after_exclusion] 
	return filtered_cis

def main():

	parser = argparse.ArgumentParser(description='Python utility to test ServiceNow API')
	parser.add_argument('--servicenow_hostname', help='DNS resolvable hostname or IP address')
	parser.add_argument('--servicenow_username', help='ServiceNow username')
	parser.add_argument('--servicenow_password', help='ServiceNow password')
	args = parser.parse_args()

	if args.servicenow_hostname == None:
		print("No hostname was specified. Use --servicenow_hostname argument to provide a hostname. Exiting ...")
	if args.servicenow_username == None:
		print("No username was specified. Use --servicenow_username argument to provide a username. Exiting ...")

	servicenow_password = args.servicenow_password
	if servicenow_password == None or servicenow_password == "":
		servicenow_password = getpass.getpass

	print("ServiceNow")
	try:
		servicenow = ServiceNow(args.servicenow_hostname, args.servicenow_username, args.servicenow_password)
	except:
		raise

	#print("Getting a list of tables from ServiceNow")
	#tables = servicenow._get_from_table('sys_db_object')
	#for table in tables[:10]:
	#	if 'name' in table:
	#		print(table['name'])

	print("Getting all CIs from ServiceNow")
	parameters = []
	parameters.append({'name':'sysparm_display_value', 'value':'all'})

	cis = servicenow.get_configuration_items(parameters=parameters)
	ci_count = len(cis)
	print(f"There are {ci_count} CIs in ServiceNow.")

	include_filters = [{'name':'category', 'value':'Hardware'}]
	exclude_filters = []
	filtered_cis = filter_cis(cis, include_filters=include_filters)

	first_data_list = []
	for filtered_ci in filtered_cis:
		data = {}
		data['name'] = filtered_ci['name']
		data['sys_class_name'] = filtered_ci['sys_class_name']
		data['location'] = filtered_ci['location']
		data['ip_address'] = filtered_ci['ip_address']
		data['sys_id'] = filtered_ci['sys_id']
		data['operational_status'] = filtered_ci['operational_status']
		data['vendor'] = filtered_ci['vendor']
		data['model_id'] = filtered_ci['model_id']
		data['monitor'] = filtered_ci['monitor']
		first_data_list.append(data)
	print(first_data_list)

	#second_data_list = []
	#for filtered_ci in filtered_cis:
	#	# Get a series of information about the CI
	#	fields = []
	#	# Name
	#	fields.append('name')		
	#	# Class
	#	fields.append('sys_class_name')
	#	# Location
	#	fields.append('location')
	#	# IP Address
	#	fields.append('ip_address')
	#	# CI ID
	#	fields.append('sys_id')
	#	# CI Status
	#	fields.append('operational_status')
	#	# Manufacturer
	#	fields.append('vendor')
	#	# Model 
	#	fields.append('model_id')
	#	# Monitor
	#	fields.append('monitor')
	#	# Monitored Type
	#	fields.append('type')
	#
	#	sys_id = filtered_ci['sys_id']
	#	if 'value' in sys_id:
	#		sys_id = sys_id['value']
	#	#data = servicenow.get_configuration_item_data(sys_id, fields, display_value=True)
	#
	#	second_data_list.append(data)
	#print(second_data_list)

	locations = servicenow.get_locations()
	if locations != None:
		location_count = len(locations)
		print(f"There are {location_count} locations in the ServiceNow instance.")

	return

if __name__ == "__main__":
	main()
