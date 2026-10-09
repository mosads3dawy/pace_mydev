#!/usr/bin/bash
# needed the operands to be like : one:two:three:four
#
echo $@ > /root/diskref
flag=1
#while [ $flag -eq 1 ];
#do
#	if pidof -x "`basename $0`" -o $$ >/dev/null; then
#    		echo "Process already running"
#		sleep 2
#	else
#		flag=0
#	fi
#done
leader=`echo $@ | awk '{print $1}'`
leaderip=`echo $@ | awk '{print $2}'`
myhost=`echo $@ | awk '{print $3}'`
myhostip=`echo $@ | awk '{print $4}'`
echo $leader | grep $myhost
if [ $? -eq 0 ];
then
	etcdip=$leaderip
else
	etcdip=$myhostip
fi
#/pace/iscsirefresh.sh $etcdip $myhost
/pace/caddtargetdisks.sh $etcdip $myhost
/pace/iscsirefresh.sh $etcdip $myhost
#stamp=`date +%s`
#/pace/etcdput.py $leaderip sync/dirty/____/request  dirty_$stamp
