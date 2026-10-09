#!/usr/bin/python3
import subprocess,sys, os
#from socket import gethostname as hostname
from levelthis import levelthis
from logqueue import queuethis, initqueue
from raidrank import getraidrank
from ast import literal_eval as mtuple
from etcdgetpy import etcdget as get
from etcdput import etcdput as put
from etcddel import etcddel as dels 
#from deltolocal import deltolocal as delstolocal
from poolall import getall as getall
from time import sleep
from sendhost import sendhost
from time import time as stamp
#from syncpools import syncmypools
os.environ['ETCDCTL_API']= '3'
newop=[]
disksvalue=[]
usedfree=[]
myhost = '' 

def dosync(*args):
 global leader, leaderip, myhost, myhostip, etcdip
 put(leaderip, *args)
 put(leaderip, args[0]+'/'+leader,args[1])


def mustattach(cmdline,disksallowed,raid):
   global leader, leaderip, myhost, myhostip, etcdip
   print('################################################')
   if len(disksallowed) < 1 : 
    return 'na'
   print('helskdlskdkddlsldssd#######################')
   cmd=cmdline.copy()
   spare=disksallowed
   print('spare',spare)
   print('###########################')
   spareplsclear=get(etcdip, 'clearplsdisk/'+spare['actualdisk'])
   spareiscleared=get(etcdip, 'cleareddisk/'+spare['actualdisk']) 
   if spareiscleared[0] != spareplsclear[0] or spareiscleared[0] == '_1':
    print('asking to clear')
    put(etcdip, 'clearplsdisk/'+spare['actualdisk'],spare['host'])
    dels(etcdip , 'cleareddisk/'+spare['actualdisk']) 
    hostip=get(etcdip, 'ready/'+spare['host'])
    z=['/TopStor/Zpoolclrrun',spare['actualdisk']]
    msg={'req': 'Zpool', 'reply':z}
    print(hostip[0], str(msg),'recvreply',myhost)
    sendhost(hostip[0], str(msg),'recvreply',myhost)
    print('returning')
    print('raid',raid)
    return 'wait' 
   dels(etcdip, 'clearplsdisk/'+spare['actualdisk']) 
   dels(etcdip, 'cleareddisk/'+spare['actualdisk']) 
   print('cmd',cmd)
   print('raidname',raid)
   if 'stripe' in raid['name']:
    print('############start attaching')
    cmd = cmd+[raid['disklist'][0]['name'],'/dev/disk/by-id/'+spare['name']] 
    print('thecmd',' '.join(cmd))
    res = subprocess.run(cmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode !=0:
     print('somehting went wrong', res.stderr.encode())
    else:
     print(' the most suitable disk is attached')
    return
   dmcmd = 'zpool status '+raid['pool']
   dmstup = subprocess.run(dmcmd.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode('utf-8')
   if 'dm-' in dmstup:
    print('somthing wrong, there is already a stup found for this degraded group')
    return
   dmstup = 'dm-'+dmstup.split('dm-')[1].split(' ')[0]
   cmd = cmd+[dmstup, '/dev/disk/by-id/'+spare['name']] 
   res = subprocess.run(cmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE) 
   #cmd = ['systemctl', 'restart', 'zfs-zed']
   #subprocess.run(cmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
   with open('/root/dmproblem','w') as f:
    f.write('cmdline '+ " ".join(cmd)+'\n')
    f.write('result: '+res.stdout.decode()+'\n')
    f.write('result: '+res.stderr.decode()+'\n')
   print('result', res.stderr.decode())    
   if int(res.stderr.decode()) == 0:
    dels('needtoreplace', spare['name'])
   return 
 
 
def norm(val):
 units={'B':1/1024**2,'K':1/1024, 'M': 1, 'G':1024 , 'T': 1024**2 }
 if type(val)==float:
  return val
 if val[-1] != 'B':
  return float(val) 
 else:
  if val[-2] in list(units.keys()):
   return float(val[:-2])*float(units[val[-2]])
  else:
   return float(val[:-1])*float(units['B'])



def getbalance(diskA,diskB,balancetype,hostcounts,onlinedisks=[]):
 global newop
 global leader, leaderip, myhost, myhostip, etcdip
  
 print('################################################################################33')
 print('diskB', diskB)
 print('diskA', diskA)
 raidhosts=hostcounts.copy()
 w=0
 if 'free' in diskA['changeop']:
  w=1
########## Stripe  DiskA free policy: Any###################################
 if 'stripe' in diskB['raid']: # if stripe calcualte the 
  print('spare1')
  if norm(diskB['size']) > norm(diskA['size']):
   print('spare1_1')
   w=1000000
   return w
########## Stripe  DiskA free policy: Useability###############################
  if 'useable' in balancetype:
   print('spare1_2')
   sizediff=10*(norm(diskA['size'])-norm(diskB['size'])) # tendency to same size
   w+=sizediff+int(diskA['host'] in diskB['host'])
   return w
########## Stripe  DiskA free policy: Availability##############################
  else:
   print('spare1_3')
   sizediff=(norm(diskA['size'])-norm(diskB['size']))
   w+=sizediff+10*int(diskA['host'] in diskB['host'])    # tendency to otherhost
   return w
######### RAID DiskB online DiskA free policy: useability #####################
 elif 'free' in diskA['changeop'] and 'ONLINE' in diskB['status']:# DiskB online
  print('spar2')
  if 'useable' in balancetype:
   print('spar2_1')
   sizediff=(norm(diskA['size'])-norm(diskB['size'])) # tendency to same size
 ########### Mirror and DiskB online diskA free policy: useability ############
   if 'mirror' in diskB['raid']:    # useable type not to mirror large disks
    print('spar2_2')
    if norm(diskA['size']) > norm(diskB['size']):
     print('spar2_3')
     w=100002
     return w
    print('spar2_4')
    w+=10*sizediff+int(diskA['host'] in diskB['host'])
    return w
 ########### RAID and DiskB online diskA free policy: Availability #########
  else:
   print('spar2_5')
   minB=min(onlinedisks,key=lambda x:norm(x['size']))
   if norm(minB['size']) > norm(diskA['size']):
    print('spar2_6')
    w=1000000
    return w
   print('spar2_7')
   raidhosts[diskA['host']]+=1
   raidhosts[diskB['host']]-=1
   if 'raidz' in diskB['raid']:
    print('spar2_8')
    sizediff=norm(diskA['size'])-norm(diskB['size']) 
    if diskA['host']==diskB['host'] and norm(diskA['size']) >= norm(diskB['size']) :
     print('spar2_9')
     w=2200000
     return w
   if 'raidz1' in diskB['raid']:
    print('spar2_10')
    if raidhosts[diskA['host']] > 1:
     print('spar2_11')
     w=2000000
     return w
    elif raidhosts[diskA['host']]==1 and raidhosts[diskB['host']]<1:
     print('spar2_12')
     w=2100000
     return w
    elif raidhosts[diskA['host']]<=1 and raidhosts[diskB['host']] >=raidhosts[diskA['host']]:
     print('spar2_13')
     w+=sizediff+10*int(raidhosts[diskA['host']]-raidhosts[diskB['host']])
     return w
    else:
      print('spar2_14')
      print('Error',raidhosts)

   elif 'raidz2' in diskB['raid']:
    print('spar2_15')
    if raidhosts[diskA['host']] > 2:
     print('spar2_16')
     w=2000000
     return w
    elif raidhosts[diskA['host']]==2 and raidhosts[diskB['host']]<2:
     print('spar2_17')
     w=2100000
     return w
    elif raidhosts[diskA['host']]==1 and raidhosts[diskB['host']]<0:
     print('spar2_18')
     w=2200000
     return w
    elif raidhosts[diskA['host']]<=2 and raidhosts[diskB['host']] >=raidhosts[diskA['host']]:
     print('spar2_19')
     w+=sizediff+10*int(raidhosts[diskA['host']]-raidhosts[diskB['host']])
     return w
    else:
      print('spar2_20')
      print('Error',raidhosts)
    
 ########### Mirror and DiskB online diskA free policy: Availability #########
   elif 'mirror' in diskB['raid']:
    print('spar2_21')
    if raidhosts[diskA['host']]==2:
     w=3100000
     return w
    print('spar2_22')
    sizediff=norm(diskA['size'])-norm(diskB['size']) 
    if sizediff >= 0 and hostcounts[diskB['host']]==1:
     print('spar2_23')
     w=3200000
     return w
    print('spar2_24')
    w+=sizediff+10*int(diskA['host'] in diskB['host'])
    return w
########### RAID and DiskB online diskA in Raid policy: Any #########
 elif diskB['raid'] in diskA['raid'] and 'ONLINE' in diskB['status']:  
  print('spare3')
  sizediff=norm(diskA['size'])-norm(diskB['size']) 
 ########### Mirror and DiskB online diskA in Raid policy: Useability #########
  if 'useable' in balancetype:  # tendency not to take the large size
   print('spare3_1')
   if 'mirror' in diskB['raid']:
    print('spare3_2')
    w+=10*sizediff+int(diskA['host'] in diskB['host'])
    return w
 ########### RAID and DiskB online diskA in Raid policy: Availability ########
  else:
   print('spare3_3')
   if 'raidz' in diskB['raid']:
    w=3000000
    return w
   elif 'mirror' in diskB['raid']:
    print('spare3_4')
    w=3000000
    #w+=sizediff+10*int(diskA['host'] in diskB['host'])
    return w 
########### RAID DiskB Failed diskA free policy: Any ########
 elif 'free' in diskA['changeop'] and 'ONLINE' not in diskB['status']:
  print('spare4')
  minB=min(onlinedisks,key=lambda x:norm(x['size']))
  sizediff=norm(diskA['size'])-norm(minB['size']) 
  minB=min(onlinedisks,key=lambda x:norm(x['size']))
########### RAIDZ DiskB Failed diskA free policy: Any ########
  if 'raidz' in diskB['raid']:
   print('spare4_1')
   try:
    print('spare4_2')
    raidhosts[diskA['host']]+=1
   except:
    print('spare4_3')
    raidhosts[diskA['host']]=1
   print('spare4_4')
   minB=min(onlinedisks,key=lambda x:norm(x['size']))
   if norm(minB['size']) > norm(diskA['size']):
    print('spare4_5')
    w=1000000
    return w
   print('spare4_6')
   sizediff=norm(diskA['size'])-norm(diskB['size']) 
 ########### RAID DiskB Failed diskA free policy: Useability ########
  if 'useable' in balancetype:
   print('spare4_7')
   if 'raidz1' in diskB['raid']:
    print('spare4_8')
    w+=10*sizediff+int(raidhosts[diskA['host']]-1)
    return w
   elif 'raidz2' in diskB['raid']:
    print('spare4_9')
    w+=10*sizediff+int(raidhosts[diskA['host']]-2)
    return w
 ########### Mirror DiskB Failed diskA free policy: Useability ########
   elif 'mirror' in diskB['raid']:    # useable type not to mirror large disks
    print('spare4_10')
    if norm(diskA['size']) > norm(minB['size']):
     w=100002
     return w
   else:
    print('spare4_11')
    w+=sizediff+10*int(diskA['host'] in diskB['host'])
    return w
 ########### RAID DiskB Failed diskA free policy: Availability ########
  else:
   print('spare4_12')
 ########### Raidz and DiskB Failed diskA free policy: Availability #########
   if 'raidz1' in diskB['raid']:
    print('spare4_13')
    w=sizediff+10*int(raidhosts[diskA['host']]-1)
    return w
   elif 'raidz2' in diskB['raid']:
    print('spare4_14')
    w=sizediff+10*int(raidhosts[diskA['host']]-2)
    return w
   elif 'raidz3' in diskB['raid']:
    print('spare4_15')
    w=sizediff+10*int(raidhosts[diskA['host']]-3)
    return w
 ########### Mirror and DiskB Failed diskA free policy: Availability #########
   elif 'mirror' in diskB['raid']:
    print('spare4_16')
    w+=sizediff+10*int(raidhosts[diskA['host']] -1)
    return w
  
def selectthedisk(freedisks,raid,allraids,allhosts):
 global leader, leaderip, myhost, myhostip, etcdip
 weights=[]
 finalw=[]
 hostcounts=allhosts.copy()
 balancetype=get(etcdip, 'balancetype/'+raid['pool'])
 for disk in raid['disklist']:
  if 'ONLINE' in disk['status']:
   if disk['host'] in hostcounts.keys():
    hostcounts[disk['host']]+=1
   else:
    hostcounts[disk['host']]=1
 if 'stripe' not in raid['name'] and 'ONLINE' in raid['status']:
  for diskA in raid['disklist']:
   for diskB in raid['disklist']:
    if diskA['actualdisk'] not in diskB['actualdisk']:
     w=getbalance(diskA.copy(),diskB.copy(),balancetype,hostcounts.copy(),raid['disklist'].copy())
     finalw.append({'newd':diskA,'oldd':diskB,'w':w})
  for diskA in freedisks:
   for diskB in raid['disklist']:
    if diskA['actualdisk'] not in diskB['actualdisk']:
     w=getbalance(diskA,diskB,balancetype,hostcounts,raid['disklist'])
     finalw.append({'newd':diskA,'oldd':diskB,'w':w})
 elif 'stripe' in raid['name']:
  for diskA in freedisks:
   for diskB in raid['disklist']: 
    w=getbalance(diskA,diskB,balancetype,hostcounts)
    finalw.append({'newd':diskA,'oldd':diskB,'w':w})
 elif 'DEGRAD' in raid['status']:
  defdisks=[x for x in raid['disklist'] if 'ONLINE' not in x['status']]
  onlinedisks=[x for x in raid['disklist'] if 'ONLINE' in x['status']]
  for diskA in freedisks:
   for diskB in defdisks:
    #####################################################
    #I need to check why we are comparing a faulty disk instead of the others
    ######################################################
    w=getbalance(diskA,diskB,balancetype,hostcounts,onlinedisks)
    finalw.append({'newd':diskA,'oldd':diskB,'w':w})
 finalw=sorted(finalw,key=lambda x:x['w'])
 print('finalw',finalw[0])
 return finalw[0] 

 
def solvestriperaids(striperaids,freedisks,allraids):
 global leader, leaderip, myhost, myhostip, etcdip
 global usedfree
 sparefit={}
 for raid in striperaids:
  sparelist=selectthedisk(freedisks,raid,allraids,{})
  if len(sparelist) > 0:
   try:
    sparefit[sparelist['newd']['actualdisk']].append(sparelist)
   except:
    sparefit[sparelist['newd']['actualdisk']]=[]
    sparefit[sparelist['newd']['actualdisk']].append(sparelist)
 for k in sparefit:
  sparefit[k]=sorted(sparefit[k],key=lambda x:x['w'])
 for k in sparefit:
  oldd=sparefit[k][0]['oldd'] 
  newd=sparefit[k][0]['newd'] 
  olddpool=sparefit[k][0]['oldd']['pool'] 
 cmdline=['/sbin/zpool', 'attach','-f', olddpool]
 ret=mustattach(cmdline,newd,oldd)
 if 'fault' not in ret:
  usedfree.append(ret)
 return
 
def solvedegradedraid(raid,disksfree):
 global leader, leaderip, myhost, myhostip, etcdip
 hosts=get(etcdip, 'ready','--prefix')
 hosts=[host[0].split('/')[1] for host in hosts]
 raidhosts= set()
 defdisk = [] 
 disksample = []
 sparedisk = []
 for disk in raid['disklist']:
  if 'ONLINE' in disk['changeop']:
   disksample.append(levelthis(disk['size']))
   raidhosts.add(disk['host'])
  else:
   if 'stripe' in raid['name']:
    cmdline2=['/sbin/zpool', 'detach',raid['pool'], disk['actualdisk']]
    forget=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print('detaching the faulty disk',forget.stderr.decode())
    #cmdline2=['systemctl', 'restart','zfs-zed']
    #subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return disksfree
   defdisk.append(disk['name'])
   dmcmd=['zpool', 'status']
   dminuse = subprocess.run(dmcmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().split()
   dmcmd=['zpool','import']
   dminuse = dminuse + subprocess.run(dmcmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().split()
   dminuse = [ 'dm-'+x.split('dm-')[1].split(' ')[0] for x in dminuse  if 'dm-' in x ] + [ 'dm-1', 'dm-0' ]
   dmcmd = '/pace/lstdm.sh'
   dmstuplst = subprocess.run(dmcmd.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().split()
   dmstup = '0'
   for dm in dmstuplst:
    if dm not in str(dminuse) or 'was /dev/'+dm in (dminuse):
     dmstup = dm
   print('dmstuplst',dmstuplst)
   print('dmstup',dmstup)
   if dmstup == '0':
    print('creating new dm')
    cmddm= ['/pace/mkdm.sh']
    dmstup = subprocess.run(cmddm,stdout=subprocess.PIPE).stdout.decode().split('result_')[1]
    print('new',dmstup,'is created')
   diskuid = disk['actualdisk']
   if 'scsi' in disk['actualdisk']:
    cmdline2='/sbin/zdb -e -C '+disk['pool']
    forget=subprocess.run(cmdline2.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if forget.returncode:
     cmdline2='/sbin/zdb -C '+disk['pool']
     forget=subprocess.run(cmdline2.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    forget=forget.stdout.decode().replace(' ','').split('\n')
    faultdisk = [ x for x in forget if 'guid' in x or (disk['actualdisk'] in x and 'path' in x) ]
    eindex = 0 
    for fa in faultdisk:
     if disk['actualdisk'] in fa:
      eindex = faultdisk.index(fa)
      break
    diskuid = faultdisk[eindex-1].split(':')[1]
   if 'dm-' in str(raid):
    return
   cmdline2=['/sbin/zpool', 'replace','-f',raid['pool'], diskuid,'/dev/'+dmstup]
   forget=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
   sleep(2)
   cmdline2=['/sbin/zpool', 'offline',raid['pool'],'/dev/'+dmstup]
   forget2=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
   sleep(2)
   cmdline2=['/sbin/zpool', 'detach',raid['pool'],diskuid]
   forget2=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
   sleep(2)
   cmdline2=['/pace/putzpool.py']
   forget2=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
   with open('/root/dmproblem','w') as f:
    f.write('cmdline '+ " ".join(cmdline2)+'\n')
    f.write('result: '+forget.stdout.decode()+'\n')
    f.write('result: '+forget.stderr.decode()+'\n')
   
   #sleep(3)
   #cmdline2=['/sbin/zpool', 'offline',raid['pool'], '/dev/'+dmstup]
   #subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
   #cmdline2=['systemctl', 'restart','zfs-zed']
   #subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
   print('forgetting the dead disk result by internal dm stup',forget.stderr.decode())
   print('returncode',forget.returncode)
   if forget.returncode == 0:
    put(etcdip, dmstuplst[0][0],'inuse/'+dmstup)
   else:
    if forget.returncode != 255:
     dels(etcdip, dmstuplst[0][0], '--prefix')
     #delstolocal(dmstuplst[0][0], '--prefix')
     return disksfree 
 print('################## start replace in solvedegradedraid')
 if len(disksample) == 0 :
  return disksfree
 if len(defdisk):
  print('no def disk')
  return disksfree
################## put a wrapping condition after the next "for" line for every new feature (disk type, node load, AI analysis,..etc ##########
 disksamplesize= min(disksample)
 for disk in disksfree:
  print('disk',disk['devname'],disk['size'])
  if disk['size'] =='-' or levelthis(disk['size']) < disksamplesize:
   continue 
  ######  for best host split
  if disk['host'] not in raidhosts:
   sparedisk.append([disk,10])
  else:
   sparedisk.append([disk,0])
  ###### then for minimum disk size in the host
  if levelthis(disk['size']) ==  levelthis(disksamplesize):
   sparedisk[-1] = [disk,sparedisk[-1][1]+10]
 if len(sparedisk) == 0:
  return disksfree
 print('##############################################') 
 print('sparedisk',sparedisk)  
 print('##############################################') 
 sparedisklst = max(sparedisk,key=lambda x:x[1])
 sparedisk = sparedisklst[0]
 print('sparedisk',sparedisk)  
 print('##############################################') 
 if 'stripe' in raid['name']:
  print('attaching the disk')
  cmdline=['/sbin/zpool', 'attach', '-f', raid['pool']]
 else:
  cmdline=['/sbin/zpool', 'replace', '-f',raid['pool']]
 ret=mustattach(cmdline,sparedisk,raid)
 if ret == 0:
  return sparedisklst[1:]
 else:
  return sparedisklst

def solvetheasks(needtoreplace):
    global leader, leaderip, myhost, myhostip, etcdip
    theasks = get(leaderip, 'ask/needtoreplace', '--prefix')
    for askleft,askright in theasks:
        freedisk = askright.split('/')[-2] 
        if freedisk in str(needtoreplace) and askleft.replace('ask/','') in str(needtoreplace):    ### ignore
            continue
        elif freedisk in str(needtoreplace) and askleft.replace('ask/','') not in str(needtoreplace): ### reject
            dels(leaderip, askleft)
        elif freedisk not in str(needtoreplace):    ##### accept
            put(leaderip, askleft.replace('ask/',''), askright)
        print(askleft,askright, freedisk)
    return
  
def spare2(*args):
 global newop
 global usedfree 
 global leader, leaderip, myhost, myhostip, etcdip
 if args[0]=='init':
        leader = args[1]
        leaderip = args[2]
        myhost = args[3]
        myhostip = args[4]
        etcdip = args[5]
        initqueue(leaderip, myhost) 
        getall('init',leader, leaderip, myhost, myhostip, etcdip)
        return

 print('hihiihihihih',etcdip)
 needtoreplace = get(leaderip, 'needtoreplace', '--prefix') 
 if myhost == leader:
    solvetheasks(needtoreplace)
 myneedtoreplace = [x for x in needtoreplace if myhost in str(x) ] 
 exception = get(etcdip,'offlinethis','--prefix')
 print('it is needtoreplace',needtoreplace)
 for raidinfo in myneedtoreplace:
  print('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
  print('need to replace',raidinfo)
  poolname = raidinfo[0].split('/')[-3]
  if poolname in str(exception):
   print('this pool should not be automatically healed ')
   continue
  dmcmd = 'zpool status '+poolname
  chkstatus = subprocess.run(dmcmd.split(),stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode('utf-8')
  if 'resilvering' in chkstatus:
   continue
  print(raidinfo[0])
  raidname = raidinfo[0].split('/')[-1]
  rmdisks = raidinfo[1].split('/')[:-2]
  print('rmdisks',rmdisks)
  adisk = raidinfo[1].split('/')[-1]
  adiskname = raidinfo[1].split('/')[-2]
  cmdline2=['/sbin/zpool', 'status',poolname]
  cpoolinfo=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()
  for rmdisk in rmdisks:
   print(rmdisk)
   print('hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh')
   if rmdisk in cpoolinfo:
       print('will do:', poolname, raidname, rmdisk, adisk)
       if 'mirror-temp' in raidname:
           cmdline2=['/sbin/zpool', 'attach',poolname, rmdisk,adiskname]
       else:
           cmdline2=['/sbin/zpool', 'replace','-f',poolname, rmdisk,adiskname]
       forget=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
       print('forget',forget.returncode)
       print('cmdline2'," ".join(cmdline2))
       print('thereuslt',forget.stdout.decode())
       print('return code',forget.returncode)
       if forget.returncode == 0: 
        break
  dels(leaderip,'ask/needtoreplace',raidname)
  dels(leaderip,'needtoreplace',raidname)
  sleep(10) 
  #cmd = ['systemctl', 'restart', 'zfs-zed']
  #subprocess.run(cmd,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  #dels(leaderip,'ask/needtoreplace',raidname)
  #dels(leaderip,'needtoreplace',raidname)
  #dosync('sync/needtoreplace/____/request','needtoreplace_'+str(stamp()))
  return
 freedisks=[]
 allraids=[]
 freeraids=[]
 hosts=get(etcdip, 'ready','--prefix')
 allhosts=set()
 print('slddddddddddddddddddddddddddddd')
 for host in hosts:
  allhosts.add(host[0].replace('ready/',''))
 newop=getall(myhost)
 striperaids=[]
 if len(str(newop)) < 10:
  return
 raidsset = set()
 print('hhhhhhhhhhhhhhhhhhhhhhhhhhh')
 availability = get(etcdip, 'balance','--prefix')
 degradedpools=[x for x in newop['pools'] if myhost in x['host'] and  'DEGRADED' in x['status']]
 for spool in newop['pools']:
  if spool['name']  in str(exception):
   print('this pool should not be automatically healed ')
   continue
  for sraid in spool['raidlist']:
    if myhost not in str(sraid):
     continue
    #if 'ree' not in sraid['name'] and spool['name'] in str(availability):
    if 'ree' not in sraid['name']: 
     raidsset.add(sraid['name'])
  for sraid in spool['raidlist']:
    if sraid['name'] in raidsset:
        allraids.append(sraid)
 striperaids=[x for x in allraids if 'stripe' in x['name']]
 onlineraids=[x for x in allraids if 'ONLINE' in x['changeop']]
 degradedraids=[x for x in allraids if 'DEGRADE' in x['status']]
 print('ddddddddddddddddddddddddddddddddddddddddddddddddd')
 print(degradedpools)
 print(len(degradedraids))
 for raid in degradedraids:
  if raid['pool']  in str(exception):
   print('this pool should not be automatically healed ')
   continue
  for disk in raid['disklist']:
   if 'ONLINE' not in disk['changeop']:
     dels(etcdip, 'disk',disk['actualdisk'])
     #delstolocal('disk',disk['actualdisk'])
 onlinedisks=get(etcdip, 'disks','ONLINE')    
 errordisks=get(etcdip, 'errdiskpool','--prefix')
 currentneedtoreplace = [x for x in needtoreplace if myhost not in str(x) ] + get(leaderip,'ask','--prefix')
 freedisks=[ x for x in newop['disks']  if ('free' in x['raid'] or (x['name'] in str(onlinedisks) and 'OFFLINED' not in x['status'] and 'ONLINE' not in x['changeop'])) and x['name'] not in str(currentneedtoreplace) ]  
 disksfree=[x for x in freedisks if x['actualdisk'] not in str(usedfree)]
 print('#####################')
 print('solving degraded raids' )
 print('degraded raids:',degradedraids)
 print('#####################')
 for raid in degradedraids:
  if raid['pool']  in str(exception):
   print('this pool should not be automatically healed ')
   continue
  disksfree = solvedegradedraid(raid, disksfree)
 print('#####################')
 print('continue to the spare' )
 print(disksfree)
 print('#####################')

#####################################  set the right replacements for all raids
 #newop=getall()
 getcurrent = get(leaderip, 'hosts/'+myhost,'current')
 allraids = [] 
 raidsset = set()
 
 for spool in newop['pools']:
   if spool['name']  in str(exception):
    print('this pool should not be automatically healed ')
    continue
   if spool['name'] not in str(getcurrent) or 'ree' in spool['name']:
    continue
   for sraid in spool['raidlist']:
    print('hihihihihihihihihi',spool['name'], sraid['name'],sraid['host'])
    if len(availability) > 0:
     print('sssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssssss')
     if spool['name'] in str(availability):
      raidsset.add(sraid['name'])
    if sraid['name'] in str(getcurrent):
      raidsset.add(sraid['name'])
   for sraid in spool['raidlist']:
    if sraid['name'] in raidsset:
        allraids.append(sraid)
 diskreplace = {}
 allraidsranked = []
 if len(allraids) == 0:
  print(' no raids in the system')
  return
  
 for raid in allraids:
    if raid['pool']  in str(exception):
     print('this pool should not be automatically healed ')
     continue
    rankdisks=[]
    raid['raidrank']=[10000000,10000000]
    print('raiddisklist',raid['disklist'])
    raiddms = [x for x in raid['disklist'] if 'dm-' in x['name']]
    raiddmsc = len(raiddms)
    for disk in raid['disklist']:
        if disk['changeop'] == 'ONLINE':
            rankdisk = disk
            rankdisks.append(disk)
        print('hihihihihihihi',disk['changeop'], disk['status'])
        if 'Removed' in disk['changeop'] and 'OFFLINE' not in disk['status'] and 'OFFLINE' in str(raid):
            cmdline2=['/sbin/zpool', 'detach', raid['pool'], disk['actualdisk']]
            forget=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print('unavailable',' '.join(cmdline2))
        if raiddmsc > 1 and 'dm-' in disk['name']:
            if 'dm-' in disk['name'] and 'dm-' not in str(raid).replace(disk['name'],''):
                continue
            cmdline2=['/sbin/zpool', 'detach', raid['pool'], disk['name']]
            raiddmsc -= 1
            forget=subprocess.run(cmdline2,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print('many dms',' '.join(cmdline2))
    raid = getraidrank(raid,rankdisk,rankdisk)
    if 'dm-' in str(raid):
     raid['raidrank'] = (1000000,1000000)
    print('----originalrank----------raidname,raidrank',raid['name'],raid['raidrank'])
    print(raid)
    print(rankdisk)
    print(rankdisk)
 replacements = dict() 
 currentraid = raid.copy()
 foundranks = [] 
 for raid in allraids:
  if raid['pool']  in str(exception):
     print('this pool should not be automatically healed ')
     continue
  combinedrank = abs(raid['raidrank'][0])*1000 + raid['raidrank'][1]
  if combinedrank == 0:
   continue
  origcombinedrank = combinedrank
  bestrank = (0,0,0,combinedrank)
  for fdisk in freedisks:
   replacements[fdisk['name']] = []
   for rdisk in raid['disklist']:
    if 'dm-' in str(raid):
     if 'dm-' not in str(rdisk):
      continue
    if '_1' in str(rdisk['size']):
        continue
    if fdisk['size'] == '-' or rdisk['size'] == '-' or fdisk['name'] == rdisk['name'] or levelthis(fdisk['size']) < levelthis(rdisk['size']):
     continue
    thisrank = getraidrank(raid,rdisk,fdisk)

    thiscombinedrank = abs(thisrank['raidrank'][0])*1000 + thisrank['raidrank'][1]
    if thiscombinedrank < combinedrank:
     print('----foundnewrank----------raidname,raidrank',raid['name'],raid['raidrank'],fdisk['devname'],rdisk['devname'])
     combinedrank = thiscombinedrank
     bestrank = (rdisk,fdisk,thisrank,thiscombinedrank)
  if bestrank[3] != origcombinedrank:
    foundranks.append(bestrank)
 if len(foundranks) == 0:
  dels(leaderip, 'needtoreplace/'+myhost,'--prefix')
  dels(leaderip, 'ask/needtoreplace/'+myhost,'--prefix')
  print('no need to re- optmize raid groups')
 foundranks = sorted(foundranks, key = lambda x: x[3], reverse = True)
 diskraids = set() 
 ranks = set()
   
 print('foundrank sort',foundranks)
 for rank in foundranks:
  if rank[1]['name'] not in diskraids and rank[2]['name'] not in diskraids:
   print('needtoreplace/'+rank[0]['actualdisk'],'with',rank[1]['name'],'for raid',rank[2]['name'], 'combined rank = ',rank[3])
   diskraids.add(rank[1]['name'])
   diskraids.add(rank[2]['name'])
  print('rrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrr')
  print('rank1',rank[1]['devname'],rank[1]['actualdisk'])
  print('rank2',rank[2]['name'],rank[2]['host'])
  print('rank0',rank[0]['devname'],rank[0]['actualdisk'])
  print('if dm ?',rank[0]['name'])
  print('rrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrr')
  #dels(leaderip, 'neeedtoreplace',rank[1]['devname'])
  #dels(leaderip, 'neeedtoreplace',rank[2]['name'])
  raiddisk = rank[0].copy()
  if 'mirror-temp' in rank[2]['name']:
    for rdisk in raid['disklist']:
        if rdisk['changeop'] == 'ONLINE':
            raiddisk = rdisk.copy()
            break
  if 'dm-' in raiddisk['name'] :
   raiddisk['actualdisk'] = raiddisk['name']
   raiddisk['devname'] = raiddisk['name']
  put(leaderip, 'ask/needtoreplace/'+myhost+'/'+rank[2]['pool']+'/'+rank[2]['name']+'/'+rank[0]['devname'],raiddisk['name']+'/'+raiddisk['devname']+'/'+raiddisk['actualdisk']+'/'+rank[1]['name']+'/'+rank[1]['devname'])
  #dosync('sync/needtoreplace/____/request','needtoreplace_'+str(stamp()))
 return
 
 
 
if __name__=='__main__':
  leaderip = sys.argv[1]
  myhost = sys.argv[2]
  leader=get(leaderip, 'leader')[0]
  myhostip=get(leaderip,'ready/'+myhost)[0] 
  if myhost == leader:
   etcdip = leaderip
  else:
   etcdip = myhostip
  getall('init',leader, leaderip, myhost, myhostip, etcdip)
  spare2(sys.argv[1:])
