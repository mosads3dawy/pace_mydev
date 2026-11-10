#!/usr/bin/python3
import subprocess,sys,os
from etcdgetpy import etcdget as get
from etcdgetnoportpy import etcdget as getnoport
from etcdput import etcdput as put
from etcddel import etcddel as dels 
from ast import literal_eval as mtuple
from time import time as _timestamp

leader, leaderip, myhost, myhostip, pport = '','','','','-1'
def usrfninit(ldr,ldrip,hst,hstip,pprt='-1'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 leader, leaderip, myhost, myhostip, pport = ldr, ldrip, hst, hstip, pprt
 return
allusers = []

def usersgroups(username, pullsync=False):
 """comma separated groups (never Everyone, which UnixChangeUser always adds) of the sender that list `username` as a member;
 the user's own name when there is none (what UnixAddUser/UnixChangeUser always accepted: a group named like the user is skipped)."""
 try:
  if pullsync:
   groups = getnoport(leaderip,pport,'usersigroup','--prefix')
  else:
   groups = get(leaderip,'usersigroup','--prefix')
 except Exception as e:
  print('usersgroups: cannot read the groups', e)
  return username
 found = []
 for grp in groups:
  try:
   name = grp[0].replace('usersigroup/','')
   members = grp[1].split('/')[2].split(',')
  except Exception:
   continue
  # a group that does not exist on this node yet (initial sync: users come before groups) would make usermod refuse the whole
  # list, Everyone included: groupsyncall adds the members of such a group right after
  if name != 'Everyone' and name != username and username in members and name not in found and subprocess.run(['getent','group',name],stdout=subprocess.DEVNULL).returncode == 0:
   found.append(name)
 return ','.join(found) if found else username

def thread_add(user,syncip, tosync='pullavail'):
 global myusers
 global allusers, leader ,leaderip, myhost, myhostip,pport
 username=user[0].replace('usersinfo/','')
 if 'NoUser' == username:
  return
 with open('/root/usersync2','w') as f:
  f.write(str(user)+' + '+str(username)+'\n')
 
 if 'pullsync' in tosync:
    userhash=getnoport(leaderip,pport,'usershash/'+username)[0]
    everyone=getnoport(leaderip,pport,'usersigroup/Everyone',username)
    if '_1' not in str(everyone):
        everyone=',Everyone'
    else:
        everyone=''
 else:
    userhash=get(leaderip,'usershash/'+username)[0]
    everyone=get(leaderip, 'usersigroup/Everyone',username)
    if '_1' not in str(everyone):
        everyone=',Everyone'
    else:
        everyone=''
 userinfo=user[1].split(':')
 userid=userinfo[0]
 usergd=userinfo[1]
 usersplit = user[1].split('/')
 homePool = usersplit[1]
 # usersinfo/<user> = <id>:<gd>:/<pool>/<user>/<size>/<privileges>: field 2 is the USER NAME, never its groups.  The groups of the
 # user are the usersigroup/<group> entries (value <id>:<gd>:<home>/<size>/<members>/...) that list it as a member.  The receiver
 # used to hand its own name to UnixAddUser as the groups, so a user replicated with a live change lost its group membership
 # (only Everyone was applied) -- the later UsrChange request is not a safe carrier: it is filed 10 s after the change started
 # and is applied before the user exists on the receiver when the sender is slow.
 usergroups = usersgroups(username, pullsync=('pullsync' in tosync))
 userpass = userhash
 size = usersplit[3]
 HomeAddr = usersplit[-3]
 HomeSubnet = usersplit[-2]
 active = usersplit[-1]
 permissions = ",".join(usersplit[4:-3])
 cmdline=['/TopStor/UnixAddUser',leaderip,username, homePool, 'groups'+usergroups+everyone,userhash, size, HomeAddr, HomeSubnet, tosync, userid,usergd,active, permissions,'system']
 print('***************************')
 print(cmdline)
 print('***************************')
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)

def delexactkey(etcdip, key):
 """'etcdctl del <key>' without --prefix: removes exactly this one key.  etcddel.py (dels) matches by SUBSTRING of key or value
 (dels(ip,'user','usr1') also removed usersinfo/usr10.., usershash/usr10.. and usersigroup/Everyone), so never use it for a user."""
 try:
  subprocess.run(['etcdctl','--endpoints=http://'+etcdip+':2379','del',key],stdout=subprocess.PIPE,timeout=10,env=dict(os.environ,ETCDCTL_API='3'))
 except Exception as e:
  print('delexactkey',key,e)

def thread_del(username,syncip, pullsync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 if  'NoUser' == username or 'Everyone' == username or 'admin' == username or '' == username:
  return
 # the user is deleted here only when the sending leader really has no usersinfo/<user> (exact key); a user that was deleted
 # and created again before this node applied the delete request is kept.  (`username not in str(allusers)` was always true
 # for a single request: allusers is only filled by a full sync, and it is a substring test.)
 # a read that failed looks like a missing key ('_1') for a plain key read, so read the key as a prefix (strict: a failed read is
 # 'not reachable') and take only the entry with exactly this key; anything that is not a (key,value) pair means "unknown": keep
 try:
  if 'pullsync' in pullsync:
   found = getnoport(leaderip,pport,'usersinfo/'+username,'--prefix')
  else:
   found = get(leaderip,'usersinfo/'+username,'--prefix',strict=True)
  if [ x for x in found if not isinstance(x,tuple) ]:
   print('thread_del: cannot read usersinfo/'+username+' of the leader, user kept', found)
   return
  if [ x for x in found if x[0] == 'usersinfo/'+username and x[1] not in ('_1','-1','','None') ]:
   print('thread_del: the leader still has usersinfo/'+username+', user kept')
   return
 except Exception as e:
  print('thread_del: cannot read usersinfo/'+username+' of the leader, user kept', e)
  return
 cmdline=['/TopStor/UnixDelUser',leaderip, username,'system',pullsync]
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)
 # exact keys of this user only (UnixDelUser already removed them; this clears what it could not)
 delexactkey(syncip,'usersinfo/'+username)
 delexactkey(syncip,'usershash/'+username)

