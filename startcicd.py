#!/usr/bin/env python3

import json
import requests
import sys
import time
import tempfile
import os
from git.repo import Repo
from datetime import datetime

settingsfile    = 'settings.json'


## Functions

def return_url ( settingsobject ):
    
    """
    input:
    - settingsobject : JSON object

    returns constructed url & httheaders if required

    This function reads cli arguments and reads corresponding settings from json file.
    It constructs the url for the API call & the required http headers.
    With the urls, the receiver starts and stops gns3 projects and ansible tower templates.
    This script is started by the Jenkins pipeline.
    """
    a = sys.argv
    url = ""
    httpheaders = {}
    jtname = ""
    jturl = ""
    jsonobj = {}

    if 'startgns3' in a[1:] or 'stopgns3' in a[1:]: #It is a call to a GNS3 project
        toplevelkey = 'gns3'
        s = settingsobject[toplevelkey] #get gns3 keys from settings
        url = s['prot']+s['serverip']+":"+s['serverport']+"/"+s['projecturi']

        if 'devstage' in a[2:]: #dev/test stage is specified
            projectname = s['newprojectdevjson']['name']
        elif 'prodstage' in a[2:]: #prod stage is specified
            projectname = s['newprojectprodjson']['name']
        else:
            print('No Stage specified. Please add "devstage" or "prodstage"')
            sys.exit()

        urltuple = ( url, httpheaders )
        resp = json.loads(request ( urltuple, 'get' )) #Get project id
        for x in resp:
            if x['name'] == projectname:
                projectid = x['project_id']
                print('Found project id ' + projectid + ' for project name ' + projectname)
                time.sleep(1)
                url = url + "/" + projectid

        if 'startgns3' in a[1:]:
            checkurl = url + '/' + s['nodescheck'] #construct gns3 api to check node status
            urltuple = ( checkurl, httpheaders )
            print('Check if nodes in GNS3 are already running...')
            resp = request ( urltuple, 'get' ) #Check status of all nodes in the project
            #print(resp)
            if type(resp) == str: resp = json.loads(resp) #From str to json
            stopped = False #used to track if a gns3 node is stopped
            for item in resp: #find all nodes and their status
                nodename = item['name']
                nodeid = item['node_id']
                status = item['status'].lower()
                if status == 'stopped': #Stopped node, need to start all nodes with API request
                    #stopped = True
                    #print('There is a stopped node. Will start all nodes now in GNS3')
                    #url = url +  "/" + s['nodescheck'] + '/' + s['nodesstarturi']
                    #break #exit loop
                    if 'leaf' in nodename.lower() or 'spine' in nodename.lower():
                        stopped = True
                        print('There is a stopped fabric node. Will start node ' + nodename + ' in GNS3...')
                        starturl = checkurl + '/' + nodeid + '/' + s['nodesstarturi']
                        nodestarttuple = ( starturl, httpheaders )
                        print(nodestarttuple)
                        resp = request ( nodestarttuple, "post") 
                        time.sleep(1)

                        #url = url +  "/" + s['nodescheck']
            #url = url +  "/" + s['nodescheck'] + '/' + s['nodesstarturi']
            #break #exit loop

            if stopped == False: url = "proceed = True" #All nodes already started, jenkins can proceed
            else: url = checkurl + '/allstarted'
  
        #stop all gns3 nodes
        if 'stopgns3' in a[1:]: url = url + "/" + s['nodescheck'] + '/' + s['nodesstopuri']

    elif 'launchawx' in a[1:]: #It is a call to Ansible Tower
        toplevelkey = 'awx'
        s = settingsobject[toplevelkey] #get tower details from settings
        if 'httpheaders' in s: httpheaders = s['httpheaders']

        if 'relaunch' in a[2:]: #their were failed playbook runs and a relaunch was requested
            relaunchsuffix = str(a[3]) #the job relaunch uri of the failed job
            url = s['prot']+s['serverip']+':'+s['serverport'] + relaunchsuffix

        else: #tower find template matched to setting file
            url = s['prot']+s['serverip']+':'+s['serverport']+'/'+s['projecturi']
            urltuple = ( url, httpheaders )
            resp = request ( urltuple, 'get' ) #get all job templates from tower
            if type(resp) == str: resp = json.loads(resp) #From str to json
        
            if 'devstage' in a[2:]: #dev/test stage specified
                if 'configure' in a[3:]:
                    jtname = s['teststage_jobtemplate_name_deploy']
                elif 'test' in a[3:]:
                    jtname = s['teststage_jobtemplate_name_test']
                else:
                    print('No stagefase specified. Please add "configure" or "test"')
                    sys.exit()

            elif 'prodstage' in a[2:]: #prod stage specified
                if 'configure' in a[3:]:
                    jtname = s['prodstage_jobtemplate_name_deploy']
                elif 'test' in a[3:]:
                    jtname = s['prodstage_jobtemplate_name_test']
                else:
                    print('No stagefase specified. Please add "configure" or "test"')
                    sys.exit()
            elif 'template' in a[2]: #Template specified on cli
                try:
                    jtname = a[3] #Template name in Tower to run
                except:
                    print('No Tower Project template name specified.\nPlease add "template <Your_Tower_Template_Name>"')
                    sys.exit()
      
            else:
                print('No Stage specified. Please add "devstage" or "prodstage" or "template <template>"')
                sys.exit()

            templates = resp['count'] #number of job templates found
        
            for jt in resp['results']: #search through available jobtemplates and find the one we need
                #print(jtname)
                #print(jt['name'])
                if jtname == jt['name']: #found match
                    print('Found requested Job Template')
                    jturl = jt['url'] #This uri addon is needed to launch the template
                    jtid = jt['id'] #Job template id
                    print('Job Template ID : ' + str(jtid))
            
            if jturl == "":
                print('No matching Job template found on Ansible Tower for "' + jtname + '".')
                print('Check spelling or the available Job templates on Tower.')
                sys.exit()
        
            #this is the api url to start the job template
            url = s['prot']+s['serverip']+':'+s['serverport'] + jturl + s['launchsuffix']+"/"
    
    elif 'creategns3project' in a[1:]:
        toplevelkey = 'gns3'
        s = settingsobject[toplevelkey] #get gns3 keys from settings
        url = s['prot']+s['serverip']+":"+s['serverport']+"/"+s['projecturi']
        if 'devstage' in a[2:]: #dev/test stage specified
            jsonobj = s['newprojectdevjson'] 
        elif 'prodstage' in a[2:]: #prodstage specified
            jsonobj = s['newprojectprodjson'] 
        else:
            print('No Stage specified. Please add "devstage" or "prodstage"')
            sys.exit()

    else: #No cli arguments given
        print('\nusage : ' + sys.argv[0] + ' <option>\n')
        print(' - creategns3project devstage/prodstage : will start GNS3 dev or prod project')
        print(' - startgns3 devstage/prodstage [ optional: noztp_check ]: start GNS3 project')
        print(' - stopgns3 devstage/prodstage : will stop GNS3 project')
        print(' - launchawx devstage: will start job template for test env on AWX (from settingsfile)')
        print(' - launchawx prodstage: will start job template for prod env on AWX (from settingsfile)')
        print(' - launchawx template "AWX template to start" : will start this job template on AWX')
        print(' - config=<your_custom_settingsfile.json> (instead of default settings.json')
        print('=========================================================================')
        sys.exit()

    if 'relaunch' in url: #a job relaunch is requested, add failed hosts only
        return url, httpheaders, { "runtype" : toplevelkey }, { "hosts" : "failed" }
    else: #normal job template url
        return url, httpheaders, { "runtype" : toplevelkey }, jsonobj



