# shared shell utility functions for dep-track scripts

# eecho message ...
# message: text to write to error output
#
# writes message to error output
eecho() {
    echo "$@" >&2
}


# errexit message ...
# message: text to write to error output
#
# writes message to error output and exits
errexit() {
    echo "$@" >&2
    exit 5
}


# pkgname_from_srpm_file srpm
# srpm: a source rpm file path
#
# return package name string from given SRPM file
pkgname_from_srpm_file() {
  local srpm="$1"

  rpm -q --nosignature --qf "%{name}" -p ${srpm}
}


# evr_from_srpm_file srpm
# srpm: a source rpm file path
#
# return EVR (epoch-version-release) string from given SRPM file
evr_from_srpm_file() {
  local srpm="$1"

  rpm -q --nosignature --qf "%{evr}" -p ${srpm}
}


# order_srpm_files srpm1 srpm2
# srpm1: a source rpm file path
# srpm2: another source rpm file path
#
# return older file first based on NVR, newer second
order_srpm_files() {
  local srpm1="$1" srpm2="$2"
  local evr1 evr2
  local cmpstat

  evr1=$(evr_from_srpm_file ${srpm1})
  evr2=$(evr_from_srpm_file ${srpm2})

  if [ -z "$evr1" -o -z "$evr2" ]; then
    eecho "Unable to compare $srpm1 and $srpm2!"
    return
  fi

  rpmdev-vercmp "$evr1" "$evr2" >/dev/null
  cmpstat="$?"
  case "$cmpstat" in
  0)  # EVRs are equal
    echo "$srpm1" "$srpm2"
    ;;
  11) # EVR1 is newer
    echo "$srpm2" "$srpm1"
    ;;
  12) # EVR2 is newer
    echo "$srpm1" "$srpm2"
    ;;
  *)  # problems
    eecho "Unable to compare $srpm1 and $srpm2!"
    ;;
  esac
}
