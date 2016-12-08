# A platform neutral way to get the md5 hash sum of a file.
function md5sum_file() {
  if which md5sum > /dev/null 2>&1; then
    md5sum "$1" | awk '{ print $1 }'
  else
    md5 -q "$1"
  fi
}

# A platform neutral way to get the sha1 hash sum of a file.
function sha1sum_file() {
  if which sha1sum > /dev/null 2>&1; then
    sha1sum "$1" | awk '{ print $1 }'
  else
    shasum -a1 "$1" | awk '{ print $1 }'
  fi
}

# A platform neutral way to get the sha256 hash sum of a file.
function sha256sum_file() {
  if which sha256sum > /dev/null 2>&1; then
    sha256sum "$1" | awk '{ print $1 }'
  else
    shasum -a256 "$1" | awk '{ print $1 }'
  fi
}

# Create an archive and print the hash values for that file.
function create_archive() {
  local directory=${1}
  local archive=${2}
  local files="${3}"
  # Change to the target directory.
  cd ${directory}
  tar -cvzf ${archive} ${files}
  echo "$(ls -hl ${archive} | cut -d ' ' -f 5) $(basename ${archive})"
  echo "$(md5sum_file ${archive}) $(basename ${archive})"
  echo "$(sha1sum_file ${archive}) $(basename ${archive})"
  echo "$(sha256sum_file ${archive}) $(basename ${archive})"
}

# Return the operating system of the host system.
function get_os() {
  local os
  # Get the kernel name.
  case "$(uname -s)" in
    Darwin)
      os=darwin
      ;;
    Linux)
      os=linux
      ;;
    *)
      echo "Unsupported OS.  Must be Linux or Mac OS X." >&2
      exit 1
      ;;
  esac
  echo ${os}
}

# Return the architecture of the host system.
function get_arch() {
  local arch
  # Get the machine hardware name.
  case "$(uname -m)" in
    x86_64*)
      arch=amd64
      ;;
    i?86_64*)
      arch=amd64
      ;;
    amd64*)
      arch=amd64
      ;;
    aarch64*)
      arch=arm64
      ;;
    arm64*)
      arch=arm64
      ;;
    arm*)
      arch=arm
      ;;
    i?86*)
      arch=x86
      ;;
    s390x*)
      arch=s390x
      ;;
    ppc64le*)
      arch=ppc64le
      ;;
    *)
      echo "Unsupported arch. Must be x86_64, 386, arm, arm64, s390x or ppc64le." >&2
      exit 1
      ;;
  esac
  echo "${arch}"
}