def readsettings ( jsonfile ):

    """
    input
    - jsonfile : json file with all settings

    return
    - json object with all settings
    """

    try:
        f       = open(jsonfile)
        data    = json.load(f)

    except:
        result  = { "tryerror" : "Error reading settings file " + jsonfile }

    else:
        result = data
    
    f.close()
    return result


def request ( url, reqtype, jsondata={} ):
    
    """
    input
    - url : array object with url and headers
    
    return
    - http request result

    This function requests an api call to the url endpoint.
    """
    try:
        if url[3] != '{}': #there is json data added to url
            jsondata = url[3]
    except:
        pass

    if reqtype == 'post':
        #print(url)
        #print(url[0])
        #print(url[1])
        r = requests.post ( url[0], headers=url[1], json=jsondata )
    elif reqtype == 'get':
        r = requests.get ( url[0], headers=url[1], json=jsondata )
    elif reqtype == 'put':
        #print(url[0])
        #print(url[1])
        #print(jsondata)
        r = requests.put ( url[0], headers=url[1], json=jsondata )
    elif reqtype == 'delete':
        r = requests.delete ( url[0], headers=url[1], json=jsondata )
  
    statuscode = r.status_code
    if statuscode >= 400:
        #obj = statuscode
        #print(r.content.decode('utf-8'))
        obj = r.content.decode('utf-8') #from bytes to dict
    else:
        obj = r.content.decode('utf-8') #from bytes to dict
    #print(obj)
    
    return obj



