#!/usr/bin/python3
import subprocess,sys, datetime
import json
from etcdgetlocalpy import etcdget as getlocal
from etcdgetpy import etcdget as get
from etcdput import etcdput as put 
from ast import literal_eval as mtuple
from sendhost import sendhost

leaderip = ''
myhsot = ''
def initlog(ldr,host):
    global leaderip, myhost
    leaderip = ldr
    myhost = host

def sendlog(*args):
 global leaderip, myhost
 z=[]
 knowns=[]
 dt=datetime.datetime.now().strftime("%m/%d/%Y")
 tm=datetime.datetime.now().strftime("%H:%M:%S")
 z=['/TopStor/logmsg2.sh', dt, tm, myhost ]
 for arg in args:
  z.append(arg)
 knowninfo=get(leaderip, 'known','--prefix')
 msg={'req': 'msg2', 'reply':z}
 put(leaderip, 'notification',' '.join(z))
 # One unreachable host (e.g. a known/ peer that is down) must not stop the others nor the log record below, and must never
 # raise into the caller (fapi.py login() answered HTTP 500 while a peer was off; P-DEVELOPMENT note 118).  Each host once.
 targets = [leaderip]
 for k in knowninfo:
  if isinstance(k, (tuple, list)) and len(k) > 1 and k[1] not in targets:
   targets.append(k[1])
 for h in targets:
  try:
   sendhost(h, str(msg),'recvreply',myhost)
  except Exception:
   pass      # skipped; the next sendlog tries this host again

if __name__=='__main__':
 initlog(getlocal('leaderip')[0], getlocal('clusternode')[0])
 sendlog(*sys.argv[1:])
