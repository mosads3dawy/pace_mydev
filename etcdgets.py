#!/usr/bin/python3
import subprocess,sys, os
import json
from time import sleep

os.environ['ETCDCTL_API']= '3'
key=sys.argv[1]
try:
 prefix=sys.argv[2]
except:
 prefix=''
err = 2
while err == 2:
 endpoints=''
 data=json.load(open('/pacedata/runningetcdnodes.txt'));
 for x in data['members']:
  endpoints=endpoints+str(x['clientURLs'])[2:][:-2]+','
 endpoints = endpoints[:-1]
 cmdline=['etcdctl','--user=root:YN-Password_123','--endpoints='+endpoints,'get',key,prefix]
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)
 err = result.returncode
 if err == 2:
  sleep(2)
ilist=[]
try:
 if(prefix !=''):
  mylist=str(result.stdout.decode()).replace('\n\n','\n').split('\n')
  zipped=zip(mylist[0::2],mylist[1::2])
  for x in zipped:
   ilist.append(str(x).replace('run/','').replace('(','[').replace(')',']'))
  print(ilist)
 else:
  print(str(result.stdout).split(key)[1][2:][:-3])
 
except:
 print('(_1)')
