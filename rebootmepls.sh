#!/bin/sh
cd /pace/
export ETCDCTL_API=3
leaderip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
myhostip=`docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip`
leader=`docker exec etcdclient /TopStor/etcdgetlocal.py leader`
configuredlocal='S'
isrebootlocal='S'
echo $myhost | grep $leader
if [ $? -ne 0 ];
then
	isrebootlocal='S'`/pace/etcdget.py $myhostip rebootme/$myhost`
 	configuredlocal='S'`/pace/etcdget.py $myhostip configured/$myhost`
fi
isreboot=`/pace/etcdget.py $leaderip rebootme/$myhost`$isrebootlocal

echo S$isreboot | grep pls
if [ $? -eq 0 ];
then
 		configured=`/pace/etcdget.py $leaderip configured/$myhost`$configuredlocal
		echo S$configured  | egrep 'yes|reset'
		if [ $? -ne 0 ];
		then
			# QSD5.312: a missing configured/<me> record (not yet written/synced on the leader, or unreadable) is not
			# "never configured": a node that already joined (nodeconfigured says yes) must keep its configuration,
			# or the reboot wipes /TopStordata and the node comes back as its own primary (test 10 round 17).
			echo S`cat /root/nodeconfigured 2>/dev/null` | grep '^Syes'
			if [ $? -eq 0 ];
			then
				configured='yes'
			else
				rm -rf /TopStordata/*
				configured='no'
			fi
		fi
 		echo ${configured}_$isreboot > /root/nodeconfigured
 		./etcdput.py $leaderip rebootme/$myhost donot 

		echo $myhost | grep $leader
		if [ $? -ne 0 ];
		then
 			./etcdput.py $myhostip rebootme/$myhost donot 
		fi
 		#/TopStor/resetdocker.sh
 		#reboot
		/TopStor/docker_setup.sh reboot & disown 
	else
		echo $isreboot ____ no reboot
fi
#/sbin/reboot
