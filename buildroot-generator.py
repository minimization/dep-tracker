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
import os
import re
import requests
import rpm
import shutil
import tempfile
from pathlib import Path

# Arguments
parser = argparse.ArgumentParser()
parser.add_argument("arch", help="What arch are we using",
        choices=["aarch64", "ppc64le", "s390x", "x86_64"])
parser.add_argument("repo", help="What repo are we using",
        choices=["rawhide", "rawhide-archful-source", "eln", "eln-archful-source", "c9s", "c9s-archful-source"])
args = parser.parse_args()
repoName = args.repo
repoBase = args.repo
if args.repo == "rawhide-archful-source":
    repoBase = "rawhide"
elif args.repo == "eln-archful-source":
    repoBase = "eln"
elif args.repo == "c9s-archful-source":
    repoBase = "c9s"
arch = args.arch
if repoBase == "rawhide":
    BestEVRVAR = "fc\d\d"
elif repoBase == "eln":
    BestEVRVAR = "eln\d\d\d"
else:
    BestEVRVAR = "el9"


# Configuration
workDir = os.getcwd() + "/"
repoConfDir = workDir + "repos/"
outputDir = workDir + "data-" + repoBase + "/" + arch + "/new/"
Path(outputDir + "errors").mkdir(parents=True, exist_ok=True)
Path(outputDir + "output").mkdir(parents=True, exist_ok=True)
installroot = "/installroot-" + arch
releasever = "33"

# Lists
listSources = []
listSourcesDone = []
listSourcesQueue = open(workDir + "packagelists-" + repoBase + "/Sources.all-arches").read().splitlines()
#listSourcesQueue =['bash', 'sed']
coreBuildRoot = ['bash', 'bzip2', 'coreutils', 'cpio', 'diffutils', 'findutils', 'gawk', 'glibc-minimal-langpack', 'grep', 'gzip', 'info', 'make', 'patch', 'redhat-rpm-config', 'rpm-build', 'sed', 'shadow-utils', 'tar', 'unzip', 'util-linux', 'which', 'xz']
if repoBase == "eln":
    coreBuildRoot.append("fedora-release-eln")
    placeholderURL="https://tiny.distro.builders/view-placeholder-srpm-details--view-eln--x86_64.json"
elif repoBase == "c9s":
    coreBuildRoot.append("redhat-release")
    placeholderURL="https://tiny.distro.builders/view-placeholder-srpm-details--view-c9s--x86_64.json"
else:
    coreBuildRoot.append("fedora-release")
    placeholderURL="https://tiny.distro.builders/view-placeholder-srpm-details--view-eln--x86_64.json"
coreBuildRootBinaries = []
coreBuildRootSources = []
placeholderBinaries = []
placeholderSources = []

# Package dependency data
binary_pkg_relations = {}

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


# Saves given data as JSON
def dump_data(path, data):
    with open(path, 'w') as file:
        json.dump(data, file)


print(arch + ": Setup")
baseCore = dnf.Base()
baseCore.conf.read(repoConfDir + repoName + "." + arch + ".repo")
baseCore.conf.substitutions['releasever'] = releasever
baseCore.conf.installroot = installroot
baseCore.conf.arch = arch
baseCore.conf.install_weak_deps = False
baseCore.repos.enable_source_repos()

#print(" Start read repos")
baseCore.read_all_repos()

#print(" Start fill sack")
baseCore.fill_sack(load_system_repo=False)

print(arch + ": Populating Core Buildroot")
for this_binary in coreBuildRoot:
    try:
        baseCore.install(this_binary)
    except dnf.exceptions.MarkingError:
        print('    Cannot Install: ' + this_binary)
