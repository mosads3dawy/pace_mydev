#!/usr/bin/python3
import subprocess, sys
import os
from logqueue import queuethis, initqueue
from etcdput import etcdput as put
from etcdgetpy import etcdget as get 
from etcddel import etcddel as dels
from poolstoimport import getpoolstoimport, initgetpoolstoimport
from allphysicalinfo import getall 
from time import time as stamp
from time import sleep
from ast import literal_eval as mtuple


#leader=get('leader','--prefix')[0][0].split('/')[1]
stampi = str(stamp())

def selecthosting(minhost,hostname,hostpools):
 if len(hostpools) < minhost[1]:
  minhost = (hostname, len(hostpools))
 return minhost


def dosync(sync, *args):
  global leader, leaderip, myhost, myhostip, etcdip, stmapi
  #dels(leaderip, sync)  
  put(leaderip, *args)
  put(leaderip, args[0]+'/'+leader,args[1])
  return 

def selecthost(poolinfo,readies):
    global leader, leaderip, myhost, myhostip, etcdip, stmapi
    mincount = 1000000000 
    selectedhost = 'nohost'
    # QSD5.352 (QC 684): the next host of a pool is any ready node but the one that holds the pool now.  The leader skipped
    # ITSELF, so a pool held by a follower got that follower as its "next" host (useless when it dies), and a pool the leader
    # imported while it was alone kept poolnxt = the leader after the other node came back: when that leader was stopped the
    # survivor had no assignment and did not import the pool for ~5 minutes.  An exported pool (from 'zpool import') carries
    # the scanning node as its host, so it is the same rule as before for it.
    owner = poolinfo.get('host', myhost) if isinstance(poolinfo, dict) else myhost
    readyhosts = [ h[0].split('/')[1] for h in readies if isinstance(h, (list, tuple)) and len(h) > 0 and '/' in str(h[0]) ]
    if owner not in readyhosts:
        owner = myhost
    for hostinfo in readies:
        host = hostinfo[0].split('/')[1]
        if owner == host and len(readies) > 1  :
            continue   ########  pass this since we are searching for the next host 
        counts = list(str(poolinfo['raids'])).count(host)
        if counts  < mincount:
            selectedhost =  host
            mincount = counts
        #elif selectedhost[0] == counts:
        #    selectedhost[1] = selectedhost[1] + [ host ]
    return selectedhost
        
