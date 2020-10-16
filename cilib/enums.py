"""Contains all the concrete variables used throughout job processing code"""

from pathlib import Path
import yaml

JOBS_PATH = Path("jobs")

# Current supported STABLE K8s MAJOR.MINOR release
# This should be updated whenever a new major.minor is released
K8S_STABLE_VERSION = "1.19"

# Next MAJOR.MINOR
K8S_NEXT_VERSION = "1.20"

# Supported Versions
K8S_SUPPORT_VERSION_LIST = yaml.safe_load(str(JOBS_PATH / 'includes/k8s-snap-support-versions.inc'))

# Kubernetes build source to go version map
K8S_GO_MAP = {
    "1.20": "go/1.15/stable",
    "1.19": "go/1.15/stable",
    "1.18": "go/1.13/stable",
    "1.17": "go/1.13/stable",
    "1.16": "go/1.13/stable",
    "1.15": "go/1.12/stable",
    "1.14": "go/1.12/stable",
    "1.13": "go/1.12/stable",
}

# Charm layer map
CHARM_LAYERS_MAP = yaml.safe_load(str(JOBS_PATH / 'includes/charm-layer-list.inc'))

# Charm map
CHARM_MAP = yaml.safe_load(str(JOBS_PATH / 'includes/charm-support-matrix.inc'))

# Charm Bundles
CHARM_BUNDLES_MAP = yaml.safe_load(str(JOBS_PATH / 'includes/charm-bundles-list.inc'))

# Ancillary map
ANCILLARY_MAP = yaml.safe_load(str(JOBS_PATH / 'includes/ancillary-list.inc'))

# Snap list
SNAP_LIST = yaml.safe_load(str(JOBS_PATH / 'includes/k8s-snap-list.inc'))

# Eks Snap list
EKS_SNAP_LIST = yaml.safe_load(str(JOBS_PATH / 'includes/k8s-eks-snap-list.inc'))

# Snap k8s version <-> track mapping
# Allows us to be specific in which tracks should get what major.minor and dictate when a release
# should be put into the latest track.
SNAP_K8S_TRACK_MAP = {
    "1.20": ["1.20/edge"],
    "1.19": ["1.19/stable", "1.19/candidate", "1.19/beta", "1.19/edge"],
    "1.18": ["1.18/stable", "1.18/candidate", "1.18/beta", "1.18/edge"],
    "1.17": ["1.17/stable", "1.17/candidate", "1.17/beta", "1.17/edge"],
    "1.16": ["1.16/stable", "1.16/candidate", "1.16/beta", "1.16/edge"]
}
