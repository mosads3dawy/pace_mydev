#!/usr/bin/python3
import subprocess, sys
from etcdget import etcdget as get
from etcdput import etcdput as put 
from etcddel import etcddel as dels 


def ispoolhere(pool):
    # the pool is imported on THIS node (never hangs: zpool list under timeout)
    try:
        out = subprocess.run(['timeout','10','zpool','list','-H','-o','name'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.decode()
    except Exception:
        return False
    return pool in out.split()


def croncall(*args):
    leaderip = args[0]
    calls = get(leaderip,'call','--prefix')
    for call in calls:
        # every node runs this loop and the first one to delete the key runs the call; a Snapshotnowhost call is only
        # valid on the node that holds the pool, the other nodes used to take it and exit "host not owner" (the tick,
        # and its replication, was lost). Leave such a key for the owner.
        parts = call[1].split('::')
        if parts[0].endswith('Snapshotnowhost') and len(parts) > 1 and not ispoolhere(parts[1].split('/')[0]):
            continue
        dels(leaderip, call[0])
        runthis = call[1].replace('::',' ') 
        print(runthis)
        result = subprocess.run(runthis.split(),stdout=subprocess.PIPE).stdout.decode()
        #if 'successfulwork' not in result:
        #    put(leaderip, call[0], call[1])
if __name__=='__main__':
    leaderip = sys.argv[1]
    croncall(leaderip) 
