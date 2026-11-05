#!/usr/bin/python3
import subprocess, sys, re
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
    for hostinfo in readies:
        host = hostinfo[0].split('/')[1]
        if myhost == host and len(readies) > 1  :
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


OWNERDOWNSECS = 60

def ownergone(pool, owner):
 # pools/<pool> names another host that is NOT ready.  In a normal take over hostlost() (heartbeat.py) deletes the lost
 # host's pools/ keys first, so this is the unusual case: e.g. a node that boots as primary because it cannot find the
 # cluster ip deletes ready/ (docker_setup.sh) while the named owner may still be alive and hold the pool (QC test 22,
 # validator 643c R1: hostid 0 and multihost off, so nothing in ZFS stops a second import).  Import only when the owner
 # has not answered a ping for OWNERDOWNSECS in a row; any answer resets the wait.  Owner ip from ActivePartners/<owner>.
 import re
 mark = '/root/zpooltoimport-ownerdown.'+pool
 ownerip = str(get(leaderip, 'ActivePartners/'+owner, strict=True)[0])
 if ownerip == 'not reachable':
  print('leader etcd not readable, no import of', pool, 'in this round')
  return False
 if not re.match(r'^([0-9]{1,3}\.){3}[0-9]{1,3}$', ownerip):
  print('pool', pool, 'named for', owner, 'with no known address: imported as before')
  return True
 answered = False
 for _ in range(3):
  try:
   if subprocess.run(['ping','-c','1','-W','1',ownerip],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode == 0:
    answered = True
    break
  except subprocess.TimeoutExpired:
   pass
 now = stamp()
 if answered:
  try:
   os.remove(mark)
  except OSError:
   pass
  msg = 'pool '+pool+' is named for '+owner+' ('+ownerip+'), not ready but it answers ping: not imported'
  print(msg)
  with open('/root/zpooltoimport-guard.log','a') as f:
   f.write(str(now)+' '+msg+'\n')
  return False
 try:
  with open(mark) as f:
   since = float(f.read().strip())
 except (OSError, ValueError):
  since = now
  with open(mark,'w') as f:
   f.write(str(now))
 if now - since < OWNERDOWNSECS:
  print('pool', pool, 'owner', owner, ownerip, 'silent for', int(now-since), 's: waiting', OWNERDOWNSECS, 's before the import')
  return False
 with open('/root/zpooltoimport-guard.log','a') as f:
  f.write(str(now)+' pool '+pool+' owner '+owner+' '+ownerip+' silent for '+str(int(now-since))+' s: import allowed\n')
 return True     # the mark is removed after a successful import (a failed try keeps the wait done)

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

BYID = '/dev/disk/by-id'

def scanimportable(out, pool, poolid):
 # pure parser of 'zpool import -d <dir>' output: True when exactly ONE listed pool has this NAME and this exact numeric ID and a
 # state 'zpool import' accepts without -f (ONLINE / DEGRADED).  Other pools in the scan are ignored (a disk of this node may
 # still carry the labels of another, deleted pool: QC test 22 643e, node1 sdc/sde = pdhcp288205696 id 9940180792541655089).
 # A block whose status/action text (before 'config:') says the pool is or was in use by another system, or needs '-f', is
 # refused (validator 643e F2).
 if not re.match(r'^[0-9]+$', str(poolid)):
  return False                     # expected id unknown: never import by a scan
 blocks, cur = [], None
 for line in out.splitlines():
  m = re.match(r'^\s*pool:\s*(\S+)\s*$', line)
  if m:
   cur = {'pool': m.group(1), 'text': '', 'inconfig': False}
   blocks.append(cur)
   continue
  if cur is None:
   continue
  if re.match(r'^\s*config:\s*$', line):
   cur['inconfig'] = True
  if not cur['inconfig']:
   cur['text'] += ' ' + line.strip()
  m = re.match(r'^\s*(id|state):\s*(\S+)\s*$', line)
  if m and m.group(1) not in cur:
   cur[m.group(1)] = m.group(2)
 hits = [b for b in blocks if b.get('pool') == pool and b.get('id') == str(poolid)]
 if len(hits) != 1 or hits[0].get('state') not in ('ONLINE', 'DEGRADED'):
  return False
 if re.search(r"another system|'-f'|(^|\s)-f(\s|$)", hits[0]['text'], re.I):
  return False
 return True

def anysuspended():
 # a SUSPENDED pool holds the ZFS namespace lock; a 'zpool import' scan then sits in D state and timeout= cannot end it
 # (validator 643e F3): no scan while any pool of this kernel is SUSPENDED
 import glob
 for f in glob.glob('/proc/spl/kstat/zfs/*/state'):
  try:
   with open(f) as fh:
    if fh.read().strip() == 'SUSPENDED':
     return True
  except OSError:
   pass
 return False

def peersilent(pool, host, ip):
 # True when <host> (ip) has not answered a ping for OWNERDOWNSECS in a row (mark file per pool and host); any answer resets it
 mark = '/root/zpooltoimport-peerdown.'+pool+'.'+host
 answered = False
 for _ in range(3):
  try:
   if subprocess.run(['ping','-c','1','-W','1',ip],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode == 0:
    answered = True
    break
  except (OSError, subprocess.TimeoutExpired):
   pass
 now = stamp()
 if answered:
  try:
   os.remove(mark)
  except OSError:
   pass
  return False
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
 return now - since >= OWNERDOWNSECS

def peersclear(pool, alldsks, readyhosts):
 # By-scan import only (no member disk listed; validator 643e F1).  A node that boots as PRIMARY wipes hosts/ and ready/
 # (docker_setup.sh) and its own etcd copy may name itself in pools/<pool>: then no guard above pings the real holder, whose
 # live leg the scan would show here.  So EVERY other host in ActivePartners/ must be either ready with a published
 # hosts/<h>/current that does not list the pool, or silent to ping for OWNERDOWNSECS.  Otherwise: no import this round.
 partners = get(leaderip, 'ActivePartners', '--prefix', strict=True)
 if 'not reachable' in str(partners):
  guardlog('pool '+pool+': ActivePartners not readable, no by-scan import in this round')
  return False
 currents = {}
 for x in alldsks:
  if isinstance(x, tuple) and len(x) > 1:
   currents[str(x[0])] = str(x[1])
 clear = True
 for x in partners:
  if not isinstance(x, tuple) or len(x) < 2 or len(str(x[0]).split('/')) < 2:
   continue
  host, ip = str(x[0]).split('/')[1], str(x[1])
  if host in ('', myhost):
   continue
  cur = currents.get('hosts/'+host+'/current')
  if host in readyhosts and cur is not None:
   if re.search(r'[\'"]'+re.escape(pool)+r'[\'"]', cur):
    guardlog('pool '+pool+': listed in hosts/'+host+'/current, no by-scan import')
    clear = False
   continue
  if not re.match(r'^([0-9]{1,3}\.){3}[0-9]{1,3}$', ip):
   guardlog('pool '+pool+': partner '+host+' has no usable address and no published current: no by-scan import in this round')
   clear = False
   continue
  if peersilent(pool, host, ip):
   guardlog('pool '+pool+': partner '+host+' '+ip+' silent for '+str(OWNERDOWNSECS)+' s, not a holder')
   continue
  guardlog('pool '+pool+': partner '+host+' '+ip+' answers or was silent < '+str(OWNERDOWNSECS)+' s and has no published current'
           +(' (not ready)' if host not in readyhosts else '')+': no by-scan import in this round')
  clear = False
 return clear

def legpaths(pool):
 # after a by-scan import: log the device paths ZFS chose; warn when a leg is not an iSCSI scsi-/wwn- path (validator 643e F4)
 try:
  res = subprocess.run(['/usr/sbin/zpool','status','-P',pool],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
 except (OSError, subprocess.TimeoutExpired):
  guardlog('pool '+pool+': zpool status -P failed after the by-scan import')
  return
 paths = re.findall(r'(/dev/\S+)', res.stdout.decode('utf-8','replace'))
 guardlog('pool '+pool+': by-scan import legs '+' '.join(paths))
 for pth in paths:
  base = os.path.basename(pth)
  if not (base.startswith('scsi-') or base.startswith('wwn-')):
   guardlog('WARNING pool '+pool+': leg '+pth+' is not a scsi-/wwn- device')

def localscan(pool, poolid):
 # cold start / sole survivor: no pool is imported anywhere, so hosts/*/current shows every disk as free ('pree') and
 # memberimportdir() finds nothing.  The pool may still be importable from this node's own disks: a read-only scan of
 # /dev/disk/by-id (60 s timeout), matched by the exact expected id AND name (scanimportable()).
 if not re.match(r'^[0-9]+$', str(poolid)):
  return False
 if anysuspended():
  guardlog('pool '+pool+': a SUSPENDED pool is present, no by-id scan in this round')
  return None
 try:
  res = subprocess.run(['/usr/sbin/zpool','import','-d',BYID],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
 except (OSError, subprocess.TimeoutExpired):
  return False
 return scanimportable(res.stdout.decode('utf-8','replace'), pool, poolid)

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
 # Fail closed: every leader read that decides an import is strict (['not reachable'] on a failed etcdctl) and a failed one
 # skips the whole round.  A failed read used to look like "no pool is held" and the follower imported the pool the leader
 # held (split brain, QC test 21 step 30.5, QSD5.315).
 nextpools=get(leaderip, 'poolnxt', '--prefix', strict=True) 
 if 'not reachable' in str(nextpools):
        return
 needtoimport=[ x for x in nextpools if myhost in str(x)] 
 alldsks = get(leaderip, 'host', 'current', strict=True)
 if 'not reachable' in str(alldsks):
        return
 pools = [v for k,v in getall(leaderip, alldsks)['pools'].items()]
 mypools = [v  for v in pools if v['host'] == myhost ]
 if '_1' in str(poouids):
    poouids = []
 for poo in poouids:
    print('poouids start')
    pool=poo[0].split('/')[1]
    # Ours is decided by the pool itself (owner property / imported here), not by the pools list of etcd: right after a
    # take over that list still names the old host for a few seconds, the marker was dropped in that window and the pool kept
    # its old id for ever (seen in QC test 14, QSD5.304: the returning node imported its stale leg and the data was lost).
    if not poolishere(pool):
        dels(etcdip, 'poouids/'+pool)      # the pool is not ours any more (taken over elsewhere or deleted): nothing to retry here
        continue
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
   # poolnxt/<pool> is only the STANDBY assignment: it names this node while the owner is alive too.  Import only when
   # the leader's pools/<pool> is absent, names this node, or names a host that is not ready (hostlost() removes both).
   owner = str(get(leaderip, 'pools/'+pool, strict=True)[0])
   readies = get(leaderip, 'ready', '--prefix', strict=True)
   if owner == 'not reachable' or 'not reachable' in str(readies) or len(readies) == 0:
    print('leader etcd not readable, no import in this round')
    return
   readyhosts = [ x[0].split('/')[1] for x in readies if len(x[0].split('/')) > 1 ]
   if owner not in ('_1', '', myhost) and owner in readyhosts:
    print('pool', pool, 'is held by', owner, '(ready): not imported')
    continue
   if owner not in ('_1', '', myhost) and not ownergone(pool, owner):
    continue
   print('pool to be imported now', pool)
   poolid = get(leaderip,'ActPool/'+pool)[0]
   if poolid == '_1':
    poolid = pool
   # Import only from the disks that are members of this pool (etcd), so a stale leg that kept the pool's name but was
   # detached while its node was away (old guid, free disk now) can never be imported as the pool and then be re-attached over.
   # Never a plain 'zpool import <id>' (it scans every device of the host): with no member disk here there is nothing of this
   # cluster to import, and a leftover disk or a deleted pool of the same id could be imported (QC test 22 validator 643d B,
   # P-DEVELOPMENT note 116).  The stale poolnxt/pools keys are removed by the leader after STALESECS (nomemberhere()).
   impdir = memberimportdir(pool, getall(leaderip)['disks'])
   byscan = False
   if not impdir:
    # No disk is listed as a member (cold start / sole survivor: nothing is imported anywhere, every disk is 'pree').  The checks
    # above made sure that no host lists the pool in hosts/*/current and that pools/<pool> is absent, mine, or names a host that
    # is not ready and silent for OWNERDOWNSECS.  Import only if a scan of this node's own disks lists exactly this pool id AND
    # name as importable and every other ActivePartners host is ready with a published current that does not list the pool or
    # is silent for OWNERDOWNSECS (peersclear(); a node that boots as primary wiped hosts/ and ready/) -- P-DEVELOPMENT note 117.
    # Never with an unknown id, never another pool of the scan.  While the scan shows the pool importable (or cannot run because
    # a pool is SUSPENDED) the stale-key removal (nomemberhere) is not run: no poolnxt delete/re-create loop.
    seen = localscan(pool, poolid)
    if seen is None:
     continue
    if not seen:
     nomemberhere(pool, poolline, owner)
     continue
    if not peersclear(pool, alldsks, readyhosts):
     continue
    impdir = BYID
    byscan = True
    guardlog('pool '+pool+': no member disk listed, '+BYID+' shows id '+str(poolid)+' importable here: importing')
   try:
    os.remove('/root/zpooltoimport-nomember.'+pool)
   except OSError:
    pass
   if not byscan and not seenbyscan(impdir, poolid):
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
    if byscan:
     legpaths(pool)
     import glob
     for mk in glob.glob('/root/zpooltoimport-peerdown.'+pool+'.*'):
      try:
       os.remove(mk)
      except OSError:
       pass
    try:
     os.remove('/root/zpooltoimport-ownerdown.'+pool)
    except OSError:
     pass
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
    # not imported (yet): poolnxt stays, the next round (9 s) tries again.  Drop only OUR claim (put above): the old
    # dels(leaderip,'pools/',pool) removed every pools/ key matching the name, also the real owner's.
    if str(get(leaderip, 'pools/'+pool, strict=True)[0]) == myhost:
     dels(leaderip, 'pools/'+pool, str(('pools/'+pool, myhost)))   # exact (key, value) pair of etcddel's filter
        
    
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
    if (notpname in str(activepools) and (notpid in str(activepools) or len(readies) == 1)) or notpname not in str(activepools): 
        cpools = cpools + [notpo] 
    #if len(readies) == 1:
    #    dels(leaderip, 'ActPool/'+notpname)
 
 for poolinfo in cpools:
    pool = poolinfo['name']
    if 'pree' in pool:
     continue
    if pool not in str(needtoimport):
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
