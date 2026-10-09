#!/usr/bin/bash

leader=`echo $@ | awk '{print $3}'`
leaderip=`echo $@ | awk '{print $1}'`
myhost=`echo $@ | awk '{print $2}'`
myhostip=`echo $@ | awk '{print $4}'`
diskref() {
cd /pace
/pace/cdiskref.sh $leader $leaderip $myhost $myhostip 
}

while true 
do
 echo another round
 diskref 
 sleep 5 
done

