#!/usr/bin/python3
import subprocess, sys
import os, atexit
from logqueue import queuethis
from etcdgetpy import etcdget as get
from etcdgetnoportpy import etcdget as getnoport
from etcdputnoport import etcdput as putnoport
from etcdput import etcdput as put 
from Evacuatelocal import setall
from etcddel import etcddel as dels
from usersyncall import usersyncall, usrfninit, oneusersync
from groupsyncall import groupsyncall, grpfninit, onegroupsync
from socket import gethostname as hostname
from etcdsync import synckeys
from time import time as timestamp
from etctocron import etctocron 
from collectconfig import collectConfig

dirtydic = { 'pool': 0, 'volume': 0 } 
syncanitem = [ 'getconfig','priv','dirty','hostdown', 'replipart','evacuatehost','Snapperiod', 'cron','UsrChange', 'GrpChange', 'user','group','nextlead','cluip','ipaddr', 'namespace', 'tz','ntp','gw','dns','cf', 'log', 'bond' ]
special1 = [ 'passwd' ]
forReceivers = [ 'user', 'group', 'GrpChange', 'UsrChange' ] + special1
wholeetcd = [ 'etherports','offlinethis','localrun','known','nmspce','gateway','deens','enteepe', 'teezee','ceecee', 'pool','pools', 'needtoreplace','Partnr', 'Snappreiod','leader', 'running','volumes','ports', 'offlines','diskref', 'ports', 'cachespares']
etcdonly = [ 'cleanlost','balancedtype','sizevol', 'ActPool', 'alias', 'hostipsubnet', 'allowedPartners','activepool', 'poolnxt','pools', 'logged','ActivePartners','configured','ready', 'pool']
restartetcd = wholeetcd + etcdonly
replisyncs = ['user','group', 'UsrChange', 'GrpChange']
syncs = etcdonly + syncanitem + special1 + wholeetcd

noinit = [ 'getconfig', 'replipart' , 'evacuatehost','hostdown','namespace' , 'ipaddr','cluip']
##### sync request etcdonly template: sync/Operation/ADD/Del_oper1_oper2_../request Operation_stamp###########
##### sync request syncanitem with bash script: sync/Operation/commandline_oper1_oper2_../request Operation_stamp###########
##### sync request syncanitem with python script: sync/Operation/syncfn_commandline_oper1_oper2_../request Operation_stamp###########
##### synced template for request sync[0]/+node stamp #####################
##### initial sync for known nodes : sync/Operation/initial Operation_stamp #######################
##### synced template for initial sync for known nodes : sync/Operation/initial/node Operation_stamp #######################
##### delete request of same sync if ActivePartners qty reached #######################

def signal_reboot_via_etcd(etcd_endpoint, myhost, reason):
    """
    Write the etcd key that the running rebootmepls.sh watcher is polling
    so it will fire /TopStor/docker_setup.sh reboot (which ends in
    /TopStor/reboot.sh — a container-safe power-cycle analog).

    Do NOT call /TopStor/reboot.sh directly from here: that helper is
    invoked exactly once per cycle by rebootmepls.sh. Writing the etcd
    key is the canonical "I need a reboot" signal in this codebase;
    see syncbonds.sh, Evacuate.py, Evacuatelocal.py for the same
    pattern. Inside this privileged container, /sbin/reboot or
    `systemctl reboot` would reboot the HOST kernel, not just us.
    """
    key = 'rebootme/' + myhost
    try:
        put(etcd_endpoint, key, reason)
        print(f"[checksyncs] signaled reboot via etcd {etcd_endpoint} key={key} value={reason}")
    except Exception as exc:
        print(f"[checksyncs] WARNING: failed to write {key}={reason} to {etcd_endpoint}: {exc}")

