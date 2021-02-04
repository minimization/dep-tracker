# shell configuration variables
#
# Include this file by using the following convention in the main script
#   WORK_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
#   source $WORK_DIR/conf/config.inc

if [ ! -v WORK_DIR ]; then
    echo "Programming error: \$WORK_DIR must be set" >&2
    exit 1
fi

: ${VERBOSE:="FALSE"}

#####
# Variables
#####
ARCH_LIST=(aarch64 ppc64le s390x x86_64)
URL_BASE="https://tiny.distro.builders/"
# DIRS
CONF_DIR="${WORK_DIR}/conf"
REPO_DIR="${WORK_DIR}/repos"
GIT_DIR="${WORK_DIR}/git"
CACHE_DIR="${WORK_DIR}/cache"
PACKAGELIST_DIR="${CONF_DIR}"
PACKAGE_DIR_BASE="${WORK_DIR}/packages"
# FILES/VARIABLES
PACKAGE_LIST_HEAD="Packages"
PACKAGE_NVR_LIST_HEAD="Package-NVRs"
SOURCE_LIST_HEAD="Sources"
SOURCE_NVR_LIST_HEAD="Source-NVRs"
REPONAME="eln"
NEW_DIR="new"
LAST_DIR="last"
BR_BINARY_NVRS_FILENAME="buildroot-binary-package-nvrs.txt"
BR_BINARY_PKGNAMES_FILENAME="buildroot-binary-package-names.txt"
BR_SOURCE_NVRS_FILENAME="buildroot-source-package-nvrs.txt"
BR_SOURCE_PKGNAMES_FILENAME="buildroot-source-package-names.txt"
BR_ARCHFUL_SOURCE_PKGNAMES_FILENAME="buildroot-archful-srpm-names.txt"
BR_SOURCE_PKGMAP_FILENAME="buildroot-package-to-srpm-map.txt"
BR_TIMESTAMP_FILENAME="buildroot-date-check.txt"
EMAIL_LIST="tdawson@redhat.com"
DT_ACTION_LIST="email"

###############
# Show help
###############
usage() {
  echo >&2
  echo "Usage `basename $0` <options> [ [--] ...]" >&2
  echo >&2
  echo "Options:" >&2
  echo "  -r | --repo [reponame]" >&2
  echo "    Use the repo file.  Default: ${REPONAME}" >&2
  echo "  -p | --pkglist [packagelist-dir]" >&2
  echo "    Package lists are in this dir.  Default: ${PACKAGELIST_DIR} " >&2
  echo >&2
  popd &>/dev/null
  exit 1
}

###############
# Get our arguments
###############
while [[ "$#" -ge 1 ]]
do
  case "$1" in
    -r | --repo )
        REPONAME="${2}"
        shift 2
        ;;
    -p | --pkglist )
        PACKAGELIST_DIR="${2}"
        shift 2
        ;;
    -- )
        shift
        break
        ;;
    -* )
        echo "Unknown option: $1" >&2
        usage
        ;;
    * )
        break
        ;;
  esac
done

#####
# Repo configs
#####
if echo ${REPONAME} | grep -q archful-source ; then
  REPO_BASE=$(echo ${REPONAME} | cut -d'-' -f1)
  if ! [ -s ${REPO_DIR}/${REPONAME}.repo ] ; then
    cp ${REPO_DIR}/${REPONAME}.repo.template ${REPO_DIR}/${REPONAME}.repo
    sed -i "s|BASE-DIR|${WORK_DIR}/data-${REPO_BASE}|" ${REPO_DIR}/${REPONAME}.repo
  fi
else
  REPO_BASE=${REPONAME}
fi

for this_arch in ${ARCH_LIST[@]}
do
  if ! [ -s ${REPO_DIR}/${REPONAME}.${this_arch}.repo ] ; then
    mkdir -p ${CACHE_DIR}/${REPONAME}-${this_arch}
    cp ${REPO_DIR}/${REPONAME}.repo.localcache.template ${REPO_DIR}/${REPONAME}.${this_arch}.repo
    sed -i "s|CACHE-DIR|${CACHE_DIR}/${REPONAME}-${this_arch}|" ${REPO_DIR}/${REPONAME}.${this_arch}.repo
    if echo ${REPONAME} | grep -q archful-source ; then
      sed -i "s|BASE-DIR|${WORK_DIR}/data-${REPO_BASE}|" ${REPO_DIR}/${REPONAME}.${this_arch}.repo
    fi
  fi
done

#####
# Variables
#   That might change with command line options
#####
DATA_DIR_BASE="${WORK_DIR}/data-${REPO_BASE}"
DNF_OPTIONS_BASE="-c ${REPO_DIR}/${REPONAME}.repo --disablerepo=* --enablerepo=dt-main --enablerepo=dt-main-source -y"
DNF_OPTIONS_NOCONF_BASE="--disablerepo=* --enablerepo=dt-main --enablerepo=dt-main-source -y"
DNF_OPTIONS_SOURCE_ONLY="-c ${REPO_DIR}/${REPONAME}.repo --disablerepo=* --enablerepo=dt-main-source"
DNF_OPTIONS_BINARY_ONLY="-c ${REPO_DIR}/${REPONAME}.repo --disablerepo=* --enablerepo=dt-main"

