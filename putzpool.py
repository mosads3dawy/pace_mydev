#!/usr/bin/python3
import subprocess, time, json,sys
import os
from os import listdir
from logqueue import queuethis, initqueue
from etcdput import etcdput as put
from etcdgetpy import etcdget as get 
from etcddel import etcddel as dels 
from os.path import getmtime

# Real capacity of a pool in operation: at 90 percent used (used / (used + available) of the pool dataset) a warning goes to the
# log and the notifications, and again every 2 hours while the pool stays above 90 percent.  The time of the last warning is kept
# in /TopStordata/capwarn_<pool> on the node that owns the pool.
def capacitywarn(pool, limit=90, every=7200):
 try:
  result=subprocess.run(['/sbin/zfs','get','-Hp','-o','value','used,available',pool],stdout=subprocess.PIPE,timeout=30)
  used,avail=[int(x) for x in result.stdout.decode().split()[:2]]
  if used + avail <= 0 or used * 100 < limit * (used + avail):
   return
  stamp='/TopStordata/capwarn_'+pool
  try:
   with open(stamp) as f:
    if time.time() - float(f.read().strip()) < every:
     return
  except (OSError, ValueError):
   pass
  with open(stamp,'w') as f:
   f.write(str(time.time()))
  free='%.1fG' % (avail/1024/1024/1024)
  subprocess.run(['docker','exec','etcdclient','/TopStor/logmsg.py','Poolcap90','warning','system',pool,free],stdout=subprocess.PIPE,timeout=60)
 except Exception as e:
  print('capacitywarn',pool,e)


