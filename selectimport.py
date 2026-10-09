#!/usr/bin/python3
import sys
from etcdgetpy import etcdget as get
from logqueue import queuethis
from etcdput import etcdput as put 
from etcddel import etcddel as dels 
from time import time as stamp
from ast import literal_eval as mtuple
#from zpooltoimport import zpooltoimport as importables

  
def selecthost(minhost,hostname,hostpools):
    """
    - if len(hostpools) > 1, what should be the correct behavior?
    - current solution worst case = O(n^3), but much faster in practice
    - simple optimization with early exits
    - if we exit once we find a match, we might miss a better host. (not accounting for host with minimum number of pools
    - a better but less simple approach would be using class-based auto-caching
        - O(1) after initial cache build
        - create a dictionary of matched hosts and the number of pools they are a member in for each pool {P:{H : nP}}, need to understand behaviour and structure more before implementing
        - should automatically update cache when hostpools change
    """

    # FOR DEBUGGING
    #print("DEBUG selecthost: minhost input:", minhost)
    #print("DEBUG selecthost: hostname:", hostname) 
    #print("DEBUG selecthost: hostpools:", hostpools)
    #print("DEBUG selecthost: len(hostpools):", len(hostpools))

    has_disk_in_pool = False
    for pool in hostpools:
        for raid in pool.get('raidlist', []):
            for disk in raid.get('disklist', []):
                if hostname == disk.get('host'):
                    has_disk_in_pool = True

    if has_disk_in_pool:
        if len(hostpools) < minhost[1]:
            minhost = (hostname, len(hostpools))

    return minhost

def selectimport(*args):
    global leader, leaderip, myhost, myhostip, etcdip
    if args[0]=='init':
     leader = args[1]
     leaderip = args[2]
     myhost = args[3]
     myhostip = args[4]
     etcdip = args[5]
     return
    knowns=get(etcdip, 'ready','--prefix')
    allpools=get(etcdip, 'pools/','--prefix')
    knowns = [x[0].split('/')[1] for x in knowns ]
    for poolpair in allpools:
        if myhost not in poolpair[1]:
            continue
        pool=poolpair[0].split('/')[1]
        chost=poolpair[1]
        nhost=str(get(etcdip, 'poolnxt/'+pool)[0])
        if nhost in knowns and chost not in nhost:
            continue
        stampit=str(int(stamp()))
        print('nohost',nhost,chost)
        print('knowns',knowns)
        #if nhost != '_1':
        #	put('sync/poolnxt/Del_poolnxt_'+nhost+'/request','poolnxt_'+str(stamp))
        #	put('sync/poolnxt/Del_poolnxt_'+nhost+'/request/'+leader,'poolnxt_'+str(stamp))
        hosts=get(leaderip, 'hosts','/current')
        #print("DEBUG selectimport: hosts: ", hosts)
        #print("DEBUG selectimport: hosts type: ", type(hosts))

        if len(hosts) < 2:
            #print("DEBUG selectimport: hosts < 2, continuing")
            continue

        poolnxt = get(etcdip,'poolnxt/'+pool)
        #print("DEBUG selectimport: poolnxt value: ", poolnxt)
        #print("DEBUG selectimport: poolnxt type: ", type(poolnxt))
        #print("DEBUG selectimport: str(poolnxt): ", str(poolnxt))
        #print("DEBUG selectimport: poolnxt value:", poolnxt)

        if 'dhcp' in str(poolnxt) or nhost == '_1' or chost == nhost:
            minhost = ('',float('inf'))
            #print("DEBUG selectimport: initial minhost: ", minhost)

            for host in hosts: 
                hostname = host[0].split('/')[1]
                #print("DEBUG selectimport: hostname: ", hostname)
                #print("DEBUG selectimport: host[1] raw: ", host[1])

                if hostname == chost:
                    continue

                hostpools=mtuple(host[1])
                #print("DEBUG selectimport: hostpools after mtuple: ", hostpools)

                minhost = selecthost(minhost,hostname,hostpools)
                #print("DEBUG selectimport: minhost after selecthost: ",minhost)

            dels(leaderip, 'sync/poolnxt/', pool)
            put(leaderip, 'poolnxt/'+pool,minhost[0])
            put(leaderip, 'sync/poolnxt/Add_'+pool+'_'+minhost[0]+'/request','poolnxt_'+stampit)
            put(leaderip, 'sync/poolnxt/Add_'+pool+'_'+minhost[0]+'/request/'+leader,'poolnxt_'+stampit)
    return

 

if __name__=='__main__':
    leaderip = sys.argv[1]
    myhost = sys.argv[2]
    myhostip = get(leaderip, 'ready/'+myhost)[0]
    leader = get(leaderip, 'leader')[0]
    if leader == myhost:
        etcdip = leaderip
    else:
        etcdip = myhostip
    selectimport(leader, leaderip, myhost, myhostip)

