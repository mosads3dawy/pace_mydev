#!/usr/bin/python3
import subprocess,sys, os
import json
from time import sleep

def etcddel(etcd, *args):
 os.environ['ETCDCTL_API']= '3'
 endpoints='http://'+etcd+':2379'
 if args[-1]=='--prefix':
  pointer=-1
 else:
  pointer=0
 err = 2
 if len(args) > 1:
  cmdline=['etcdctl','--user=root:YN-Password_123','--endpoints='+endpoints,'get',args[0],'--prefix']
  cmdline=['etcdctl','--endpoints='+endpoints,'get',args[0],'--prefix']
 else:
  cmdline=['etcdctl','--user=root:YN-Password_123','--endpoints='+endpoints,'get',args[0]]
  cmdline=['etcdctl','--endpoints='+endpoints,'get',args[0]]
 try:
    result=subprocess.run(cmdline,stdout=subprocess.PIPE, timeout=2)
 except:
    print('no reachable')
    return
 mylist=str(result.stdout.decode()).replace('\n\n','\n').split('\n')
 zipped=zip(mylist[0::2],mylist[1::2])
 if mylist==['']:
  print('-1')
  return '-1'
 if len(args) > 1 and args[1] !='--prefix':
  todel=[]
  args2=args[1:]
  for x in args2:
   for y in zipped:
    if x in str(y):
     todel.append(y[0])
 else:
  todel=mylist
 if todel == []:
  print('-1')
  return (-1)
 count=0
 for key in todel:
  err = 2
  if len(str(key)) < 3:
      continue
  cmdline=['etcdctl','--user=root:YN-Password_123','--endpoints='+endpoints,'del',key]
  cmdline=['etcdctl','--endpoints='+endpoints,'del',key]
  try:
   result=subprocess.run(cmdline,stdout=subprocess.PIPE, timeout=2)
  except:
   print('no reachable')
   continue
  err = result.returncode
  reslist=str(result.stdout)[2:][:-3]
  if '1' in reslist:
   count+=1
 print(count)
 

if __name__=='__main__':
 etcddel(*sys.argv[1:])
