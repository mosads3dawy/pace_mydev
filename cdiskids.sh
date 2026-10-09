#!/usr/bin/sh
# cdiskids.sh -- CONTAINER flavour only (called by iscsiwatchdog.sh when is_container).
# It does for SCSI disks what udev does on a physical node; a container has no udev and its /dev is a tmpfs
# that is filled once, when the container starts.
#
#  1. device nodes: a disk that appears later (the LIO disks of a node that joins, a re-login) exists in
#     /sys/block but has no /dev/sdX, so lsscsi shows '-' as its device and the inventory skips it.  Missing
#     nodes of sd* disks and their partitions are created (mknod, numbers from sysfs), nodes of disks that are
#     gone are removed.
#  2. ids: udev makes /dev/disk/by-id/scsi-3<wwn> and "lsscsi -i" prints that id; the disk inventory
#     (putzpool.py and friends) names a disk 'scsi-'+<id>.  Without the links lsscsi printed '-', every LIO disk
#     was named 'scsi--', and the API -- which keys the disks by name -- showed one bogus disk instead of all.
#     The links udev would make are kept here:  scsi-3<naa hex> -> ../../sdX  and  ...-partN -> ../../sdXN
#     (from /sys/block/sdX/device/wwid = naa.<hex>); links of disks that are gone or changed are removed.
#
# Cheap (sysfs only) and safe to run every few seconds.
mkdir -p /dev/disk/by-id
want=""
node() {	# node <name> <sysfs dir>: make /dev/<name> when it is missing
	if [ ! -b /dev/$1 ] && [ -r $2/dev ]
	then
		mm=`cat $2/dev`
		mknod /dev/$1 b `echo $mm | cut -d: -f1` `echo $mm | cut -d: -f2` 2>/dev/null && chmod 660 /dev/$1
	fi
}
for d in /sys/block/sd*
do
	[ -d "$d" ] || continue
	dev=`basename $d`
	node $dev $d
	id=`tr -d ' \n' < $d/device/wwid 2>/dev/null`
	case $id in
	naa.*) id=3`echo $id | sed 's/^naa\.//'` ;;
	*) id="" ;;
	esac
	if [ -n "$id" ]
	then
		link=/dev/disk/by-id/scsi-$id
		want="$want $link"
		[ "`readlink $link 2>/dev/null`" = "../../$dev" ] || ln -sfn ../../$dev $link
	fi
	for p in $d/$dev[0-9]*
	do
		[ -d "$p" ] || continue
		part=`basename $p`
		node $part $p
		if [ -n "$id" ]
		then
			plink=/dev/disk/by-id/scsi-$id-part`cat $p/partition 2>/dev/null`
			want="$want $plink"
			[ "`readlink $plink 2>/dev/null`" = "../../$part" ] || ln -sfn ../../$part $plink
		fi
	done
done
# links of disks that are gone or whose id changed
for link in /dev/disk/by-id/scsi-3*
do
	[ -L "$link" ] || continue
	case " $want " in
	*" $link "*) ;;
	*) unlink $link ;;
	esac
done
# nodes of sd disks / partitions that no longer exist
for n in /dev/sd*
do
	[ -b "$n" ] || continue
	[ -e /sys/class/block/`basename $n` ] || unlink $n
done
exit 0
