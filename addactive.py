#!/usr/bin/python3
import sys
from socket import gethostname as hostname
from logqueue import queuethis
from etcddel import etcddel as etcddel
from time import time as stamp
from etcdgetpy import etcdget as get
from etcdgetlocalpy import etcdget as getlocal
from etcdput import etcdput as put 


def dosync(leader,*args):
  put(*args)
  put(args[0]+'/'+leader,args[1])
  return 


def addactive(leader, myhost):
 toactivate=get('toactivate','--prefix')
 if toactivate != []:
  for x in toactivate:
   Active=get('ActivePartners','--prefix')
   if x[0].replace('toactivate','') in str(Active):
    etcddel('toactivate',x[0])
   put('known/'+x[0].replace('toactivate',''),x[1])
   dosync(leader, 'sync/known/Add_'+x[0].replace('toactivate','')+'_'+x[1]+'/request','known_'+str(stamp()))
   put('nextlead/er',x[0].replace('toactivate','')+'/'+x[1])
   dosync(leader, 'sync/nextlead/Add_er_'+x[0].replace('toactivate','')+'::'+x[1]+'/request','nextlead_'+str(stamp()))
   etcddel('losthost/'+x[0].replace('toactivate',''))
   dosync(leader, 'sync/losthost/Del_'+x[0].replace('toactivate','')+'_--prefix/request','losthost_'+str(stamp()))
   frstnode=get('frstnode')
   print('frst',frstnode[0])
   if x[0].replace('toactivate','') not in frstnode[0]:
    newfrstnode=frstnode[0]+'/'+x[0].replace('toactivate','')
    put('frstnode',newfrstnode)
   put('change/'+x[0].replace('toactivate','')+'/booted',x[1])
   put('tosync','yes')
 else:
  print('toactivate is empty')


if __name__=='__main__':
 if len(sys.argv) > 1:
  leader = sys.argv[1]
  myhost = sys.argv[2]
 else:
  leader=get('leader','--prefix')[0][0].split('/')[1]
  myhost = hostname()
 addactive(leader, myhost)

