# -*- mode:yaml; -*-
- k8s-ci-charm:
    charmhub-entity: 'kubernetes-ci-charm'
    upstream: "https://github.com/charmed-kubernetes/jenkins.git"
    branch: main
    downstream: 'charmed-kubernetes/jenkins.git'
    build-resources: "cd {out_path}; bash {src_path}/build-k8s-ci-charm-resource.sh"
    namespace: 'containers'
    tags: ['k8s', 'k8s-ci-charm']