def usersyncall(tosync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip,pport
 global allusers
 global myusers
 if 'pullsync' in tosync:
    allusers=getnoport(leaderip,pport,'usersinfo','--prefix')
 else:
    allusers=get(leaderip,'usersinfo','--prefix')
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 myusers=get(syncip,'usersinfo','--prefix')
 threads=[]
 if '_1' in allusers:
  allusers=[]
 if '_1' in myusers:
  myusers=[]
 for user in allusers:
  thread_add(user,syncip, tosync)
 if 'pullsync' in tosync:
  pulladminhash('admin')
 elif myhost not in str(leader):
  # admin has no usersinfo, so no UnixAddUser above carries its hash: a node that was down while the admin
  # password changed kept the old one in its etcd and handed it to the cluster when it became the leader
  try:
   newhash = str(get(leaderip,'usershash/admin')[0]).replace('\n','')
   if newhash not in ('_1','-1','','None') and len(newhash) > 3 and newhash != str(get(myhostip,'usershash/admin')[0]).replace('\n',''):
    put(myhostip,'usershash/admin',newhash)
    subprocess.run(['/TopStor/UnixChangePass','admin','admin'],stdout=subprocess.PIPE)
  except Exception as e:
   print('admin hash sync', e)
 leader=get(leaderip,'leader','--prefix')
 if myhost not in str(leader) or 'pullsync' in tosync:
  for user in myusers:
   if user not in allusers:
     user=user[0].replace('usersinfo/','')
     thread_del(user, syncip, tosync)

_hashchecked = 0
def followhashes(ldrip, hstip, every=60):
 """Follower side, called by every sync pass (checksyncs.syncrequest): a password hash that differs from the leader's is replaced
 by the leader's (admin, and every user that has a usersinfo record here).  A node that was down while a password changed, or whose
 pending 'passwd' request was withdrawn, otherwise kept the old hash and handed it to the cluster when it became the leader (QC
 test 26 step 35).  At most once per `every` seconds; never creates a hash for a user that does not exist here."""
 global _hashchecked
 now = _timestamp()
 if now - _hashchecked < every:
  return 0
 _hashchecked = now
 changed = 0
 try:
  theirs = get(ldrip,'usershash','--prefix',strict=True)
  mine = get(hstip,'usershash','--prefix',strict=True)
  if [ x for x in theirs + mine if not isinstance(x,tuple) ]:
   return 0
  mine = dict(mine)
  for key, newhash in theirs:
   username = key.replace('usershash/','',1)
   newhash = str(newhash).replace('\n','')
   if not key.startswith('usershash/') or '/' in username or len(newhash) <= 3 or newhash in ('_1','-1','None') or mine.get(key) == newhash:
    continue
   if username != 'admin' and not [ x for x in get(hstip,'usersinfo/'+username,'--prefix',strict=True) if x[0] == 'usersinfo/'+username ]:
    continue
   print('followhashes: the password hash of', username, 'follows the leader')
   put(hstip,key,newhash)
   subprocess.run(['/TopStor/UnixChangePass',username,'admin'],stdout=subprocess.PIPE)
   changed += 1
 except Exception as e:
  print('followhashes', e)
 return changed

def pulladminhash(username='admin'):
 """Receiver (DR site) side of the replication: the password hash of `username` on the sending cluster replaces the one
 on this cluster, so the sender's admin password also logs in here (QualityCheck replication tests).  The hash is
 encrypted with a key that depends only on the user name, so it is valid on any cluster.  The new hash is stored in
 this cluster's leader etcd and a 'passwd' sync request makes every node apply it (UnixChangePass reads it from etcd).
 Only for admin and for users that already exist here (their own usersinfo), never creates a stray usershash key."""
 global leaderip, pport
 try:
  newhash = str(getnoport(leaderip, pport, 'usershash/'+username)[0]).replace('\n','')
  oldhash = str(get(leaderip, 'usershash/'+username)[0]).replace('\n','')
  if username != 'admin' and str(get(leaderip, 'usersinfo/'+username)[0]) in ('_1', '-1', '', 'None'):
   return False
 except Exception as e:
  print('pulladminhash: cannot read the hash of', username, e)
  return False
 if len(newhash) < 3 or newhash == '_1' or newhash == oldhash:
  return False
 print('pulladminhash: the password of', username, 'follows the sending cluster')
 put(leaderip, 'usershash/'+username, newhash)
 dels(leaderip, 'sync', 'UnixChangePass_'+username+'_')
 put(leaderip, 'sync/passwd/UnixChangePass_'+username+'_admin/request', 'passwd_'+str(int(_timestamp()*1000)))
 return True

def oneusersync(oper,usertosync,tosync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 print('args',oper,usertosync)
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 
 if oper == 'Add':
    if 'pullsync' in tosync:
        user=getnoport(leaderip,pport,'usersinfo', usertosync)[0]
    else:
        user=get(leaderip,'usersinfo', usertosync)[0]
    thread_add(user,syncip,tosync)
 else:
    user = usertosync
    thread_del(user,syncip,tosync)
 
  
if __name__=='__main__':
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
 leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
 leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
 myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
 myhostip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 if len(sys.argv[1:]) < 2:
    usersyncall(*sys.argv[1:])
 else:
    oneusersync(*sys.argv[1:])