## Resolve the coreBuildRoot
try:
    baseCore.resolve()
    query = baseCore.sack.query().filterm(pkg=baseCore.transaction.install_set)
    fileCoreBuildRootBinaries=open(outputDir + "CoreBuildRootBinaries", "a+")
    fileCoreBuildRootSources=open(outputDir + "CoreBuildRootSources", "a+")
    fileCoreBuildRootSourcesNVR=open(outputDir + "CoreBuildRootSourcesNVR", "a+")
    for pkg in query:
        ## Put the binaries on the coreBuildRootBinaries list
        if not pkg.name in coreBuildRootBinaries:
            coreBuildRootBinaries.append(pkg.name)
            fileCoreBuildRootBinaries.write("%s\n" % (pkg.name))
        ## Put the source for the binary on the coreBuildRootSources list
        ##   if it is not already there
        if not pkg.source_name in coreBuildRootSources:
            coreBuildRootSources.append(pkg.source_name)
            fileCoreBuildRootSources.write("%s\n" % (pkg.source_name))
            fileCoreBuildRootSourcesNVR.write("%s\n" % (pkg.sourcerpm))
            listSources.append(pkg.source_name)
            listSourcesQueue.append(pkg.source_name)
    fileCoreBuildRootBinaries.close()
    fileCoreBuildRootSources.close()
    fileCoreBuildRootSourcesNVR.close()
except dnf.exceptions.DepsolveError as e:
    print("Core BuildRoot Resolution Error")
    print(e)
  		
base = baseCore

## BEGIN: placeholder work
print(arch + ": Working on Placeholders")
base.reset(goal='true')
placeholderJsonData = {}
placeholderJsonData = json.loads(requests.get(placeholderURL, allow_redirects=True).text)
for placeholder_source in placeholderJsonData:
    print(arch + ": Placeholder: " + placeholder_source)
    placeholderSources.append(placeholder_source)
    thisBinaryList = []
    thisSourceList = []
    base.reset(goal='true')
    # Source rpm: Create a blank deps-source file, add to lists
    open(outputDir + "output/" + placeholder_source + "-deps-source", "w").close()
    listSources.append(placeholder_source)
    with open(outputDir + "BuildRootSourcesNVR", "a+") as fileBuildRootSourcesNVR:
        fileBuildRootSourcesNVR.write("%s-PLACEHOLDER.src.rpm\n" % (placeholder_source))
    # Dep Binaries: Add to deps-binary file, add to local list for processing
    fileBinaryDeps=open(outputDir + "output/" + placeholder_source + "-deps-binary", "w")
    for this_binary in placeholderJsonData[placeholder_source]['build_requires']:
        thisBinaryList.append(this_binary)
        fileBinaryDeps.write("%s\n" % (this_binary))
        try:
            base.install(this_binary)
        except dnf.exceptions.MarkingError:
            print(arch + ": Placeholder:  Cannot Install: " + this_binary)
    try:
        base.resolve()
        query = base.sack.query().filterm(pkg=base.transaction.install_set)
        # Save package dependency data
        new_binary_pkg_relations = _analyze_package_relations(query)
        _update_package_relations_dict(new_binary_pkg_relations, binary_pkg_relations)
        for pkg in query:
            ## Write the binary to the file
            if not pkg.name in coreBuildRootBinaries and not pkg.name in thisBinaryList:
                fileBinaryDeps.write("%s\n" % (pkg.name))
            if not pkg.source_name in thisSourceList and not pkg.source_name in coreBuildRootSources:
                thisSourceList.append(pkg.source_name)
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
    fileBinaryDeps.close()
    with open(outputDir + "output/" + placeholder_source + "-deps-source", "a+") as fileSourceDeps:
        for src in thisSourceList:
            fileSourceDeps.write("%s\n" % (src))
## END: placeholder work

