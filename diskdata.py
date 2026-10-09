#!/usr/bin/python3
import subprocess, socket, sys
from logqueue import queuethis
from levelthis import levelthis


myhost=socket.gethostname()
def diskdata(diskname):
 ddict = dict() 
 cmdline='/bin/lsscsi -is'
 result=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout
 lsscsi=[x for x in str(result)[2:][:-3].replace('\\t','').split('\\n') if 'LIO' in x ]
 for lss in lsscsi:
  lssa = lss.split()
  if lssa[6] in diskname:
   ddict={'name':diskname,'actualdisk':lssa[5].split('/')[-1],'id': lsscsi.index(lss), 'host':myhost, 'size':lssa[7],'devname':lssa[5].split('/')[-1]}
   print('dict',ddict) 
   return ddict

if __name__=='__main__':
 diskdata(*sys.argv[1:])
