#!/bin/bash
# Implement the feedback-pipeline buildroot workflow
#   f.p -> b.g. -> a.s.r. -> b.g. -> fp
#     f.p.   = feedback-pipeline
#     b.g.   = buildroot-generator
#     a.s.r. = archful source repos
#   Summary, start with a list of packages from feedback-pipeline
#     Return, as a workload, a list of packages that constitue
#     a build root for that initial set of packages.
#

#####
# Variables
#####
WORK_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source ${WORK_DIR}/conf/config.inc

BAD_PACKAGES=(nodejs-find-up nodejs-grunt-contrib-uglify nodejs-http-errors nodejs-json-diff nodejs-load-grunt-tasks nodejs-locate-path nodejs-pkg-up nodejs-p-locate nodejs-raw-body nodejs-closure-compiler texlive-collection-latexrecommended texlive-fancyvrb texlive-pstricks texlive-biblatex texlive-xmltex texlive-l3kernel texlive-xetex texlive-dvipdfmx texlive-collection-basic texinfo-tex nodejs-rollup nodejs-js-yaml nodejs-tap-parser)
PACKAGELIST_DIR="${WORK_DIR}/packagelists-${REPO_BASE}"
URL_BASE="https://tiny.distro.builders/"
if [ "${REPO_BASE}" == "rawhide" ] ; then
  VIEW="prototype-eln"
elif [ "${REPO_BASE}" == "eln" ] ; then
  VIEW="eln"
elif [ "${REPO_BASE}" == "released" ] ; then
  VIEW="released"
else
  echo "View not setup for ${REPO_BASE}"
  echo "  Exiting."
  exit 6
fi
## Create buildroot from feedback-pipeline packages

