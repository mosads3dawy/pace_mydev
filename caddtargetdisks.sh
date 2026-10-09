#!/usr/bin/bash
# diskserial <device name>: a serial for the LIO backstore that depends on the DISK only, so the same shared disk
# has the same SCSI id (naa.6001405<serial>) whichever node exports it -- as a real shared disk has one WWN.
# With LIO's default (a random serial per backstore) a pool lost all its disks' names when another node took the
# disks over.  For a loop device the identity is its backing file; otherwise the device name.
diskserial() {
	ident=`losetup -n -O BACK-FILE /dev/$1 2>/dev/null | tr -d ' '`
	[ -z "$ident" ] && ident=$1
	echo -n "$ident" | md5sum | sed 's/^\(........\)\(....\)\(....\)\(....\)\(............\).*/\1-\2-\3-\4-\5/'
}
# setproduct <backstore name>: the SCSI product id the initiators see (lsscsi model column) is "<disk>-<host>", and
# every reader takes the host from it.  LIO's default cuts the name to 15 characters, so "loop1-dhcp328043" lost the
# last digit of the host name and the disks belonged to a host that does not exist.  The field holds 16, and it can
# only be written before the backstore is exported -- so right after it is created.  (loop10 and up: see below.)
setproduct() {
	pid=$1
	# loop10 and up: "loop10-<host>" is 17 characters and does not fit; the readers only take what follows the first "-" (the host),
	# so "l10-<host>" (14 characters) is used as the product id there; the backstore keeps its full name
	[ ${#pid} -gt 16 ] && pid=`echo "$pid" | sed 's/^loop\([0-9][0-9]*\)-/l\1-/'`
	if [ ${#pid} -le 16 ]; then
		for pf in /sys/kernel/config/target/core/*/$1/wwn/product_id; do
			[ -w "$pf" ] && echo -n "$pid" > "$pf" 2>/dev/null
		done
	else
		echo "setproduct: $pid is longer than 16 characters, the host name in it will be cut"
	fi
}
######################
#exit
##########################
stamp=`date +%s`
echo $@ > /root/addtargets
bootpart=`lsblk -o NAME,MOUNTPOINT | grep boot | awk '{print $1}'`
bootdisk='sd' 
echo bootdisk is $bootdisk
cd /pace
etcdip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
actives=`/pace/etcdget.py $etcdip Active --prefix`
change=0
#echo hi1 $myhost>> /root/targetadd
#declare -a iscsitargets=(`cat /pacedata/iscsitargets | awk '{print $2}' `);
initialt=$(targetcli ls)
echo hhhhhhhhhhhhhhhhhhh
initialtarget=`echo $initialt | wc -l`
myip=`docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip`
mycluster=`nmcli conn show mycluster | grep ipv4.addresses | awk '{print $2}' | awk -F'/' '{print $1}'`
declare -a iscsitargets=(`docker exec etcdclient /pace/iscsiclients.py $etcdip | grep target | awk -F'/' '{print $2}'`);
#currentdisks=$(echo "$initialt" | awk '/o- iscsi/{flag=1} flag; /o- loopback/{flag=0}')
currentdisks=$(echo "$initialt" | awk '/iscsi/{flag=1} flag; /loopback/{flag=0}')
#currentdisks=`targetcli ls /iscsi`
lsblk=$(lsblk -n -o name,serial,vendor)
disks=(`echo "$lsblk" | grep -v $bootdisk | grep -v sr0 |  grep -v LIO | awk '{print $1}'`)
# container flavour: /root/loopdisks lists the only disks this node may export (the nodes of several clusters share
# the host's loop devices).  No file = every disk, as before.
[ -f /TopStor/flavor.sh ] && . /TopStor/flavor.sh
if [ -s /root/loopdisks ] && is_container 2>/dev/null; then
	alloweddisks=(`cat /root/loopdisks`)
	keep=()
	for d in "${disks[@]}"; do
		for a in "${alloweddisks[@]}"; do [ "$d" = "$a" ] && keep+=($d); done
	done
	disks=("${keep[@]}")
fi
nodes=(`docker exec etcdclient /TopStor/etcdgetlocal.py Active --prefix | awk -F'Partners/' '{print $2}' | awk -F"'" '{print $1}'`)
diskids=`echo "$lsblk" | grep -v $bootdisk | grep -v sr0 | grep -v LIO | awk '{print $1" "$2}'`
mappedhosts=`echo "$currentdisks" | grep Mapped`;
blocks=$(echo "$initialt" | awk '/^  \| o- block /{flag=1} flag; /^  \| o- fileio /{flag=0}')
targets=`echo "$blocks" | grep -v deactivated |  grep dev | awk -F'[' '{print $2}' | awk '{print $1}'`
#blocks=`targetcli ls backstores/block `
# filter the new iscsi disks that were not part of the backstore , then create them if needed
flag=0
for ddisk in  "${disks[@]}"; do
	echo ddisk $ddisk
	echo the disk $ddisk not a part in the targets
	ordinary=${ddisk}$myhost
	#scsidisk=`ls -l /dev/disk/by-id/ | grep -w $ddisk | grep -v part | grep scsi | grep -v LIO | grep -v SLS | awk '{print $9}'`
	scsidisk='scsi-'$ordinary
	ln -s /dev/$ddisk /dev/disk/by-id/$scsidisk 2> /dev/null
	echo scsidisk=$scsidisk, ordinary=$ordinary
	echo targetcli backstores/block create ${ddisk}-${myhost} /dev/$ddisk
	targetcli backstores/block create name=${ddisk}-${myhost} dev=/dev/$ddisk wwn=`diskserial $ddisk`
	setproduct ${ddisk}-${myhost}
	if [ $? -ne 0 ];
	then
		echo the disk $ddisk is a part in the targets backstore
	else
		flag=1
	fi
done
declare -a newdisks=();
# check and create the t1 entry of myhost
if [ $flag -eq 1 ];
then
	initialt=`targetcli ls`
	blocks=$(echo "$initialt" | awk '/^  \| o- block /{flag=1} flag; /^  \| o- fileio /{flag=0}')
	targets=$(echo "$blocks" | grep -v deactivated |  grep dev | awk -F'[' '{print $2}' | awk '{print $1}')
	currentdisks=$(echo "$initialt" | awk '/iscsi/{flag=1} flag; /loopback/{flag=0}')
	flag=0
fi
echo ii$currentdisks | grep $myhost:t1 >/dev/null
if [ $? -ne 0 ];
then
 targetcli iscsi/ create iqn.2016-03.com.$myhost:t1
 flag=1
else
	echo t1 entry is already created for $myhost
fi
if [ $flag -eq 1 ];
then
	initialt=`targetcli ls`
	blocks=$(echo "$initialt" | awk '/^  \| o- block /{flag=1} flag; /^  \| o- fileio /{flag=0}')
	targets=$(echo "$blocks" | grep -v deactivated |  grep dev | awk -F'[' '{print $2}' | awk '{print $1}')
	currentdisks=$(echo "$initialt" | awk '/iscsi/{flag=1} flag; /loopback/{flag=0}')
	flag=0
fi
#tpgs1=(`targetcli ls /iscsi | grep iqn`) 
# check if my ip was changed so I have a wrong tpg1, of it my tpg was not created before. so I create the write tpg 
echo "$currentdisks" | grep $myip:3266 &>/dev/null
if [ $? -ne 0 ]; then
 targetcli iscsi/iqn.2016-03.com.${myhost}:t1/tpg1/portals delete 0.0.0.0 3260
 targetcli iscsi/iqn.2016-03.com.${myhost}:t1/tpg1/portals ls | grep 3266 | awk -F'o-' '{print $2}' | awk -F':' '{print $1}'
 oldip=`targetcli iscsi/iqn.2016-03.com.${myhost}:t1/tpg1/portals ls | grep 3266 | awk -F'o-' '{print $2}' | awk -F':' '{print $1}'`
 targetcli iscsi/iqn.2016-03.com.${myhost}:t1/tpg1/portals delete $oldip 3260
 echo oldip=$oldip
 #targetcli iscsi/iqn.2016-03.com.${myhost}:t1/tpg1/portals delete$olidp 3266
 targetcli iscsi/iqn.2016-03.com.$myhost:t1/tpg1/portals create $myip 3266
 flag=1
else
  echo my tpg1 portal is already created
fi
if [ $flag -eq 1 ];
then
	initialt=`targetcli ls`
	blocks=$(echo "$initialt" | awk '/^  \| o- block /{flag=1} flag; /^  \| o- fileio /{flag=0}')
	targets=$(echo "$blocks" | grep -v deactivated |  grep dev | awk -F'[' '{print $2}' | awk '{print $1}')
	currentdisks=$(echo "$initialt" | awk '/iscsi/{flag=1} flag; /loopback/{flag=0}')
	flag=0
fi
targetcli /iscsi/iqn.2016-03.com.${myhost}:t1 set global auto_add_mapped_luns=true
i=0;
# check if there is a new disk to create it as devdisk-myhsot in the backstore block
diskids=$(ls /dev/disk/by-id/)
for ddisk in "${disks[@]}"; do
 devdisk=$ddisk 
 idisk=`echo "$diskids" | grep $ddisk`
 echo $currentdisks | grep $devdisk-$myhost &>/dev/null
 if [ $? -ne 0 ]; then
  pdisk=$idisk
  targetcli backstores/block create name=${devdisk}-${myhost} dev=/dev/disk/by-id/$pdisk wwn=`diskserial $devdisk`
  setproduct ${devdisk}-${myhost}
  flag=1
 else
  echo $devdisk-$myhost is already created in the backstores/block 
 fi
done;
if [ $flag -eq 1 ];
then
	initialt=`targetcli ls`
	blocks=$(echo "$initialt" | awk '/^  \| o- block /{flag=1} flag; /^  \| o- fileio /{flag=0}')
	targets=$(echo "$blocks" | grep -v deactivated |  grep dev | awk -F'[' '{print $2}' | awk '{print $1}')
	currentdisks=$(echo "$initialt" | awk '/iscsi/{flag=1} flag; /loopback/{flag=0}')
	flag=0
fi

targetcli /iscsi/iqn.2016-03.com.${myhost}:t1 set global auto_add_mapped_luns=true

tpgs1=`echo "$currentdisks" | grep iqn | grep TPG | grep :t1`
#tpgs1=(`targetcli ls /iscsi | grep iqn | grep TPG | grep ':t1'`)
# only MY target: with several clusters in one kernel (containers) the LIO config also holds other nodes' targets
tpgs=`echo "$currentdisks" | grep iqn | grep TPG | grep "com.${myhost}:t1" | awk -F'iqn' '{print $2}' | awk '{print $1}'`
# mapping the luns to every iqn in the tpgs create the missing ones and create also the 
for node in "${nodes[@]}"; do
 for ddisk in "${disks[@]}"; do
	for iqn in "${tpgs[@]}"; do

 		echo "$currentdisks" |  awk -v iqn="iqn$iqn" '$0 ~ iqn {flag=1} flag; /o- portals/{flag=0}'  | grep redhat:$node >/dev/null
		if [ $? -ne 0 ];
		then
  			targetcli iscsi/iqn${iqn}/tpg1/acls/ create iqn.1994-05.com.redhat:$node
		 	echo An tpg1/acl is create for the node $node
		else
		 	echo the node $node already has an acl entry the tpgs 
		fi
		
 		devdisk=`echo $ddisk | awk '{print $1}'`
 		echo "$currentdisks" |  awk -v iqn="iqn$iqn" '$0 ~ iqn {flag=1} flag; /o- portals/{flag=0}' | awk -v iqn="o- luns" '$0 ~ iqn {flag=1} flag; /o- portals/{flag=0}' | grep  ${devdisk}-${myhost}  >/dev/null
		if [ $? -eq 0 ];
		then
			echo iqn$iqn already has a map for $devdisk-$myhost
		else
			echo iqn$iqn is not mapped to  $devdisk
   			targetcli iscsi/iqn${iqn}/tpg1/luns/ create /backstores/block/${devdisk}-${myhost}  
		fi
	done
 done
done
#######check if one of the hosts is new and was not mapped before
#echo hi8 >> /root/targetadd
targetcli /iscsi/iqn.2016-03.com.${myhost}:t1 set global auto_add_mapped_luns=false

#echo hi9 >> /root/targetadd
#targetcli saveconfig
#exit
#endingtarget=`targetcli ls | wc -l`
#if [[ $initialtarget != $endingtarget ]];
#then
stamp2=`date +%s`
echo endtime=$((stamp2-stamp))
#fi
