#!/usr/bin/python3
import subprocess,sys, logmsg
from logqueue import queuethis, initqueue
from etcddel import etcddel as etcddel
from etcdgetpy import etcdget as get
from time import time as stamp
from etcdput import etcdput as put 

stamp = str(stamp())

def dosync(leader,*args):
  global leaderip, myhost, myhostip, etcdip
  put(leaderip, *args)
  put(leaderip, args[0]+'/'+leader,args[1])
  return 

def remknown(*args):
 global leader, leaderip, myhost, myhostip, etcdip
 if args[0]=='init':
     leader = args[1]
     leaderip = args[2]
     myhost = args[3]
     myhostip = args[4]
     etcdip = args[5]
     logmsg.initlog(leaderip, myhost)
     initqueue(leaderip, myhost) 
     return

 known=get(etcdip, 'known','--prefix')
 ready=get(etcdip, 'ready','--prefix')
 nextone=get(etcdip, 'nextlead/er')[0]
 knownchange = 0
 if len(ready) > len(known)+1:
  for r in ready:
   if r[0].split('/')[1] not in ( str(known) and str(leader)) :
    put(leaderip, 'known/'+r[0].split('/')[1],r[1])
    dosync(leader,'sync/known/Add_'+r[0].split('/')[1]+'_'+r[1]+'/request','known_'+stamp)
    knownchange = 1
 if knownchange == 1:
  known=get(etcdip, 'known','--prefix')
  
 if str(nextone) != '_1':
  if str(nextone[1]).split('/')[0] not in  str(known):
   etcddel(leaderip, 'nextlead/er')
   nextone=[]
 if known != []:
  for kno in known:
   kn=kno 
   heart=get(leaderip, kn[1],'local','--prefix')
   if( '_1' in str(heart) or len(heart) < 1) or (heart[0][1] not in kn[1]):
    thelost = kn[0].split('/')[1]
    etcddel(leaderip, kn[0])
    etcddel(leaderip, 'host',thelost)
    etcddel(leaderip, 'list',thelost)
    etcddel(leaderip, 'sync/known','_'+thelost)
    dosync(leader,'sync/known/Del_known::_'+thelost+'/request','known_'+stamp)
    etcddel(leaderip, 'sync/ready','_'+thelost)
    etcddel(leaderip, 'sync/volumes','_'+thelost)
    etcddel(leaderip, 'volumes',thelost)
    dosync(leader,'sync/volumes/request','volumes_'+stamp)
    etcddel(leaderip, 'pools',thelost)
    etcddel(leaderip, 'sync/pools','_'+thelost)
    dosync(leader,'sync/poolnxt/Del_poolnxt_'+thelost+'/request','poolnxt_'+stamp)
    dosync(leader,'sync/pools/Del_pools_'+thelost+'/request','pools_'+stamp)
    etcddel(leaderip, 'sync/nextlead',thelost)
    if kn[1] in str(nextone):
     etcddel(leaderip, 'nextlead/er')
     dosync(leader,'sync/nextlead/Del_nextlead_--prefix/request','nextlead_'+stamp)
    logmsg.sendlog('Partst02','warning','system', kn[0].replace('known/',''))
    etcddel(leaderip, 'ready/'+kn[0].replace('known/',''))
    dosync(leader,'sync/ready/Del_ready::_'+thelost+'/request','ready_'+stamp)
    etcddel(leaderip, 'running'+kn[0].replace('known/',''))
    dosync(leader,'sync/running/____/request','running_'+stamp)
    etcddel(leaderip, 'ipaddr',kn[0].replace('known/',''))
    #print('hostlost ###########################################33333')
    #cmdline=['/pace/hostlost.sh',kn[0].replace('known/','')]
    #subprocess.run(cmdline,stdout=subprocess.PIPE)
    etcddel(leaderip, 'localrun/'+str(kn[0]))

   else:
    if nextone == []:
     put(leaderip, 'nextlead/er',kn[0].replace('known/','')+'/'+kn[1])
     dosync(leader,'sync/nextlead/Add_er_'+kn[0].split('/')[1]+'::'+kn[1]+'/request','nextlead_'+stamp)
     #etcddel('nextlead','--prefix')
 poss = get(leaderip, 'pos','--prefix')
 if poss != []:
  for pos in poss:
   heart = get(etcdip, pos[1],'local','--prefix')
   if( '_1' in str(heart) or len(heart) < 1) or (heart[0][1] not in pos[1]):
    etcddel(leaderip, 'ready/'+pos[0].replace('possible',''))
    dosync(leader,'sync/ready/Del_ready::_'+pos[0].replace('possible','')+'/request','ready_'+stamp)
    etcddel(leaderip, pos[0])
   
   


if __name__=='__main__':
  leaderip = sys.argv[1]
  myhost = sys.argv[2]
  leader=get(leaderip, 'leader')[0]
  myhostip=get(leaderip,'ready/'+myhost)[1] 
  if myhost == leader:
   etcdip = leaderip
  else:
   etcdip = myhostip
 
  logmsg.initlog(leaderip, myhost)
  initqueu(leaderip, myhost) 
  remknown()
