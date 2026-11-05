#!/usr/bin/python3
import sys
from etcdgetpy import etcdget as get
from etcdput import etcdput as put 
from etcddel import etcddel as dels 

def synckeys(fromhost, tohost, fromkey, tokey):
 # Copying a prefix onto itself (the leader syncing its own keys: checksyncs main sets myhostip = leaderip) is a no-op; doing it
 # as del + put deleted the keys and lost them whenever the read below failed (QC test 22 step 16.5: Partner/* vanished on c1).
 if fromhost == tohost and fromkey == tokey:
  return
 # Read FIRST and delete the target only after a good read: a failed read (etcdctl timeout under load) used to delete the
 # target and then exit, leaving it empty.  An empty but successful read still clears the target as before.
 fromlist=get(fromhost,fromkey,'--prefix',strict=True)
 if '_1' in fromlist or 'not reachable' in fromlist:
  exit()
 dels(tohost,tokey,'--prefix')
 for item in fromlist:
  lefti = item[0].replace(fromkey,tokey)
  righti = item[1]
  put(tohost, lefti, righti)

if __name__=='__main__':
 synckeys(*sys.argv[1:])
