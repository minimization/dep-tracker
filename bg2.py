#!/usr/bin/python3

import sys
import argparse
import copy
import dnf
import dnf.cli
import dnf.exceptions
import dnf.rpm.transaction
import dnf.yum.rpmtrans
import json
import libdnf.repo
import logging
import os
import re
import requests
import rpm
import shutil
import tempfile
import urllib
from multiprocessing import Pool
from pathlib import Path
import psutil

# Arguments
parser = argparse.ArgumentParser()
parser.add_argument('-f', '--file', default='./package-list.txt', help="List of package NVRs")
parser.add_argument('-r', '--repo', default='eln', help="What repo are we using",
        choices=["rawhide", "eln", "c9s"])
parser.add_argument('-w', '--workdir', default=os.getcwd()+"/", help="Where we are doing the work")
parser.add_argument("-v", "--verbose", help="Enable debug logging", action='store_true')
args = parser.parse_args()
repoName = args.repo
repoBase = args.repo
if repoBase == "rawhide":
    BestEVRVAR = "fc\d\d"
    kojiStyle = "koji"
    coreAppend = "fedora-release"
    baseURL = "https://kojipkgs.fedoraproject.org//packages"
    placeholderURL="https://tiny.distro.builders/view-placeholder-srpm-details--view-eln--"
elif repoBase == "eln":
    BestEVRVAR = "eln\d\d\d"
    kojiStyle = "koji"
    coreAppend = "fedora-release-eln"
    baseURL = "https://kojipkgs.fedoraproject.org//packages"
    placeholderURL="https://tiny.distro.builders/view-placeholder-srpm-details--view-eln--"
else:
    BestEVRVAR = "el9"
    kojiStyle = "stream"
    coreAppend = "redhat-release"
    baseURL = "https://kojihub.stream.rdu2.redhat.com/kojifiles/packages"
    placeholderURL="http://dell-per930-01.4a2m.lab.eng.bos.redhat.com/content-resolver/view-placeholder-srpm-details--view-c9s--"
if args.verbose:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.WARNING)


# Configuration
pool_num = 10
workDir = args.workdir
repoConfDir = workDir + "repos/"
cacheDir = workDir + "cache/" + kojiStyle
Path(cacheDir).mkdir(parents=True, exist_ok=True)
dataDir = workDir + "data/" + repoBase + "/"
Path(dataDir + "output/").mkdir(parents=True, exist_ok=True)
installroot = "/installroot"

# Lists
full_archList = ["noarch", "aarch64", "ppc64le", "s390x", "x86_64"]
archList = ["aarch64", "ppc64le", "s390x", "x86_64"]
coreBuildRoot = ['bash', 'bzip2', 'coreutils', 'cpio', 'diffutils', 'findutils', 'gawk', 'glibc-minimal-langpack', 'grep', 'gzip', 'info', 'make', 'patch', 'redhat-rpm-config', 'rpm-build', 'sed', 'shadow-utils', 'tar', 'unzip', 'util-linux', 'which', 'xz']
coreBuildRootBinaries = []
coreBuildRootSourceName = []
coreBuildRootSourceNVR = []
listSources = []
listSourceNVRCached = []
listSourceNVRNeedCache = []
listSourcesDone = []
listSourcesQueue = []
placeholderBinaries = []
placeholderSources = []

# DNF Bases
def get_base(this_arch):
    logging.info("  Setup dnf base: " + this_arch)
    this_base = dnf.Base()
    this_base.conf.read(repoConfDir + repoName + "." + this_arch + ".repo")
    this_base.conf.installroot = installroot
    this_base.conf.arch = this_arch
    this_base.conf.install_weak_deps = False
    this_base.read_all_repos()
    this_base.fill_sack(load_system_repo=False)
    return this_base

