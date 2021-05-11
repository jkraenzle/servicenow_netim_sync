This project contains examples showcasing NetIM REST APIs, and utility methods to make using the APIs easier.

All python files can be run from the command line. They take the URL of a NetIM Core as an optional parameter, 
and otherwise assume NetIM Core is running on localhost:8543.

Most utility functions take a "test" parameter. 
When set to true the function will output JSON to the console instead of sending it as a request.

Required python libraries:
urllib3
requests

These scripts require Python 3.6 or later.

add_devices.py - 
    Read ExampleInput/add_new_devices.txt 
    POST to /api/netim/v1/devices
        
add_devices_to_alert_profiles.py - 
    Read ExampleInput/add_devices_to_alert_profiles.txt 
    PATCH to /api/netim/v1/alert-profiles
    
add_devices_to_polling_profiles.py - 
    Read ExampleInput/add_devices_to_polling_profiles.txt
    PATCH to /api/netim/v1/polling-profiles
 
basic_auth.py - Basic authentication example using requests library to log in to /api/netim/v1/rpc/login

delete_device.py - 
    Read ExampleInput/devices_to_delete.txt
    DELETE /api/netim/v1/devices/<id>

delete_device_list.py -
    Read ExampleInput/devices_to_delete.txt
    DELETE /api/netim/v1/devices/

get_devices.py - get /api/netim/v1/devices/
    
get_devices_by_vendor.py -
    Read ExampleInput/vendor_list.txt
    get /api/netim/v1/devices/ and filter on vendor name
    
get_devices_with_custom_attributes.py - 
    Read ExampleInput/custom_attribute_filter.txt
    get /api/netim/v1/custom-attribute-values/
    Find listed custom attributes and return associated device lists
    
get_metric_data_for_device.py - 
    Read ExampleInput/metric_types.txt for metric types to get
    read ExampleInput/device_metric_request_input.txt for metric classes to get from each device
    get /swarm/NETIM_NETWORK_METRIC_DATA_SERVICE/api/v1/network-metric-data
    
remove_devices_from_alert_profiles.py - 
    Read ExampleInput/remove_devices_from_alert_profiles.txt
    PATCH to /api/netim/v1/alert-profiles
    
remove_devices_from_polling_profiles.py
    Read ExampleInput/remove_devices_from_polling_profiles.txt
    PATCH to /api/netim/v1/polling-profiles