def jobstatuschecker ( dataobject ):

    """
    inputs
    - dataobject : json or string object, i.e. returned from API call

    return
    - proceed : string (True, False or relaunch url)

    This function checks the status of an Ansible Tower Job.
    The dataobject is the return object of an previous started API call to start
    a Job Template. The job template starts a job and with the job id
    the jobstatuschecker will poll the status till finished.
    
    """

    status   = ''
    failed   = ''
    finished = ''
    proceed  = "False" #This can be used by Jenkins to determine if pipeline should continue
    st       = 10 #Delay between check requests
    
    if type(dataobject) == str: dataobject = json.loads(dataobject) #From str to json
    #print(dataobject) 
    urisuffix = dataobject['url'] #Catch the job url that was created
    relaunchsuffix = dataobject['related']['relaunch'] #needed if relaunch is needed
    #print(relaunchsuffix)
    s = settings['awx']
    url = s['prot']+s['serverip']+":"+s['serverport']+urisuffix #create uri for API call to awx to check job status
    myurltuple = ( url, urltuple[1] ) #Create urltuple with url and headers
   
    # start Loop, get every 10 seconds jobstatus
    #
    # - jobstatus   (can be pending, running, successful, failed)
    # - jobfailed   (can be false, true)
    # - jobfinished (can be null or time, i.e 2022-10-24T14:38:50.009531Z)

    print('\n Starting jobchecker. Waiting till AWX template finishes its job...')

    while True: #check job status. when finished return status, used by jenkins
    
        response = request ( myurltuple, "get" ) #Request API call
        if type(response) == str: response = json.loads(response) #From str to json
   
        #Get status of three keys available in the job dict
        result = { 
                   "jobstatus"   : response['status'],
                   "jobfailed"   : response['failed'],
                   "jobfinished" : response['finished']
                 }

        status   = result['jobstatus'].lower()
        failed   = result['jobfailed']
        finished = result['jobfinished']
    
        if status == 'successful':
            if failed == 'false' or failed == False:
                print('\n Succesful job finish at ' + finished)
                proceed = "True"
                break
            else:
                print('\n Job finished succesful but with failed result.')
                break
            cont
        elif status == 'failed':
            if finished != None and finished != 'null': #return relaunch task to jenkins
                print('\n Job finished with "failed" status. Check job logs on AWX.')
                print(' Will notify to run job again on failed hosts.')
                proceed = relaunchsuffix
                break
            else:
                print('\n Job finished with "failed" status due to finish errors. Will not proceed.')

        print('  Job status : ' + status + '. Wait ' + str(st) + ' secs till next check..')
        time.sleep(st)

    print()

    return proceed #returns the status of the job that was started