def process_core_buildroot():
    print("Working on Core Buildroot:")
    if os.path.exists(workDir + "corebuildroot.txt"):
        this_coreBuildRoot = open(workDir + "corebuildroot.txt").read().splitlines()
    else:
        this_coreBuildRoot=coreBuildRoot
    this_coreBuildRoot.append(coreAppend)
    for arch in archList:
        base = get_base(arch)
        logging.debug("  " + arch + ": Populating Core Buildroot")
        for this_binary in this_coreBuildRoot:
            try:
                base.install(this_binary)
            except dnf.exceptions.MarkingError:
                logging.info('    Cannot Install: ' + this_binary)
        ## Resolve the coreBuildRoot
        try:
            base.resolve()
            query = base.sack.query().filterm(pkg=base.transaction.install_set)
            # new_binary_pkg_relations = _analyze_package_relations(query)
            for pkg in query:
                if not pkg.name in coreBuildRootBinaries:
                    coreBuildRootBinaries.append(pkg.name)
                sourcenvr = pkg.sourcerpm.rsplit(".",2)[0]
                sourcename = sourcenvr.rsplit("-",2)[0]
                if not sourcename in coreBuildRootSourceName:
                    coreBuildRootSourceName.append(sourcename)
                    if not sourcenvr in listSourcesQueue:
                        listSourcesQueue.append(sourcenvr)
                    if not pkg in listSourceNVRCached and not pkg in listSourceNVRNeedCache:
                        listSourceNVRNeedCache.append(sourcenvr)
                    if not sourcenvr in coreBuildRootSourceNVR:
                        coreBuildRootSourceNVR.append(sourcenvr)
            # logging.debug(json.dumps(new_binary_pkg_relations, indent=2, sort_keys=True))
        except dnf.exceptions.DepsolveError as e:
            logging.info("Core BuildRoot Resolution Error")
            logging.info(e)
        base.close()
    coreBuildRootSourceName.sort()
    coreBuildRootSourceNVR.sort()
    # Write these out to a file
    with open(dataDir+'CoreBuildRootSourceNames', 'w') as f:
        for item in coreBuildRootSourceName:
            f.write("%s\n" % item)
    with open(dataDir+'CoreBuildRootSourceNVRs', 'w') as f:
        for item in coreBuildRootSourceNVR:
            f.write("%s\n" % item)
    return coreBuildRootSourceNVR

def process_placeholders():
    ## BEGIN: placeholder work
    print("Working on Placeholders:")
    for arch in archList:
        placeholderJsonData = {}
        placeholderJsonData = json.loads(requests.get(placeholderURL + arch + ".json", allow_redirects=True).text)
        for placeholder_source in placeholderJsonData:
            print(arch + ": Placeholder: " + placeholder_source)
            if not placeholder_source in placeholderSources:
                placeholderSources.append(placeholder_source)
            thisBinaryList = []
            thisSourceList = []
            thisSourceNVRList = []
            base = get_base(arch)
            open(outputDir + "output/" + placeholder_source + "-deps-source", "w").close()
            for this_binary in placeholderJsonData[placeholder_source]['build_requires']:
                if not this_binary in coreBuildRootBinaries and not this_binary in thisBinaryList:
                    thisBinaryList.append(this_binary)
                try:
                    base.install(this_binary)
                except dnf.exceptions.MarkingError:
                    print(arch + ": Placeholder:  Cannot Install: " + this_binary)
            try:
                base.resolve()
                query = base.sack.query().filterm(pkg=base.transaction.install_set)
                # Save package dependency data
                # new_binary_pkg_relations = _analyze_package_relations(query)
                # _update_package_relations_dict(new_binary_pkg_relations, binary_pkg_relations)
                for pkg in query:
                    # Deal with binaries 
                    if not pkg.name in coreBuildRootBinaries and not pkg.name in thisBinaryList:
                        thisBinaryList.append(pkg.name)
                    # Deal with sources 
                    sourcenvr = pkg.sourcerpm.rsplit(".",2)[0]
                    sourcename = sourcenvr.rsplit("-",2)[0]
                    if not sourcename in coreBuildRootSourceName and not sourcename in placeholderSources:
                        if not pkg.source_name in thisSourceList :
                            thisSourceList.append(pkg.source_name)
                            if not sourcenvr in listSourcesDone:
                                listSourcesDone.append(sourcenvr)
                                if not sourcenvr in listSourcesQueue:
                                    listSourcesQueue.append(sourcenvr)
                                if not pkg in listSourceNVRCached and not pkg in listSourceNVRNeedCache:
                                    listSourceNVRNeedCache.append(sourcenvr)
                            if not sourcenvr in thisSourceEVR:
                                thisSourceEVR.append(sourcenvr)
                    ## Put source on the SourceQueue
                    if not pkg.source_name in listSources:
                        listSources.append(pkg.source_name)
                        with open(outputDir + "BuildRootSourcesNVR", "a+") as fileBuildRootSourcesNVR:
                            fileBuildRootSourcesNVR.write("%s\n" % (pkg.sourcerpm))
                    if not pkg.source_name in listSourcesQueue:
                        listSourcesQueue.append(pkg.source_name)
            except dnf.exceptions.DepsolveError as e:
                print(arch + ": Placeholder Resolution Error")
                print(e)
            # Write the things out to a file
            with open(dataDir+'/output/'+placeholder_source+'-deps-'+arch+'-binary', 'w') as f:
                for item in thisBinaryList:
                    f.write("%s\n" % item)
            with open(outputDir + "output/" + placeholder_source + "-deps-source", "a+") as fileSourceDeps:
                for src in thisSourceList:
                    fileSourceDeps.write("%s\n" % (src))
    ## END: placeholder work