print(arch + ": Working on Source Queue")
while 0 < len(listSourcesQueue):
    ## Get the source package name
    this_package = listSourcesQueue.pop(0)
    # print("thepackage: " + this_package)
    if this_package in placeholderSources:
        print(arch + ": SKIPPING Placeholder: " + this_package)
        continue
    thisBinaryList = []
    thisSourceList = []
    thisSourceEVR = []
    base.reset(goal='true')
    
    ## Get the source as a pkg, from the package name
    # Although in rawhide there should only be one package with that name
    # Treat it as multi-packages, just incase
    pkgs = base.sack.query().available().filter(
        name=(this_package), arch="src").run()
    if not pkgs:
        print((arch + ': no package matched: %s') % this_package)
    ## Find the BuildRequires needed to build the correct source
    # Get list of EVR's
    for pkg in pkgs:
        thisSourceEVR.append(str(pkg.evr))
    # Figure out the best EVR's
    bestEVR = ""
    for evr in thisSourceEVR:
        if re.search( BestEVRVAR, evr):
            bestEVR = evr
            break
        elif evr > bestEVR:
            bestEVR = evr
    # Get the BuildRequires from the best evr package
    for pkg in pkgs:
        # 
        if bestEVR == pkg.evr:
            #print("    CHOSEN ONE")
            #print("      " + pkg.name + " " + pkg.evr)
            for req in pkg.requires:
                if not str(req) in thisBinaryList:
                    thisBinaryList.append(str(req))
            with open(outputDir + "BuildRootSourcesNVR", "a+") as fileBuildRootSourcesNVR:
                fileBuildRootSourcesNVR.write("%s-%s\n" % (pkg.name,pkg.evr))
            break

    ## Add all the BuildRequires to the base, to be installed
    for this_binary in thisBinaryList:
        try:
            base.install(this_binary)
        except dnf.exceptions.MarkingError:
            print('')
            print(arch + ":     Cannot Install: " + this_binary)
            fileNoInstall=open(outputDir + "errors/" + this_package + "-NoInstall", "a+")
            fileNoInstall.write(this_package + ": " + this_binary + "\n")
            fileNoInstall.close()
    
    ## Pretend we are installing all the BuildRequires
    try:
        base.resolve()
        ## We were successful fake installing, use this information
        query = base.sack.query().filterm(pkg=base.transaction.install_set)

        # Save package dependency data
        new_binary_pkg_relations = _analyze_package_relations(query)
        _update_package_relations_dict(new_binary_pkg_relations, binary_pkg_relations)

        fileBinaryDeps=open(outputDir + "output/" + this_package + "-deps-binary", "a+")
        for pkg in query:
            ## Write the binary to the file
            if not pkg.name in coreBuildRootBinaries:
                fileBinaryDeps.write("%s\n" % (pkg.name))
      ## Put the source for the binary on the source lists
      ##   if it is not already there, or in coreBuildRoot
      ## 3 source lists:  for this package, overall, and queue
            if not pkg.source_name in coreBuildRootSources:
                if not pkg.source_name in thisSourceList:
                    #print("  " + pkg.name + " : " + pkg.source_name)
                    thisSourceList.append(pkg.source_name)
                    if not pkg.source_name in listSources:
                        listSources.append(pkg.source_name)
                        listSourcesQueue.append(pkg.source_name)  
        fileBinaryDeps.close()
        
        fileSourceDeps=open(outputDir + "output/" + this_package + "-deps-source", "a+")
        for src in thisSourceList:
            fileSourceDeps.write("%s\n" % (src))
        fileSourceDeps.close()


    ## We could not install all the BuildRequires, let us know somehow
    except dnf.exceptions.DepsolveError as e:
        print('')
        print(arch + ": No Resolution for " + this_package)
        print(e)
        fileBadDeps=open(outputDir + "errors/" + this_package + "-BadDeps", "a+")
        fileBadDeps.write("===============================\n")
        fileBadDeps.write("ERROR: %s\n" % (this_package))
        fileBadDeps.write("%s\n" % (e))
        fileBadDeps.close()

    listSourcesDone.append(this_package)


# Dumping package dependency data
view_id = "view-" + repoBase
filename = "buildroot-package-relations--{view_id}--{arch}.json".format(
    view_id=view_id,
    arch=arch
)
filepath = os.path.join(outputDir, filename)
file_data = {}
file_data["document_type"] = "buildroot-binary-relations"
file_data["version"] = "1"
file_data["data"] = {}
file_data["data"]["view_id"] = view_id
file_data["data"]["arch"] = arch
file_data["data"]["pkgs"] = binary_pkg_relations
dump_data(filepath, file_data)

print('')
print(arch + ": FINAL SOURCES: " + str(len(listSources)))
