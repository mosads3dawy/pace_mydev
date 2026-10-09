#!/usr/bin/python3
import sys, subprocess, logmsg
from socket import gethostname as hostname
from etcddel import etcddel as etcddel
from etcddellocal import etcddel as dellocal
from logqueue import queuethis
#from broadcast import broadcast as broadcast 
from time import time as stamp
#from broadcasttolocal import broadcasttolocal as broadcasttolocal
from etcdgetpy import etcdget as get
from etcdgetlocalpy import etcdget as getlocal
from etcdput import etcdput as put 
from etcdputlocal import etcdput as putlocal 

def dosync(leader,*args):
  put(*args)
  put(args[0]+'/'+leader,args[1])
  return 


def addknown(leader,myhost):
 possible=get('possible','--prefix')
 active = get('Active','--prefix')
 stampit = str(stamp())
 for pos in possible:
  posname=pos[0].replace('possible','')
  if posname in str(active):
   #print('posname',posname)
   etcddel('lost',posname)
   etcddel('poss',posname)
   put('known/'+posname,pos[1])
   dosync(leader,'sync/known/Add_'+posname+'_'+pos[1]+'/request','known_'+'known_'+stampit)
   aliast = getlocal(pos[1],'alias/'+posname)[0]
   #print('pos',pos[1],posname,str(aliast))
   put('alias/'+posname,str(aliast))
   #print('############')
   dosync(leader,'sync/alias/Add_'+posname+'_'+str(aliast).replace('_',':::').replace('/',':::')+'/request','alias_'+stampit)
 allow=get('allowedPartners')
 if 'notallowed' in str(allow):
  return 
 possible=get('possible','--prefix')
 if possible != []:
  for x in possible:
   #print('x=',x[0], x[1])
   if 'yestoall' not in str(allow):
    #print(x[0].replace('possible',''))
    #print(str(allow))
    if x[0].replace('possible','') not in str(allow):
     #print('iamhere')
     Active=get('AcivePartners','--prefix')
     if x[0].replace('possible','') not in str(Active):
      return 
   knowns=get('known','--prefix')
   putlocal(x[1],'configured/'+myhost,'yes')
   frstnode=get('frstnode')
   if frstnode == [-1]:
    frstnode = [""] 
   if x[0].replace('possible','') not in frstnode[0]:
    newfrstnode=frstnode[0]+'/'+x[0].replace('possible','')
    put('frstnode',newfrstnode)
   dellocal(x[1],'sync','--prefix') 
   put('known/'+x[0].replace('possible',''),x[1])
   #print('syncing')
   dosync(leader,'sync/known/Add_'+x[0].replace('possible','')+'_'+x[1]+'/request','known_'+stampit)
   hostsubnet = getlocal(x[1],'hostipsubnet/'+x[0].replace('possible',''))[0]
   if hostsubnet == -1:
    hostsubnet = "24"
   etcddel('modified',x[0].replace('possible',''))
   #deltolocal('modified',x[0].replace('possible',''))
   #print('syncing2')
   put('ActivePartners/'+x[0].replace('possible',''),x[1])
   dosync(leader,'sync/ActivePartners/Add_'+x[0].replace('possible','')+'_'+x[1]+'/request','ActivePartners_'+stampit)
 
   put('hostipsubnet/'+x[0].replace('possible',''),hostsubnet)
   dosync(leader,'sync/hostipsubnet/Add_'+x[0].replace('possible','')+'_'+x[1]+'/request','hostipsubnet_'+stampit)
   put('configured/'+x[0].replace('possible',''),'yes')
   dosync(leader,'sync/configured/Add_'+x[0].replace('possible','')+'_yes/request','configured_'+stampit)
   put('nextlead/er',x[0].replace('possible','')+'/'+x[1])
   dosync(leader,'sync/nextlead/Add_er_'+x[0].replace('possible','')+'::'+x[1]+'/request','nextlead_'+stampit)
   aliast = getlocal(x[1],'alias/'+x[0].replace('possible',''))[0]
   put('alias/'+x[0].replace('possible',''),str(aliast))
   dosync(leader,'sync/alias/Add_'+x[0].replace('possible','')+'_'+x[1].replace('_',':::').replace('/',':::')+'/request','alias_'+stampit)
   cmdline=['/sbin/rabbitmqctl','add_user','rabb_'+x[0].replace('possible',''),'YousefNadody']
   result=subprocess.run(cmdline,stdout=subprocess.PIPE)
   cmdline=['/sbin/rabbitmqctl','set_permissions','-p','/','rabb_'+x[0].replace('possible',''),'.*','.*','.*']
   etcddel('losthost/'+x[0].replace('possible',''))
   dosync(leader, 'sync/cleanlost/Del_'+x[0].replace('possible','')+'_--prefix/request','cleanlost_'+stampit)
   put('change/'+x[0].replace('possible','')+'/booted',x[1])
 #  put('tosync','yes')
   if x[0].replace('possible','') in str(knowns):
    put('allowedPartners','notoall')
    #print('sync3')
    dosync(leader, 'sync/allowedPartners/Add_notoall_/request','allwedPartners_'+stampit)
    etcddel('possible',x[0])
    put('possible',x[0])
    logmsg.sendlog('AddHostsu01','info',arg[-1],name)
    #queuethis('AddHost','stop',bargs[-1])
 else:
  #print('possible is empty')
  print('')
 #queuethis('addknown.py','stop','system')

if __name__=='__main__':
 if len(sys.argv) > 1:
  leader = sys.argv[1]
  myhost = sys.argv[2]
 else:
  leader=get('leader','--prefix')[0][0].split('/')[1]
  myhost = hostname()
 addknown(leader, myhost)
