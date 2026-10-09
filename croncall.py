#!/usr/bin/python3
import subprocess, sys
from etcdget import etcdget as get
from etcdput import etcdput as put 
from etcddel import etcddel as dels 


def croncall(*args):
    leaderip = args[0]
    calls = get(leaderip,'call','--prefix')
    for call in calls:
        dels(leaderip, call[0])
        runthis = call[1].replace('::',' ') 
        print(runthis)
        result = subprocess.run(runthis.split(),stdout=subprocess.PIPE).stdout.decode()
        #if 'successfulwork' not in result:
        #    put(leaderip, call[0], call[1])
if __name__=='__main__':
    leaderip = sys.argv[1]
    croncall(leaderip) 