def putzpool():
 global leader, leaderip, myhost, myip
 sitechange=0
 replacingroup = ''
 replaceflag = 0
 readyhosts=get(myip, 'ready','--prefix')
 knownpools=[f for f in listdir('/TopStordata/') if 'pdhcp' in f and 'pree' not in f ]
 cmdline='/sbin/zpool status '
 # container flavour: every node sees every pool (one kernel).  A node reports only the pools it owns
 # (zfs property topstor:owner, /pace/cpoolowner.sh), as a physical node sees only the pools it imported.
 if os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10'):
  mine=subprocess.run(['/pace/cpoolowner.sh','mine',myhost],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.decode().split()
  cmdline = '/sbin/zpool status '+' '.join(mine) if len(mine) > 0 else '/bin/true'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout
 sty=str(result)[2:][:-3].replace('\\t','').split('\\n')
 cmdline='/bin/lsscsi -is'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout
 drives=[x.split('/dev/')[1].split(' ')[0] for x in str(result)[2:][:-3].replace('\\t','').split('\\n') if 'zd' not in x and '/sd' in x ]
 lsscsi=[x for x in str(result)[2:][:-3].replace('\\t','').split('\\n') if 'LIO' in x and 'zd' not in x ]
 internalls=[x for x in str(result)[2:][:-3].replace('\\t','').split('\\n') if 'LIO' not in x and 'zd' not in x ]
 
 freepool=[x for x in str(result)[2:][:-3].replace('\\t','').split('\\n') if 'LIO' in x and 'zd' not in x ]
 periods=get(myip, 'Snapperiod','--prefix')
 raidtypes=['mirror','raidz','stripe']
 availraid=['mirror','raidz']
 raid2=['log','cache','spare']
 zpool=[]
 stripecount=0
 spaces=-2
 raidlist=[]
 disklist=[]
 missingdisks=[0]
 lpools=[]
 ldisks=[]
 ldefdisks=[]
 linusedisks=[]
 lfreedisks=[]
 lcachedisks=[]
 lsparedisks=[]
 lhosts=set()
 phosts=set()
 lraids=[]
 lvolumes=[]
 lsnapshots=[]
 poolsstatus=[]
 x=list(map(chr,(range(97,123))))
 #cmdline=['fdisk','-l']
 #cdisks=subprocess.run(cmdline,stderr=subprocess.PIPE, stdout=subprocess.PIPE)
 #devs=cdisks.stdout.decode().split('Disk /dev/')
 #drives = []
 #for dev in devs:
 # dsk = dev.split(':')[0]
 # if 'sd' in dsk:
 #  drives.append(dsk) 
 cmdline=['/sbin/zfs','list','-t','snapshot,filesystem,volume','-o','name,creation,used,quota,usedbysnapshots,refcompressratio,prot:kind,available,referenced,status:mount,snap:type,partner:receiver,partner:sender,compression,dedup','-H']
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)
 zfslistall=str(result.stdout)[2:][:-3].replace('\\t',' ').split('\\n')
 #lists=[lpools,ldisks,ldefdisks,lavaildisks,lfreedisks,lsparedisks,lraids,lvolumes,lsnapshots]
 #zfslistall=str(result.stdout)[2:][:-3].replace('\\t',' ').split('\\n')
 #lists={'pools':lpools,'disks':ldisks,'defdisks':ldefdisks,'inusedisks':linusedisks,'freedisks':lfreedisks,'sparedisks':lsparedisks,'raids':lraids,'volumes':lvolumes,'snapshots':lsnapshots, 'hosts':list(lhosts), 'phosts':list(phosts)}
 lists={'pools':lpools,'disks':ldisks,'defdisks':ldefdisks,'inusedisks':linusedisks,'freedisks':lfreedisks,'cachedisks':lcachedisks,'sparedisks':lsparedisks,'raids':lraids,'volumes':lvolumes,'snapshots':lsnapshots, 'hosts':list(lhosts), 'phosts':list(phosts)}
 silvering = 'no'
 silveringflag = 'no'
 for a in sty:
  b=a.split()
  if len(b) > 0:
   zname = b[0]
   b.append(b[0])
   actualdisk=b[0]
   if any(drive in str(b[0]) for drive in drives):
    for lss in lsscsi:
     if any('/dev/'+b[0] in lss for drive in drives):
      b[0]='scsi-'+lss.split()[6]
   
  if "pdhc" in str(b) and  'pool' not in str(b):
   raidlist=[]
   volumelist=[]
   zdict={}
   rdict={}
   ddict={}
   zfslist=[x for x in zfslistall if b[0] in x ]
   cmdline=['/sbin/zfs','get','avail:type',b[0], '-H']
   result=subprocess.run(cmdline,stdout=subprocess.PIPE)
   try:
    availtype=str(result.stdout)[2:][:-3].split('\\t')[2]
   except:
    availtype='suspended'
   cmdline=['/sbin/zpool','list',b[0],'-H']
   result=subprocess.run(cmdline,stdout=subprocess.PIPE)
   zlist=str(result.stdout)[2:][:-3].split('\\t')
   cmdline=['/sbin/zfs','get','compressratio','-H']
   result=subprocess.run(cmdline,stdout=subprocess.PIPE)
   zlist2=str(result.stdout)[2:][:-3].split('\\t')
   if b[0] in knownpools:
    cachetime=getmtime('/TopStordata/'+b[0])
   else:
    cmdline='/sbin/zpool set cachefile=/TopStordata/'+b[0]+' '+b[0]
    subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
    cachetime='notset'
   #put('pools/'+b[0],myhost)
   poolsstatus.append(('pools/'+b[0],myhost))
   if len(zfslist) > 0:
    zfslst = zfslist[0].split()[11]
    zused = zfslist[0].split()[6]
   else:
    zfslst = 'SUSPENDED'
    zused = 0
   zdict={ 'name':b[0],'changeop':b[1], 'availtype':availtype, 'status':b[1],'host':myhost, 'used':str(zused),'available':str(zfslst), 'alloc': str(zlist[2]), 'size': zlist[1], 'empty': zlist[3], 'dedup': zlist[7], 'compressratio': zlist2[2],'timestamp':str(cachetime), 'raidlist': raidlist ,'volumes':volumelist, 'silvering':'no'}
   zpool.append(zdict)
   lpools.append(zdict) 
   capacitywarn(b[0])
   for vol in zfslist:
    if b[0]+'/' in vol and '@' not in vol and b[0] in vol:
     volume=vol.split()
     volname=volume[0].split('/')[1]
     snaplist=[]
     snapperiod=[]
     snapperiod=[[x[0],x[1]] for x in periods if volname in x[0]]
     vdict={'fullname':volume[0],'name':volname, 'pool': b[0], 'host':myhost, 'creation':' '.join(volume[1:4]+volume[5:6]),'time':volume[4], 'used':volume[6], 'quota':volume[7], 'usedbysnapshots':volume[8], 'refcompressratio':volume[9], 'prot':volume[10],'available':volume[11], 'referenced':volume[12],'statusmount':volume[13], 'compression':(volume[17] if len(volume) > 17 else '-'), 'dedup':(volume[18] if len(volume) > 18 else '-'), 'snapshots':snaplist, 'snapperiod':snapperiod}
     if 'CIFS_' in volume[10]:
        cmdline = 'zfs get ip:addr -H '+volume[0]
        ipaddr=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split()[2]
        cmdline = '/TopStor/getdomvolstatus.sh '+ipaddr+' '+'CIFS_'
        vdict['runtime']=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('_result')[1]
     elif 'NFS' in volume[10]:
        cmdline = 'zfs get ip:addr -H '+volume[0]
        ipaddr=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split()[2]
        cmdline = '/TopStor/getdomvolstatus.sh '+ipaddr+' '+'NFS'
        vdict['runtime']=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('_result')[1]
 
     else:
        vdict['runtime'] ='serviceok'
     volumelist.append(vdict)
     lvolumes.append(vdict['name'])
    elif '@' in vol and b[0] in vol:
     snapshot=vol.split()
     snapname=snapshot[0].split('@')[1]
     partnerr=''
     partners=''
     if len(snapshot) >= 17:
      partners = snapshot[16]
     if len(snapshot) >= 16:
      partnerr = snapshot[15]
     sdict={'fullname':snapshot[0],'name':snapname, 'volume':volname, 'pool': b[0], 'host':myhost, 'creation':' '.join(snapshot[1:4]+volume[5:6]), 'time':snapshot[4], 'used':snapshot[6], 'quota':snapshot[7], 'usedbysnapshots':snapshot[8], 'refcompressratio':snapshot[9], 'prot':snapshot[10],'referenced':snapshot[12], 'statusmount':snapshot[13],'snaptype':snapshot[14], 'partnerR': partnerr, 'partnerS': partners}
     snaplist.append(sdict)
     lsnapshots.append(sdict['name'])
     
  elif any(raid in str(b) for raid in raidtypes):
   spaces=len(a.split(a.split()[0])[0])
   disklist=[]
   missingdisks=[0]
   if 'Availability' in zdict['availtype'] and 'stripe' in b[0]: 
    b[1] = 'DEGRADED' 
   rdict={ 'name':b[0], 'changeop':b[1],'status':b[1],'pool':zdict['name'],'host':myhost,'disklist':disklist,'silvering':'no', 'missingdisks':missingdisks }
   raidlist.append(rdict)
   lraids.append(rdict)
  elif any(raid in str(b) for raid in raid2):
   spaces=len(a.split(a.split()[0])[0])
   disklist=[]
   missingdisks=[0]
   b[1] = 'NA'
   if 'Availability' in zdict['availtype'] and b[0] not in availraid: 
    b[1] = 'DEGRADED' 
   rdict={ 'name':b[0], 'changeop':b[1],'status':b[1],'pool':zdict['name'],'host':myhost,'disklist':disklist,'silvering':'no', 'missingdisks':missingdisks }
   raidlist.append(rdict)
   lraids.append(rdict)
    
  elif 'scsi' in str(b) or 'disk' in str(b) or '/dev/' in str(b) or 'dm-' in str(b) or (len(b) > 0 and 'sd' in b[0] and len(b[0]) < 5) or 'UNAVA' in str(b) or 'replacing' in str(b):
    if 'dm-' in str(b) :
        missingdisks[0] += 1
        #b[1] = 'FAULT'
    diskid='_1'
    host='_1'
    size='_1' 
    devname='_1'
    disknotfound=1
    if  len(a.split('scsi')[0]) < (spaces+2) or (len(raidlist) < 1 and len(zpool)> 0):
     disklist=[]
     b[1] = 'NA'
     if 'Availability' in zdict['availtype'] : 
      b[1] = 'DEGRADED' 
      rname='mirror-temp'+str(stripecount)
     else:
        rname='stripe-'+str(stripecount)
     stripecount+=1
         
     rdict={ 'name':rname, 'pool':zdict['name'],'changeop':b[1],'status':b[1],'host':myhost,'disklist':disklist,'silvering':'no', 'missingdisks':[0] }
     raidlist.append(rdict)
     lraids.append(rdict)
     disknotfound=1
    for lss in lsscsi:
     z=lss.split()
     if (z[6] in b[0] and len(z[6]) > 3 and 'OFF' not in b[1]) or (z[3].split('-')[0] in str(internalls)):
      diskid=lsscsi.index(lss)
      host=z[3].split('-')[1]
      lhosts.add(host)
      phosts.add(host)
      size=z[7]
      devname=z[5].replace('/dev/','')
      disknotfound=0
      if z[3].split('-')[0] not in str(internalls):
        freepool.remove(lss)
      break
    if disknotfound == 1:
      diskid=0
      host='_1'
      size='_1'
      devname=b[0]
      
     #else:
     # cmdline='/pace/hostlost.sh '+z[6]
     # subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
    if 'Availability' in zdict['availtype'] and 'DEGRAD' in rdict['changeop'] and 'UNAVAIL' not in b[1] and 'FAULT' not in b[1] and 'OFF' not in b[1] and 'REMOVED' not in b[1]:
     b[1] = 'ONLINE' 
    changeop=b[1]
    if host=='_1':
     raidlist[len(raidlist)-1]['changeop']='Warning'
     zpool[len(zpool)-1]['changeop']='Warning'
     changeop='Removed'
     sitechange=1
    devname = b[-1]
    if 'dm-' in b[0]:
        size = 0
        changeop = 'FAULT'
    if 'UNAVAIL' in b[1] or 'FAULT' in b[1]:
        b[-1] = b[0]
        diskid = b[0]
        devname = b[0] 
        size = '0'
    if 'OFF' not in b[1] and 'REMOVED' not in b[1] and 'UNAVAI' not in b[1] and 'FAULT' not in b[1] and 'dm-' not in b[0]:
     try:
        devinfo = [x.split() for x in lsscsi if devname[-20:] in x][0]
        host = devinfo[3].split('-')[1]
        size = devinfo[-1]
        with open('/'+zdict['name']+'/tmpsmall','w') as f:
            f.write('hi')
     except:
        b[1]='UNAVAILABLE'
        host ='UNAVAIL'
        size = '0' 
    if 'resilvering' in str(b):
        silvering = 'yes' 
        silveringflag = 'yes'
        zdict['silvering'] = silvering
    if 'replac' in b[0]:
        replaceflag = 2
        replacingroup = b[0]
    elif replaceflag == 0:
            replacingroup = ''
    else:
        replaceflag -= 1
        
    if 'dm' in b[0]:
        zname = b[0]
    ddict={'name':b[0],'zname':zname, 'actualdisk':actualdisk, 'changeop':changeop,'pool':zdict['name'],'raid':rdict['name'],'status':b[1],'id': str(diskid), 'host':host, 'size':size,'devname':devname, 'silvering': silvering, 'replacingroup':replacingroup}
    rdict['silvering'] = silvering
    silvering = 'no'
    disklist.append(ddict)
    ldisks.append(ddict)

 try:
    cache_config_raw = get(myip, 'cachespares')
    print(f"DEBUG: Cache raw value: {cache_config_raw}")
    if cache_config_raw and isinstance(cache_config_raw, list) and len(cache_config_raw) > 0:
        raw_json_string = cache_config_raw[0]
        raw_json_string = raw_json_string.replace("'", '"').strip()
        if '[' in raw_json_string:
            cache_ids = json.loads(raw_json_string)
            print(f"DEBUG: Cache IDs from etcd: {cache_ids}")     
        else:
            cache_ids = []
    else:
        cache_ids = []
 except:
    cache_ids = []
 print(f"DEBUG 2: Cache IDs from etcd: {cache_ids}")
