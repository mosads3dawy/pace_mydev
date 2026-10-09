#!/usr/bin/bash
# closthost.sh <lost host>  -- CONTAINER flavour only (called by hostlost.sh when is_container).
#
# When a physical server dies, everything it held dies with it: its iSCSI target, the pools it had imported.
# A container that dies leaves all of that behind in the kernel it shared with the other nodes:
#   - its LIO target and backstores stay configured (and keep the shared loop disks claimed, so no other node
#     can export them),
#   - its pools stay "imported", with vdevs that no longer answer (the pool suspends).
# This script puts the surviving node where a physical one would be:
#   1. removes the lost host's iSCSI target, its backstores and the dead sessions to it;
#   2. waits until this node exports the shared disks itself and sees them again (caddtargetdisks.sh and
#      iscsiwatchdog.sh do that on their own; the disks keep their serial = their SCSI id, see caddtargetdisks.sh);
#   3. resumes the pools of the lost host (zpool clear) and exports them cleanly.
# After that the pool is simply "not imported anywhere", and the normal path takes over, the same as on physical
# servers: the leader names a node (poolnxt), that node imports the pool (zpooltoimport.py) and gives it a local cache.
lost=$1
[ -z "$lost" ] && exit 0
log() { echo "`date '+%H:%M:%S'` closthost $lost: $*" >> /root/closthost.log; }
exec 9>/tmp/closthost.lock
flock -n 9 || { log "another run is in progress"; exit 0; }
log "start"
# pools of the lost host, read before anything is touched
orphans=`/pace/cpoolowner.sh mine $lost`
# a pool that is already SUSPENDED cannot be asked for its owner; with its disks gone it is the lost host's by definition
for sp in `ls /proc/spl/kstat/zfs 2>/dev/null | grep '^pdhcp'`; do
	case "`cat /proc/spl/kstat/zfs/$sp/state 2>/dev/null`" in ONLINE|DEGRADED) ;; *) orphans="$orphans $sp" ;; esac
done
orphans=`echo $orphans | tr ' ' '\n' | sort -u | tr '\n' ' '`
log "its pools: ${orphans:-none}"
# 1. the target side it left behind
if targetcli ls /iscsi 2>/dev/null | grep -q "iqn.2016-03.com.$lost:t1"; then
	timeout 60 targetcli /iscsi delete iqn.2016-03.com.$lost:t1 >/dev/null 2>&1
	log "target removed"
fi
# the names are taken with sed on "o- <name> ...": the tree is printed with or without a leading "|", so a column number is not safe
for bs in `targetcli ls /backstores/block 2>/dev/null | sed -n 's/.*o- \(loop[0-9]*-'$lost'\) .*/\1/p'`; do
	timeout 30 targetcli /backstores/block delete $bs >/dev/null 2>&1
done
log "backstores left for $lost: `targetcli ls /backstores/block 2>/dev/null | grep -c -- "-$lost "`"
# the initiator side: the sessions to the dead target would only end after the replacement timeout
timeout 20 iscsiadm -m node -T iqn.2016-03.com.$lost:t1 -u >/dev/null 2>&1
timeout 10 iscsiadm -m node -T iqn.2016-03.com.$lost:t1 -o delete >/dev/null 2>&1
[ -z "$orphans" ] && { log "no pool to hand over"; exit 0; }
# 2. wait for the disks of every orphan pool to answer again (through this node's own export)
for p in $orphans; do
	n=0
	while [ $n -lt 90 ]; do
		/pace/cdiskids.sh
		missing=0
		for v in `zpool status -P $p 2>/dev/null | awk '$1 ~ /^\/dev\//{print $1}'`; do
			[ -b "`readlink -f $v`" ] || missing=$((missing+1))
		done
		[ $missing -eq 0 ] && break
		sleep 2; n=$((n+2))
	done
	log "pool $p: disks back after ${n}s (missing=$missing)"
	# 3. resume and export -- but NEVER export a pool that is not healthy again: "zpool export" on a suspended
	#    pool does not return and keeps ZFS's global lock, which blocks every zpool/zfs command on the host until a
	#    reboot.  So: all disks back, zpool clear, state ONLINE and a test write, only then the export.
	if [ $missing -ne 0 ]; then
		log "pool $p: $missing disk(s) did not come back -- left as it is, NOT exported"
		continue
	fi
	timeout 60 zpool clear $p >/dev/null 2>&1
	n=0; while [ $n -lt 30 ] && [ "`cat /proc/spl/kstat/zfs/$p/state 2>/dev/null`" != "ONLINE" ]; do sleep 2; n=$((n+2)); timeout 60 zpool clear $p >/dev/null 2>&1; done
	if [ "`cat /proc/spl/kstat/zfs/$p/state 2>/dev/null`" != "ONLINE" ] || ! timeout 30 zfs set topstor:resumed=`date +%s` $p >/dev/null 2>&1; then
		log "pool $p: state `cat /proc/spl/kstat/zfs/$p/state 2>/dev/null`, a test write failed -- NOT exported"
		continue
	fi
	if zpool export $p >> /root/closthost.log 2>&1; then
		log "pool $p exported -- it can be imported by the node the leader names"
	else
		log "pool $p: export refused (see above) -- left imported"
	fi
done
log "done"
exit 0
