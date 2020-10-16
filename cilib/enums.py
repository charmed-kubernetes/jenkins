"""Contains all the concrete variables used throughout job processing code"""

from pathlib import Path
import yaml

JOBS_PATH = Path("jobs")


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
