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
DATA_DIR_BASE="${WORK_DIR}/data"
PACKAGE_DIR_BASE="${WORK_DIR}/packages"
# FILES/VARIABLES
PACKAGE_LIST_HEAD="Packages"
NEW_DIR="new"
LAST_DIR="last"
DNF_OPTIONS_BASE="-c ${REPO_DIR}/rawhide.repo --disablerepo=* --enablerepo=dt-rawhide --enablerepo=dt-rawhide-source -y"
DNF_OPTIONS_SOURCE_ONLY="-c ${REPO_DIR}/rawhide.repo --disablerepo=* --enablerepo=dt-rawhide-source"
DNF_OPTIONS_BINARY_ONLY="-c ${REPO_DIR}/rawhide.repo --disablerepo=* --enablerepo=dt-rawhide"
BR_BINARY_PKGNAMES_FILENAME="buildroot-binary-package-names.txt"
BR_SOURCE_PKGNAMES_FILENAME="buildroot-source-package-names.txt"
BR_ARCHFUL_SOURCE_PKGNAMES_FILENAME="buildroot-archful-srpm-names.txt"
BR_TIMESTAMP_FILENAME="buildroot-date-check.txt"
