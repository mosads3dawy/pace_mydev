#!/usr/bin/python3
import subprocess,sys
import json
from logqueue import queuethis, initqueue
from ast import literal_eval as mtuple
from poolall import getall as getall, putall, delall
import logmsg


leaderip, leader, myhost, myhostip, etcdip = '','','','',''

def forceoffline(*args):
 global leader, leaderip, myhost, myhostip, etcdip
 with open('/root/changeop','w') as f:
  f.write(str(args))
 alls=getall(myhost)
 mypools=[x for x in alls['pools'] if 'pree' not in x['name'] ]  
 for mypool in mypools:
  if args[1] in str(mypool):
   cmdline='/sbin/zpool offline '+mypool['name']+' '+args[-1]
   subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
 return

def changeop(*args):
 global leader, leaderip, myhost, myhostip, etcdip
 leader, leaderip, myhost, myhostip, etcdip = args[:5]
 alls=getall(myhost)
 if type(alls) != dict :
  return -1
 if len(args) > 1:
  if args[1] == 'old':
   putall(myhost,'old')
   return 1
 oldlls=getall(myhost,'old')
 if type(oldlls) != dict :
  for disk in alls['defdisks']:
   logmsg.sendlog('Diwa1','warning','system', disk['pool'])
   cmdline='/sbin/zpool offline '+disk['pool']+' '+disk['name']
   subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
  putall(myhost,'old')
  return
 changeddisks={k:alls[k] for k in alls if alls[k] != oldlls[k] and 'disk' in k} 
 print('changed',len(changeddisks))
 if len(changeddisks) > 0:
  delall(myhost,'old')

def initchangeop():
    global leader, leaderip, myhost, myhostip, etcdip
    logmsg.initlog(leaderip, myhost)
    initqueue(leaderip, myhost)
    getall('init',leader, leaderip, myhost, myhostip, etcdip)
    return
     


if __name__=='__main__':
 leader, leaderip, myhost, myhostip, etcdip = sys.argv[1:6]
 initchangeop()
 if len(sys.argv[4:]) > 2 and 'scsi' in sys.argv[2]:
   forceoffline(sys.argv[4],sys.argv[-1])
 else: 
   changeop(*sys.argv[1:])
