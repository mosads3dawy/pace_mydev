#!/usr/bin/python3
# Safety helpers for the automatic handling of a faulty disk in a pool (selectspare.py solvedegradedraid, P-DEVELOPMENT note 116).
# Pure parsing / decision code (no etcd, no zpool calls) so it can be checked offline; the caller collects the command outputs.
#
# Rules (QC test 22 validator 643d: the old lookup fell back to the LAST guid of the config, the healthy leg, and replaced it
# with a dm "zero" stub; ZFS then detached the healthy leg and wiped its labels):
#  * the faulty vdev is found by the disk's identity (path, devid, phys_path, the "was" path of zpool status), never by position;
#    no unique match = no action;
#  * a vdev is touched only when zpool status shows it UNAVAIL/FAULTED/REMOVED/OFFLINE and at least one OTHER real
#    (not a dm zero stub) leaf of the same parent vdev is ONLINE;
#  * an ONLINE leaf is never replaced, offlined or detached.
import re

BADSTATES = ('UNAVAIL', 'FAULTED', 'REMOVED', 'OFFLINE')
VDEVSTATES = ('ONLINE', 'DEGRADED', 'FAULTED', 'OFFLINE', 'UNAVAIL', 'REMOVED', 'AVAIL', 'INUSE', 'SPLIT', 'SUSPENDED')


def normid(s):
    # '/dev/sdg1', 'sdg', "'/dev/disk/by-id/scsi-3600..-part1'", 'scsi-3600..' -> one comparable name
    s = str(s).strip().strip("'\"").strip()
    if not s:
        return ''
    s = s.split('/')[-1]
    s = re.sub(r'-part[0-9]+$', '', s)
    m = re.match(r'^((?:sd|vd|xvd|hd)[a-z]+)[0-9]+$', s)
    if m:
        s = m.group(1)
    m = re.match(r'^((?:nvme[0-9]+n[0-9]+)|(?:mmcblk[0-9]+))p[0-9]+$', s)
    if m:
        s = m.group(1)
    return s


def parse_zdb_leaves(text):
    # zdb -C / zdb -e -C output -> {guid: set(identities)} for the leaf vdevs (type disk/file)
    leaves = {}
    cur = None
    for raw in str(text).split('\n'):
        line = raw.strip()
        if ':' not in line:
            continue
        key, val = line.split(':', 1)
        key = key.strip()
        val = val.strip().strip("'\"")
        if key == 'type':
            cur = {'type': val, 'guid': None, 'ids': set()}
        elif key == 'guid' and cur is not None and cur['guid'] is None:
            cur['guid'] = val
            if cur['type'] in ('disk', 'file'):
                leaves[val] = cur['ids']
        elif key in ('path', 'devid', 'phys_path') and cur is not None and cur['guid'] is not None and val:
            cur['ids'].add(val)
    return leaves


