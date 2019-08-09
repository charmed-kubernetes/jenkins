# Build charms and bundles
Builds the charms and bundles that make up the Charmed Kubernetes
deployment.

## Overview

This spec automates the building of charms in CI. The current method of
building is as follows:

1. Download all layers from the defined **LAYER_LIST**, **LAYER_INDEX**,
**LAYER_BRANCH**
2. Build each charms using **CHARM_LIST** and **CHARM_BRANCH**. This allows
the job to build for different risks, _ie. kubernetes-master@stable branch_.
3. Publishes the built charm to the charmstore for the particular channel
set by **TO_CHANNEL**

## Plan Phase
### Plugin: **charmstore**
Builds the charms that make up Kubernetes

### Plugin: **charmstore**
Buildes the bundles that make up Kubernetes