def provisiongns3project (jsonobject):

    """
    Build complete GNS3 project.
    """
    try:
        projectid = jsonobject['project_id']
    except:
        projectid = "7eb56e95-0b70-48c8-90bc-fa920e44f599"

    templateid = ""
    httpheaders = {} 
    s = settings['gns3']
    nd = s['nodesdata']
    baseurl = s['prot']+s['serverip']+':'+s['serverport']
    projecturi = s['projecturi']
    templatesuri = s['templatesuri']
    templatedict = nd['templates'] #Data for the Network fabric roles
    leafcount = templatedict['leaf']['count']
    spinecount = templatedict['spine']['count']
    bordercount = templatedict['border']['count']
    hosts = templatedict['leaf']['hosts']
    url = baseurl + '/' + templatesuri
    urltuple = ( url, httpheaders )
    templates = request ( urltuple, "get" )
    jsondict = json.loads(templates) #All templates found on GNS3 server
    newdict = { "nodes" : {}, "clouds" : {}, "hostlinkarray" : [] }
    jsonadd = {}
    switchnr = 0 #counter for only leaf & spine switches
    bswitchnr = 0
    projecturl = baseurl + '/' + projecturi + '/' + projectid
    computeurl = baseurl + '/v2/projects/' + projectid

    #First create Host nodes
    hostlinkarray = [] #This array is used to create links between leafs and hosts
    hostcount = hosts['count'] #This is hostcount per leafpair
    totalhosts = int(hostcount * leafcount/2) #Total hosts connected to leafs

    if hostcount > 0: #need to build hosts connected to leafs (server nodes)

        hosttemplatename = hosts['name']
        leaflinkjson = hosts['leaflinks']
        hostlinkjson = hosts['hostlinks']
        hostpos = templatedict['leaf']['pos']
        posshift = nd['posshift']
        hostmgtports = hosts['mgtport']
        createnodeurl = projecturl + '/templates'
        macadd = ":00:01"
        hostbasemac = hosts['mac']['base']
        hostmacstart = hosts['mac']['start']
        counter = 0
        absolutehostswitchnr = leafcount + spinecount + bordercount

        for tn in jsondict: #Loop through available templates in GNS3 and find id
            if tn['name'] == hosttemplatename: #Found template match for servernodes
                tid = tn['template_id'] #VNF Template ID from GNS3
                cid = tn['compute_id'] #compute id of template
                ttype = tn['template_type']
                print('Found template for Hostnode with id ' + tid + ' with name ' + hosttemplatename)
                if cid == None or cid == 'null': #Embedded GNS3 template
                    #urltuple = ( computeurl+'/'+ttype+'/nodes', httpheaders )
                    urltuple = ( computeurl+'/templates/' + tid, httpheaders )
                else: #Custom GNS3 template
                    urltuple = ( createnodeurl+'/'+tid, httpheaders )

                print(urltuple)
                startx = hostpos['x'] + int(posshift/2) 
                starty = hostpos['y'] + int(posshift)
                i = 0
                linkarray = [ ]

                for cnt in range(int(leafcount/2)): #For all leafpairs, create hostnodes
                    leafpair = cnt+1
                    x = startx + cnt*posshift*2 
                    y = starty
                    hostadapterstep = hostlinkjson['adapterstep']
                    hostportstep    = hostlinkjson['portstep']
                    leafadapterstep = leaflinkjson['adapterstep']
                    leafportstep    = leaflinkjson['portstep']
                    hostadapter = hostlinkjson['1st_adapter_number']
                    hostport    = hostlinkjson['port']
                    leafadapter = leaflinkjson['1st_adapter_number']
                    leafport    = leaflinkjson['port']

                    for host in range(hostcount): #Create all hosts per leafpair

                        counter += 1
                        absolutehostswitchnr += 1
                        if cid == None or cid == 'null': jsonadd = { "compute_id" : "local", "x" : x, "y" : y }
                        else: jsonadd = { "x" : x, "y" : y } #Position of the node on GNS raster
                        resp = json.loads(request ( urltuple, "post", jsonadd )) #create node in project
                        nodeid = resp['node_id'] #Get nodeid for later usage
                        time.sleep(0.5)
                        x += int(posshift/3) #How much to shift position for next device icon
                        y += int(posshift/3) #How much to shift position for next device icon

                        hostmac = hostbasemac + str(hostmacstart) + macadd
                        newdict['nodes']['host'+str(counter)] = { "nodeid" : nodeid, "mgtport" : hostmgtports, "mac" : hostmac, 'nr' : absolutehostswitchnr }

                        for linkcnt in range(2): #Create both link objects for later usage
                            linkobject = { "node_id" : nodeid, "adapter_number" : hostadapter, "port_number" : hostport }
                            hostlinkarray.append(linkobject)
                            linkobject = { "node_id" : "leaf"+str(leafpair+cnt+linkcnt), "adapter_number" : leafadapter, "port_number" : leafport }
                            hostlinkarray.append(linkobject)
                            hostadapter += hostadapterstep
                            hostport += hostportstep

                        leafadapter += leafadapterstep
                        leafport += leafportstep
                        hostmacstart += 1

        newdict['hostlinkarray'] = hostlinkarray #Replace later the leafname by node_id of leaf


    for template in templatedict: #Loop through desired templates from settingsfile
        reqname = templatedict[template]['name']
        
        if template == 'cloud': #Build Nodetype cloud
            cdict = templatedict[template] #cloud Key/values
            if cdict['count'] == "": count = leafcount + spinecount + bordercount + totalhosts #Number of clouds to create
            else: count = int(cdict['count']) #How many clouds to create
            print('Will create ' + str(count) + ' clouds for oob management ports of switches..')
            time.sleep(1)

            pos = cdict['pos'] #Which pos will clouds be drawn in raster
            port = cdict['port'] #Adapter, port of eth port
            cid = { "compute_id" : "local", "x" : pos['x'], "y" : pos['y'] }
            for tn in jsondict: #Loop through available templates in GNS3 and find id
                if tn['name'] == reqname: #Found template matching desired cloud role
                    tid = tn['template_id'] #VNF Template ID from GNS3
                    print('Found template id ' + tid + ' for name ' + reqname)

                    #Build json dict to create clouds
                    newdict[template] = { "name" : reqname, "count" : count,
                                          "tid" : tid, "pos" : pos,
                                          "port" : cdict['port'] }

                    url = baseurl + '/' + projecturi + '/' + projectid + '/templates/' + tid
                    urltuple = ( url, httpheaders )
                    #print(url)
                    for cnt in range(count): #Build x amount of clouds
                        print('Creating cloud ' + str(cnt+1) + '...') 
                        resp = json.loads(request ( urltuple, "post", cid )) #create node in project
                        #nodeid = resp['node_id'] #Get nodeid for later usage
                        #print(resp)
                        #print()
                        newdict['clouds'][str(cnt+1)] = { "name" : resp['name'], "node_id" : resp["node_id"], "port" : port }
                        time.sleep(0.5)

                    
                   # print(newdict['clouds'])

        else:
            count = templatedict[template]['count'] #Number of type (spine or leafs)
        
        pos     = templatedict[template]['pos']
        x = pos['x']
        y = pos['y']

        if template == 'leaf' or template == 'spine' or template == 'border': #Leaf or spine switch
            basemac = templatedict[template]['mac']['base']
            macstart = templatedict[template]['mac']['start']
            macadd = ":00:01"
            interlinks = templatedict[template]['interlinks']
            borderlinks = templatedict[template]['borderlinks']
            vlti = templatedict[template]['vlti']

            if template == 'leaf':
                il = spinecount #How many interlinks on leaf
                
            elif template == 'spine':
                il = leafcount #How many interlinks on spine
            elif template == 'border':
                il = 0
        
            print('Working on role: ' + template)
            print('Start position: ' + str(pos))
            print('provision ' + str(count) + ' elements.')
            print('start mac: ' + str(macstart))

            for tn in jsondict: #Loop through available templates in GNS3 and find id
 
                if tn['name'] == reqname: #Found template matching desired role (i.e. leaf, spine..)  
                    tid = tn['template_id'] #VNF Template ID from GNS3
                    print('Found template id ' + tid + ' for name ' + reqname)
                    newdict[template] = { "name" : reqname, "count" : count, "tid" : tid, "pos" : pos } #Build new key/value dict
                    url = baseurl + '/' + projecturi + '/' + projectid + '/templates/' + tid
                    #print(url)
                    urltuple = ( url, httpheaders )
                    #adapterstep = interlinks['adapterstep'] #Next adapter step
                    #portstep = interlinks['portstep'] #Next port step

                    for loop in range (0, count): #Provision all devices for this role

                        #if template == 'leaf' or template == 'spine':
                        switchnr += 1 #Only raise switchnr for spines & leafs

                        nodename = template + str(loop+1) #Which node we are working on
                        print('Creating node ' + nodename + '...')
                        jsonadd = { "x" : x, "y" : y } #Position of the node on GNS raster
                        resp = json.loads(request ( urltuple, "post", jsonadd )) #create node in project
                        nodeid = resp['node_id'] #Get nodeid for later usage
                        #print(type(resp))
                        time.sleep(0.5)
                        x += nd['posshift'] #How much to shift position for next device icon

                        #Build JSON data to build links for later usage
                        mgtport = templatedict[template]['mgtport']
                      
                        if template == 'border':
                            adapterstep = borderlinks['adapterstep'] #Next adapter step
                            portstep = borderlinks['portstep'] #Next port step
                            adapter = borderlinks['1st_adapter_number'] #First adapter
                            port = borderlinks['port']
                            bswitchnr += 1
                        else:
                            adapterstep = interlinks['adapterstep'] #Next adapter step
                            portstep = interlinks['portstep'] #Next port step
                            adapter = interlinks['1st_adapter_number'] #First adapter
                            port = interlinks['port'] #First port
                        
                        ports = { }
                        bports = { }


                        for link in range(0, il): #Add for total nr of interlinks needed the port details
                            linknr = link+1 #Start @1
                            ports[str(linknr)] = { "adapter_number" : adapter, "port" : port }
                            adapter += adapterstep #Next adapter
                            port += portstep #Next port

                        if template == 'border':
                            linknr = 0
                            for link in range(2): #Add for total nr of borderlinks needed the port details
                                linknr = link+1 #Start @1
                                bports[str(linknr)] = { "adapter_number" : adapter, "port" : port }
                                adapter += adapterstep #Next adapter
                                port += portstep #Next port
                        
                        
                        if nodename == 'leaf1' or nodename == 'leaf2': #Only add borderlink details for leaf1 and leaf2
                            adapterstep = borderlinks['adapterstep'] #Next adapter step
                            portstep = borderlinks['portstep'] #Next port step
                            adapter = borderlinks['1st_adapter_number'] #First adapter
                            port = borderlinks['port'] #First port
                            bports = { }

                            for blink in range(0, bordercount): #Add for total nr of borderlinks needed the port details
                                blinknr = blink+1 #Start @1
                                bports[str(blinknr)] = { "adapter_number" : adapter, "port" : port }
                                adapter += adapterstep #Next adapter
                                port += portstep #Next port
                   

                        vltarray = []
                        jsonadd = {}

                        if vlti['count'] > 0: #Found VLTi links
                            vltlinks = vlti['count']
                            vltadapter = vlti['1st_adapter_number']
                            vltport = vlti['port'] 
                            adapterstep = vlti['adapterstep']
                            portstep = vlti['portstep']
                            for vltlink in range(0, vltlinks): #Add for total nr of links needed the port details
                                jsonadd = { "node_id" : nodeid, "adapter_number" : vltadapter, "port_number" : vltport } 
                                vltarray.append(jsonadd)
                                vltadapter += adapterstep
                                vltport += portstep

                        #print(nodename)
                        #print(ports)
                        mac = basemac + str(macstart) + macadd
                        if template == 'border':
                            #nr = bswitchnr+100
                            nr = switchnr
                        else: nr = switchnr
                        #print(bports)
                        newdict['nodes'][nodename] = {  "vlt" : vltarray,
                                                        "nr" : str(nr),
                                                        "nodeid" : nodeid,
                                                        "interlinks" : ports,
                                                        "borderlinks" : bports,
                                                        "mgtport" : mgtport, #Add nodeid & ports to hostname for later usage
                                                        "mac" : mac }

                        macstart += 1

    #print(newdict)


    #Add hostname and mac address to created nodes
    print('Adding custom base mac-address & nodename to Nodes...')
    url = baseurl + '/' + projecturi + '/' + projectid
    for obj in newdict['nodes']: #cycle to all nodes and request API call to change values in GNS3 project
        nodeid = newdict['nodes'][obj]['nodeid']
        nodename = obj
        nodeurl = url + '/' + 'nodes/' + nodeid
        macaddress =  newdict['nodes'][obj]['mac'] 
        jsonadd = { "name" : nodename, "properties" : { "mac_address" : macaddress }  }
        urltuple = ( nodeurl, httpheaders )
        print('nodename ' + nodename +', base mac-address ' + macaddress)
        resp = request ( urltuple, "put", jsonadd ) #Update node config
        time.sleep(0.5)


    #Add links to nodes
    linkurl = url + '/links' #Url to create links
    #print('Creating links between elements...')
    time.sleep(0.5)

    for nodename in newdict['nodes']: #Cycle through list wih node names (leaf1, leaf2, spine1, spine2, border1 etc)
        obj =  newdict['nodes'][nodename] #This is dict of node with links nr, ports, nodeid

        if 'leaf' in nodename: #When found a leaf
            leafnr = nodename.lstrip('leaf') #What is the leaf nr
            mynodeid = obj['nodeid'] #Node ID of leaf
            
            #Need to replace leafname with nodeid in hostlinkarray
            for idx, item in enumerate(newdict['hostlinkarray']):
                if item['node_id'] == nodename:
                    item['node_id'] = mynodeid
                    print('Replaced linkarray pos ' + str(idx) + ',' + nodename + ' with node_id ' + mynodeid)
                    newdict['hostlinkarray'][idx] = item
                
                    break
           
            linkcnt = 0

            for cnt in range(2):

                linktype = ""

                if cnt == 0:
                    linktype = 'interlinks'
                    linkcnt = len(obj[linktype]) #How many interlinks on the leaf
                    print(nodename + ' has ' + str(linkcnt) + ' interlinks.')

                if cnt == 1:
                    linktype = 'borderlinks'
                    linkcnt = len(obj[linktype]) #How many interlinks on the leaf
                    print(nodename + ' has ' + str(linkcnt) + ' borderlinks.')

                for link in range (linkcnt): #Loop through all links for this node
                    mylinkarray = [] #Array with the json data to create a link
                    linknr = link+1 #Start count at 1 (these numbers are in the dict)
                    myadapter = obj[linktype][str(linknr)]['adapter_number']
                    myport = obj[linktype][str(linknr)]['port']
                    if linktype == 'interlinks':
                       peerswitchprefix = 'spine'
                    elif linktype == 'borderlinks':
                       peerswitchprefix = 'border'

                    #print(newdict['nodes'])
                    peerswitch = peerswitchprefix + str(linknr)  #Which peer switch are we connected
                    linkpeerid = newdict['nodes'][peerswitch]['nodeid'] #Id of spine
                    linkpeeradapter = newdict['nodes'][peerswitch][linktype][leafnr]['adapter_number']
                    linkpeerport = newdict['nodes'][peerswitch][linktype][leafnr]['port']
                    #print('peerswitch :', peerswitch, 'linkpeerport :', linkpeerport)

                    #Add to array with two json objects for one link
                    
                    for mycnt in range(2):
                        if mycnt == 0: #Add my side of link
                            linkobj = { "node_id" : mynodeid, "adapter_number" : myadapter, "port_number" : myport }
                        elif mycnt == 1: #Add peer side of link
                            linkobj = { "node_id" : linkpeerid, "adapter_number" : linkpeeradapter, "port_number" : linkpeerport }

                        mylinkarray.append(linkobj) #create array with to JSON objects, is for 1 link
                    
                    jsonadd = { "nodes" : mylinkarray } #This is json for the api call to create a link
                    #print(nodename, peerswitch, jsonadd)
                    urltuple = ( linkurl, httpheaders )
                    print('Create link between ' + nodename + ' and ' + peerswitch)
                    resp = request ( urltuple, "post", jsonadd ) #create link
                    time.sleep(0.5)



        #print(newdict['hostlinkarray'])
        try:
            vltlinks = len(obj['vlt'])
        except:
            vltlinks = 0

        if vltlinks != 0: #Need to add vlt links
            switchnr = int(obj['nr'])
            peerswitchnr = switchnr+1
            peervltlinkarray = []
            for switch in newdict['nodes']:
                nr = int(newdict['nodes'][switch]['nr'])
                if nr == peerswitchnr: #Found vlt partnerswitch
                    peervltlinkarray = newdict['nodes'][switch]['vlt']
                    
            mylinkarray = []
            if (switchnr % 2) != 0: #Odd switchnr
                #print('switchnr',switchnr)
                for cnt in range(vltlinks): #Loop through all vlt links
                    mylinkarray.append(obj['vlt'][cnt])
                    mylinkarray.append(peervltlinkarray[cnt])
                    jsonadd = { "nodes" : mylinkarray }
                    #print(mylinkarray)
                    urltuple = ( linkurl, httpheaders )
                    print('Create VLTi link between ' + nodename + ' and ' + str(peerswitchnr))
                    resp = request ( urltuple, "post", jsonadd ) #create link
                    #print(resp)
                    time.sleep(0.5)

                    mylinkarray = []
                    #linkobj = { "node_id" : mynodeid, "adapter_number" : myadapter, "port_number" : myport }
                    #print(nodename)


    #Adding links between Hosts and Leafs
    if hostcount > 0:
        counter  = 0
        array = []

        print('Create links between hosts and leafs...')
        for index, linkitem in enumerate(newdict['hostlinkarray']):
            array.append(linkitem) 
            counter += 1
            if counter == 2:
                jsonadd = { "nodes" : array }
                resp = request ( urltuple, "post", jsonadd ) #create link
                #print(resp)
                counter = 0
                array = []


    for cloud in newdict['clouds']: #Cycle through clouds for mgt connections
        clouddict = newdict['clouds'][cloud]
        
        for fabricrole in newdict['nodes']:
            if 'leaf' in fabricrole or 'spine' in fabricrole or 'border' or 'host' in fabricrole:
                dictobj = newdict['nodes'][fabricrole]
                switchnr = dictobj['nr']
                if str(cloud) == (str(switchnr)): #Found match to build link between cloud and switch
                    mylinkarray = [] #Array with the json data to create a link
                    myadapter = clouddict['port']['adapter_number']
                    myport = clouddict['port']['port_number']
                    myid = clouddict['node_id']
                    linkpeeradapter = dictobj['mgtport']['adapter_number']
                    linkpeerport = dictobj['mgtport']['port_number']
                    peerid = dictobj['nodeid']
                    
                    jsonmyside = { "node_id" : myid, "adapter_number" : myadapter, "port_number" : myport }
                    jsonpeerside = { "node_id" : peerid, "adapter_number" : linkpeeradapter, "port_number" : linkpeerport }

                    jsonadd = { "nodes" : [ jsonmyside, jsonpeerside ] } #create array with to JSON objects, is for 1 link
                    urltuple = ( linkurl, httpheaders )
                    print('Create link between cloud' + str(cloud) + ' and ' + fabricrole)
                    resp = request ( urltuple, "post", jsonadd ) #create link
                    time.sleep(0.5)
        
    #print(newdict)
    return 'proceed = True'                

            