def parse_status(text):
    # zpool status [-g] [-P] <pool> -> list of nodes {depth, name, state, extra} of the config block (pool line = depth 0;
    # section lines logs/cache/spares/special/dedup have state None)
    nodes = []
    started = False
    for raw in str(text).split('\n'):
        if not started:
            if raw.strip().startswith('NAME') and 'STATE' in raw:
                started = True
            continue
        if raw.strip() == '' or raw.strip().startswith('errors:'):
            if nodes:
                break
            continue
        line = raw[1:] if raw.startswith('\t') else raw
        lead = len(line) - len(line.lstrip(' '))
        fields = line.split()
        state = fields[1] if len(fields) > 1 and fields[1] in VDEVSTATES else None
        extra = ''
        if ' was ' in line:
            extra = line.split(' was ', 1)[1].strip()
        nodes.append({'depth': lead // 2, 'name': fields[0], 'state': state, 'extra': extra})
    return nodes


def isleaf(nodes, i):
    return nodes[i]['state'] is not None and (i + 1 >= len(nodes) or nodes[i + 1]['depth'] <= nodes[i]['depth'])


def parentindex(nodes, i):
    for j in range(i - 1, -1, -1):
        if nodes[j]['depth'] < nodes[i]['depth']:
            return j
    return None


def children(nodes, p):
    out = []
    for j in range(p + 1, len(nodes)):
        if nodes[j]['depth'] <= nodes[p]['depth']:
            break
        if nodes[j]['depth'] == nodes[p]['depth'] + 1:
            out.append(j)
    return out


def descendants(nodes, p):
    out = []
    for j in range(p + 1, len(nodes)):
        if nodes[j]['depth'] <= nodes[p]['depth']:
            break
        out.append(j)
    return out


def guidpaths(gnodes, pnodes):
    # zpool status -gP and zpool status -P list the same tree in the same order: pair them -> {guid: set(paths)}
    out = {}
    if len(gnodes) != len(pnodes):
        return out
    for g, p in zip(gnodes, pnodes):
        if g['depth'] != p['depth']:
            return {}
        ids = out.setdefault(g['name'], set())
        if p['name'] != g['name']:
            ids.add(p['name'])
        if g['extra']:
            ids.add(g['extra'])
        if p['extra']:
            ids.add(p['extra'])
    return out


def isreal(paths, zerodms):
    # a leaf is "real" when one of its known paths is a device that is not a dm zero stub.  A dm device is real only when
    # zerodms (normalized names of the dm zero devices) could be read (zerodms is None = unknown: every dm counts as a stub).
    if not paths:
        return False
    for p in paths:
        n = normid(p)
        if not n:
            continue
        isdm = n.startswith('dm-') or '/dev/mapper/' in p or n.startswith('dm-name-')
        if isdm:
            if zerodms is None:
                continue
            if n in zerodms or n.replace('dm-name-', '') in zerodms:
                continue
        return True
    return False


def plan(diskname, zdbtext, gstatus, pstatus, zerodms=None, needparent=True):
    # Decide what may be done to the faulty disk <diskname>.  Returns (action, guid, reason); action is
    #   'none'    : do nothing (no unique match, target ONLINE/healthy, no other ONLINE real leg, unknown state ...)
    #   'offline' : zpool offline <pool> <guid>     (target FAULTED or REMOVED)
    #   'keep'    : target already UNAVAIL/OFFLINE: nothing to do, the leg stays and can resilver when it comes back
    # needparent=False (stripe raid): only the identity and the not-ONLINE state are checked, action is 'detach'.
    want = normid(diskname)
    if not want:
        return ('none', None, 'empty disk name')
    gnodes = parse_status(gstatus)
    pnodes = parse_status(pstatus)
    if len(gnodes) == 0:
        return ('none', None, 'zpool status -gP gave no config')
    ids = {}
    for g, s in parse_zdb_leaves(zdbtext).items():
        ids.setdefault(g, set()).update(s)
    for g, s in guidpaths(gnodes, pnodes).items():
        ids.setdefault(g, set()).update(s)
    leafguids = set(gnodes[i]['name'] for i in range(len(gnodes)) if i > 0 and isleaf(gnodes, i))
    matches = set()
    for g in leafguids:
        if str(diskname).strip() == g:
            matches.add(g)
            continue
        for x in ids.get(g, ()):
            if normid(x) == want:
                matches.add(g)
                break
    if len(matches) != 1:
        return ('none', None, 'no unique vdev for '+str(diskname)+': '+str(sorted(matches)))
    guid = matches.pop()
    idx = [i for i in range(1, len(gnodes)) if gnodes[i]['name'] == guid]
    if len(idx) != 1:
        return ('none', guid, 'guid not found once in zpool status -gP')
    i = idx[0]
    state = gnodes[i]['state']
    if state not in BADSTATES:
        return ('none', guid, 'target '+guid+' is '+str(state)+': never touched')
    if not needparent:
        return ('detach', guid, 'stripe target '+guid+' is '+state)
    p = parentindex(gnodes, i)
    if p is None or p == 0 or gnodes[p]['state'] is None:
        return ('none', guid, 'target '+guid+' is not inside a redundant vdev')
    good = []
    for c in children(gnodes, p):
        if c == i:
            continue
        cand = [c] if isleaf(gnodes, c) else [d for d in descendants(gnodes, c) if isleaf(gnodes, d)]
        for d in cand:
            if gnodes[d]['state'] == 'ONLINE' and isreal(ids.get(gnodes[d]['name'], set()), zerodms):
                good.append(gnodes[d]['name'])
    if not good:
        return ('none', guid, 'no other ONLINE real leg next to '+guid)
    if state in ('UNAVAIL', 'OFFLINE'):
        return ('keep', guid, 'target '+guid+' already '+state+', other ONLINE leg(s) '+str(good))
    return ('offline', guid, 'target '+guid+' '+state+', other ONLINE leg(s) '+str(good))
