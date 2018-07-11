#!/bin/bash
#

# This script creates an HTML table to be shown on our dashboard.
# The table shows the release version and snap revision
# of the kubectl snap we have released.

declare -a TRACKS=('1.14' '1.13' '1.12' '1.11' '1.10' '1.9' '1.8');
declare -a CHANNELS=('stable' 'candidate' 'beta' 'edge');

SNAP_INFO=$(snap info kubectl)

function find_release {
    # Finds the release k8s version and snap revision in a track/channel
    #
    # Input:
    # TRACK track to search for
    # CHANNEL channel to search for
    # Outpu:
    # $RELEASE the release
    if [[ $TRACK == "none" ]]
    then
      export RELEASE=$(echo "$SNAP_INFO" | grep " $CHANNEL:" | awk '{print $2" "($3)}')
    else
      export RELEASE=$(echo "$SNAP_INFO" | grep "$TRACK/$CHANNEL:" | awk '{print $2" "($3)}')
    fi
}

echo -n "<center><table width=\"100%\">" > results.html
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
  if [[ $SNAP_INFO == *$TRACK/edge* ]]
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

# The output must be a single line so the job description setter plugin will
# grab it. The marker -> is what the description plugin setter script will
# need to search for in its regex
RES=$(cat ./results.html)
echo "->$RES"