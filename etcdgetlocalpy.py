#!/usr/bin/python3
import subprocess,sys, os
import json
from time import sleep
from checkleader import checkleader

dev = 'enp0s8'
os.environ['ETCDCTL_API']= '3'

def etcdctl(key,prefix):
 cmdline=['etcdctl','--user=root:YN-Password_123','--endpoints=http://etcd:2379','get',key,prefix]
 cmdline=['etcdctl','--endpoints=http://etcd:2379','get',key,prefix]
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)
 return result 
 
def etcdget(key, prefix=''):
 result = etcdctl(key,prefix)
 z=[]
 try:
  if(prefix =='--prefix'):
   mylist=(lambda o: (o[:-1] if o.endswith('\n') else o).split('\n') if o else [])(str(result.stdout.decode()))   # an empty value stays an (empty) line: collapsing it shifted every later key/value pair
   zipped=zip(mylist[0::2],mylist[1::2])
   for x in zipped:
    z.append(x) 
  elif(prefix == ''):
   if len(str(result.stdout).split(key)) > 2 :	
    z.append(key.join(str(result.stdout).split(key)[1:])[2:][:-3])
   else:
    z.append((str(result.stdout).split(key)[1][2:][:-3]))
  else:
   result = etcdctl(key,'--prefix')
   mylist=(lambda o: (o[:-1] if o.endswith('\n') else o).split('\n') if o else [])(str(result.stdout.decode()))   # an empty value stays an (empty) line: collapsing it shifted every later key/value pair
   zipped=zip(mylist[0::2],mylist[1::2])
   for x in zipped:
    if prefix in str(x):
     z.append(x)
   if(len(z) == 0):
     z.append('_1')
 except:
  z.append('_1')
 print(z)
 return z
if __name__=='__main__':
 etcdget(*sys.argv[1:])