def get_ansible_inventory ( ):

    """
    This function requests the ansible inventory file from Github.
    The ip-addresses and ansible hostnames are read from the file.
    The result is returned.

    output:
    - array with hostname and ip
    """
    stringmatch = '_host='

    gitrepourl = settings["externals"]["ansible_playbook_repo"]['url']
    hostfile = settings["externals"]["ansible_playbook_repo"]['inventoryfile']

    tempdir = tempfile.TemporaryDirectory()
    clonerepo = Repo.clone_from ( gitrepourl, tempdir.name )
    myrepo = tempdir.name
    hostfilepath = myrepo + '/' + hostfile
    obj = {}
    if not os.path.isfile(hostfilepath):
        print('Hostfile does not exist.')
        print('Not able to build a list with IP addresses from an ansible inventory.')

    else:
        with open(hostfilepath) as f:
            content = f.read().splitlines()

        # Show the file contents line by line.
        # We added the comma to print single newlines and not double newlines.
        # This is because the lines contain the newline character '\n'.
        leafcnt = 0
        spinecnt = 0
        obj = { "hosts" : {} }

        for line in content:
            if stringmatch in line.lower():
                linearray = line.split()
                hostname = linearray[0]
                for item in linearray:
                    if stringmatch in item:
                        ip = item.split(stringmatch)[1]
                        obj['hosts'][ip] = { "name" : hostname }
                        break

                if 'leaf' in hostname.lower():
                    leafcnt += 1 
                    obj['hosts'][ip]['type'] = 'leaf'
                   
                elif 'spine' in hostname.lower():
                    spinecnt += 1
                    obj['hosts'][ip]['type'] = 'spine'
                else:
                    print('Could not find fabric with leaf or spine names.')
                    print('All ansible host IP addresses are returned.')
                    obj['hosts'][ip]['type'] = 'unknown'

        obj['leafcnt'] = leafcnt
        obj['spinecnt'] = spinecnt

    return obj


