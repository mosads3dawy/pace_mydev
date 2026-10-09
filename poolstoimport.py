#!/usr/bin/python3
import subprocess, json,sys
from os import listdir
from logqueue import queuethis, initqueue
from etcdput import etcdput as put
from etcdgetpy import etcdget as get 
from etcddel import etcddel as dels 
from os.path import getmtime
def getpoolstoimport():
 global leader, leaderip, myhost, myip
 sitechange=0
 replacingroup = ''
 replaceflag = 0
 readyhosts=get(myip, 'ready','--prefix')
 knownpools=[f for f in listdir('/TopStordata/') if 'pdhcp' in f and 'pree' not in f ]
 cmdline='/sbin/zpool import '
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
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
 zfslistall = []
 lists={'pools':lpools,'disks':ldisks,'defdisks':ldefdisks,'inusedisks':linusedisks,'freedisks':lfreedisks,'sparedisks':lsparedisks,'raids':lraids,'volumes':lvolumes,'snapshots':lsnapshots, 'hosts':list(lhosts), 'phosts':list(phosts)}
 silvering = 'no'
 silveringflag = 'no'
 poolid = ''
 for a in sty:
  b=a.split()
  print(',,,,,,,,,b:',b)
  if len(b) > 0:
   zname = b[0]
   b.append(b[0])
   actualdisk=b[0]
   if any(drive in str(b[0]) for drive in drives):
    for lss in lsscsi:
     if any('/dev/'+b[0] in lss for drive in drives):
      b[0]='scsi-'+lss.split()[6]
  if 'id:' in str(b):
    poolid = b[1] 
  if "pdhcp" in str(b) and  'pool' not in str(b):
   raidlist=[]
   volumelist=[]
   zdict = {}
   rdict={}
   ddict={}
   zfslist=[x for x in zfslistall if b[0] in x ]
   cmdline=['/sbin/zfs','get','avail:type',b[0], '-H']
   result=subprocess.run(cmdline,stdout=subprocess.PIPE)
   try:
    availtype=str(result.stdout)[2:][:-3].split('\\t')[2]
   except:
    availtype='willchecklater'
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
   poolsstatus.append(('pools/'+b[0],myhost))
   zdict={ 'name':b[0],'changeop':b[1],'guid':poolid, 'availtype':availtype, 'status':b[1],'host':myhost, 'timestamp':str(cachetime), 'raids': raidlist ,'volumes':volumelist, 'silvering':'no'}
   zpool.append(zdict)
   lpools.append(zdict) 
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
   if 'Availability' in zdict['availtype'] and raid not in availraids: 
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
    try:
        print('zdict print', zdict)
    except: 
        print('this pool is failing, will ignore it', b)
        continue
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
 if len(lhosts)==0:
    lhosts.add('')
 if len(phosts)==0:
    phosts.add('')
 for disk in ldisks:
  if disk['changeop']=='free':
   lfreedisks.append(disk)
  elif disk['changeop'] =='AVAIL':
   lsparedisks.append(disk)
  elif disk['changeop'] != 'ONLINE': 
   ldefdisks.append(disk)
 #put(leaderip, 'lists/'+myhost,json.dumps(lists))
 print('zpool##############################')
 print(zpool)
 print('##############################')
 print('ldisks##############################')
 print(ldisks)
 print('##############################')
 print('readyhosts##############################')
 print(readyhosts)
 print('##############################')
 toactivate = [x for x in zpool if 'pree' not in x['name'] and x['changeop'] in ['ONLINE','DEGRADED']]
 return toactivate
 
def initgetpoolstoimport(*args):
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
 initgetpoolstoimport()
 getpoolstoimport()
