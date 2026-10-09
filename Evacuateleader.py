#!/usr/bin/python3
import sys
from time import time
from logqueue import queuethis, initqueue
from etcdput import etcdput as put 
from etcddel import etcddel as dels 
from Evacuatebyleader import setall
from etcdget import etcdget as get 
import logmsg


discip = '10.11.11.253'

def do(leaderip,myhost, *args):
 #with open('/TopStor/tempEvacuate','w') as f:
  #f.write(" ".join([leaderip, myhost]+list(args)))
 
 logmsg.initlog(leaderip, myhost)
 initqueue(leaderip, myhost)
 readies=get(leaderip, 'ready','--prefix')
 if len(readies) < 2 and args[-2] in str(readies):
  return
 logmsg.sendlog('Evacuaest01','info',args[-1],args[-2])
 evacip = get(leaderip, 'ActivePartners/'+args[-2])[0]
 leader=get(leaderip, 'leader','--prefix')[0][0].replace('leader/','')
 stamp = time()
 
 put(leaderip, 'sync/evacuatehost/syncfn_setall_'+args[-2]+'_'+evacip+'_'+args[-1]+'/request', 'evacuatehost_'+str(stamp))
 put(leaderip, 'sync/evacuatehost/syncfn_setall_'+args[-2]+'_'+evacip+'_'+args[-1]+'/request/'+myhost, 'evacuatehost_'+str(stamp))
 setall(leaderip, myhost,args[-2],evacip,args[-1])
 dels(discip,'possible', args[-2])
 dels(leaderip,"", args[-2])
 #logmsg.sendlog('Evacuaesu01','info',args[-1],args[-2])

if __name__=='__main__':
 do(*sys.argv[1:])
