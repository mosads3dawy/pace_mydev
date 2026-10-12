#!/usr/bin/python3
import sys

def levelthis(fig,power='G'):
 leveldict = {'B':1, 'K':1024, 'M':1048576, 'G':1073741824,'T':1099511627776}
 level = str(fig).replace(',','').upper().replace('MB','M').replace('GB','G').replace('KB','K').replace('TB','T')
 try:
  if level[-1] in leveldict:
   num = float(level[:-1])*leveldict[level[-1]]/leveldict[power]
  else:
   num = float(level)/leveldict[power]
 except (ValueError, IndexError):
  # a disk that is gone (REMOVED, host '_1') has the size '_1': it must not kill getall (and with it the
  # selectspare round that has to replace that very disk)
  num = 0.0
 return num 

if __name__=='__main__':
 num = levelthis(*sys.argv[1:]) 
 print(num)