def foreignpool(pool):
 # container flavour: one kernel for every cluster, so a pool of ANOTHER cluster is visible here.  Its owner (zfs property
 # topstor:owner, /pace/cpoolowner.sh) is a host this cluster has never known (no ipaddr/<host> key): never import,
 # reguid or re-own such a pool, and drop what already points at it (seen in QC test 23, QSD5.280).
 if not (os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10')):
  return False
 try:
  owner = subprocess.run(['/pace/cpoolowner.sh','of',pool],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.decode().strip()
 except Exception:
  return False
 if owner in ('', '-', myhost):
  return False
 return str(get(leaderip,'ipaddr/'+owner)[0]) == '_1'

def ownedbylivepeer(pool):
 # container flavour: one kernel, so a pool that a node has just created is already "imported" here. The leader names a
 # standby (poolnxt) at once, and in the first seconds the pools list does not hold the pool yet: the standby "imported" it
 # (a no-op), took the owner property and left the creator holding the mount -- the pool then showed host UNAVAIL / not
 # balanced and its delete ended 'pool is busy' (QC test 10, QSD5.332).  A pool that is imported and whose owner is another
 # node that is still ready is not taken over; a dead owner is not in ready, so a real take over is not affected.
 if not (os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10')):
  return False
 if not os.path.exists('/proc/spl/kstat/zfs/'+pool):
  return False
 try:
  owner = subprocess.run(['/pace/cpoolowner.sh','of',pool],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30).stdout.decode().strip()
  if owner in ('', '-', myhost):
   return False
  return owner in str(get(leaderip,'ready','--prefix'))
 except Exception:
  return False

def destroyedpool(pool):
 # QSD5.345: DGdestroyPool leaves a tombstone destroyedpool/<pool> (leader etcd, copied to every node): a pool of that name
 # that shows up again in 'zpool import' is a stale leg of the deleted pool (its node was away at the delete) and is never
 # assigned, imported or re-registered here.  A pool the user imports on purpose (DGsetPool 'import') clears the tombstone.
 for ip in (leaderip, etcdip):
  try:
   if str(get(ip,'destroyedpool/'+pool)[0]) not in ('_1', '-1', '', 'None'):
    return True
  except Exception:
   pass
 return False

def poolonline(pool):
 # "zpool reguid / export / import ..." wait for a transaction group.  On a SUSPENDED pool (its disks are gone) that
 # wait never ends, in the kernel (state D, not killable), and it holds ZFS's global lock: after that every zpool /
 # zfs command on the host hangs until the host is rebooted (seen on 2026-10-07, twice).  So such a pool is left
 # alone here; /pace/closthost.sh (container flavour) gives it its disks back and resumes it first.
 try:
  with open('/proc/spl/kstat/zfs/'+pool+'/state') as f:
   return f.read().strip() in ('ONLINE', 'DEGRADED')   # DEGRADED answers; only SUSPENDED hangs
 except OSError:
  return False


def poolishere(pool):
 # container flavour: one kernel, the owner is written on the pool; physical: the pool is imported here or it is not
 if os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10'):
  try:
   res = subprocess.run(['/pace/cpoolowner.sh','of',pool],stdout=subprocess.PIPE,timeout=30)
   return res.stdout.decode('utf-8','replace').strip() in (myhost, '')
  except Exception:
   return True       # unknown: keep the marker
 return os.path.exists('/proc/spl/kstat/zfs/'+pool)


def memberimportdir(pool, disks):
 # a directory of symlinks to the by-id devices (and their partitions) of the disks etcd lists in <pool>; '' when none is present
 import glob
 impdir = '/tmp/impdir-'+pool
 subprocess.run(['rm','-rf',impdir])
 os.makedirs(impdir, exist_ok=True)
 found = 0
 for name, d in disks.items():
  if d.get('pool') != pool:
   continue
  for key in ('actualdisk','zname','name'):
   dname = str(d.get(key,'')).replace('/dev/disk/by-id/','')
   if dname and dname != '_1':
    for dev in glob.glob('/dev/disk/by-id/'+dname+'*'):
     link = impdir+'/'+os.path.basename(dev)
     if not os.path.exists(link):
      os.symlink(dev, link)
      found += 1
 if found == 0:
  return ''
 return impdir

STALESECS = 300

def guardlog(msg):
 print(msg)
 try:
  with open('/root/zpooltoimport-guard.log','a') as f:
   f.write(str(stamp())+' '+msg+'\n')
 except OSError:
  pass

def seenbyscan(impdir, poolid):
 # the pool (by its id, or by its name when no ActPool id is known) is listed by a scan of the member disks only
 import re
 try:
  res = subprocess.run(['/usr/sbin/zpool','import','-d',impdir],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
 except (OSError, subprocess.TimeoutExpired):
  return False
 out = res.stdout.decode('utf-8','replace')
 pat = r'^\s*(id|pool):\s*'+re.escape(str(poolid))+r'\s*$'
 return re.search(pat, out, re.M) is not None

def nomemberhere(pool, poolline, owner):
 # poolnxt/<pool> names me but no disk that etcd lists for <pool> is present here and no ready host lists the pool (checked
 # by the caller): no import.  Right after a take over the own iSCSI disks may still be missing, so the keys are kept for
 # STALESECS; after that the LEADER deletes poolnxt/<pool> and (if it names me) pools/<pool>, by exact key and value.
 # ActPool/<pool> is kept: the only copy of the pool may sit on a node that is off now (note 116).
 mark = '/root/zpooltoimport-nomember.'+pool
 now = stamp()
 try:
  with open(mark) as f:
   since = float(f.read().strip())
 except (OSError, ValueError):
  since = now
  try:
   with open(mark,'w') as f:
    f.write(str(now))
  except OSError:
   pass
 if now - since < STALESECS or myhost != leader:
  guardlog('pool '+pool+': no member disk here, not imported (no key removed, '+str(int(now-since))+' s, leader '+str(leader)+')')
  return
 guardlog('pool '+pool+': no member disk here for '+str(int(now-since))+' s and no ready host lists it: stale keys removed')
 dels(leaderip, poolline[0], str((poolline[0], poolline[1])))
 if owner == myhost:
  dels(leaderip, 'pools/'+pool, str(('pools/'+pool, myhost)))
 try:
  os.remove(mark)
 except OSError:
  pass

def zpooltoimport(*args):
 global leader, leaderip, myhost, myhostip, etcdip
 if args[0]=='init':
     leader = args[1]
     leaderip = args[2]
     myhost = args[3]
     myhostip = args[4]
     etcdip = args[5]
     initqueue(leaderip, myhost) 
     initgetpoolstoimport(leader,leaderip,myhost,myhostip)
     return
 poouids = get(etcdip,'poouids',myhost) 
 nextpools=get(leaderip, 'poolnxt', '--prefix') 
 if 'not reachable' in str(nextpools):
        return
 needtoimport=[ x for x in nextpools if myhost in str(x)] 
 pools = [v for k,v in getall(leaderip)['pools'].items()]
 mypools = [v  for v in pools if v['host'] == myhost ]
 if 'not reachable' in str(pools):
        return
 if '_1' in str(poouids):
    poouids = []
 for poo in poouids:
    print('poouids start')
    pool=poo[0].split('/')[1]
    # Ours is decided by the pool itself (owner property / imported here), not by the pools list of etcd: right after a
    # take over that list still names the old host for a few seconds, the marker was dropped in that window and the pool kept
    # its old id for ever (seen in QC test 14, QSD5.304: the returning node imported its stale leg and the data was lost).
    if not poolishere(pool) or destroyedpool(pool):
        dels(etcdip, 'poouids/'+pool)      # the pool is not ours any more (taken over elsewhere or deleted): nothing to retry here
        continue
    if str(get(leaderip,'destroying/'+pool)[0]) != '_1':
        continue                           # QSD5.345: being destroyed: no reguid, no new ActPool/<pool> meanwhile
    if poolonline(pool):
        cmdline = 'zpool reguid '+pool
        result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        with open('/root/poouids.log','a') as f:
            f.write(str(stamp())+' '+pool+' reguid rc='+str(result.returncode)+' '+result.stderr.decode('utf-8','replace')+'\n')
        if result.returncode == 0:
            print('done')
            cmdline="zpool get guid "+pool+" -H "
            guid=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split()[2]
            dels(leaderip,'sync/ActPool', pool)
            put(leaderip,'ActPool/'+pool,guid)
            dosync('actpool_', 'sync/ActPool/Add_'+pool+'_'+guid+'/request','actpool_'+str(stamp()))
            dels(etcdip, 'poouids/'+pool) 
        else:
            print('pool not ready yet')
 if myhost not in str(needtoimport):
  print(needtoimport)
  print('no need to import a pool here')
                  
 else:
  for poolline in needtoimport:
   pool = poolline[0].replace('poolnxt/','')
   if pool in str(pools):
    continue
   if foreignpool(pool):
    print('pool of another cluster, not imported', pool)
    dels(leaderip, 'poolnxt', pool)
    dels(leaderip, 'pools', pool)
    continue
   # holder of the pool in the leader's etcd, used by nomemberhere() below (as upstream 1688ff5a; it was left out of the port and
   # raised NameError in every round).  A missing pools/<pool> key reads '_1' (etcdget has no strict argument here): unknown owner.
   owner = str(get(leaderip, 'pools/'+pool)[0])
   if str(get(leaderip,'destroying/'+pool)[0]) != '_1':
    print('pool is being destroyed, not imported', pool)
    continue
   if destroyedpool(pool):
    print('pool was deleted, a stale copy is not imported', pool)
    dels(leaderip, 'poolnxt/'+pool)
    continue
   if ownedbylivepeer(pool):
    print('pool is imported and owned by a live node, not taken over', pool)
    continue
   print('pool to be imported now', pool)
   # the assignment may have been withdrawn since the list was read (DGdestroyPool exports the pool for a moment): a pool that
   # is being destroyed must not be taken over here (QSD5.325)
   if str(get(leaderip,'poolnxt/'+pool)[0]) != myhost:
    print('assignment of', pool, 'withdrawn, not imported')
    continue
   poolid = get(leaderip,'ActPool/'+pool)[0]
   if poolid == '_1':
    poolid = pool
   # Import only from the disks that are members of this pool (etcd), so a stale leg that kept the pool's name but was
   # detached while its node was away (old guid, free disk now) can never be imported as the pool and then be re-attached over.
   # Never a plain 'zpool import <id>' (it scans every device of the host): with no member disk here there is nothing of this
   # cluster to import, and a leftover disk or a deleted pool of the same id could be imported (QC test 22 validator 643d B,
   # P-DEVELOPMENT note 116).  The stale poolnxt/pools keys are removed by the leader after STALESECS (nomemberhere()).
   impdir = memberimportdir(pool, getall(leaderip)['disks'])
   if not impdir:
    nomemberhere(pool, poolline, owner)
    continue
   try:
    os.remove('/root/zpooltoimport-nomember.'+pool)
   except OSError:
    pass
   if not seenbyscan(impdir, poolid):
    print('pool', pool, 'id', poolid, 'is not seen by zpool import -d', impdir, ': not imported in this round')
    continue
   cmdline= '/usr/sbin/zpool import -d '+impdir+' '+poolid
   # poolnxt/<pool> is the only trigger of this import: it is deleted only after the import worked (below).  It used to be deleted here,
   # before the import, so one failed first try (the disk session of the survivor was not up yet after a take over) orphaned the pool for ever.
   print(cmdline)
   put(leaderip, 'pools/'+pool,myhost)
   res = subprocess.run(cmdline.split(),stdout=subprocess.PIPE)
   result = res.stdout.decode('utf-8')
   sleep(1)
   cmdline= '/usr/sbin/zpool status  '
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   print('result',result)
   if pool in result and poolonline(pool):
    dels(leaderip, 'poolnxt', pool )      # imported: the assignment is done
    # The pool is imported by its id (ActPool/<pool>), and a new id is given right after the import, so the next import
    # (by the id every node knows) finds only the devices that took part in THIS import: a disk that was away meanwhile
    # keeps the old id and can no longer be imported as the pool.  ZFS refuses 'zpool reguid' on a pool that is not healthy,
    # and after a take over the pool is degraded (the dead node's disk is missing) until the missing disk is replaced.
    # That refusal was ignored: the old id was stored again, nothing retried, and the next take over imported the stale
    # disk of the dead node and lost what had been written meanwhile.  Now a refused reguid keeps the old id published
    # and leaves a retry marker (poouids/<pool>) that the loop at the top of this function works off as soon as the pool is healthy.
    cmdline = 'zpool reguid '+pool
    result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode == 0:
       print('done')
       cmdline="zpool get guid "+pool+" -H "
       guid=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split()[2]
       dels(leaderip,'sync/ActPool', pool)
       put(leaderip,'ActPool/'+pool,guid)
       dosync('actpool_', 'sync/ActPool/Add_'+pool+'_'+guid+'/request','actpool_'+str(stamp()))
       dels(etcdip, 'poouids/'+pool) 
    else:
       print('reguid refused (pool not healthy yet), retried later:', result.stderr.decode('utf-8','replace'))
       put(etcdip, 'poouids/'+pool, myhost)

    # container flavour: the pool is visible in every node (one kernel), its owner is written on the pool
    if os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10'):
        subprocess.run(['/pace/cpoolowner.sh','set',myhost,pool])
    # the cache (L2ARC) must sit on the node that owns the pool: a cache disk of another -- or a lost -- node is
    # replaced by a local one.  DGsetPool did this for a manual import only; a pool taken over after its owner
    # died comes through here.
    try:
        res = subprocess.run(['/usr/bin/python3','/TopStor/fixcachelocality.py',leaderip,pool,myhost],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        with open('/root/fixcachelocality.log','a') as f:
            f.write(str(stamp())+' '+pool+' '+myhost+'\n'+res.stdout.decode('utf-8','replace')+'\n')
    except Exception as e:
        print('fixcachelocality failed:',e)
    put(etcdip, 'dirty/volume','0')
    #put(etcdip, 'poouids/'+pool,myhost)
    print('before sync')
    print('sync pools Add')
    dels(leaderip,'sync/pools', pool)
    dosync('pools_', 'sync/pools/Add_'+pool+'_'+myhost+'/request','pools_'+str(stamp()))
    print('pools_', 'sync/pools/Add_'+pool+'_'+myhost+'/request','pools_'+str(stamp()))
    print('After sync')
    #cmdline= 'systemctl restart zfs-zed  '
    #result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   else:
    dels(leaderip, 'pools/',pool)         # not imported (yet): poolnxt stays, the next round (9 s) tries again
        
    
 if myhost != leader:
  return

 readies=get(etcdip,'ready','--prefix')
 hosts=get(leaderip,'host','/current')
 
 #pools = [poolinfo[0].split('/')[1]+'_'+poolinfo[1] for poolinfo in pools ]
 activepools = get(leaderip, 'ActPool','--prefix')
 notactivepools = getpoolstoimport()
 cpools = pools
 for notpo in notactivepools:
    notpname = notpo['name']
    notpid = notpo['guid'] 
    # container flavour: one kernel for every cluster, so an EXPORTED pool of another cluster (its owner node is down or
    # stopped, the pool is listed by "zpool import" and has no readable owner property) looks like a pool nobody knows.
    # This cluster has never had it (no ActPool/<pool>, not in pools/): never assign it (QC test 21, QSD5.315).
    if (os.path.exists('/.dockerenv') or os.path.isdir('/sys/class/net/eth10')) and notpname not in str(activepools):
        continue
    if destroyedpool(notpname):
        continue      # QSD5.345: a stale copy of a deleted pool (both flavours)
    if (notpname in str(activepools) and (notpid in str(activepools) or len(readies) == 1)) or notpname not in str(activepools): 
        cpools = cpools + [notpo] 
    #if len(readies) == 1:
    #    dels(leaderip, 'ActPool/'+notpname)
 
 importedpools = set(str(p.get('name')) for p in pools if isinstance(p, dict))
 for poolinfo in cpools:
    pool = poolinfo['name']
    if 'pree' in pool:
     continue
    # QSD5.352 (QC 684): an imported pool is always re-checked; poolnxt naming this leader (written while it was alone)
    # kept the pool in needtoimport and was never moved to the node that came back
    if pool not in str(needtoimport) or (pool in importedpools and len(readies) > 1):
        nxthost=selecthost(poolinfo,readies)
        print('nxthosts',nxthost)
        poolnxt=get(leaderip,'poolnxt/'+pool)[0]
        # exact comparison: "poolnxt in str(nxthost)" was True for an EMPTY stored value ('' is a substring of every
        # string), so a pool whose poolnxt had been emptied was never assigned to a node again and never imported
        if poolnxt == nxthost:
            continue 
        print('adding')
        #dels(leaderip,'poolnxt/'+pool)
        put(leaderip,'poolnxt/'+pool,nxthost)
        print('sync poolnxt Add',nxthost,pool)
        dels(leaderip,'sync/poolnxt',pool)
        dosync('poolnxt', 'sync/poolnxt/Add_'+pool+'_'+nxthost+'/request','poolnxt_'+str(stamp()))
 return
     
       
if __name__=='__main__':
    import sys
    if len(sys.argv) == 5:
        leader=sys.argv[1]
        leaderip=sys.argv[2]
        myhost=sys.argv[3]
        myhostip=sys.argv[4]
    else:
        print('sysargv',len(sys.argv))
        cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
        leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
        cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
        leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
        cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
        myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
        cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
        myhostip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
    if leader == myhost:
        etcdip = leaderip 
    else:
        etcdip = myhostip
    initqueue(leaderip, myhost) 
    initgetpoolstoimport(leader,leaderip,myhost,myhostip)
    zpooltoimport('hi')
