#!/usr/bin/bash
# Periodically re-runs cdiskref.sh (caddtargetdisks.sh + iscsirefresh.sh) so that
# newly attached local disks and newly joined iSCSI target nodes get picked up
# automatically, without touching anything already mapped/connected.
#
# Safe by construction:
#  - caddtargetdisks.sh only creates backstores/LUNs/ACLs that are not already
#    present (checked against `targetcli ls` each time); it never deletes an
#    existing block backstore, LUN mapping or ACL.
#  - iscsirefresh.sh only rescans sessions that are already logged in (additive,
#    picks up new LUNs) and only logs in to portals that are not yet in the
#    session list; it never logs out an existing session.
#  - a flock guards each cycle so this never overlaps a manual cdiskref.sh run
#    or a concurrent instance of itself (concurrent targetcli writers could
#    otherwise corrupt the LIO config).
#
# Usage: /pace/cdiskreflooper.sh [interval_seconds]
# Leave running in the background (e.g. `/pace/cdiskreflooper.sh & disown`).

interval=${1:-10}
lockfile=/var/run/cdiskref.lock

while true; do
	leader=`docker exec etcdclient /TopStor/etcdgetlocal.py leader`
	leaderip=`docker exec etcdclient /TopStor/etcdgetlocal.py leaderip`
	myhost=`docker exec etcdclient /TopStor/etcdgetlocal.py clusternode`
	myhostip=`docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip`

	flock -n "$lockfile" /pace/cdiskref.sh $leader $leaderip $myhost $myhostip
	if [ $? -ne 0 ]; then
		echo cdiskreflooper: skipped cycle, cdiskref.sh already running elsewhere
	fi

	sleep $interval
done