software = 'na'
def insync(leaderip, leader):
    print('checking in sync -------------------')
    isinsync = 1 
     
    if isinsync == 1:
        result = get(leaderip,'nodedirty','--prefix')
        if 'dhcp' in str(result):
            isinsync = 0 
    if isinsync == 1:
        allsyncs=get(leaderip,'sync','--prefix')
        allsyncs=[x for x in allsyncs if 'initial' not in x[0] ]
        for sync in allsyncs:
            # sync/cversion requests are no longer handled here; scripts that still post them must not block insync
            syncgroup = [ x for x in allsyncs if sync[1] in x[1] and 'cversion' not in x[0] ]
            initrequest = [ x for x in syncgroup if 'request/dhcp' not in x[0] ]
            if len(syncgroup) > 0 and len(initrequest) == 0 :
                print('to delete', sync,'syncgroup',len(syncgroup),'initrequest',len(initrequest))
                dels(leaderip,'sync',sync[1])
                print('some syncs not to initialize or remove')
                isinsync = 0
                break
            if len(syncgroup) > 0:
                print('syncgroup:',syncgroup)
                print("some nodes didn't sync completely")
                isinsync = 0 
                break
    if isinsync:
        print('the cluster is in sync')
        put(leaderip,'isinsync', 'yes')
    else:
        print('some nodes still syncing')
        put(leaderip,'isinsync', 'no')
        
def initchecks(leader, leaderip, myhost, myhostip):
    if leader == myhost:
        return leaderip
    else:
        return myhostip

def checksync(hostip='request',*args):
 synctypes[hostip](*args)


def syncinit(leader,leaderip, myhost,myhostip):
 global syncs, syncanitem, forReceivers, etcdonly, allsyncs, noinit
 stamp = int(timestamp() + 3600)
 cinitial = str(get(leaderip, 'sync/','initia'))
 for sync in syncs:
  if 'sync/'+sync  not in cinitial:
    print('found new sync')
    put(leaderip,'sync/'+sync+'/'+'initial/request',sync+'_initial_'+str(stamp)) 
    put(leaderip,'sync/'+sync+'/'+'initial/request/'+myhost,sync+'_initial_'+str(stamp)) 
 return

def doinitsync(leader,leaderip,myhost, myhostip, syncinfo,pullsync='pullavail',pport='',myalias=''):
 global syncs, syncanitem, forReceivers, etcdonly, allsyncs, noinit
 syncleft = syncinfo[0]
 stamp = syncinfo[1]
 sync = syncleft.split('/')[1]
 flag = 1
 if sync in syncanitem and sync not in noinit :
    if 'Snapperiod'in sync:
     print('found etctocron')
     synckeys(leaderip,myhostip, sync,sync)
     etctocron(leaderip)
    if sync in 'group':
     print('syncing all groups')
     grpfninit(leader,leaderip, myhost,myhostip,pport)
     groupsyncall(pullsync)
    if sync in 'user':
     print('syncing all users')
     usrfninit(leader,leaderip, myhost,myhostip,pport)
     usersyncall(pullsync)
     groupsyncall(pullsync)
     #synckeys(leaderip, myhostip, pullsync+'user', 'user')
    if sync in ['tz','ntp','gw','dns']: 
     cmdline='/TopStor/HostManualconfig'+sync.upper()+" "+" ".join([leader, leaderip, myhost, myhostip]) 
     print('cmd',cmdline)
     result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
    if sync == 'priv':
        user=syncleft.split('/')[2]
        synckeys(leaderip, myhostip, 'usersinfo/'+user, 'usersinfo/'+user)
        newinfo = get(myhostip,'usersinfo/'+user)[0]
        oldinfo = get(leaderip, 'usersinfo/'+user)[0]
        if oldinfo != newinfo:
            flag = 0
    if 'bond' in sync:
        synckeys(leaderip, myhostip, sync, sync)
        cmdline = f"/TopStor/syncbonds.sh {leaderip}"        
        result = subprocess.run(cmdline.split(), stderr=subprocess.STDOUT)
        if result.returncode == 10:
            print("Bond config changed. Signaling reboot via etcd for after syncs complete.")
            signal_reboot_via_etcd(leaderip, myhost, 'pls_fromsyncs')
 if sync not in syncs:
  print('there is a sync that is not defined:',sync)
  return 
 if sync in syncs:
  if sync == 'Partnr':
   synckeys(leaderip, myhostip, 'Partner','Partner')
  else:
   if 'pullsync' not in pullsync:
    synckeys(leaderip, myhostip, sync,sync)

 if flag:
    if 'pullsync' not in pullsync:
        put(leaderip,syncleft+'/'+myhost, stamp)
    else:
        putnoport(leaderip,pport,syncleft+'/'+myalias, stamp)
        
 if 'pullsync' not in pullsync:
    synckeys(leaderip,myhostip, syncleft, syncleft)

 return