def test_reachability ( addresslist):
    
    hosts = addresslist['hosts']
    result = 'down'
    pingstats = {}

    for ip in hosts:
        pingrespons = os.system("ping -c3 -i10 " + ip)

        if pingrespons == 0:
            result = 'up'
            print (ip, 'is ' + result + '!')
        else:
            result = 'down'
            print (ip, 'is ' + result + '!')

        pingstats[ip] = result

    for item in pingstats:
        status = pingstats[item]
        if status == 'down':
            result = status
            break
        else:
            result = status

    return result


def check_ztp_finish ( addresslist):

    fabricswitchcount = settings['gns3']['nodesdata']['templates']['leaf']['count'] +\
                        settings['gns3']['nodesdata']['templates']['spine']['count']

    ztpjson = settings['ztp']
    reportdir = ztpjson['ztp_finished_dir']
    reportfilesuffix = ztpjson['ztp_finished_suffix']
    webcontainer = ztpjson['dyn_http_contname']
    if webcontainer == "": ztp_finish_base_url = ztpjson['prot'] + ztpjson['serverip'] + '/' + reportdir
    else: ztp_finish_base_url = ztpjson['prot'] + webcontainer + '/' + reportdir

    hosts = addresslist['hosts']
    result = 'down'
    ztpstats = {}
    goodcnt = 0

    print('Check ztp status for all nodes...')
    time.sleep(2)
    
    for ip in hosts:

        if hosts[ip]['type'] != 'unknown': #Only check ztp status of fabric nodes (spine/leaf)
            checkfile = ip + reportfilesuffix
            url = ztp_finish_base_url + '/' + checkfile
            urltuple = ( url, {} )
        
            print('Check ztp status for node ' + ip + ', polling file: ' + url + '....')
            resp = request ( urltuple, 'get' )
 
            if isinstance(resp, int) and resp >= 400 or isinstance(resp, str) and '404' in resp or isinstance(resp, str) and 'Not Found' in resp: #File does not exist on server (staging not finished)
                result = 'ztp_busy'
                print (ip, 'seems ' + result + '...')
            else:
                result = 'ztp_finished'
                print ('GOOD !! ' + ip, 'is ' + result + ' !')
                goodcnt += 1

            ztpstats[ip] = result
            time.sleep(3)

    if goodcnt >= fabricswitchcount:
        result = 'ztp_finished'
    else:
        for item in ztpstats:
            status = ztpstats[item]
            if status == 'ztp_busy':
                result = status
                break
            else:
                result = status

    return result


