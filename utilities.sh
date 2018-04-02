# Define some common utility functions that are used by other scripts here.


# The maximum amount of seconds to wait in a loop.
MAXIMUM_WAIT_SECONDS=3600

# Download requires the url and the output directory or name.
function download() {
  local url=$1
  local destination=$2
  echo "Downloading ${url}"
  # -f fail silently
  # -L Follow location redirects
  # --retry three times
  # -o write output to a file
  curl -f -L --retry 3 ${url} -o ${destination}
  # Print out the size and sha256 hash sum of the archive.
  echo "$(ls -hl ${destination} | cut -d ' ' -f 5) $(basename ${destination})"
  echo "$(sha256sum_file ${destination}) $(basename ${destination})"
}

# The check_time function requires two parameters start_time and max_seconds.
function check_time() {
  local start_time=$1
  local maximum_seconds=$2
  local current_time=`date +"%s"`
  local difference=$(expr ${current_time} - ${start_time})
  # When the difference is greater than maximum seconds, exit this script.
  if [ ${difference} -gt ${maximum_seconds} ]; then
    echo "The process is taking more than ${maximum_seconds} seconds!"
    # End this script because too much time has passed.
    exit 3
  fi
}

# Run a command in a loop waiting for specific output use MAXIMUM_WAIT_SECONDS.
function run_and_wait() {
  local cmd=$1
  local match=$2
  local sleep_seconds=${3:-5}
  local start_time=`date +"%s"`
  # Run the command in a loop looking for output.
  until $(${cmd} | grep -q "${match}"); do 
    # Check the time so this does not loop forever.
    check_time ${start_time} ${MAXIMUM_WAIT_SECONDS}
    sleep ${sleep_seconds}
  done
}

# Wait for deployment to get ready.
function wait_for_ready() {
  local cmd='juju status'
  local sleep_seconds=30
  local start_time=`date +"%s"`
  # NB: If lines == 0, grep $? > 0 (wc -l got no lines). This will fail scripts
  # with set -e, but it's valid for us to have 0 lines here. Use || true to
  # ensure we don't error out of this function unintentionally.
  lines=$(${cmd} | grep  -e "waiting" -e "executing" -e "maintenance" -e "blocked" -e "error" | wc -l) || true
  until (( $lines <= 0 )); do
    # Check the time so this does not loop forever.
    check_time ${start_time} ${MAXIMUM_WAIT_SECONDS}
    sleep ${sleep_seconds}
    lines=$(${cmd} | grep  -e "waiting" -e "executing" -e "maintenance" -e "blocked" -e "error" | wc -l) || true
  done
}

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
  local directory=$1
  shift
  local archive=$1
  shift
  # The rest of the arguments are for the tar command.
  local files="$@"
  # Change to the target directory.
  cd ${directory}
  tar -cvzf ${archive} ${files}
  echo "$(ls -hl ${archive} | cut -d ' ' -f 5) $(basename ${archive})"
  echo "$(md5sum_file ${archive}) $(basename ${archive})"
  echo "$(sha1sum_file ${archive}) $(basename ${archive})"
  echo "$(sha256sum_file ${archive}) $(basename ${archive})"
  cd -
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

# Get the major.minor part of a version of the format vX.Y.Z
function get_major_minor() {
  local version=$1
  # version is of format vX.Y.Z
  echo `expr "${version#v}" : '\(.[0-9]*.[0-9]*\)'`
}

# Get the previous version of X.Y
function get_prev_major_minor() {
  local version=$1
  # version is of format X.Y
  X="$(expr "${version#v}" : '\(.[0-9]*\)')"
  Y="$(expr "${version#*.}" : '\(.[0-9]*\)')"
  if [ "$Y" != "0" ]
  then
    Y=$(expr $Y - 1)
    echo "$X.$Y"
  else
    X=$(expr $X - 1)
    Y="0"
    while wget -S --spider https://dl.k8s.io/release/stable-$X.$Y.txt  2>&1 | grep 'HTTP/1.1 200 OK' > /dev/null
    do
      OK_Y=$Y
      Y=$(expr $Y + 1)
    done
    echo "$X.${OK_Y}"
  fi
}

# Create a release tag at gh_owner/gh_repo
function tag_release() {
  gh_owner=$1
  gh_repo=$2
  gh_branch=$3
  gh_user=$4
  gh_token=$5
  tag=$6

  rm -rf /tmp/repo2tag
  mkdir /tmp/repo2tag
  (
    cd /tmp/repo2tag
    git clone https://github.com/${gh_owner}/${gh_repo}.git
    cd ${gh_repo}
    git checkout ${gh_branch}
    if git rev-parse -q --verify "refs/tags/$tag" >/dev/null
    then
      echo "Tag $tag already present"
    else
      git tag ${tag}
      git push https://${gh_user}:${gh_token}@github.com/${gh_owner}/${gh_repo}.git ${tag}
    fi
  )
  rm -rf /tmp/repo2tag
}

# Create a branch in gh_owner/gh_repo
function create_branch() {

  gh_owner=$1
  gh_repo=$2
  gh_user=$3
  gh_token=$4
  branch=$5

  rm -rf /tmp/repo2branch
  mkdir /tmp/repo2branch
  (
    cd /tmp/repo2branch
    git clone https://github.com/${gh_owner}/${gh_repo}.git
    cd ${gh_repo}
    git checkout -b ${branch}
    git push https://${gh_user}:${gh_token}@github.com/${gh_owner}/${gh_repo}.git --all
  )
  rm -rf /tmp/repo2branch
}
