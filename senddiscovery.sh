#!/usr/bin/sh
# Runs on a node that is not in the cluster yet (started by iscsiwatchdog.sh).
#
# It announces itself on the discovery etcd (possible/<me>) and waits for the leader's
#   tojoin/<me> = ip=<node ip/prefix>|cip=<cluster ip/prefix>|alias=<alias>|sw=<primary node ip>|br=<branch>|ts=<epoch>
# (ip and alias only when the user supplied them). When it arrives the node
#   1. writes /root/newipaddr, /root/newcaddr, /root/newalias (docker_setup applies and deletes them),
#   2. acknowledges with ackjoin/<me> = <ts>, deletes tojoin/<me> and possible/<me> from the discovery
#      etcd (it leaves the discovery list; only the acknowledge stays),
#   3. pulls the primary's branch (joinpull.sh) and restarts through docker_setup.sh reboot.
# Every time it announces itself again, it first deletes its own old acknowledge: a node that is
# announcing is alive for joining, so the acknowledge no longer holds.
#
# The whole script is one block so sh has parsed it completely before it runs: the pull below
# replaces /pace and /TopStor, this file included.
{
# everything this script says goes to a log (it is started in the background, nothing else shows it)
exec >> /root/senddiscovery.log 2>&1
cd /pace
disc=10.11.11.253
myhost=`hostname`
myhostip=`docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip`
while true
do
	/pace/etcddel.py $disc ackjoin/$myhost >/dev/null
	/pace/etcdput.py $disc possible/$myhost $myhostip
	joinline=`/pace/etcdget.py $disc tojoin/$myhost`
	echo $joinline | grep 'cip=' >/dev/null
	if [ $? -eq 0 ];
	then
		break
	fi
	echo ./etcdput.py $disc possible/$myhost $myhostip
	sleep 3
done
joinfield() {
	echo "$joinline" | tr '|' '\n' | grep "^$1=" | head -1 | cut -d= -f2-
}
newip=`joinfield ip`
newcip=`joinfield cip`
newalias=`joinfield alias`
swip=`joinfield sw`
swbranch=`joinfield br`
joints=`joinfield ts`
echo will join the cluster: ip=$newip cip=$newcip alias=$newalias sw=$swip br=$swbranch ts=$joints

# acknowledge first, and confirm it actually landed: etcdput.py swallows unreachable-etcd errors
# (it always "succeeds" even when the put never happened), so the only proof is reading it back.
# /root/nodeconfigured must not be written until this is confirmed: iscsiwatchdog.sh only starts
# this script when that file does not already say yes, so writing it on an unconfirmed ack would
# strand the node here forever with no acknowledgment ever sent and nothing left to retry it.
acked=0
for attempt in 1 2 3 4 5
do
	/pace/etcdput.py $disc ackjoin/$myhost $joints >/dev/null
	if [ "`/pace/etcdget.py $disc ackjoin/$myhost`" = "$joints" ];
	then
		acked=1
		break
	fi
	echo ackjoin not confirmed yet, retrying attempt $attempt
	sleep 2
done
if [ $acked -ne 1 ];
then
	echo could not confirm ackjoin after retries, giving up without marking this node configured
	exit 1
fi

echo yes_fromsenddtarget > /root/nodeconfigured
rm -f /root/newipaddr /root/newalias
[ -n "$newip" ] && echo $newip > /root/newipaddr
echo $newcip > /root/newcaddr
[ -n "$newalias" ] && echo $newalias > /root/newalias

# the files are in place and the ack is confirmed. The node leaves the discovery list; only the ack stays.
/pace/etcddel.py $disc tojoin/$myhost >/dev/null
/pace/etcddel.py $disc possible/$myhost >/dev/null

# pull the primary's branch and commit before restarting, so this node joins on the same software
echo $swip | grep '\.' >/dev/null
if [ $? -eq 0 ] && [ ${#swbranch} -gt 3 ];
then
	cp /TopStor/joinpull.sh /root/joinpull.run
	sh /root/joinpull.run $swip $swbranch
	rm -f /root/joinpull.run
else
	echo no software to pull from the primary .... joining with the local software
fi
cd /pace
# restart through docker_setup.sh in its own session, detached from this script: resetdocker.sh starts
# with `pkill send`, which kills this very script, and a restart must not die with its parent
setsid nohup /TopStor/docker_setup.sh reboot >> /root/senddiscovery.log 2>&1 < /dev/null &
disown 2>/dev/null
exit
}
