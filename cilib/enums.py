"""Contains all the concrete variables used throughout job processing code"""

from pathlib import Path
import yaml

JOBS_PATH = Path("jobs")

# Current supported STABLE K8s MAJOR.MINOR release. This determines what the
# latest/stable channel is set to. It should be updated whenever a new CK
# major.minor is GA.
K8S_STABLE_VERSION = "1.32"

# Next MAJOR.MINOR
# This controls whether or not we publish pre-release snaps in our channels.
# Typically, this is K8S_STABLE_VERSION+1. However, when preparing the next
# stable release, this will be +2. For example, 1.30 is currently stable and
# we're working on the 1.31 GA. Set this value to '1.32' sometime between the
# final RC and GA so we don't get pre-release builds (e.g. 1.31.1-alpha.0) in
# our 1.31 tracks.
K8S_NEXT_VERSION = "1.33"

# Lowest K8S SEMVER to process, this is usually K8S_STABLE_VERSION - 4
K8S_STARTING_SEMVER = "1.28.0"

# Supported arches
K8S_SUPPORT_ARCHES = ["amd64", "ppc64el", "s390x", "arm64"]

# Supported charm arches
K8S_CHARM_SUPPORT_ARCHES = ["amd64", "s390x", "arm64"]

# Support series map
K8S_SERIES_MAP = {
    "xenial": "16.04",
    "bionic": "18.04",
    "focal": "20.04",
    "jammy": "22.04",
    "noble": "24.04",
}

# Kubernetes CNI version
K8S_CNI_SEMVER = "0.8"

# Cri tools version
K8S_CRI_TOOLS_SEMVER = "1.19"

# Kubernetes build source to go version map
K8S_GO_MAP = {
    "1.33": "go/latest/edge",
    "1.32": "go/1.23/stable",
    "1.31": "go/1.22/stable",
    "1.30": "go/1.22/stable",
    "1.29": "go/1.21/stable",
    "1.28": "go/1.20/stable",
    "1.27": "go/1.20/stable",
    "1.26": "go/1.19/stable",
    "1.25": "go/1.19/stable",
    "1.24": "go/1.19/stable",
    "1.23": "go/1.19/stable",
    "1.22": "go/1.16/stable",
    "1.21": "go/1.16/stable",
    "1.20": "go/1.15/stable",
    "1.19": "go/1.15/stable",
    "1.18": "go/1.13/stable",
    "1.17": "go/1.13/stable",
    "1.16": "go/1.13/stable",
}

# Snap k8s version <-> track mapping
# Allows us to be specific in which tracks should get what major.minor and dictate
# when a release should be put into the latest track.
SNAP_K8S_TRACK_LIST = [
    ("1.16", ["1.16/stable", "1.16/candidate", "1.16/beta", "1.16/edge"]),
    ("1.17", ["1.17/stable", "1.17/candidate", "1.17/beta", "1.17/edge"]),
    ("1.18", ["1.18/stable", "1.18/candidate", "1.18/beta", "1.18/edge"]),
    ("1.19", ["1.19/stable", "1.19/candidate", "1.19/beta", "1.19/edge"]),
    ("1.20", ["1.20/stable", "1.20/candidate", "1.20/beta", "1.20/edge"]),
    ("1.21", ["1.21/stable", "1.21/candidate", "1.21/beta", "1.21/edge"]),
    ("1.22", ["1.22/stable", "1.22/candidate", "1.22/beta", "1.22/edge"]),
    ("1.23", ["1.23/stable", "1.23/candidate", "1.23/beta", "1.23/edge"]),
    ("1.24", ["1.24/stable", "1.24/candidate", "1.24/beta", "1.24/edge"]),
    ("1.25", ["1.25/stable", "1.25/candidate", "1.25/beta", "1.25/edge"]),
    ("1.26", ["1.26/stable", "1.26/candidate", "1.26/beta", "1.26/edge"]),
    ("1.27", ["1.27/stable", "1.27/candidate", "1.27/beta", "1.27/edge"]),
    ("1.28", ["1.28/stable", "1.28/candidate", "1.28/beta", "1.28/edge"]),
    ("1.29", ["1.29/stable", "1.29/candidate", "1.29/beta", "1.29/edge"]),
    ("1.30", ["1.30/stable", "1.30/candidate", "1.30/beta", "1.30/edge"]),
    ("1.31", ["1.31/stable", "1.31/candidate", "1.31/beta", "1.31/edge"]),
    ("1.32", ["1.32/stable", "1.32/candidate", "1.32/beta", "1.32/edge"]),
    ("1.33", ["1.33/edge"]),
]
SNAP_K8S_TRACK_MAP = dict(SNAP_K8S_TRACK_LIST)

# Deb k8s version <-> ppa mapping
DEB_K8S_TRACK_MAP = {
    "1.16": "ppa:k8s-maintainers/1.16",
    "1.17": "ppa:k8s-maintainers/1.17",
    "1.18": "ppa:k8s-maintainers/1.18",
    "1.19": "ppa:k8s-maintainers/1.19",
    "1.20": "ppa:k8s-maintainers/1.20",
    "1.21": "ppa:k8s-maintainers/1.21",
    "1.22": "ppa:k8s-maintainers/1.22",
    "1.23": "ppa:k8s-maintainers/1.23",
    "1.24": "ppa:k8s-maintainers/1.24",
    "1.25": "ppa:k8s-maintainers/1.25",
    "1.26": "ppa:k8s-maintainers/1.26",
    "1.27": "ppa:k8s-maintainers/1.27",
    "1.28": "ppa:k8s-maintainers/1.28",
    "1.29": "ppa:k8s-maintainers/1.29",
    "1.30": "ppa:k8s-maintainers/1.30",
    "1.31": "ppa:k8s-maintainers/1.31",
    "1.32": "ppa:k8s-maintainers/1.32",
    "1.33": "ppa:k8s-maintainers/1.33",
}


# Charm layer map
CHARM_LAYERS_MAP = yaml.safe_load(
    Path(JOBS_PATH / "includes/charm-layer-list.inc").read_text(encoding="utf8")
)

# Charm map
CHARM_MAP = yaml.safe_load(
    Path(JOBS_PATH / "includes/charm-support-matrix.inc").read_text(encoding="utf8")
)

# Charm Bundles
CHARM_BUNDLES_MAP = yaml.safe_load(
    Path(JOBS_PATH / "includes/charm-bundles-list.inc").read_text(encoding="utf8")
)

# Ancillary map
ANCILLARY_MAP = yaml.safe_load(
    Path(JOBS_PATH / "includes/ancillary-list.inc").read_text(encoding="utf8")
)

# Snap list
SNAP_LIST = yaml.safe_load(
    Path(JOBS_PATH / "includes/k8s-snap-list.inc").read_text(encoding="utf8")
)

# Eks Snap list
EKS_SNAP_LIST = yaml.safe_load(
    Path(JOBS_PATH / "includes/k8s-eks-snap-list.inc").read_text(encoding="utf8")
)