def process_package(this_nvr):
    # Get our package name,version and release
    pkg_name = this_nvr.rsplit("-",2)[0]
    pkg_version = this_nvr.rsplit("-",2)[1]
    pkg_release = this_nvr.rsplit("-",2)[2]
    # Process out package, one arch at a time.
    for arch in archList:
        file_dir = cacheDir+"/"+pkg_name+"/"+pkg_version+"/"+pkg_release+"/"+arch
        pkg_deps = parse_root_log(file_dir)
        thisBinaryList = []
        thisSourceList = []
        thisSourceEVR = []
        base = get_base(arch)
        for this_binary in pkg_deps:
            try:
                base.install(this_binary)
            except dnf.exceptions.MarkingError:
                logging.info('    Cannot Install: ' + this_binary + ' for: ' + this_nvr)
        ## Resolve the coreBuildRoot
        try:
            base.resolve()
            query = base.sack.query().filterm(pkg=base.transaction.install_set)
            # new_binary_pkg_relations = _analyze_package_relations(query)
            for pkg in query:
                # Deal with binaries 
                if not pkg.name in coreBuildRootBinaries and not pkg.name in thisBinaryList:
                    thisBinaryList.append(pkg.name)
                # Deal with sources 
                sourcenvr = pkg.sourcerpm.rsplit(".",2)[0]
                sourcename = sourcenvr.rsplit("-",2)[0]
                if not sourcename in coreBuildRootSourceName and not sourcename in placeholderSources:
                    if not sourcename in thisSourceList:
                        thisSourceList.append(sourcename)
                        if not sourcenvr in listSourcesDone:
                            listSourcesDone.append(sourcenvr)
                            if not sourcenvr in listSourcesQueue:
                                listSourcesQueue.append(sourcenvr)
                            if not pkg in listSourceNVRCached and not pkg in listSourceNVRNeedCache:
                                listSourceNVRNeedCache.append(sourcenvr)
                        if not sourcenvr in thisSourceEVR:
                            thisSourceEVR.append(sourcenvr)
            # Write these out to a file
            with open(dataDir+'/output/'+pkg_name+'-deps-'+arch+'-binary', 'w') as f:
                for item in thisBinaryList:
                    f.write("%s\n" % item)
            with open(dataDir+'/output/'+pkg_name+'-deps-'+arch+'-source-name', 'w') as f:
                for item in thisSourceList:
                    f.write("%s\n" % item)
            with open(dataDir+'/output/'+pkg_name+'-deps-'+arch+'-source-nvr', 'w') as f:
                for item in thisSourceEVR:
                    f.write("%s\n" % item)
            # logging.debug(json.dumps(new_binary_pkg_relations, indent=2, sort_keys=True))
        except dnf.exceptions.DepsolveError as e:
            logging.info("Package Resolution Error: " + this_nvr)
            logging.info(e)
        base.close()


