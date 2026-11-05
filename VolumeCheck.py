#!/usr/bin/python3
import subprocess,sys, os
from etcdgetpy import etcdget as get
from etcdput import etcdput as put 
from etcddel import etcddel as dels 
#from broadcasttolocal import broadcasttolocal 
from time import time as stamp
from glob import glob


#leader=get('leader','--prefix')[0][0].split('/')[1]

def dosync(*args):
  global leaderip, leader
  put(leaderip, *args)
  put(leaderip, args[0]+'/'+leader,args[1])
  return 

import re
BAD = ('', '_1', 'not reachable')

def restartargsok(reslist, ippos, what):
    # A share container is removed (undockerthis.sh) and its start script is called only when every value of the new start is
    # known to be valid.  A failed read of the leader etcd gave '_1' here, the running share was removed and cifs.py/cifs.sh
    # got shifted arguments (QC test 22 step 18, QSD5.315).
    global leader, leaderip, myhost, myhostip, etcdip
    try:
        values = [leader, leaderip, myhost, myhostip, etcdip, reslist[0], reslist[1], reslist[ippos], reslist[ippos+1]]
    except IndexError:
        print('VolumeCheck: short volume line, nothing done for', what, reslist)
        return False
    if any(str(v).strip() in BAD for v in values) \
       or not re.match(r'^([0-9]{1,3}\.){3}[0-9]{1,3}$', reslist[ippos]) or not re.match(r'^[0-9]{1,2}$', reslist[ippos+1]):
        print('VolumeCheck: bad restart values, share left as it is', what, values)
        return False
    return True

def getippos(vtype):
    print('vtype',vtype)
    if vtype in ['cifs', 'home']:
        return 7
    elif 'nfs' in vtype:
        return 9
    else: 
        return 0
def getdirtyvols(vtype, etcds, replis, dockers):
    global leader, leaderip, myhost, myhostip, etcdip
    cmdline = '/TopStor/getvols.sh '+vtype
    result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('\n')
    result = [x for x in result if 'pdhc' in x]
    resultdisabled = [ x for x in result if 'disable' in str(x) ]
    resultactive = [ x for x in result if 'active' in str(x) ]
    etcddisabled= [ x for x in etcds if 'disable' in str(x) ]
    etcdactive= [ x for x in etcds if 'active' in str(x) ]
    dirtyset = set()
    ipset = set()
    for res in result:
        reslist=res.split('/')
        ippos = getippos(vtype)
        if reslist[-1] == 'active':
            if reslist[1] in str(etcddisabled):
                dirtyset.add(res)
        else:
            if reslist[1] in str(etcdactive):
                dirtyset.add(res)
                print('here2', res)
        if reslist[1] not in str(etcds):
            dirtyset.add(res)
        for dckr in dockers.split('\n'):
            dckrip = dckr.split(' ')[-1].split('-')[-1]
            if dckrip != reslist[ippos]:
                continue
            if reslist[ippos] in dckr and reslist[-1] =='active':
                dckrname=dckr.split(' ')[-1]
                cmdline = 'docker inspect '+dckrname
                result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
                print(dckrname, reslist[1],reslist)
                if reslist[1] not in str(result):
                    print('gggggggggggggggggggggggggggggggggggggggggg')
                    print('not in',ippos, reslist[ippos], dckrip)
                    print('reslist1',reslist[1], dckrname)
                    print('gggggggggggggggggggggggggggggggggggggggggg')
                    dirtyset.add(res)
        if reslist[ippos] not in dockers and 'active' in reslist[-1]:
            dirtyset.add(res)
    print('dirtyset', dirtyset)
    return dirtyset

def nfs( etcds, replis, exports):
    global leader, leaderip, myhost, myhostip, etcdip
    #dirtyset = getdirtyvols('nfs', etcds, replis, )
    flag = 0
    for export in exports:
        with open(export) as f:
            pool = export.split('/')[1]
            vol = export.split('.')[1]
            print(pool,vol)
            exportetctip = 0
            for line in f:
                if len(line) < 5:
                    continue
                print('theline',line)
                if 'SUMMARY' in line:
                    exportetc = line.split(' ')[3]
                    exportetcip = exportetc.split('/')[-3]
                    exportetcsub = exportetc.split('/')[-2]
                    exportetcactive = exportetc.split('/')[-1]
                    if exportetc[2:-2] not in str(etcds):
                        dels(leaderip, 'volumes', vol)
                        put(leaderip,'volumes/NFS/'+myhost+'/'+pool+'/'+vol,exportetc)
                        flag = 1
                else:
                    if 'active' in exportetcactive: 
                        with open('/TopStordata/exportip.'+vol+'_'+exportetcip, 'w') as fip:
                            fip.write(line)
                        cmdline = '/TopStor/nfs.sh '+exportetcip+' '+exportetcsub
                        subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
                    else:
                        cmdline = '/TopStor/nfsumount.sh '+vol
                        subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
    if flag:
        dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
        
    return    