def syncall(leader,leaderip,myhost, myhostip,pullsync='pullavail'):
 global syncs, syncanitem, forReceivers, etcdonly, allsyncs
 # The requests that are pending NOW are covered by the initial syncs below (those copy the leader's
 # current keys), so they are marked done without being applied.  The list must be taken BEFORE the
 # initial syncs: a request posted while they run (this node's own nextlead announcement at the end of
 # docker_setup.sh, for one) is not covered by a copy that was already made, and marking it done lost it --
 # the node then kept nextlead/er = None and never took over when the leader died.  Such a request now
 # stays pending and the syncrequest looper applies it.
 allrequests = get(leaderip,'sync','--prefix')
 otherrequests = [ x for x in allrequests if '/request/dhcp' not in str(x) and 'initial' not in str(x) ] 

 allinitials = get(leaderip,'sync','initial')
 myinitials = [ x for x in allinitials if 'initial' in str(x)  and '/request/dhcp' not in str(x) ] 
 for syncinfo in myinitials:
   doinitsync(leader,leaderip,myhost,myhostip, syncinfo,pullsync)

 for done in otherrequests:
      put(leaderip,done[0]+'/'+myhost,done[1])
      synckeys(leaderip,myhostip, done[0], done[0]) 


 return
def replisyncrequest(replirev, leader,leaderip,myhost, myhostip):
 global syncs, syncanitem, forReceivers, etcdonly,  allsyncs
 print('***************************************************************************')
 print('syncing replication data')
 print(replirev, leader,leaderip,myhost, myhostip)
 print('***************************************************************************')
 flag=1
 pport = replirev[1]
 print('bug',pport)
 grpfninit(leader,leaderip, myhost,myhostip,pport)
 usrfninit(leader,leaderip, myhost,myhostip,pport)
 myalias = replirev[0].split('/')[-2]
 allsyncs = getnoport(leaderip,pport,'sync','request') 
 newallsyncs = []
 for sync in allsyncs:
     for forr in forReceivers:
         if '/'+forr+'/' in sync[0]:
             newallsyncs.append(sync)
 donerequests = [ x for x in newallsyncs if '/request/dhcp' in str(x) ] 
 mysyncs = [ x[1] for x in newallsyncs if '/request/dhcp'+myalias in str(x) or '/request/'+myalias in str(x)] 
 if myhost == leader:
     etcdip = leaderip
     myrequests = [ x for x in newallsyncs if x[1] not in mysyncs  and '/request/dhcp' not in x[0] ] 
 else:
    etcdip = myhostip
    myrequests = [ x for x in newallsyncs if x[1] not in mysyncs  and '/request/'+leader in x[0] ] 
 if len(myrequests) > 1:
     myrequests.sort(key=lambda x: x[1].split('_')[1], reverse=False)
 
 print('myrequests are', myrequests)
 for syncinfo in myrequests:
  evacuateflag = 0
  flag = 1
  if  len(syncinfo[0]) == 1:
    continue
  if '/initial/' in str(syncinfo):
   print(leader,leaderip,myhost,myhostip, syncinfo)
   doinitsync(leader,leaderip,myhost,myhostip, syncinfo,'pullsync',pport,myalias)
   continue
  else:
   syncleft = syncinfo[0]
   stamp = syncinfo[1]
   sync = syncleft.split('/')[1]
   opers= syncleft.split('/')[2].split('_')
   print('#########################################################################')
   print('the sync',sync)
   if sync in wholeetcd+special1 :
    if sync == 'Partnr':
      print('iam here')
      synckeysnoport(leaderip, pport, leaderip, 'Partner', 'Partner')
    else:
      print('or here')
      synckeysnoport(leaderip, pport, leaderip, sync,sync)
   if sync in etcdonly and myhost != leader:
     if opers[0] == 'Add':
      if 'Split' in opers[1]:
       put(myhostip,sync,opers[2].replace(':::','_').replace('::','/'))
      else:
       print('oper', opers, sync)
       put(myhostip,sync+'/'+opers[1].replace(':::','_').replace('::','/'),opers[2].replace(':::','_').replace('::','/'))
     else:
      print(sync,opers)
      if 'ready' not in sync:
        dels(myhostip,opers[1].replace(':::','_').replace('::','/'),opers[2].replace(':::','_').replace('::','/'))
   if sync in syncanitem:
      if 'nextlead' in sync:
        synckeys(leaderip,myhostip, sync,sync)
        if myhost in str(get(myhostip,'nextlead','--prefix')):
            cmdline='/TopStor/promrepli.sh '+leaderip+' '+myhostip
            result=subprocess.run(cmdline.split(),stderr=subprocess.STDOUT)
      elif 'getconfig' in sync:
        collectConfig(leaderip, myhost)
      elif sync in 'Snapperiod' :
       synckeys(leaderip,myhostip, sync,sync)
       etctocron(leaderip)
      elif sync in 'diskref':
        #cmdline='/pace/diskchange.sh '+' checksync'+' '+opers[0]+' '+opers[1]
        print('diskref',cmdline)
        #result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      elif sync in 'hostdown':
        cmdline='/pace/hostdown.sh '+opers[0]
        result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      elif sync in 'dirty':
        for dirt in dirtydic:
            put(etcdip, 'dirty/'+dirt, str(dirtydic[dirt]))
      elif 'syncfn' in opers[0]:
        print('opers_syncfn',opers)
        if 'evacuatehost' in str(syncleft):
            isready = get(etcdip, 'ready',opers[2])
            evacuateflag = 1
            if opers[2] not in str(isready):    
                globals()[opers[1]](*opers[2:])
                dels(etcdip, 'ActivePartners',opers[2])
                if myhost == leader:
                    cmdline = '/TopStor/promserver.sh '+leaderip
                    subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
                    dels(leaderip,'reboot', opers[2])
                    dels(leaderip,'bybyleader',opers[2])
                    discip = '10.11.11.253'
                    put(leaderip, 'excepts/'+opers[2],opers[2])
                    put(discip, 'excepts/'+opers[2],opers[2])
                    dels(discip,'possible', opers[2])
                    dels(leaderip,'possible', opers[2])
                evacuateflag = 0 

        else:        
            globals()[opers[1]](*opers[2:])
      elif sync == 'priv':
        user=syncleft.split('/')[2]
        synckeys(leaderip, myhostip, 'usersinfo/'+user, 'usersinfo/'+user)
        newinfo = get(myhostip,'usersinfo/'+user)[0]
        oldinfo = get(leaderip, 'usersinfo/'+user)[0]
        if oldinfo != newinfo:
            flag = 0
 
      else:
       print('opers_else',opers)
       if sync in ['cluip','ipaddr', 'namespace','tz','ntp','gw','dns', 'cf']: 
        cmdline='/TopStor/HostManualconfig'+sync.upper()+" "+" ".join([leader, leaderip, myhost, myhostip]) 
        print('cmdline',cmdline)
        try:
         result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
        except subprocess.CalledProcessError as e:
         print('HostManualconfig'+sync.upper()+' failed (exit '+str(e.returncode)+'): '+e.output.decode('utf-8','replace'))
         result=''
       elif sync in ['UsrChange', 'GrpChange']:
        cmdline = '/TopStor/'+opers[0]+' '+leaderip+' '+" ".join(opers[2:-1])+' '+'pullsync'
        print('cmdline',cmdline)
        result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
       else:
        print(opers,sync)
        if 'Add' in opers[0]:
            if 'user' in sync:
               print('____________________________________________________________________________________________________________')
               oneusersync('Add',opers[2],'pullsync') 
               print('____________________________________________________________________________________________________________')
            else:
               onegroupsync('Add',opers[2],'pullsync') 
        elif 'Del' in opers[0]:
            if 'user' in sync:
               oneusersync('Del',opers[2],'pullsync') 
            else:
               onegroupsync('Del',opers[2],'pullsync') 
        else:    #'UnixChange' in opers[0]:
            cmdline = '/TopStor/'+opers[0]+' '+leaderip+' '+" ".join(opers[2:]) 
            print('cmdline',cmdline)
            result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
   if sync in special1 :
      try:
       cmdline='/TopStor/'+opers[0]+' '+opers[1]+' '+opers[2]
       print('replipass',cmdline)
       result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      except:
       print('in case of admin change, the reuslt is not that ok')
      #cmdline='/TopStor/'+opers[0].split(':')[1]+' '+result+' '+opers[2] +' '+ opers[3]
      #result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
   if sync not in syncs:
    # skip it, never stop: a 'return' here dropped every later request on every pass.  A node that came
    # back after a fail over met an old sync/cversion request first (not handled here any more) and so
    # never applied anything again -- stale nextlead/er, cluster never in sync.
    print('there is a sync that is not defined:',sync)
    continue
   if flag == 1 and evacuateflag == 0:
    print(';;;;;;;;;;;;;;;;;;;;updating the remote leader')
    putnoport(leaderip,pport,syncleft+'/dhcp'+myalias, stamp)
 return     



