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
# DIRS
CONF_DIR="${WORK_DIR}/conf"
REPO_DIR="${WORK_DIR}/repos"
GIT_DIR="${WORK_DIR}/git"
DATA_DIR_BASE="${WORK_DIR}/data"
PACKAGELIST_DIR="${CONF_DIR}"
PACKAGE_DIR_BASE="${WORK_DIR}/packages"
# FILES/VARIABLES
PACKAGE_LIST_HEAD="Packages"
SOURCE_LIST_HEAD="Sources"
REPONAME="rawhide"
NEW_DIR="new"
LAST_DIR="last"
BR_BINARY_PKGNAMES_FILENAME="buildroot-binary-package-names.txt"
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
# Variables
#   That might change with command line options
#####
DNF_OPTIONS_BASE="-c ${REPO_DIR}/${REPONAME}.repo --disablerepo=* --enablerepo=dt-main --enablerepo=dt-main-source -y"
DNF_OPTIONS_SOURCE_ONLY="-c ${REPO_DIR}/${REPONAME}.repo --disablerepo=* --enablerepo=dt-main-source"
DNF_OPTIONS_BINARY_ONLY="-c ${REPO_DIR}/${REPONAME}.repo --disablerepo=* --enablerepo=dt-main"
