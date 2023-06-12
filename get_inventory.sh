#!/bin/bash

#######################################
# This script collects inventory data
# - JWT token
# - LLDP neighbors
#######################################

# BEGIN CONSTANTS
ztphost='10.10.10.201'
tftphost='10.10.10.201'
prot='http://'
sonicprot='https://'
ztp_finishedpath='/tftpboot/ztp_finished/'
username='admin'
password='YourPaSsWoRd'
inventorypath=/tftpboot/ifabric_inventory/
scriptname="get_inventory.sh"
filtered_lldp_filesuffix='.lldp_neighbors'
ztp_suffix=".ztp.finished"
# END CONSTANTS

#for pid in $(pidof -x $scriptname); do
#    if [ $pid != $$ ]; then
#        echo "[$(date)] : $scriptname : Process is already running with PID $pid"
#        exit 1
#    fi
#done

# get list of files from http ztp server
iplist=`curl -s $prot$ztphost$ztp_finishedpath | grep -o 'href=.*ztp'| sed "s/.ztp.*//" | sed s/.*=\"//`

for ip in $iplist
do
  echo $ip
  if [ ! -z "$ip" ] && [ $ip != '*' ]
    then
       # construct authentication credentials json
       json="{ \"username\" : \"$username\", \"password\" : \"$password\" }"
       # Authenticate to SONiC and receive JWT token
       resp=`curl -s -k -X POST $sonicprot$ip/authenticate -d "$json"`
       # Substract access_token key value
       token=`echo $resp |jq -r '.access_token'`

       if [ ! -z "$token" ] #If there is a token received and thus not zero
         then

           authstring="Authorization: Bearer $token" # Construct json string for token auth
           
           # Receive system metadata
	   resp=`curl -s -k -X GET $sonicprot$ip/restconf/data/sonic-device-metadata:sonic-device-metadata -H \"accept: application/yang-data+json\" -H "$authstring"|jq|sed '$ s/}$/,/'`
	   json=$resp

	   # Receive interfaces
           resp=`curl -s -k -X GET $sonicprot$ip/restconf/data/openconfig-interfaces:interfaces -H \"accept: application/yang-data+json\" -H "$authstring"|jq|sed 's/^{//'|sed '$ s/}$/,/'`
	   json=$json$resp

	   # Receive LLDP neighbor data
           resp=`curl -s -k -X GET $sonicprot$ip/restconf/data/openconfig-lldp:lldp -H \"accept: application/yang-data+json\" -H "$authstring"|jq|sed 's/^{//'`
	   json=$json$resp

	   # Add all data in JSON nice organized to file
	   echo $json|jq > $ip

	   # Create filtered LLDP neighbors file
	   lldp_neighbors=$ip$filtered_lldp_filesuffix
	   jq -r '."openconfig-lldp:lldp".interfaces.interface|.[] | select(.neighbors.neighbor != null)|.neighbors.neighbor[]|[ .id, .state ]' $ip > $lldp_neighbors

	   #upload to tftp host
	   #if curl -k --interface eth0 -T ${LOCALCONFIGFILE} tftp://${TFTPSERVER}${UPLOADPATH}${SAVEDCONFIGFILE}
	   if curl -k -T $lldp_neighbors tftp://$tftphost$inventorypath$lldp_neighbors
              then
                echo "Succesfull upload"
              else
                echo "Error uploading file"
           fi

         else # API access to device failed
           echo -e "\nCan not get API access to $ip\n"
       fi
  fi
done
