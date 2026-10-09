#!/usr/bin/python3
import sys, subprocess, re, zlib, json, base64
from etcdgetpy import etcdget as get 
from etcdput import etcdput as put

def json_zip(j):
    j = base64.b64encode(
            zlib.compress(
                json.dumps(j).encode('utf-8')
            )
        ).decode('ascii')
    
    return j

def json_unzip(j, insist=True):
    try:
        j = zlib.decompress(base64.b64decode(j))
    except:
        raise RuntimeError("Could not decode/unzip the contents of "+j)

    try:
        j = json.loads(j)
    except:
        raise RuntimeError("Could interpret the unzipped contents of "+j)

    return j

def collectConfig(leaderip, nodeName):
    cmdline = '/TopStor/collectconfig.sh'.split()
    content = subprocess.run(cmdline,stdout=subprocess.PIPE, text=True).stdout
    print(content)
    zipped = json_zip(content)
    put(leaderip, 'getconfig/'+nodeName, zipped)


if __name__=='__main__':
    leaderip = sys.argv[1]
    nodeName = sys.argv[2]
    with open('/root/upateconfig','w') as f:
        f.write(leaderip+' '+nodeName)
    collectConfig(leaderip, nodeName)
