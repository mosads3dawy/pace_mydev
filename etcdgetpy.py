#!/usr/bin/python3
import subprocess,sys, os
import json
from time import sleep
from checkleader import checkleader

dev = 'enp0s8'
os.environ['ETCDCTL_API']= '3'

def etcdctl(etcd, key,prefix):
 cmdline=['etcdctl','--user=root:YN-Password_123','--endpoints=http://'+etcd+':2379','get',key,prefix]
 cmdline=['etcdctl','--endpoints=http://'+etcd+':2379','get',key,prefix]
 try:
  result=subprocess.run(cmdline,stdout=subprocess.PIPE,timeout=30)
 except subprocess.TimeoutExpired:
  # etcdctl has its own 5 s command timeout; this only guards against a hang.  Same empty output as a failed read.
  result=subprocess.CompletedProcess(cmdline,124,stdout=b'')
 return result 
 
def _lines(result):
 # etcdctl prints "key\nvalue\n" per entry; an EMPTY value is an empty line that has to stay a line.  Collapsing "\n\n" (as it
 # was done) made every entry after a key with an empty value pair up shifted (value of the entry before = key of the next),
 # so a pool listed after an emptied poolnxt key was never seen by the import loop.
 out = str(result.stdout.decode())
 if out.endswith('\n'):
  out = out[:-1]
 return out.split('\n') if out != '' else []

def etcdget(etcd, key, prefix='', *, strict=False):   # keyword-only: old 4-argument calls stay a TypeError as before
 # A failed read (etcdctl rc != 0: 'context deadline exceeded', etcd down, timeout) prints nothing, and that looked exactly like
 # an absent key ('_1') or an empty prefix ([]).  The import loop took such a failed read of the leader for "nobody holds this
 # pool" and imported a pool the leader held (split brain, QC test 21 step 30.5, QSD5.315).  strict=True returns
 # ['not reachable'] on a failed read so the caller can skip the round; without strict the result is the same as before.
 if strict and prefix not in ('', '--prefix'):
  result = etcdctl(etcd,key,'--prefix')   # the filtered form below only uses this --prefix read
 else:
  result = etcdctl(etcd, key,prefix)
 z=[]
 if strict and result.returncode != 0:
  return ['not reachable']
 try:
  if(prefix =='--prefix'):
   mylist=_lines(result)
   zipped=zip(mylist[0::2],mylist[1::2])
   for x in zipped:
    z.append(x) 
  elif(prefix == ''):
   if len(str(result.stdout).split(key)) > 2 :	
    z.append(key.join(str(result.stdout).split(key)[1:])[2:][:-3])
   else:
    z.append((str(result.stdout).split(key)[1][2:][:-3]))
  else:
   if not strict:
    result = etcdctl(etcd,key,'--prefix')
   mylist=_lines(result)
   zipped=zip(mylist[0::2],mylist[1::2])
   for x in zipped:
    if prefix in str(x):
     z.append(x)
   if(len(z) == 0):
     z.append('_1')
 except:
  z.append('_1')
 return z
if __name__=='__main__':
 etcdget(*sys.argv[1:])
