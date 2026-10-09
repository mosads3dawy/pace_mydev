#!/usr/bin/sh
# czvoldev.sh -- CONTAINER flavour only (called by addzfsvolumeastarget.sh when is_container).
# A zvol (iSCSI volume) is a block device /dev/zdN that udev links as /dev/zvol/<pool>/<volume>.  A container has no
# udev and its /dev is a tmpfs filled when the container starts, so neither the node nor the link exists although the
# kernel (shared with the host) has the device.  Here they are made from sysfs: mknod for every /sys/block/zdN that has
# no node, and the link /dev/zvol/<dataset> -> ../../zdN, the dataset name coming from the BLKZNAME ioctl on the device
# (what zvol_id does).  Cheap and safe to repeat.
for d in /sys/block/zd*
do
	[ -d "$d" ] || continue
	n=`basename $d`
	case $n in zd*p*) continue ;; esac
	if [ ! -b /dev/$n ] && [ -r $d/dev ]
	then
		mm=`cat $d/dev`
		mknod /dev/$n b `echo $mm | cut -d: -f1` `echo $mm | cut -d: -f2` 2>/dev/null && chmod 660 /dev/$n
	fi
	[ -b /dev/$n ] || continue
	name=`/usr/bin/python3 -c '
import fcntl, os, sys
fd = os.open("/dev/" + sys.argv[1], os.O_RDONLY)
buf = bytearray(256)
fcntl.ioctl(fd, 0x8100127d, buf)
print(bytes(buf).split(b"\0")[0].decode())' $n 2>/dev/null`
	[ -n "$name" ] || continue
	mkdir -p /dev/zvol/`dirname $name`
	[ "`readlink /dev/zvol/$name 2>/dev/null`" = "../../$n" ] || ln -sfn ../../$n /dev/zvol/$name
done
exit 0
