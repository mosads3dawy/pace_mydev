#!/usr/bin/sh
# cpoolowner.sh -- CONTAINER flavour only.
# All containers of the dev cluster share ONE kernel, so a zpool is visible ("imported") in every node at once,
# while on physical servers a pool is imported on exactly one node.  The node that owns a pool is therefore
# written on the pool itself, as the zfs user property  topstor:owner=<host>:
#   cpoolowner.sh claim <host>          every imported pool that has no owner yet becomes <host>'s
#   cpoolowner.sh set <host> <pool>     this pool is now <host>'s
#   cpoolowner.sh mine <host>           the pools of <host>, one per line (putzpool.py reports only these)
#   cpoolowner.sh of <pool>             the owner of <pool> ('-' when it has none)
# A zfs command on a SUSPENDED pool does not return, and a blocked one is not killable -- one more per call,
# every few seconds.  So properties are read and written only for pools whose kernel state is ONLINE
# (/proc/spl/kstat/zfs/<pool>/state, a plain read that cannot block); any other pool counts as "no owner".
# a DEGRADED pool (a disk is gone, the rest answers) is just as readable and must keep its owner; SUSPENDED is the dangerous one
online() { case "`cat /proc/spl/kstat/zfs/$1/state 2>/dev/null`" in ONLINE|DEGRADED) true ;; *) false ;; esac; }
cmd=$1
case $cmd in
claim)
	for p in `ls /proc/spl/kstat/zfs 2>/dev/null | grep '^pdhcp'`; do
		online $p || continue
		[ "`timeout 20 zfs get -H -o value topstor:owner $p 2>/dev/null`" = "-" ] && timeout 20 zfs set topstor:owner=$2 $p 2>/dev/null
	done ;;
set)
	online $3 && timeout 20 zfs set topstor:owner=$2 $3 2>/dev/null ;;
mine)
	for p in `ls /proc/spl/kstat/zfs 2>/dev/null | grep '^pdhcp'`; do
		online $p || continue
		[ "`timeout 20 zfs get -H -o value topstor:owner $p 2>/dev/null`" = "$2" ] && echo $p
	done ;;
of)
	online $2 && timeout 20 zfs get -H -o value topstor:owner $2 2>/dev/null ;;
esac
exit 0