######################## 
####  MAIN PROGRAM #####
########################

# If report back with 'proceed = ....', the program should exit immediatly
# Else Jenkins concludes wrong feedback.

# Check if a custom settingsfile arg was used
# if so, set settingsfile variable
for arg in sys.argv:
    lowarg = arg.lower()
    matchlist = [ 'config:', 'config=', 'settings:', 'settings=' ]
    for matchstr in matchlist:
        if matchstr in lowarg:
            settingsfile=lowarg.lstrip(matchstr)
            break

settings = readsettings ( settingsfile ) #Read settings to JSON object

# Request API call
urltuple = return_url ( settings ) #Return required URL, headers if needed & other option data
#print(urltuple)

if urltuple[0] == 'proceed = True': #GNS3 is already running, Report back to proceed & exit
    print(urltuple[0]) #output used by jenkins
    sys.exit()

response = request ( urltuple, "post") #Request API POST request
#print(response)
if 'creategns3project' in sys.argv[1:]: #Add nodes to project in GNS3
    #print(response)
    if 'already exists' in response: #project was already created
        projectid = ''
        auto_del = settings['gns3']['auto_del_project'].lower()
        print(json.loads(response)['message'])

        resp = json.loads(request ( urltuple, "get" )) #Query project to find ID
        #print(resp)
        #print(urltuple)
        for obj in resp:
            if obj['name'] == urltuple[3]['name']:
                print('Project ID : ' + obj['project_id'])
                projectid = obj['project_id']
                #response = json.dumps(obj)

        if auto_del == 'yes' or auto_del == True or auto_del == 'true': # project exists, need to be deleted
           print('Found configswitch : "auto_del = ' + auto_del)
           print('Will delete project...')

           ## Add API call to delete project from GNS3
           t = list(urltuple)
           t[0] = urltuple[0]+'/'+ projectid
           newurltuple = tuple(t)
           print(newurltuple)
           response = request ( newurltuple, "delete") #Request API POST request
           ## Then create project call
           response = request ( urltuple, "post") #Request API POST request
           projectid = json.loads(response)['project_id']
           print('Project ' + projectid + ' created.')

           time.sleep(1)
           result = provisiongns3project(json.loads(response))
           print(result)
           sys.exit()

        else:
           print('If you want to rebuild, please delete the project from GNS3.')
           print('Then restart.')
           print('proceed = noztp_check')
           sys.exit() #Activate when done testing
    else:
        projectid = json.loads(response)['project_id']
        print('Project ' + projectid + ' created.')

    time.sleep(1)
    result = provisiongns3project(json.loads(response))
    print(result)
    sys.exit()

