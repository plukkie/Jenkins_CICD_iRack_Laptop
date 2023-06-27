#!/usr/bin/env python3

import json
import requests
import urllib3
import tftpy
from pyquery import PyQuery as pq
from urllib3.exceptions import InsecureRequestWarning
from git.repo import Repo
from datetime import datetime
urllib3.disable_warnings()

settingsfile    = 'settings.json'
inventory_ext = '_inventory.json'
inventorypath = '/ifabric_inventory/'
user_name = "admin"
password = "YourPaSsWoRd"

def readsettings ( jsonfile ):

    ## input
    ## - jsonfile : json file with all settings
    ## return
    ## - json object with all settings

    try:
        f       = open(jsonfile)
        data    = json.load(f)

    except:
        result  = { "tryerror" : "Error reading settings file " + jsonfile }

    else:
        httpcont = data['ztp']['dyn_http_contname']
        if httpcont == '' or httpcont == None:
            data['ztp']['dyn_http_contname'] = data['ztp']['serverip']
		
        result = data

    f.close()
    return result


def create_switchip_array ( jsonconfig ):
	
	## Collect ztp finish files and extract the ip addresses
	## return List with IPs of all ZTP finished switches

	ztp=jsonconfig['ztp']
	suffix=ztp['ztp_finished_suffix']
	httpserver = ztp['dyn_http_contname']
	url=ztp['prot']+httpserver+'/'+ztp['ztp_finished_dir']
	filelisthtml = get_request ( url, "", "" )
	#print(filelisthtml.text)
	doc = pq(filelisthtml.content)
	mylist = doc('a').text().split()
	iplist = []
	for obj in mylist:
		if suffix in obj:
			ip=obj.replace(suffix, '')
			iplist.append(ip)

	return iplist

	
def get_request ( url, headerdata, jsondata ):

	page = requests.get ( url,
			      headers=headerdata,
			      data=jsondata,
			      verify=False )

	return page


def get_token ( ip ):
	url='https://'+ip+'/authenticate'
	credjson = { "username" : user_name, "password" : password }
	
	token = requests.post ( url,
		headers={'Content-Type': 'application/yang-data+json'},
		data=json.dumps(credjson),
		verify=False )

	access_token=json.loads(token.text)['access_token']

	return access_token


def get_inventory_data ( iplist ):

	## Collect JWT token from switches
	## Collect various platform data from API calls
	## Store it in file
	## Create filtered clean data and store in file
	## Upload to TFTP server

	apibase = '/restconf/data/'

	api_calls =  { "meta" : "sonic-device-metadata:sonic-device-metadata",
		       "serial" : "openconfig-platform:components/component=softwaremodule/software-module/state/openconfig-platform-software-ext:serial-number",
		       "stag" : "openconfig-platform:components/component=softwaremodule/state/service-tag",
		       "interfaces" : "openconfig-interfaces:interfaces",
		       "lldp" : "openconfig-lldp:lldp" }

	for ip in iplist:

		cleandict = {}
		print('Get token for switch ' + ip + '...')

		try:
			token = get_token(ip)

			headers = { 'Content-Type': 'application/yang-data+json',
			    	    "Authorization" : "Bearer " + token }

			inventorydict = {}

			for item in api_calls:
				myurl = "https://" + ip + apibase
				value = api_calls[item]
				myurl = myurl + value
			
				resp = get_request ( myurl, headers, "" )
				jsonresp = json.loads(resp.content)
				inventorydict.update(jsonresp)

			# Writing complete inventory to file, named as  ip-address
			with open(ip, "w") as outfile:
    				outfile.write(json.dumps(inventorydict, indent=4))

			cleandict.update(inventorydict[api_calls['meta']])
			cleandict.update({"openconfig-platform-software-ext:serial-number" : inventorydict['openconfig-platform-software-ext:serial-number']})
			cleandict.update({"openconfig-platform:service-tag" : inventorydict['openconfig-platform:service-tag']})
			cleandict.update({"interfaces" : {} })
			cleandict.update({"lldp_neighbors" : {} })

			# Raw interface array with status
			interfacearray = inventorydict[api_calls['interfaces']]['interface']

			# loop trough all switch interfaces
			for item in interfacearray:
				intname = item['config']['name']
				intadminstatus = item['config']['enabled']
				intoperstatus = item['state']['admin-status']
				intobject = { intname : { "enabled" : intadminstatus, "status" : intoperstatus } }
				cleandict['interfaces'].update(intobject)

			# Raw interface array with lldp data
			lldp_interface_array = inventorydict[api_calls['lldp']]['interfaces']['interface']


			# loop trough all lldp interfaces
			for interface in lldp_interface_array:

				try:
					neighborarray = interface['neighbors']['neighbor']
					#print(neighborarray)
					my_interface_name = neighborarray[0]['id']
					#print( my_interface_name)
					myarray = []

					for obj in neighborarray:
						neighbordetails = obj['state']
						#print(neighbordetails)
						#print( my_interface_name, neighbordetails)
						myarray.append(neighbordetails)

					if len(myarray) != 0:
						lldp_int_object = {  my_interface_name : myarray }
						cleandict['lldp_neighbors'].update(lldp_int_object)

				except:
					print('no LLDP neighbor found on interface ' + interface['name'])

			
			filename = ip+inventory_ext

			try:
				with open(filename, "w") as outfile:
    					outfile.write(json.dumps(cleandict, indent=4))
				print('Successfully saved inventory locally: ' + filename)
				
			except:
				print('Errors writing json inventory to file: ' + filename)
				
			try:
				tftpserver = jsonconfig['ztp']['serverip']
				client = tftpy.TftpClient(tftpserver, 69)
				client.upload(inventorypath+filename, filename)	
				print('Succesfull TFTP upload to ' + tftpserver + inventorypath+filename)

			except:
				print('Failed TFTP upload: ' + tftpserver + inventorypath+filename)

		except:
			print('Error connecting to ' + ip + '. Skipping switch! ')

	

##### MAIN PROGRAM #####

# Create var from configuration file
jsonconfig = readsettings ( settingsfile )

# create list with all ip addresses of ztp finished switches
iparray = create_switchip_array ( jsonconfig )
print(iparray)

# Collect data with api requests and save to files
get_inventory_data ( iparray )

