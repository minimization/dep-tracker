#!/usr/bin/python3

import sys
import argparse
import copy
import dnf
import dnf.cli
import dnf.exceptions
import dnf.rpm.transaction
import dnf.yum.rpmtrans
import libdnf.repo
import os
import rpm
import shutil
import tempfile

# Arguments
parser = argparse.ArgumentParser()
parser.add_argument("arch", help="What arch are we using",
        choices=["aarch64", "ppc64le", "s390x", "x86_64"])
parser.add_argument("repo", help="What repo are we using",
        choices=["rawhide", "rawhide-archful-source", "eln", "eln-archful-source"])
args = parser.parse_args()
repoName = args.repo
repoBase = args.repo
if args.repo == "rawhide-archful-source":
    repoBase = "rawhide"
elif args.repo == "eln-archful-source":
    repoBase = "eln"
arch = args.arch


# Configuration
workDir = "/srv/square1/dep-tracker/"
repoConfDir = workDir + "repos/"
outputDir = workDir + "data-" + repoBase + "/" + arch + "/new/"
installroot = "/installroot-" + arch
releasever = "33"

# Lists
listSources = []
listSourcesDone = []
listSourcesQueue = open(workDir + "packagelists-" + repoBase + "/Sources.all-arches").read().splitlines()
#listSourcesQueue =['bash', 'sed']
coreBuildRoot = ['bash', 'bzip2', 'coreutils', 'cpio', 'diffutils', 'fedora-release', 'findutils', 'gawk', 'glibc-minimal-langpack', 'grep', 'gzip', 'info', 'make', 'patch', 'redhat-rpm-config', 'rpm-build', 'sed', 'shadow-utils', 'tar', 'unzip', 'util-linux', 'which', 'xz']
coreBuildRootBinaries = []
coreBuildRootSources = []


print(arch + ": Setup")
baseCore = dnf.Base()
baseCore.conf.read(repoConfDir + repoName + "." + arch + ".repo")
baseCore.conf.substitutions['releasever'] = releasever
baseCore.conf.installroot = installroot
baseCore.conf.arch = arch
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
      listSources.append(pkg.source_name)
      listSourcesQueue.append(pkg.source_name)
  fileCoreBuildRootBinaries.close()
  fileCoreBuildRootSources.close()
except dnf.exceptions.DepsolveError as e:
  print("Core BuildRoot Resolution Error")
  print(e)
  		
base = baseCore
print(arch + ": Working on Source Queue")
while 0 < len(listSourcesQueue):
  print('.', end='')
  #print('.', end='', flush=True)
  #print("DONE: " + str(len(listSourcesDone)) + "  QUEUE: " + str(len(listSourcesQueue))  + " TOTAL: " + str(len(listSources)) + " " + arch)
  ## Get the source package name
  this_package = listSourcesQueue.pop(0)
  #print("thepackage: " + this_package)
  thisBinaryList = []
  thisSourceList = []
  base.reset(goal='true')
  
  ## Get the source as a pkg, from the package name
  # Although in rawhide there should only be one package with that name
  # Treat it as multi-packages, just incase
  pkgs = base.sack.query().available().filter(
      name=(this_package), arch="src").latest().run()
  if not pkgs:
      print(('no package matched: %s') % this_package)
  ## Find the BuildRequires needed to build the source
  for pkg in pkgs:
      #print("  " + pkg.name)
      for req in pkg.requires:
          if not str(req) in thisBinaryList:
              #print("    =>%s" % (str(req)))
              thisBinaryList.append(str(req))

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
      print(arch + ": No Resolution for" + this_package)
      print(e)
      fileBadDeps=open(outputDir + "errors/" + this_package + "-BadDeps", "a+")
      fileBadDeps.write("===============================\n")
      fileBadDeps.write("ERROR: %s\n" % (this_package))
      fileBadDeps.write("%s\n" % (e))
      fileBadDeps.close()

  listSourcesDone.append(this_package)

print('')
print(arch + ": FINAL SOURCES: " + str(len(listSources)))
