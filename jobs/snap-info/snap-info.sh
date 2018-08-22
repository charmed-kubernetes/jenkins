#!/bin/bash
#

# This script creates an HTML table to be shown on our dashboard.
# The table shows the release version and snap revision
# of the kubectl snap we have released.

declare -a TRACKS=('1.14' '1.13' '1.12' '1.11' '1.10' '1.9' '1.8');
declare -a CHANNELS=('stable' 'candidate' 'beta' 'edge');
declare -a ARCHS=('amd64' 's390x' 'arm64');

SNAPCRAFT_INFO=$(snapcraft list-revisions kubectl)


function find_release {
    # Finds the release k8s version and snap revision in a track/channel
    #
    # Input:
    # TRACK track to search for
    # CHANNEL channel to search for
    # ARCH architecture we are interested in
    # Outpu:
    # $RELEASE the release
    if [[ $TRACK == "none" ]]
    then
      export RELEASE=$(echo "$SNAPCRAFT_INFO" | grep " $CHANNEL\*" | grep "$ARCH" | awk '{print $4" ("$1")"}')
    else
      export RELEASE=$(echo "$SNAPCRAFT_INFO" | grep "$TRACK/$CHANNEL\*" | grep "$ARCH" | awk '{print $4" ("$1")"}')
    fi
}


function print_table {
    # print table for an architecture
    #
    # Input:
    # ARCH architecture we are interested in

    echo -n "<center><table width=\"100%\">" >> results.html
    echo -n "  <tr>" >> results.html

    # Print table headers #
    echo -n "    <th align=\"left\">track</th>" >> results.html
    for CHANNEL in ${CHANNELS[@]}
    do
      echo -n "    <th align=\"left\">$CHANNEL</th>" >> results.html
    done
    echo -n "  </tr>" >> results.html
    echo -n "  <tr>" >> results.html

    # Print info for no specific track #
    TRACK="none"
    echo -n "  <td>$TRACK</td>" >> results.html
    for CHANNEL in ${CHANNELS[@]}
    do
      find_release $TRACK $CHANNEL
      echo -n "    <td>$RELEASE</td>" >> results.html
    done
    echo -n "  </tr>" >> results.html

    # Print info for each track #
    for TRACK in ${TRACKS[@]}
    do
      echo -n "  <tr>" >> results.html
      if [[ $SNAPCRAFT_INFO == *$TRACK/edge* ]]
      then
        echo -n "  <td>$TRACK</td>" >> results.html
        for CHANNEL in ${CHANNELS[@]}
        do
          find_release $TRACK $CHANNEL
          echo -n "    <td>$RELEASE</td>" >> results.html
        done
        echo -n "  </tr>" >> results.html
      fi
    done
    echo -n "</table></center>" >> results.html
}


DATE=$(date)
echo -n "" > results.html
for ARCH in ${ARCHS[@]}
do
  echo -n "<hl> <center>$ARCH at $DATE</center>" >> results.html
  print_table $ARCH
done

# The output must be a single line so the job description setter plugin will
# grab it. The marker -> is what the description plugin setter script will
# need to search for in its regex
RES=$(cat ./results.html)
echo "$RES"
