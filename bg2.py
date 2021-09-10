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
    baseURL = "https://kojihub.stream.centos.org/kojifiles/packages"
    placeholderURL="https://tiny.distro.builders/view-placeholder-srpm-details--view-c9s--"
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

# Package dependency data
binary_pkg_relations = {}
source_pkg_relations = {}

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

# Saves given data as JSON
def dump_data(path, data):
    with open(path, 'w') as file:
        json.dump(data, file)

# Analyzes package relations and outputs graph data
# representing package to package dependency relations
# within given DNF query
def _analyze_package_relations(dnf_query):
    relations = {}

    for pkg in dnf_query:
        pkg_id = "{name}-{evr}.{arch}".format(
            name=pkg.name,
            evr=pkg.evr,
            arch=pkg.arch
        )
        
        required_by = set()
        recommended_by = set()
        suggested_by = set()

        for dep_pkg in dnf_query.filter(requires=pkg.provides):
            dep_pkg_id = "{name}-{evr}.{arch}".format(
                name=dep_pkg.name,
                evr=dep_pkg.evr,
                arch=dep_pkg.arch
            )
            required_by.add(dep_pkg_id)

        for dep_pkg in dnf_query.filter(recommends=pkg.provides):
            dep_pkg_id = "{name}-{evr}.{arch}".format(
                name=dep_pkg.name,
                evr=dep_pkg.evr,
                arch=dep_pkg.arch
            )
            recommended_by.add(dep_pkg_id)
        
        for dep_pkg in dnf_query.filter(suggests=pkg.provides):
            dep_pkg_id = "{name}-{evr}.{arch}".format(
                name=dep_pkg.name,
                evr=dep_pkg.evr,
                arch=dep_pkg.arch
            )
            suggested_by.add(dep_pkg_id)
        
        relations[pkg_id] = {}
        relations[pkg_id]["required_by"] = sorted(list(required_by))
        relations[pkg_id]["recommended_by"] = sorted(list(recommended_by))
        relations[pkg_id]["suggested_by"] = sorted(list(suggested_by))
        relations[pkg_id]["source_name"] = pkg.source_name
    
    return relations

# Updates an existing dictionary target_relations with packages
# from source_relations
def _update_package_relations_dict(source_relations, target_relations):

    if not source_relations:
        return
    
    for pkg_id, pkg in source_relations.items():
        if pkg_id in target_relations:
            # If it exists, I just need to update the dependency lists
            required_by_set = set()
            required_by_set.update(target_relations[pkg_id]["required_by"])
            required_by_set.update(pkg["required_by"])
            target_relations[pkg_id]["required_by"] = list(required_by_set)

            recommended_by_set = set()
            recommended_by_set.update(target_relations[pkg_id]["recommended_by"])
            recommended_by_set.update(pkg["recommended_by"])
            target_relations[pkg_id]["recommended_by"] = list(recommended_by_set)

            suggested_by_set = set()
            suggested_by_set.update(target_relations[pkg_id]["suggested_by"])
            suggested_by_set.update(pkg["suggested_by"])
            target_relations[pkg_id]["suggested_by"] = list(suggested_by_set)
            
        else:
            target_relations[pkg_id] = pkg

def process_core_buildroot():
    print("Working on Core Buildroot:")
    if os.path.exists(workDir + "corebuildroot.txt"):
        this_coreBuildRoot = open(workDir + "corebuildroot.txt").read().splitlines()
    else:
        this_coreBuildRoot=coreBuildRoot
    this_coreBuildRoot.append(coreAppend)
    for arch in archList:
        print("  "+arch)
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
                        if not sourcenvr in coreBuildRootSourceNVR:
                            coreBuildRootSourceNVR.append(sourcenvr)
                        if not sourcenvr in listSourcesQueue:
                            listSourcesQueue.append(sourcenvr)
#                        if not pkg in listSourceNVRCached and not pkg in listSourceNVRNeedCache:
#                            listSourceNVRNeedCache.append(sourcenvr)
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

