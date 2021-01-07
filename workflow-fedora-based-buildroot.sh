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

BAD_PACKAGES=(python3-pytest-relaxed python3-pytest4 kernel-headers kernel-tools python3-pywbem)
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
  	awk NF ${PACKAGELIST_DIR}/Packages.${this_arch} >> ${PACKAGELIST_DIR}/Packages.all-arches
  	awk NF ${PACKAGELIST_DIR}/Sources.${this_arch} >> ${PACKAGELIST_DIR}/Sources.all-arches
  	awk NF ${PACKAGELIST_DIR}/Package-NVRs.${this_arch} >> ${PACKAGELIST_DIR}/Package-NVRs.all-arches
  	awk NF ${PACKAGELIST_DIR}/Source-NVRs.${this_arch} >> ${PACKAGELIST_DIR}/Source-NVRs.all-arches
  done
  sort -u -o ${PACKAGELIST_DIR}/Packages.all-arches ${PACKAGELIST_DIR}/Packages.all-arches
  sort -u -o ${PACKAGELIST_DIR}/Sources.all-arches ${PACKAGELIST_DIR}/Sources.all-arches
  sort -u -o ${PACKAGELIST_DIR}/Package-NVRs.all-arches ${PACKAGELIST_DIR}/Package-NVRs.all-arches
  sort -u -o ${PACKAGELIST_DIR}/Source-NVRs.all-arches ${PACKAGELIST_DIR}/Source-NVRs.all-arches
fi

# Cleanup Cache
rm -rf ${CACHE_DIR}/${REPO_BASE}-*

# Generate the initial buildroot
#./buildroot-generator -r ${REPO_BASE} -p ${PACKAGELIST_DIR}
## New style buildroot
# Cleanup for the buildroot
for this_arch in ${ARCH_LIST[@]}
do
  DATA_DIR="${DATA_DIR_BASE}/${this_arch}/${NEW_DIR}"
  rm -rf ${DATA_DIR_BASE}/${this_arch}/${LAST_DIR}
  mv ${DATA_DIR} ${DATA_DIR_BASE}/${this_arch}/${LAST_DIR}
  mkdir -p ${DATA_DIR}/{errors,output}
  echo "${TIMESTAMP}" > ${DATA_DIR}/${BR_TIMESTAMP_FILENAME}
done
# generate buildroot
printf '%s\n' "${ARCH_LIST[@]}" | xargs --max-procs=4 -I THIS_ARCH \
       python3 buildroot-generator.py THIS_ARCH ${REPO_BASE}
