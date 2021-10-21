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

TIMESTAMP=$(date +%Y-%m-%d-%H:%M)

if [ "${REPO_BASE}" == "combined" ] ; then
  VIEW="all"
elif [ "${REPO_BASE}" == "minimal" ] ; then
  VIEW="minimum"
elif [ "${REPO_BASE}" == "neptune" ] ; then
  VIEW="neptune"
elif [ "${REPO_BASE}" == "podman" ] ; then
  VIEW="podman"
elif [ "${REPO_BASE}" == "qpodman" ] ; then
  VIEW="qemu_podman"
elif [ "${REPO_BASE}" == "servers" ] ; then
  VIEW="servers"
else
  VIEW=${REPO_BASE}
fi

## Create buildroot from feedback-pipeline packages

# Get package lists from feedback-pipeline
PACKAGELIST_DIR="${WORK_DIR}/packagelists-${REPO_BASE}"
mkdir -p ${PACKAGELIST_DIR}
rm -f ${PACKAGELIST_DIR}/*

for this_arch in ${ARCH_LIST[@]}
do
echo "Downloading package lists for ${this_arch}"
wget -q -O ${PACKAGELIST_DIR}/Packages.${this_arch} ${URL_BASE}view-binary-package-name-list--automotive-base-c8s-view-${VIEW}--${this_arch}.txt
wget -q -O ${PACKAGELIST_DIR}/Sources.${this_arch} ${URL_BASE}view-source-package-name-list--automotive-base-c8s-view-${VIEW}--${this_arch}.txt
wget -q -O ${PACKAGELIST_DIR}/Package-NVRs.${this_arch} ${URL_BASE}view-binary-package-list--automotive-base-c8s-view-${VIEW}--${this_arch}.txt
wget -q -O ${PACKAGELIST_DIR}/Source-NVRs.${this_arch} ${URL_BASE}view-source-package-list--automotive-base-c8s-view-${VIEW}--${this_arch}.txt
sort -u -o ${PACKAGELIST_DIR}/Packages.${this_arch} ${PACKAGELIST_DIR}/Packages.${this_arch}
sort -u -o ${PACKAGELIST_DIR}/Sources.${this_arch} ${PACKAGELIST_DIR}/Sources.${this_arch}
sort -u -o ${PACKAGELIST_DIR}/Package-NVRs.${this_arch} ${PACKAGELIST_DIR}/Package-NVRs.${this_arch}
sed -i "s/.src.rpm$//" ${PACKAGELIST_DIR}/Source-NVRs.${this_arch}
sort -u -o ${PACKAGELIST_DIR}/Source-NVRs.${this_arch} ${PACKAGELIST_DIR}/Source-NVRs.${this_arch}
awk NF ${PACKAGELIST_DIR}/Packages.${this_arch} >> ${PACKAGELIST_DIR}/Packages.all-arches
awk NF ${PACKAGELIST_DIR}/Sources.${this_arch} >> ${PACKAGELIST_DIR}/Sources.all-arches
awk NF ${PACKAGELIST_DIR}/Package-NVRs.${this_arch} >> ${PACKAGELIST_DIR}/Package-NVRs.all-arches
awk NF ${PACKAGELIST_DIR}/Source-NVRs.${this_arch} >> ${PACKAGELIST_DIR}/Source-NVRs.all-arches
done
sort -u -o ${PACKAGELIST_DIR}/Packages.all-arches ${PACKAGELIST_DIR}/Packages.all-arches
sort -u -o ${PACKAGELIST_DIR}/Sources.all-arches ${PACKAGELIST_DIR}/Sources.all-arches
sort -u -o ${PACKAGELIST_DIR}/Package-NVRs.all-arches ${PACKAGELIST_DIR}/Package-NVRs.all-arches
sort -u -o ${PACKAGELIST_DIR}/Source-NVRs.all-arches ${PACKAGELIST_DIR}/Source-NVRs.all-arches


# Cleanup Cache
# rm -rf ${CACHE_DIR}/${REPO_BASE}-*

# Run bg2.py
./bg2.py -r ${REPO_BASE} -f ${PACKAGELIST_DIR}/Source-NVRs.all-arches