def process_package(this_nvr):
    # print("  Processing: " + this_nvr)
    this_package = {}
    this_package["snvr"] = this_nvr
    # Get our package name,version and release
    pkg_name = this_nvr.rsplit("-",2)[0]
    pkg_version = this_nvr.rsplit("-",2)[1]
    pkg_release = this_nvr.rsplit("-",2)[2]
    print("    Processing: " + this_nvr + " :: " + pkg_name + " " + pkg_version + " " + pkg_release)
    # Process our package, one arch at a time.
    for arch in archList:
        file_dir = cacheDir+"/"+pkg_name+"/"+pkg_version+"/"+pkg_release+"/"+arch
        pkg_deps = parse_root_log(file_dir)
        thisBinaryList = []
        thisSourceList = []
        thisSourceEVR = []
        this_required = {}
        this_required_deps = {}
        if len(pkg_deps) >= 1 :
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
                # Save package dependency data
                # new_binary_pkg_relations = _analyze_package_relations(query)
                # _update_package_relations_dict(new_binary_pkg_relations, binary_pkg_relations)
                for pkg in query:
                    if not pkg.name in coreBuildRootBinaries:
                        # Setup Variables
                        binarynvr = pkg.name+"."+pkg.evr
                        sourcenvr = pkg.sourcerpm.rsplit(".",2)[0]
                        sourcename = sourcenvr.rsplit("-",2)[0]
                        if not sourcename in coreBuildRootSourceName:
                            this_pkg = {
                                    "nvr": binarynvr ,
                                    "sname": sourcename ,
                                    "snvr": sourcenvr
                                }
                            if pkg.name in pkg_deps:
                                this_required[pkg.name] = this_pkg
                            else:
                                this_required_deps[pkg.name] = this_pkg
                            if not sourcenvr in listSourcesQueue and not sourcenvr in listSourcesDone:
                                listSourcesQueue.append(sourcenvr)
            except dnf.exceptions.DepsolveError as e:
                logging.info("Package Resolution Error: " + this_nvr)
                logging.info(e)
            base.close()
        this_arch = {}
        this_arch["required"] = this_required
        this_arch["required_deps"] = this_required_deps
        this_package[arch] = this_arch
    source_pkg_relations[pkg_name] = this_package
    #print(source_pkg_relations)
    #print(listSourcesQueue)
    #print(source_pkg_relations)
    listSourcesQueue.remove(this_nvr)
    listSourcesDone.append(this_nvr)


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
        Path(full_path).mkdir(parents=True, exist_ok=True)
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
                        if "=================" in line[2]:
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
                        if "=================" in line[2]:
                            parseStatus = 4
                            logging.debug("    Status: " + str(parseStatus))
                    elif parseStatus == 4:
                        if "=================" in line[2]:
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

pool = Pool(pool_num)
logging.info("Core Buildroot:")
logging.info("  Setup and Getting NVRs")
initialCoreNVRs = process_core_buildroot()
print("  Done: " + str(len(source_pkg_relations)) + " Queue: " + str(len(listSourcesQueue)))
        
print("Adding Package List to Queue:")
initialPkgs = open(args.file).read().splitlines()
for pkg in initialPkgs:
    if not "placeholder" in pkg:
        if not pkg in listSourcesQueue:
            listSourcesQueue.append(pkg)
#        if not pkg in listSourceNVRCached and not pkg in listSourceNVRNeedCache:
#            listSourceNVRNeedCache.append(pkg)
print("  Done: " + str(len(source_pkg_relations)) + " Queue: " + str(len(listSourcesQueue)))
print("Working on Queue:")
while 0 < len(listSourcesQueue):
    print("  Processed: " + str(len(source_pkg_relations)) + " Queue: " + str(len(listSourcesQueue)) + " Done: " + str(len(listSourcesDone)))
    #print(listSourcesQueue)
    tmpQueue = list(listSourcesQueue)
    #logging.info(listSourceNVRNeedCache)
    #logging.info(len(listSourceNVRNeedCache))
#    print("  Checking root log cache")
#    check_cache()
    #logging.info(len(listSourceNVRNeedCache))
    print("  Downloading root logs to cache")
    results = pool.map(download_root_logs, listSourcesQueue)
#    print("    Done: " + str(len(listSourceNVRNeedCache)))
    # this_nvr = listSourcesQueue.pop(0)
    print("  Processing packages")
    for pkg in tmpQueue:
      process_package(pkg)
#    find_new_sources()

pool.close()
pool.join()

# Dumping package dependency data
filename = "output.json"
filepath = os.path.join(dataDir, filename)
file_data = {}
file_data["document_type"] = "buildroot-source-relations"
file_data["version"] = "1"
file_data["data"] = {}
file_data["data"]["view_id"] = "1"
file_data["data"]["pkgs"] = source_pkg_relations
dump_data(filepath, file_data)