def nfsnew( etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 dirtyset = getdirtyvols('nfs', etcds, replis, dockers)
 print('cccccccccccccccccccccccccccccc')
 print('dirty',dirtyset)
 print('cccccccccccccccccccccccccccccc')
 for res in dirtyset:
   reslist=res.split('/')
   print('update',reslist[1])
   if not restartargsok(reslist, getippos('nfs'), res):
     continue
   cmdline = '/TopStor/undockerthis.sh '+reslist[getippos('nfs')]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   left='volumes/NFS/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   cmdline='/TopStor/nfsnew.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[9]+' '+reslist[10]+' NFS'
   print('aloooooooooooooooooooooo')
   print(cmdline)
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   put(etcdip,'dirty/volume','0')

def cifs( etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 dirtyset = getdirtyvols('cifs', etcds, replis, dockers)
 print('cccccccccccccccccccccccccccccc')
 print('dirty',dirtyset)
 print('cccccccccccccccccccccccccccccc')
 for res in dirtyset:
   reslist=res.split('/')
   print('update',reslist[1])
   if not restartargsok(reslist, getippos('cifs'), res):
     continue
   cmdline = '/TopStor/undockerthis.sh '+reslist[7]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   if 'DOMAIN' in str(res):
    left='volumes/CIFS_'+reslist[9]+'/'+myhost+'/'+'/'.join(reslist[0:2])
   else:
    left='volumes/CIFS/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   print('tosync this',leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   if 'DOMAIN' in str(res):
     cmdline='/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' CIFS_'+reslist[9]+' '+' '.join(reslist[9:])

   else:
    cmdline='/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' CIFS '+' '.join(reslist[9:])
    print('cif cifs: '+cmdline)
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   print('cifs result',result)
   put(etcdip,'dirty/volume','0')

def homes(etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 print('----------------')
 dirtyset = getdirtyvols('home', etcds, replis, dockers)
 print('hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh')
 print('dirty',dirtyset)
 print('hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh')
 for res in dirtyset:
   reslist=res.split('/')
   print('update',reslist[1])
   if not restartargsok(reslist, getippos('home'), res):
     continue
   cmdline = '/TopStor/undockerthis.sh '+reslist[7]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   left='volumes/HOMEE/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   cmdline='/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' HOMEE '+' '.join(reslist[9:])
   print('home cifs: '+cmdline)
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   print('result',result)
   put(etcdip,'dirty/volume','0')


def iscsi(etcds, replis):
 global leader, leaderip, myhost, myhostip, etcdip
 cmdline = 'targetcli ls '
 targets = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 cmdline = '/TopStor/getvols.sh iscsi'
 result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('\n')
 result = [x for x in result if 'pdhc' in x]
 for res in result:
  reslist=res.split('/')
  print('reslist1',reslist[1])
  if reslist[1] not in str(etcds):
   left='volumes/ISCSI/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   #broadcasttolocal(left,res)
  if reslist[1] not in targets:
   print(reslist)
   cmdline='/TopStor/iscsi.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[2]+' '+reslist[3]+' ISCSI '+reslist[4]+' '+reslist[5]+' '+reslist[6]+' '+reslist[7]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')

def cleanfailed(dockers):
    fails = ['timeerror','ADnameerror', 'ADservererror']
    doms = [ (doc.split('-')[-1],doc.split(' ')[0]) for doc in dockers.split('\n') if 'CIFS_' in str(doc)]
    for dom in doms:
        cmdline = '/TopStor/getdomvolstatus.sh '+dom[0]
        result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('_result')[1]
        print('dock:',cmdline,'....',result)
        if result in fails:
            print('cleaning',dom[0],dom[1])
            cmdline = 'docker rm -f '+ dom[1]
            result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
    
def volumecheck(etcds, replis, *args):
 global leader, leaderip, myhost, myhostip, etcdip
 if str(etcds)=='init':
     leader = replis 
     leaderip = args[0]
     myhost = args[1]
     myhostip = args[2]
     etcdip = args[3]
     return

 cmdline = 'docker ps'
 dockers = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 #cmdline = 'ls /TopStordata'
 #exports = subprocess.run(cmdline.split(),shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
 #cmdline = 'rm -rf /TopStordata/exportip*'
 #subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 #exports = glob('/pdhc*/exports*')
 with open('/root/volumecheck','w') as f:
  f.write(str(etcds))
 #exports = [ x.split('exports.')[1] for x in exports ]
 print('----------------------------------------------------')
 print(etcds,'\n',dockers)
 nfsnew(etcds, replis, dockers)
 print('----------------------------------------------------')
 cifs(etcds, replis, dockers)
 #nfs(etcds, replis, exports)
 homes(etcds, replis, dockers)
 iscsi(etcds, replis)
 cleanfailed(dockers) 
   
if __name__=='__main__':
  leaderip = sys.argv[1]
  myhost = sys.argv[2]
  # Fail closed (QC test 22 step 18, QSD5.315): while the leader etcd cannot be read (take over, leader restart, partition)
  # the non-strict reads gave leader = myhostip = etcdip = '_1' and an EMPTY volume list, which looked like "no volume is
  # in etcd": every local volume was dirty on every pass (getdirtyvols), its running share was removed and restarted with
  # '_1' arguments.  A failed read now ends the pass without touching anything; the next pass (10 s) reads again.
  leader=get(leaderip, 'leader', strict=True)[0]
  myhostip=get(leaderip,'ready/'+myhost, strict=True)[0]
  if str(leader).strip() in BAD or str(myhostip).strip() in BAD or str(leaderip).strip() in BAD:
   print('VolumeCheck: leader etcd not readable (leader', leader, 'myhostip', myhostip, '), pass skipped')
   sys.exit(0)
  if myhost == leader:
   etcdip = leaderip
  else:
   etcdip = myhostip
   
 
  etcds = get(etcdip, 'volumes','--prefix', strict=True)
  replis = get(etcdip, 'replivol','--prefix', strict=True)
  if etcds == ['not reachable'] or replis == ['not reachable']:
   # a FAILED read must never count as "volume missing in etcd" (getdirtyvols)
   print('VolumeCheck: etcd', etcdip, 'not readable (volumes/replivol), pass skipped')
   sys.exit(0)
  volumecheck(etcds, replis)
