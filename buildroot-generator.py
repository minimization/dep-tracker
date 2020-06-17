#!/usr/bin/python3

import sys
import argparse
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


# Lists
listSources = ['bash']
listSourcesDone = []
listSourcesQueue = ['bash']

# Configuration
installroot = '/installroot'
releasever = "33"

base = dnf.Base()


print("Setup")
base.conf.read("/home/square1/tmp/rawhide.repo")
base.conf.substitutions['releasever'] = releasever
base.conf.installroot = installroot
base.repos.enable_source_repos()

print(" Start read repos")
base.read_all_repos()

print(" Start fill sack")
base.fill_sack(load_system_repo=False)

while 0 < len(listSourcesQueue):
  print("DONE: " + str(len(listSourcesDone)) + "  QUEUE: " + str(len(listSourcesQueue))  + " TOTAL: " + str(len(listSources)))
  this_package = listSourcesQueue.pop(0)
  thisBinaryList = []
  thisSourceList = []
  base.reset(goal='true')
  # Find the binaries needed to install the sources.
  #print("thepackage: " + this_package)
  pkgs = base.sack.query().available().filter(
      name=(this_package), arch="src").latest().run()
  if not pkgs:
      raise dnf.exceptions.Error(('no package matched: %s') % this_package)
  for pkg in pkgs:
      #print("  " + pkg.name)
      for req in pkg.requires:
          if not str(req) in thisBinaryList:
              #print("    =>%s" % (str(req)))
              thisBinaryList.append(str(req))
  		
  
  for this_binary in thisBinaryList:
      try:
          base.install(this_binary)
      except dnf.exceptions.MarkingError:
          print('    Cannot Install: ' + this_binary)
          fileNoInstall=open("errors/NoInstall", "a+")
          fileNoInstall.write(this_package + ": " + this_binary + "\n")
          fileNoInstall.close()
  
  try:
      base.resolve()
      query = base.sack.query().filterm(pkg=base.transaction.install_set)
      #print(str(len(query)))
      fileBinaryDeps=open("output/" + this_package + "-deps-binary", "a+")
  
      for pkg in query:
          fileBinaryDeps.write("%s\n" % (pkg.name))
          if not pkg.source_name in thisSourceList:
              #print("  " + pkg.name + " : " + pkg.source_name)
              thisSourceList.append(pkg.source_name)
              if not pkg.source_name in listSources:
                  listSources.append(pkg.source_name)
                  listSourcesQueue.append(pkg.source_name)
      
      fileBinaryDeps.close()
      
      fileSourceDeps=open("output/" + this_package + "-deps-source", "a+")
      for src in thisSourceList:
          fileSourceDeps.write("%s\n" % (src))
      fileSourceDeps.close()


  except dnf.exceptions.DepsolveError as e:
      print("No Resolution for" + this_package)
      print(e)
      fileBadDeps=open("errors/BadDeps", "a+")
      fileBadDeps.write("===============================\n")
      fileBadDeps.write("ERROR: %s\n" % (this_package))
      fileBadDeps.write("%s\n" % (e))
      fileBadDeps.close()

  listSourcesDone.append(this_package)


print("FINAL SOURCES: " + str(len(listSources)))