print(urltuple)
if 'gns' in urltuple[2]['runtype'] and 'start' in urltuple[0]: #Nodes are started, start checking

    if 'noztp_check' in sys.argv:
        print('Cli arg "noztp_check" discovered. Assuming nodes are already ZTP staged and reachable.')
        print('Will wait ' + str(settings['gns3']['boottimer']) + ' secs for systems to become ready.') 
        time.sleep(settings['gns3']['boottimer'])
        print('proceed = True')
        sys.exit()

    inventory = get_ansible_inventory ()
    starttimeout = settings['gns3']['starttimeout']
    st = 10 #secs

    if inventory == '{}': #Not able to create inventory, lets wait maximum timeout for nodes to start 
        print('proceed = Wait') #used by jenkins
    else: #Check startup startup status of nodes
        t1 = datetime.strptime((datetime.now()).strftime("%H:%M:%S"), "%H:%M:%S")
        print()
        print('Waiting till all nodes reported finished status...' + str(starttimeout) + ' secs till next check.')
        print()
        
        while True:
            t2 = datetime.strptime((datetime.now()).strftime("%H:%M:%S"), "%H:%M:%S")
            delta = t2 - t1
            result = check_ztp_finish ( inventory )
            #print(result)

            if delta.total_seconds() > starttimeout: #Nodes did not finish in time
                print('Reached timeout. Seems project is unreachable indefinately.')
                print('proceed = False') #Used by Jenkins
                sys.exit()

            if result == 'ztp_finished':
                print('Testing finished. All Success.')
                print('proceed = True') #Used by Jenkins
                sys.exit()

            print('Sleep ' + str(st) + 'secs...')
            print()
            time.sleep(st)





#If AWX project was launched, check its jobstatus till finished
if 'awx' in urltuple[2]['runtype']:
    checkresult = jobstatuschecker ( response )
    print('proceed =', checkresult) #used by jenkins


