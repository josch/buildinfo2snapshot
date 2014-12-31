#!/usr/bin/python3
#
# Copyright 2014 Johannes Schauer
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

from debian import deb822
import sys
import urllib.request
import json
from datetime import datetime
from collections import defaultdict
import gzip
import io

snapshot_api = "http://snapshot.debian.org/mr/"

# archive can be debian, debian-archive, debian-backports, debian-ports,
# debian-security, debian-volatile
archive = "debian"

suite = "sid"
area = "main"

timestamps = defaultdict(list)

reqpkgs = set()

with open(sys.argv[1]) as f:
    paragraph = list(deb822.Deb822.iter_paragraphs(f, use_apt_pkg=False))
    if len(paragraph) != 1:
        raise Exception("expected only one paragraph")
    paragraph = paragraph[0]
    arch = paragraph['Build-Architecture']
    for pkg in deb822.PkgRelation.parse_relations(paragraph['Build-Environment']):
        if len(pkg) != 1:
            raise Exception("Build-Environment field must not have disjunctions")
        pkg = pkg[0]
        pkgarch = pkg['arch']
        if pkgarch is None:
            pkgarch = arch
        pkgname = pkg['name']
        if len(pkg['version']) != 2:
            raise Exception("version must be a relation/number tuple")
        if pkg['version'][0] != '=':
            raise Exception("relationship must be '='")
        pkgver = pkg['version'][1]
        print(pkgname, pkgver, pkgarch)
        reqpkgs.add((pkgname,pkgver,pkgarch))
        json_data = urllib.request.urlopen("%s/binary/%s/"%(snapshot_api, pkgname))
        if json_data.status != 200:
            raise Exception("returned %d"%json_data.status)
        json_data = json_data.read()
        json_data = json.loads(json_data.decode('utf8'))
        srcver = None
        srcname = None
        for res in json_data['result']:
            if res['binary_version'] == pkgver:
                srcver = res['version']
                srcname = res['source']
                break
        if srcver is None or srcname is None:
            raise Exception("cannot find source version for binary version")
        json_data = urllib.request.urlopen("%s/package/%s/%s/binfiles/%s/%s?fileinfo=1"%(snapshot_api, srcname, srcver, pkgname, pkgver))
        if json_data.status != 200:
            raise Exception("returned %d"%json_data.status)
        json_data = json_data.read()
        json_data = json.loads(json_data.decode('utf8'))
        pkghash = None
        if len(json_data['result']) == 1:
            if json_data['result'][0]['architecture'] != 'all':
                Exception("excepted arch:all")
            pkghash = json_data['result'][0]['hash']
        else:
            for res in json_data['result']:
                if res['architecture'] == pkgarch:
                    pkghash = res['hash']
                    break
        if pkghash is None:
            raise Exception("cannot find architecture")
        first_seen = [ph['first_seen'] for ph in json_data['fileinfo'][pkghash] if ph['archive_name'] == archive]
        if len(first_seen) != 1:
            raise Exception("more than one package with the same hash")
        timestamps[datetime.strptime(first_seen[0], "%Y%m%dT%H%M%SZ")].append((pkgname,pkgver,pkgarch))

newest = sorted(timestamps.keys())[-1]

snapshot_timestamp = datetime.strftime(newest, "%Y%m%dT%H%M%SZ")

# using gz instead of xz in case old snapshots have to be retrieved
snapshot_url = "http://snapshot.debian.org/archive/%s/%s/dists/%s/%s/binary-%s/Packages.gz"%(archive, snapshot_timestamp, suite, area, arch)

pkgdata = urllib.request.urlopen(snapshot_url)
if pkgdata.status != 200:
    raise Exception("returned %d"%pkgdata.status)
pkgdata = io.BytesIO(pkgdata.read())
pkgdata = gzip.GzipFile(fileobj=pkgdata)
for pkg in deb822.Deb822.iter_paragraphs(pkgdata, use_apt_pkg=False):
    pkgname = pkg['Package']
    pkgver = pkg['Version']
    if pkg['Architecture'] == 'all':
        pkgarch = arch
    else:
        pkgarch = pkg['Architecture']
    if (pkgname,pkgver,pkgarch) in reqpkgs:
        reqpkgs.remove((pkgname,pkgver,pkgarch))

if reqpkgs:
    raise Exception("cannot find all package versions in found snapshot: %s"%reqpkgs)

print("architecture = %s"%arch)
print("mirror = http://snapshot.debian.org/archive/%s/%s/"%(archive, snapshot_timestamp))