# Massage Data
for this_arch in ${ARCH_LIST[@]}
do
  DATA_DIR="${DATA_DIR_BASE}/${this_arch}/${NEW_DIR}"
  cat ${DATA_DIR}/output/*deps-source ${DATA_DIR}/CoreBuildRootSources | sort -u -o ${DATA_DIR}/${BR_SOURCE_PKGNAMES_FILENAME}
done


# Take the initial buildroot and create archful source repos
./identify-archful-srpms -r ${REPO_BASE}
./create-srpm-repos -r ${REPO_BASE}

# (Optional) Save off initial buildroot lists
#   Not written yet, cuz it's optional

# Generate the final buildroot using the archful source repos
#./buildroot-generator -r ${REPO_BASE}-archful-source -p ${PACKAGELIST_DIR}
## New style buildroot
# Cleanup for the buildroot
for this_arch in ${ARCH_LIST[@]}
do
  DATA_DIR="${DATA_DIR_BASE}/${this_arch}/${NEW_DIR}"
  rm -rf ${DATA_DIR}/*
  mkdir -p ${DATA_DIR}/{errors,output}
  echo "${TIMESTAMP}" > ${DATA_DIR}/${BR_TIMESTAMP_FILENAME}
done
# generate buildroot
printf '%s\n' "${ARCH_LIST[@]}" | xargs --max-procs=4 -I THIS_ARCH \
       python3 buildroot-generator.py THIS_ARCH ${REPO_BASE}-archful-source
# Massage Data
for this_arch in ${ARCH_LIST[@]}
do
  DATA_DIR="${DATA_DIR_BASE}/${this_arch}/${NEW_DIR}"
  cat ${DATA_DIR}/output/*deps-source ${DATA_DIR}/CoreBuildRootSources | sort -u -o ${DATA_DIR}/${BR_SOURCE_PKGNAMES_FILENAME}
  cat ${DATA_DIR}/output/*deps-binary ${DATA_DIR}/CoreBuildRootBinaries | sort -u -o ${DATA_DIR}/${BR_BINARY_PKGNAMES_FILENAME}
done


## Create buildroot workload and upload it to feedback-pipeline

# Determine binary packages added, and which are arch specific
rm -f ${PACKAGELIST_DIR}/Packages.Binary.Buildroot.tmp
rm -f ${PACKAGELIST_DIR}/Packages.Source.Buildroot.Names.all-arches
for this_arch in ${ARCH_LIST[@]}
do
  DATA_DIR="${DATA_DIR_BASE}/${this_arch}"
  comm -13 ${PACKAGELIST_DIR}/Packages.${this_arch} ${DATA_DIR}/${NEW_DIR}/${BR_BINARY_PKGNAMES_FILENAME} | sort -u -o ${DATA_DIR}/${NEW_DIR}/added-binary-package-names.txt
  cat ${DATA_DIR}/${NEW_DIR}/added-binary-package-names.txt >> ${PACKAGELIST_DIR}/Packages.added.tmp
  cat ${DATA_DIR}/${NEW_DIR}/${BR_BINARY_PKGNAMES_FILENAME} >> ${PACKAGELIST_DIR}/Packages.Binary.Buildroot.tmp
  cat ${DATA_DIR}/${NEW_DIR}/${BR_SOURCE_PKGNAMES_FILENAME} >> ${PACKAGELIST_DIR}/Packages.Source.Buildroot.Names.all-arches
done
cat ${PACKAGELIST_DIR}/Packages.added.tmp | sort | uniq -cd | sed -n -e 's/^ *4 \(.*\)/\1/p' | sort -u -o ${PACKAGELIST_DIR}/Packages.added.common
cat ${PACKAGELIST_DIR}/Packages.Binary.Buildroot.tmp | sort | uniq -cd | sed -n -e 's/^ *4 \(.*\)/\1/p' | sort -u -o ${PACKAGELIST_DIR}/Packages.Binary.Buildroot.common
sort -u -o ${PACKAGELIST_DIR}/Packages.Source.Buildroot.Names.all-arches ${PACKAGELIST_DIR}/Packages.Source.Buildroot.Names.all-arches

if ! [ "${REPO_BASE}" == "released" ] ; then

  ## Generate the buildroot workload
  echo "Creating: ${VIEW}-buildroot-workload.yaml"
  rm -f ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  cat ${WORK_DIR}/conf/${VIEW}-buildroot-workload.head >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  cat ${PACKAGELIST_DIR}/Packages.added.common | awk '{print "        - " $1}' >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  echo "    arch_packages:" >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  for this_arch in ${ARCH_LIST[@]}
  do
    DATA_DIR="${DATA_DIR_BASE}/${this_arch}"
    echo "        ${this_arch}:" >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
    comm -13 ${PACKAGELIST_DIR}/Packages.added.common ${DATA_DIR}/${NEW_DIR}/added-binary-package-names.txt | awk '{print "            - " $1}' >> ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  done
  # Trim buildroot workload of packages we don't want in there
  for pkgname in ${BAD_PACKAGES[@]}
  do
    sed -i "/ ${pkgname}$/d" ${PACKAGELIST_DIR}/${VIEW}-buildroot-workload.yaml
  done

  ## Generate buildroot yaml
  # Start with the top of the package
  echo "Creating: buildroot-${VIEW}.yaml"
  rm -f ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
  cat ${WORK_DIR}/conf/buildroot-${VIEW}.head >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
  # Now add the base_buildroot
  echo "  Adding: base_buildroot"
  echo "  base_buildroot:" >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
  for this_arch in ${ARCH_LIST[@]}
  do
    echo "    ${this_arch}:"  >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
    DATA_DIR="${DATA_DIR_BASE}/${this_arch}/${NEW_DIR}"
    cat ${DATA_DIR}/CoreBuildRootBinaries | awk '{print "      - " $1}' >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
  done
  # Now add the source_packages
  echo "  Adding: source_packages"
  echo "  source_packages:" >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
  for this_arch in ${ARCH_LIST[@]}
  do
    echo "    ${this_arch}:"  >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
    DATA_DIR="${DATA_DIR_BASE}/${this_arch}/${NEW_DIR}"
    for this_package in $(ls -1 ${DATA_DIR}/output | grep '\-deps-binary$' | sed 's/-deps-binary$//')
    do
      echo "      ${this_package}:"  >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
      echo "        requires:"  >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
      cat ${DATA_DIR}/output/${this_package}-deps-binary | awk '{print "          - " $1}' >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
    done
  done
  # Now add the failed_buildroot
  echo "  Adding: failed_buildroot"
  echo "  failed_buildroot:" >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
  for this_arch in ${ARCH_LIST[@]}
  do
    echo "    ${this_arch}:"  >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
    DATA_DIR="${DATA_DIR_BASE}/${this_arch}/${NEW_DIR}"
    ls -1 ${DATA_DIR}/errors | sed -e 's/-BadDeps$//' -e 's/-NoInstall$//' | sort -u | awk '{print "      - " $1}' >> ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml
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
  cp ${PACKAGELIST_DIR}/buildroot-${VIEW}.yaml .
  git add buildroot-${VIEW}.yaml
  git commit -m "Update buildroot-${VIEW}.yaml $(date +%Y-%m-%d-%H:%M)"
  for this_arch in ${ARCH_LIST[@]}
  do
    DATA_DIR="${DATA_DIR_BASE}/${this_arch}/${NEW_DIR}"
    cp ${DATA_DIR}/buildroot-package-relations--view-${VIEW}--${this_arch}.json .
  done
  git add buildroot-package-relations*
  git commit -m "Update buildroot-package-relations json $(date +%Y-%m-%d-%H:%M)"
  git push
fi # end - only update if not released repo

exit 0