def parse_root_log(full_path):
    pkg_arch = full_path.rsplit("/",1)[1]
    part_path = full_path.rsplit("/",1)[0]
    logging.debug("  Parsing: " + part_path + " arch:" + pkg_arch)
    required_pkgs = []
    if os.path.exists(full_path + '/required.pkgs'):
        required_pkgs = open(full_path + '/required.pkgs').read().splitlines()
    elif os.path.exists(part_path + '/noarch/required.pkgs'):
        required_pkgs = open(part_path + '/noarch/required.pkgs').read().splitlines()
    elif not os.path.exists(full_path + '/root.log'):
        os.mknod(full_path + '/required.pkgs')
    else:
        os.mknod(full_path + '/required.pkgs')
        # parseStatus
        # 1: top, 2: base required packages 3: base other packages
        # 4: middle, 5: add already installed 6: add required packages
        # 7: add other packages, 8: bottom
        parseStatus = 1
        check = 0
        logging.debug("    Status: " + str(parseStatus))
        with open(full_path + '/root.log', 'r') as rl:
            line = rl.readline().split()
            while line:
                logging.debug("    Status: " + str(parseStatus))
                logging.debug(line)
                if len(line) >2 :
                    if parseStatus == 1:
                        if line[2] == "================================================================================":
                            if check == 0:
                                check = 1
                            else:
                                check = 0
                                parseStatus = 2
                                logging.debug("    Status: " + str(parseStatus))
                                tmpline = rl.readline()
                    elif parseStatus == 2:
                        if line[2] == "Installing":
                            parseStatus = 3
                            logging.debug("    Status: " + str(parseStatus))
                            tmpline = rl.readline()
                        else:
                            logging.debug("Base Required: " + line[2])
                            with open(full_path + '/base.pkgs', 'a') as bp:
                                bp.write("%s\n" % (line[2]))
                    elif parseStatus == 3:
                        if line[2] == "================================================================================":
                            parseStatus = 4
                            logging.debug("    Status: " + str(parseStatus))
                    elif parseStatus == 4:
                        if line[2] == "================================================================================":
                            if check == 0:
                                check = 1
                            else:
                                check = 0
                                parseStatus = 5
                                logging.debug("    Status: " + str(parseStatus))
                                tmpline = rl.readline()
                        elif line[2] == "Package":
                            if line[4] == "is":
                                logging.debug("Required Already Installed: " + line[3])
                                required_pkgs.append(line[3].rsplit("-",2)[0])
                                with open(full_path + '/required.pkgs', 'a') as rp:
                                    rp.write("%s\n" % (line[3].rsplit("-",2)[0]))
                    elif parseStatus == 5:
                        if line[2] == "Installing":
                            parseStatus = 6
                            logging.debug("    Status: " + str(parseStatus))
                            tmpline = rl.readline()
                        else:
                            logging.debug("Required: " + line[2])
                            required_pkgs.append(line[2])
                            with open(full_path + '/required.pkgs', 'a') as rp:
                                rp.write("%s\n" % (line[2]))
                line = rl.readline().split()
    return required_pkgs