# Get package lists from feedback-pipeline
mkdir -p ${PACKAGELIST_DIR}
rm -f ${PACKAGELIST_DIR}/*
if [ "${REPO_BASE}" == "released" ] ; then
  cp ${WORK_DIR}/packagelists-rawhide/* ${PACKAGELIST_DIR}/
  rm -f ${PACKAGELIST_DIR}/*.yaml
  rm -f ${PACKAGELIST_DIR}/*Buildroot*
else
  for this_arch in ${ARCH_LIST[@]}
  do
    echo "Downloading package lists for ${this_arch}"
    wget -q -O ${PACKAGELIST_DIR}/Packages.${this_arch} ${URL_BASE}view-binary-package-name-list--view-${VIEW}--${this_arch}.txt
    wget -q -O ${PACKAGELIST_DIR}/Sources.${this_arch} ${URL_BASE}view-source-package-name-list--view-${VIEW}--${this_arch}.txt
    wget -q -O ${PACKAGELIST_DIR}/Package-NVRs.${this_arch} ${URL_BASE}view-binary-package-list--view-${VIEW}--${this_arch}.txt
    wget -q -O ${PACKAGELIST_DIR}/Source-NVRs.${this_arch} ${URL_BASE}view-source-package-list--view-${VIEW}--${this_arch}.txt
  	sort -u -o ${PACKAGELIST_DIR}/Packages.${this_arch} ${PACKAGELIST_DIR}/Packages.${this_arch}
  	sort -u -o ${PACKAGELIST_DIR}/Sources.${this_arch} ${PACKAGELIST_DIR}/Sources.${this_arch}
  	sort -u -o ${PACKAGELIST_DIR}/Package-NVRs.${this_arch} ${PACKAGELIST_DIR}/Package-NVRs.${this_arch}
  	sort -u -o ${PACKAGELIST_DIR}/Source-NVRs.${this_arch} ${PACKAGELIST_DIR}/Source-NVRs.${this_arch}
  	cat ${PACKAGELIST_DIR}/Packages.${this_arch} >> ${PACKAGELIST_DIR}/Packages.all-arches
  	cat ${PACKAGELIST_DIR}/Sources.${this_arch} >> ${PACKAGELIST_DIR}/Sources.all-arches
  	cat ${PACKAGELIST_DIR}/Package-NVRs.${this_arch} >> ${PACKAGELIST_DIR}/Package-NVRs.all-arches
  	cat ${PACKAGELIST_DIR}/Source-NVRs.${this_arch} >> ${PACKAGELIST_DIR}/Source-NVRs.all-arches
  done
  sort -u -o ${PACKAGELIST_DIR}/Packages.all-arches ${PACKAGELIST_DIR}/Packages.all-arches
  sort -u -o ${PACKAGELIST_DIR}/Sources.all-arches ${PACKAGELIST_DIR}/Sources.all-arches
  sort -u -o ${PACKAGELIST_DIR}/Package-NVRs.all-arches ${PACKAGELIST_DIR}/Package-NVRs.all-arches
  sort -u -o ${PACKAGELIST_DIR}/Source-NVRs.all-arches ${PACKAGELIST_DIR}/Source-NVRs.all-arches
fi

# Generate the initial buildroot
./buildroot-generator -r ${REPO_BASE} -p ${PACKAGELIST_DIR}

# Take the initial buildroot and create archful source repos
./identify-archful-srpms -r ${REPO_BASE}
./create-srpm-repos -r ${REPO_BASE}

# (Optional) Save off initial buildroot lists
#   Not written yet, cuz it's optional

# Generate the final buildroot using the archful source repos
./buildroot-generator -r ${REPO_BASE}-archful-source -p ${PACKAGELIST_DIR}


## Create buildroot workload and upload it to feedback-pipeline

# Determine binary packages added, and which are arch specific
rm -f ${PACKAGELIST_DIR}/Packages.Binary.Buildroot.tmp
rm -f ${PACKAGELIST_DIR}/Packages.Source.Buildroot.NVR.all-arches
for this_arch in ${ARCH_LIST[@]}
do
  DATA_DIR="${DATA_DIR_BASE}/${this_arch}"
  comm -13 ${DATA_DIR}/${NEW_DIR}/Packages.${this_arch} ${DATA_DIR}/${NEW_DIR}/buildroot-binary-package-names.txt | sort -u -o ${DATA_DIR}/${NEW_DIR}/added-binary-package-names.txt
  cat ${DATA_DIR}/${NEW_DIR}/added-binary-package-names.txt >> ${PACKAGELIST_DIR}/Packages.added.tmp
  cat ${DATA_DIR}/${NEW_DIR}/buildroot-binary-package-names.txt >> ${PACKAGELIST_DIR}/Packages.Binary.Buildroot.tmp
  cat ${DATA_DIR}/${NEW_DIR}/buildroot-source-package-nvrs.txt >> ${PACKAGELIST_DIR}/Packages.Source.Buildroot.NVR.all-arches
done
cat ${PACKAGELIST_DIR}/Packages.added.tmp | sort | uniq -cd | sed -n -e 's/^ *4 \(.*\)/\1/p' | sort -u -o ${PACKAGELIST_DIR}/Packages.added.common
cat ${PACKAGELIST_DIR}/Packages.Binary.Buildroot.tmp | sort | uniq -cd | sed -n -e 's/^ *4 \(.*\)/\1/p' | sort -u -o ${PACKAGELIST_DIR}/Packages.Binary.Buildroot.common
sort -u -o ${PACKAGELIST_DIR}/Packages.Source.Buildroot.NVR.all-arches ${PACKAGELIST_DIR}/Packages.Source.Buildroot.NVR.all-arches

if ! [ "${REPO_BASE}" == "released" ] ; then
  # Generate the buildroot workload
  rm -f ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  cat ${WORK_DIR}/conf/${VIEW}-buildroot-workload.head >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  cat ${PACKAGELIST_DIR}/Packages.added.common | awk '{print "        - " $1}' >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  echo "    arch_packages:" >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  for this_arch in ${ARCH_LIST[@]}
  do
    DATA_DIR="${DATA_DIR_BASE}/${this_arch}"
    echo "        ${this_arch}:" >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
    comm -13 ${PACKAGELIST_DIR}/Packages.added.common ${DATA_DIR}/${NEW_DIR}/added-binary-package-names.txt | awk '{print "            - " $1}' >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
    #comm -13 ${PACKAGELIST_DIR}/Packages.Binary.Buildroot.common ${DATA_DIR}/${NEW_DIR}/buildroot-binary-package-names.txt | awk '{print "            - " $1}' >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  done

  # Trim buildroot workload of packages we don't want in there
  for pkgname in ${BAD_PACKAGES[@]}
  do
    sed -i "/ ${pkgname}$/d" ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  done

  # Upload to feedback-pipeline
  if ! [ -d ${GIT_DIR}/content-resolver-input ] ; then
    mkdir -p ${GIT_DIR}
    cd ${GIT_DIR}
    git clone git@github.com:minimization/content-resolver-input.git
  fi
  if ! [ -d ${GIT_DIR}/content-resolver-input ] ; then
  	echo
  	echo "You do not seem to have correct credentials for the git repo"
  	echo "Exiting so you do no harm"
  	echo
  	exit 5
  fi
  cd ${GIT_DIR}/content-resolver-input/configs
  git pull
  cp ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml .
  git add ${VIEW}-buildroot-workload.yaml
  git commit -m "Update ${VIEW}-buildroot-workload $(date +%Y-%m-%d-%H:%M)"
  git push
fi # end - only update if not released repo

exit 0