# if len(freepool) > 0:
#  raidlist=[]
#  zdict={ 'name':'pree','changeop':'pree', 'available':'0', 'status':'pree', 'host':myhost,'used':'0', 'alloc': '0', 'empty': '0','size':'0', 'dedup': '0', 'compressratio': '0','silvering':'no', 'raidlist': raidlist, 'volumes':[]}
#  zpool.append(zdict)
#  lpools.append(zdict)
#  disklist=[]
#  rdict={ 'name':'free', 'changeop':'free','status':'free','pool':'pree','host':myhost,'disklist':disklist, 'missingdisks':[0], 'silvering':'no' }
#  raidlist.append(rdict)
#  lraids.append(rdict)
#  for lss in freepool:
#   z=lss.split()
#   devname=z[5].replace('/dev/','')
#   if devname not in drives:
#    continue
#   diskid=lsscsi.index(lss)
#   host=z[3].split('-')[1]
#   if host not in str(readyhosts):
#    continue
# ##### commented for not adding free disks of freepool
#   lhosts.add(host)
#   size=z[7]
#   ddict={'name':'scsi-'+z[6],'actualdisk':'scsi-'+z[6],'zname':"", 'changeop':'free','status':'free','raid':'free','pool':'pree','id': str(diskid), 'host':host, 'size':size,'devname':devname, 'silvering':'no'}
#   if z[6] in str(zpool):
#    continue
#   disklist.append(ddict)
#   ldisks.append(ddict)

 if len(freepool) > 0:
  raidlist=[]
  
  zdict={ 'name':'pree','changeop':'pree', 'available':'0', 'status':'pree', 'host':myhost,'used':'0', 'alloc': '0', 'empty': '0','size':'0', 'dedup': '0', 'compressratio': '0','silvering':'no', 'raidlist': raidlist, 'volumes':[]}
  zpool.append(zdict)
  lpools.append(zdict)

  disklist_free = []
  disklist_cache = []

  for lss in freepool:
   z=lss.split()
   devname=z[5].replace('/dev/','')
   if devname not in drives:
    continue
   diskid=lsscsi.index(lss)
   host=z[3].split('-')[1]
   if host not in str(readyhosts):
    continue
   
   lhosts.add(host)
   size=z[7]
   
   this_disk_name = 'scsi-'+z[6]
   
   if this_disk_name in cache_ids:
       status_label = 'cache'
       target_list = disklist_cache
   else:
       status_label = 'free'
       target_list = disklist_free

   ddict={'name':this_disk_name,'actualdisk':this_disk_name,'zname':"", 'changeop':status_label,'status':status_label,'raid':status_label,'pool':'pree','id': str(diskid), 'host':host, 'size':size,'devname':devname, 'silvering':'no'}
   
   if z[6] in str(zpool):
    continue
   
   target_list.append(ddict)
   ldisks.append(ddict)

  if len(disklist_free) > 0:
      rdict_free={ 'name':'free', 'changeop':'free','status':'free','pool':'pree','host':myhost,'disklist':disklist_free, 'missingdisks':[0], 'silvering':'no' }
      raidlist.append(rdict_free)
      lraids.append(rdict_free)

  if len(disklist_cache) > 0:
      rdict_cache={ 'name':'cache', 'changeop':'cache','status':'cache','pool':'pree','host':myhost,'disklist':disklist_cache, 'missingdisks':[0], 'silvering':'no' }
      raidlist.append(rdict_cache)
      lraids.append(rdict_cache)

 if len(lhosts)==0:
    lhosts.add('')
 if len(phosts)==0:
    phosts.add('')
 put(leaderip, 'hosts/'+myhost+'/current',json.dumps(zpool))
 for disk in ldisks:
  if disk['changeop']=='free':
   lfreedisks.append(disk)
  elif disk['changeop'] =='cache':
   lcachedisks.append(disk)
  elif disk['changeop'] =='AVAIL':
   lsparedisks.append(disk)
  elif disk['changeop'] != 'ONLINE': 
   ldefdisks.append(disk)
 put(leaderip, 'lists/'+myhost,json.dumps(lists))
 xall=get(myip, 'pools/','--prefix')
 x=[y for y in xall if myhost in str(y)]
 xnotfound=[y for y in x if y[0].replace('pools/','') not in str(poolsstatus)]
 xnew=[y for y in poolsstatus if y[0].replace('pools/','') not in str(x)]
 for y in xnotfound:
  if y[0] not in xall:
   dels(leaderip, y[0].replace('pools/',''),'--prefix')
  else:
   dels(leaderip, y[0])
 for y in xnew:
  put(leaderip, y[0],y[1])
 if silveringflag == 'yes':
  put(leaderip,'nodedirty/'+myhost, 'yes')
 else:
  dels(leaderip,'nodedirty/'+myhost)
 
def initputzpool(*args):
    global leader, leaderip, myhost, myip 
    if len(args) > 0:
        leader = args[0]
        leaderip = args[1]
        myhost = args[2]
        myip = args[3]
    if leader == myhost:
        myip = leaderip
    initqueue(leaderip, myhost)
   
if __name__=='__main__':
 if len(sys.argv)> 4:
    leader = sys.argv[1]
    leaderip = sys.argv[2]
    myhost = sys.argv[3]
    myip = sys.argv[4]
 else:
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
    leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
    leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
    myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
    cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
    myip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 initputzpool()
 putzpool()