def download_root_logs(package_nvr):
    try:
        #Get our package n,v,r
        pkg_name = package_nvr.rsplit("-",2)[0]
        pkg_version = package_nvr.rsplit("-",2)[1]
        pkg_release = package_nvr.rsplit("-",2)[2]
        pkg_arch_list = []
        for arch in full_archList:
            file_dir = cacheDir+"/"+pkg_name+"/"+pkg_version+"/"+pkg_release+"/"+arch
            file_full_path = file_dir + "/root.log"
            if os.path.exists(file_full_path):
                pkg_arch_list.append(arch)
        if not pkg_arch_list:
            logging.info("  No logs for " + package_nvr + " ... processing ...")
            for arch in full_archList:
                logging.debug(arch + " " + package_nvr)
                file_dir = cacheDir+"/"+pkg_name+"/"+pkg_version+"/"+pkg_release+"/"+arch
                file_full_path = file_dir + "/root.log"
                logging.debug(file_full_path)
                file_url = baseURL+"/"+pkg_name+"/"+pkg_version+"/"+pkg_release+"/data/logs/"+arch+"/root.log"
                if not os.path.exists(file_full_path):
                    Path(file_dir).mkdir(parents=True, exist_ok=True)
                    logging.debug(file_url)
                    try:
                        urllib.request.urlretrieve (file_url, file_full_path)
                    except Exception as ex:
                        logging.debug("No logs for: " + pkg_name + " " + arch)
                        test = 0
    except Exception as e:
        logging.info(e)

def check_cache():
    for package_nvr in listSourceNVRNeedCache:
        pkg_name = package_nvr.rsplit("-",2)[0]
        pkg_version = package_nvr.rsplit("-",2)[1]
        pkg_release = package_nvr.rsplit("-",2)[2]
        found = False
        for arch in full_archList:
            file_dir = cacheDir+"/"+pkg_name+"/"+pkg_version+"/"+pkg_release+"/"+arch
            file_full_path = file_dir + "/root.log"
            if os.path.exists(file_full_path):
                found = True
        if found:
            if package_nvr in listSourceNVRNeedCache:
                listSourceNVRNeedCache.remove(package_nvr)
            if not package_nvr in listSourceNVRCached:
                listSourceNVRCached.append(package_nvr)

def find_new_sources():
    logging.info("Finding new sources")
    for package_nvr in listSourcesQueue:
        pkg_name = package_nvr.rsplit("-",2)[0]
        pkg_version = package_nvr.rsplit("-",2)[1]
        pkg_release = package_nvr.rsplit("-",2)[2]
        for arch in archList:
            this_builddep_nvrs = open(dataDir+'/output/'+pkg_name+'-deps-'+arch+'-source-nvr').read().splitlines()
            for this_nvr in this_builddep_nvrs:
                if not this_nvr in listSourcesQueue and not this_nvr in listSourcesDone:
                    listSourcesQueue.append(this_nvr)
                if not this_nvr in listSourceNVRCached and not this_nvr in listSourceNVRNeedCache:
                    listSourceNVRNeedCache.append(this_nvr)
        listSourcesQueue.remove(package_nvr)
        if not package_nvr in listSourcesDone:
            listSourcesDone.append(package_nvr)

pool = Pool(pool_num)
logging.info("Core Buildroot:")
logging.info("  Setup and Getting NVRs")
initialCoreNVRs = process_core_buildroot()
        
logging.info("Adding Package List to Queue:")
initialPkgs = open(args.file).read().splitlines()
for pkg in initialPkgs:
    if not "placeholder" in pkg:
        if not pkg in listSourcesQueue:
            listSourcesQueue.append(pkg)
        if not pkg in listSourceNVRCached and not pkg in listSourceNVRNeedCache:
            listSourceNVRNeedCache.append(pkg)
#proc = psutil.Process()
#logging.info(proc.open_files())
logging.info("Working on Queue:")
while 0 < len(listSourcesQueue):
    print("Done: " + str(len(listSourcesDone)) + " Queue: " + str(len(listSourcesQueue)) + " New: " + str(len(listSourceNVRNeedCache)))
    #logging.info(listSourceNVRNeedCache)
    #logging.info(len(listSourceNVRNeedCache))
    check_cache()
    #logging.info(len(listSourceNVRNeedCache))
    results = pool.map(download_root_logs, listSourceNVRNeedCache)
    # this_nvr = listSourcesQueue.pop(0)
    results = pool.map(process_package, listSourcesQueue)
    find_new_sources()

pool.close()
pool.join()

