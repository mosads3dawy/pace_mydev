#!/usr/bin/sh
fapipy() {
cd /TopStor
 docker exec flask /TopStor/fapi.py 
}

while true;
do
 fapipy
 # 2 s, not 10: on a node that takes the cluster over the flask container appears at some moment, and the
 # API must be started right away (10 s here was up to 10 s of the fail over time)
 sleep 2 
done

