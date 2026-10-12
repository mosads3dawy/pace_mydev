#!/usr/bin/sh
# container flavour: skip while another container owns iscsid (see /TopStor/iscsidowner.sh)
[ -f /TopStor/iscsidowner.sh ] && . /TopStor/iscsidowner.sh && iscsid_foreign && { echo "$0: iscsid is owned by another container - nothing to do here"; exit 0; }

etcdip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
cd /pace
# Rescan every already-connected session for newly mapped LUNs. This never
# logs a session out - it just asks each live target to report new LUNs, so
# in-flight I/O on already-mapped disks is undisturbed.
/sbin/iscsiadm -m session --rescan 2>/dev/null
needrescan=0;
# Authoritative list of portals we are already logged in to, from the live
# session table (not from --rescan's log text, which isn't safe to grep: a
# format mismatch there would make an already-connected target look "new"
# and trigger a logout further down).
sessions=`/sbin/iscsiadm -m session 2>/dev/null`
#mycluster=`nmcli conn show mycluster | grep ipv4.addresses | awk '{print $2}' | awk -F'/' '{print $1}'`
nodes=(`docker exec etcdclient /TopStor/etcdget.py $etcdip ready --prefix | awk -F"', " '{print $2}' | awk -F"'" '{print $2}'`)
#nodes=(`docker exec etcdclient /TopStor/etcdgetlocal.py ready --prefix | awk -F'Partners/' '{print $2}' | awk -F"'" '{print $1}'`)
for host in "${nodes[@]}" ; do
 # QSD5.294: match the portal AND the node's current IQN. A stale session of the
 # same portal with an old IQN (node re-created with the same IP) used to make
 # the host look connected, so the new target was never logged in.
 hostiqn=`timeout 30 /sbin/iscsiadm -m discovery --portal ${host}:3266 --type sendtargets 2>/dev/null | grep $host | awk '{print $2}' | head -1`
 if [ -z "$hostiqn" ]; then
  # discovery gave nothing: fall back to the old portal-only decision
  echo "$sessions" | grep -q "${host}:3266" && continue
 elif echo "$sessions" | grep "${host}:3266" | grep -qw "$hostiqn"; then
  continue
 fi
 echo sessions=$sessions
 needrescan=1;
 echo '#############################################################'
 echo new target $host, logging in
 echo hostiqn=$hostiqn
 # best-effort removal of stale same-portal sessions with another IQN
 for old in `echo "$sessions" | grep "${host}:3266" | grep -o 'iqn[^ ]*' | grep -vw "$hostiqn"`; do
  echo stale session $old on ${host}:3266, logging out
  /sbin/iscsiadm -m node --targetname $old --portal ${host}:3266 -u
 done
 [ -n "$hostiqn" ] && /sbin/iscsiadm -m node --targetname $hostiqn --portal ${host}:3266 -l
done