def syncrequest(leader,leaderip,myhost, myhostip,pullsync='pullavail'):
 global syncs, syncanitem, forReceivers, etcdonly,  allsyncs
 #if 'pullsync' in pullsync:
 #   print('***************************************************************************')
 #   print('syncing replication data')
 #   print('***************************************************************************')
 flag=1
 clusterhost = myhost
 if leader == myhost:
    etcdip = leaderip
    if 'pullsync' in pullsync:
        clusterhost = leaderip
 else:
    etcdip = myhostip
 allsyncs = get(leaderip,'sync','request') 
 if 'pullsync' in pullsync:
    print('allsyncs',pullsync,allsyncs)
 donerequests = [ x for x in allsyncs if '/request/dhcp' in str(x) ] 
 #mysyncs = [ x[1] for x in allsyncs if '/request/'+myhost in str(x) or ('request/' and '/'+clusterhost) in str(x) ] 
 mysyncs = [ x[1] for x in allsyncs if '/request/'+myhost in str(x) ] 
 print('mysyncs',mysyncs)
 if myhost == leader:
    if 'pullsync' in pullsync:
        myrequests = [ x for x in allsyncs if x[1] not in mysyncs  and '/request/dhcp' not in x[0] ] 
    else:
        myrequests = [ x for x in allsyncs if x[1] not in mysyncs  and '/request/dhcp' not in x[0] and '/initial' not in x[0] ] 
 else:
    myrequests = [ x for x in allsyncs if x[1] not in mysyncs  and '/request/dhcp' not in x[0] ] 
    print('myrequests:',myrequests)
    print('iiiiiiiiiiiiiiiiiiiiiiiiiihere')
 if len(myrequests) > 1:
    print('multiple requests',myrequests)
    myrequests.sort(key=lambda x: x[1].split('_')[1], reverse=False)
 print('myrequests are', myrequests)
 for syncinfo in myrequests:
  evacuateflag = 0
  flag = 1
  if  len(syncinfo[0]) == 1:
    continue
  if '/initial/' in str(syncinfo):
   if myhost != leader or 'pullsync' in pullsync:
    print(leader,leaderip,myhost,myhostip, syncinfo)
    doinitsync(leader,leaderip,myhost,myhostip, syncinfo,pullsync)
   elif myhost == leader:
    syncinit(leader,leaderip, myhost,myhostip)
  else:
   syncleft = syncinfo[0]
   stamp = syncinfo[1]
   print('syncleft',syncleft)
   if 'pullsync' in pullsync:
    syncleft = syncleft.replace(pullsync,'')
   sync = syncleft.split('/')[1]
   opers= syncleft.split('/')[2].split('_')
   print('#########################################################################')
   print('the sync',sync)
   if sync in wholeetcd :
    if sync == 'Partnr':
      synckeys(leaderip, myhostip, 'Partner', 'Partner')
    else:
        synckeys(leaderip,myhostip, sync,sync)
   if sync in etcdonly and myhost != leader:
     if opers[0] == 'Add':
      if 'Split' in opers[1]:
       put(myhostip,sync,opers[2].replace(':::','_').replace('::','/'))
      else:
       print('oper', opers, sync)
       put(myhostip,sync+'/'+opers[1].replace(':::','_').replace('::','/'),opers[2].replace(':::','_').replace('::','/'))
     else:
      print(sync,opers)
      if 'ready' not in sync:
        dels(myhostip,opers[1].replace(':::','_').replace('::','/'),opers[2].replace(':::','_').replace('::','/'))
   if sync in syncanitem:
      if 'nextlead' in sync:
        synckeys(leaderip,myhostip, sync,sync)
        if myhost in str(get(myhostip,'nextlead','--prefix')):
            cmdline='/TopStor/promrepli.sh '+leaderip+' '+myhostip
            result=subprocess.run(cmdline.split(),stderr=subprocess.STDOUT)
      elif 'log' in sync:
        logid=opers[0]+"_"+opers[1]
        cmdline="/TopStor/synclogs.sh  "+leaderip+" "+etcdip+" "+logid+" "+opers[1]
        result=subprocess.run(cmdline.split(), stderr=subprocess.STDOUT)
      elif 'bond' in sync:
        synckeys(leaderip, myhostip, sync, sync)
        cmdline ="/TopStor/syncbonds.sh "+etcdip
        result = subprocess.run(cmdline.split(), stderr=subprocess.STDOUT)
        if result.returncode == 10:
            print("Bond config changed. Signaling reboot via etcd for after syncs complete.")
            signal_reboot_via_etcd(etcdip, myhost, 'pls_fromsyncs')
      elif 'getconfig' in sync:
        collectConfig(leaderip, myhost)
      elif sync in 'Snapperiod' :
       synckeys(leaderip,myhostip, sync,sync)
       etctocron(leaderip)
      elif sync in 'diskref':
        #cmdline='/pace/diskchange.sh '+' checksync'+' '+opers[0]+' '+opers[1]
        print('diskref',cmdline)
        #result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      elif sync in 'hostdown':
        cmdline='/pace/hostdown.sh '+opers[0]
        result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      elif sync in 'dirty':
        for dirt in dirtydic:
            put(etcdip, 'dirty/'+dirt, str(dirtydic[dirt]))
      elif 'syncfn' in opers[0]:
        print('opers',opers)
        if 'evacuatehost' in str(syncleft):
            isready = get(etcdip, 'ready',opers[2])
            evacuateflag = 1
            if opers[2] not in str(isready):    
                globals()[opers[1]](*opers[2:])
                dels(etcdip, 'ActivePartners',opers[2])
                if myhost == leader:
                    cmdline = '/TopStor/promserver.sh '+leaderip
                    subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
                    dels(leaderip,'reboot', opers[2])
                    dels(leaderip,'bybyleader',opers[2])
                    discip = '10.11.11.253'
                    put(leaderip, 'excepts/'+opers[2],opers[2])
                    put(discip, 'excepts/'+opers[2],opers[2])
                    dels(discip,'possible', opers[2])
                    dels(leaderip,'possible', opers[2])
                evacuateflag = 0 

        else:        
            globals()[opers[1]](*opers[2:])
      elif sync == 'priv':
        user=syncleft.split('/')[2]
        synckeys(leaderip, myhostip, 'usersinfo/'+user, 'usersinfo/'+user)
        newinfo = get(myhostip,'usersinfo/'+user)[0]
        oldinfo = get(leaderip, 'usersinfo/'+user)[0]
        if oldinfo != newinfo:
            flag = 0
 
      else:
       print('opers',opers)
       if sync in ['cluip','ipaddr', 'namespace','tz','ntp','gw','dns', 'cf']: 
        cmdline='/TopStor/HostManualconfig'+sync.upper()+" "+" ".join([leader, leaderip, myhost, myhostip]) 
        print('cmdline',cmdline)
        try:
         result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
        except subprocess.CalledProcessError as e:
         print('HostManualconfig'+sync.upper()+' failed (exit '+str(e.returncode)+'): '+e.output.decode('utf-8','replace'))
         result=''
       elif sync in ['UsrChange', 'GrpChange']:
        cmdline = '/TopStor/'+opers[0]+' '+leaderip+' '+" ".join(opers[2:-1])+' '+'pullsync'
        print('cmdline',cmdline)
        result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
       else:
        print(opers,sync)
        if 'Add' in opers[0]:
            if 'user' in sync:
               oneusersync('Add',opers[2],'pullavail') 
            else:
               onegroupsync('Add',opers[2],'pullavail') 
        elif 'Del' in opers[0]:
            if 'user' in sync:
               oneusersync('Del',opers[2],'pullavail') 
            else:
               onegroupsync('Del',opers[2],'pullavail') 
        else:    
            cmdline = '/TopStor/'+opers[0]+' '+leaderip+' '+" ".join(opers[2:]) 
            print('cmdline',cmdline)
            result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')

   #if sync in special1 and myhost != leader :

   if sync in special1 :
      try:
       cmdline='/TopStor/'+opers[0]+' '+opers[1]+' '+opers[2]
       result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
      except:
       print('in case of admin change, the reuslt is not that ok')
      #cmdline='/TopStor/'+opers[0].split(':')[1]+' '+result+' '+opers[2] +' '+ opers[3]
      #result=subprocess.check_output(cmdline.split(),stderr=subprocess.STDOUT).decode('utf-8')
   if sync not in syncs:
    # skip it, never stop: a 'return' here dropped every later request on every pass.  A node that came
    # back after a fail over met an old sync/cversion request first (not handled here any more) and so
    # never applied anything again -- stale nextlead/er, cluster never in sync.
    print('there is a sync that is not defined:',sync)
    continue
   if flag == 1 and evacuateflag == 0:
    if 'sync' in pullsync:
        put(leaderip,pullsync+syncleft+'/'+myhost, stamp)
    else:
        put(leaderip,syncleft+'/'+myhost, stamp)
   if myhost != leader and flag == 1 and evacuateflag == 0:
    print(';;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;')
    put(myhostip, syncleft+'/'+myhost, stamp)
    put(myhostip, syncleft, stamp)
   if myhost == leader  and flag == 1 and evacuateflag == 0:
    print('2;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;')
    put(myhostip, syncleft+'/'+myhost, stamp)
     
 if myhost != leader:
  dones = get(leaderip,'sync','/request/dhcp')
  otherdones = [ x for x in dones if '/request/dhcp' in str(x) ] 
  localdones = get(myhostip, 'sync', '--prefix')
  for done in otherdones:
   if str(done) not in str(localdones):
    put(myhostip, done[0],done[1])
    put(myhostip, '/'.join(done[0].split('/')[:-1]), done[1])
  deleted = set()
  for done in localdones:
   if done[1] not in str(otherdones) and done[1] not in deleted :
    dels(myhostip, 'sync', done[1])
    deleted.add(done[1])
  print('hihihihi-----------------------------------------')
  print(set(get(myhostip,'sync','UsrChange')+['hi'])-set(get(leaderip,'sync','UsrChange')))
  print('hihihihi-----------------------------------------')
 else:
  actives = len(get(leaderip,'ActivePartners','--prefix')) 
  receivers = get(leaderip,'Partner','Receiver') 
  if '_1' == receivers[0]:
    receivers = 0
  else:
    receivers = len(receivers)
  readis = len(get(leaderip,'ready','--prefix')) 
  readisonly = ('leader','next','ActivePartners', 'alias','nextlead', 'hostdown','pool','volume', '/dirty', 'running','/ready/', 'diskref', '/add')
  print('pruuuuuuuuuuuuuuuuuuuuuning')
  print('receiver',get(leaderip,'Partner','Receiver'))
  toprune = [ x for x in allsyncs if 'initial' not in x[0] ]
  dhcps = [x[1] for x in allsyncs if 'request/dhcp' in x[0] ]
  requests = [ x[1] for x in allsyncs if 'request/dhcp' not in x[0] ]
  notrights = [ x for x in dhcps if x not in requests ]
  toprunedic = dict()
  for prune in toprune:
   if prune[1] not in toprunedic and 'request' in prune[0]:
    toprunedic[prune[1]] = [1,prune[0]]
   else:
    if 'request' in prune[0]:
        toprunedic[prune[1]][0] += 1
        toprunedic[prune[1]].append(prune[0])
  for prune in toprunedic:
   isinreadis = [ x for x in readisonly if x in str(toprunedic[prune][1:]) ]
   if prune.split('_')[0] in forReceivers:
    totalactives = actives + receivers
    totalreadis = readis + receivers
   else:
    totalactives = actives
    totalreadis = readis
   if toprunedic[prune][0] > totalactives or ( len(isinreadis) > 0 and toprunedic[prune][0] > totalreadis):
    if 'initial' not in prune:
        dels(leaderip,'sync',prune) 
  replirevs = get(leaderip,'replirev','--prefix')
  print(replirevs)
  for replirev in replirevs:
     replisyncrequest(replirev,leader, leaderip, myhost, myhostip) 
  insync(leaderip, leader) 
    
 return     

     
def restetcd(leader,leaderip, myhost,myhostip):
    print('restetcd is',leader,leaderip,myhost,myhostip)
    if myhost == leader:
        return
    for sync in wholeetcd :
        if sync == 'Partnr':
            synckeys(leaderip, myhostip, 'Partner', 'Partner')
        else:
            synckeys(leaderip,myhostip, sync,sync)
 
runcmd={'Snapperiod':'etctocron'} 
synctypes={'syncinit':syncinit, 'syncrequest':syncrequest, 'syncall':syncall , 'restetcd': restetcd}


if __name__=='__main__':
    leaderip=sys.argv[2]
    myhost=sys.argv[3]
    leader = get(leaderip,'leader')[0]
    myhostip = get(leaderip,'ActivePartners/'+myhost)[0]
    if myhost == leader:
        myhostip = leaderip
 
    grpfninit(leader,leaderip, myhost,myhostip)
    usrfninit(leader,leaderip, myhost,myhostip)
    synctypes[sys.argv[1]](leader,leaderip, myhost,myhostip)

