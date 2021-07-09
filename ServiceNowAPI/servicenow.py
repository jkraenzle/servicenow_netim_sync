# Copyright (c) 2021 Riverbed Technology, Inc.
#
# This software is licensed under the terms and conditions of the MIT License
# accompanying the software ("License"). This software is distributed "AS IS"
# as set forth in the License.
import logging
import os
import requests
import sys

__all__ = ['ServiceNow']

logging.captureWarnings(True)
logger = logging.getLogger(__name__)

#-----

class ServiceNow():
	"""ServiceNow API

	Responsible for ServiceNow table access for the limited set of information required to synchronize
	information with other Riverbed Network Performance Management solutions
	"""

	def __init__(self, hostname, username, password):

		self.hostname = hostname
		self.username = username
		self.password = password

		self.base_table_url = f'https://{self.hostname}/api/now/table/'
		self.tables_cache = {}

	def _cache(self, table_name, value):

		return

	def _get_table_name_and_value_from_link(self, link):
		elements = link.rsplit('/')
		# Verify https is the last element in the list
		if elements[-1] != 'https:':
			return None, None
	
		if len(elements) > 2 and elements[2] == 'table':
			value = elements[0]
			table_name = elements[1]
			return table_name, value
		else:
			logger.info(f'Unexpected link format {link}')
			return None, None
	
	def _get_from_table(self, table_name, value=None, parameters=[], verify=False):
		"""
		parameters
			name-value pairs (exclusive with sysparm_query)
			sysparm_display_value=[true|false|all]
			sysparm_exclude_reference_link=[true|false]
			sysparm_fields=[<>] where <> is comma-separated list of field names
			sysparm_query_no_domain=[true|false]
			sysparm_view=[desktop|mobile|both]

			sysparm_limit=<> for maximum number of records to return
			sysparm_no_count=[true|false]
			sysparm_offset=<> for offset into paginated data
			sysparm_suppress_pagination_header=[true|false]
		"""

		url = f'{self.base_table_url}{table_name}'

		if value != None:
			url += f'/{value}'

		if len(parameters) > 0:
			character = '?'
			for parameter in parameters:
				parameter_name = parameter_value = None
				if 'name' in parameter:
					parameter_name = parameter['name']
				if 'value' in parameter:
					parameter_value = parameter['value']
				if parameter_name != None and parameter_value != None:
					url += f'{character}{parameter_name}={parameter_value}'
					character = '&'

		headers = {}
		headers['Accept'] = 'application/json'
		headers['Content-Type'] = 'application/json'

		try:
			response = requests.get(url, auth=(self.username, self.password), headers=headers,
				verify=verify)
		except:
			raise

		if response.status_code not in [200, 204]:
			logger.info(f"Request call to get data from {url} returned an error")
			logger.debug(f"Status: {response.status_code}; Error Response: {response.text}")
			return None
		else:
			logger.info(f"{response.headers}")
			result = response.json()
			if 'result' in result:
				return result['result']
			else:
				return result

	def get_from_link(self, link):
		table_name, value = self.get_table_name_and_value_from_link(link)
		result = self._get_from_table(table_name, value)
		return result

	def get_configuration_items(self, parameters=[]):
		table_name = 'cmdb_ci'
		result = self._get_from_table(table_name, parameters=parameters)
		return result

	def get_configuration_item_data(self, sys_id, fields=[], display_value=True):
		table_name = 'cmdb_ci'
		parameters = []
		if display_value == True:
			parameters.append({'name':'sysparm_display_value', 'value':'all'})
		data = self._get_from_table(table_name, value=sys_id, parameters=parameters)

		configuration_item_data = {}
		for field in fields:
			if field in data:
				if display_value == True:
					if 'display_value' in data[field]:
						configuration_item_data[field] = data[field]['display_value']
				else:
					if 'value' in data[field]:
						configuration_item_data[field] = data[field]['value']
				
				if field not in configuration_item_data:
					logger.info(f'Did not find value for {field}')

		return configuration_item_data

	def get_locations(self, parameters=[]):
		table_name = 'cmn_location'
		result = self._get_from_table(table_name, parameters=parameters)
		return result

	def get_relationships(self, parameters=[]):
		table_name = 'cmdb_rel_ci'
		result = self._get_from_table(table_name, parameters=parameters)
		return result
		
