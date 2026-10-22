#!/bin/bash
# Mirror the container images Charmed Kubernetes needs into ghcr.io/canonical/cdk.
set -euo pipefail
shopt -s inherit_errexit

TARGET_REGISTRY=ghcr.io/canonical/cdk
ARCHES="amd64 arm64 ppc64le s390x"
# Source prefixes stripped to form the target path; first match wins.
SOURCE_PREFIXES="k8s.gcr.io/ us.gcr.io/ docker.io/library/ docker.io/ gcr.io/ nvcr.io/ quay.io/ registry.k8s.io/"
REGSYNC_VERSION=v0.11.6
REGSYNC_SHA256=138aed7deddea6e4d34bdc98d0111bd03927a430caa47b47b22081cd57e4fced

BUNDLE_DIR=${BUNDLE_DIR:-bundle}
IMAGE_LIST=$BUNDLE_DIR/container-images.txt
STATE_DIR=${STATE_DIR:-.sync-oci-images}
KUBE_VERSIONS_FILE=$STATE_DIR/kube-versions
REGSYNC=$STATE_DIR/regsync

usage() {
    echo "usage: $0 {prepare|sync|publish}" >&2
    exit 2
}

require_env() {
    local name
    for name in "$@"; do
        [[ -n ${!name:-} ]] || { echo "missing required environment: $name" >&2; exit 2; }
    done
}

is_dry_run() {
    [[ ${IS_DRY_RUN:?IS_DRY_RUN must be true or false} == true ]]
}

# Latest patch tag for a minor release, e.g. 1.36 -> v1.36.5.
resolve_kube_version() {
    local minor=$1 channel
    for channel in stable latest; do
        if curl -fsSL "https://dl.k8s.io/release/${channel}-${minor}.txt"; then
            return 0
        fi
    done
    echo "could not determine Kubernetes version for $minor" >&2
    return 1
}

# Replace or add the "<key>: images" line, keeping the file sorted and newline-terminated.
set_image_line() {
    local file=$1 line=$2 key
    key=${line%%: *}
    if [[ -s $file && -n $(tail -c1 "$file") ]]; then
        echo >> "$file"
    fi
    if grep -q "^${key}: " "$file"; then
        sed -i -e "s|^${key}: .*|${line}|" "$file"
    else
        echo "$line" >> "$file"
    fi
    sort -o "$file" "$file"
}

# Images listed under the given keys, expanded for every arch, one per line.
expand_images() {
    local arch key
    for key in "$@"; do
        grep -q "^${key}: " "$IMAGE_LIST" || { echo "missing '${key}:' line in $IMAGE_LIST" >&2; return 1; }
    done
    for arch in $ARCHES; do
        for key in "$@"; do
            grep "^${key}: " "$IMAGE_LIST" | cut -d' ' -f2- \
                | sed -e "s|{{ arch }}|${arch}|g" -e "s|{{ multiarch_workaround }}||g"
        done
    done | tr ' ' '\n' | sed '/^$/d' | sort -u
}

# Images already published under TARGET_REGISTRY, in either registry name.
is_hosted() {
    [[ $1 == "$TARGET_REGISTRY/"* || $1 == rocks.canonical.com/cdk/* ]]
}

# Reference under which an image is published in TARGET_REGISTRY.
published_ref() {
    local image=$1 prefix
    if [[ $image == rocks.canonical.com/cdk/* ]]; then
        echo "$TARGET_REGISTRY/${image#rocks.canonical.com/cdk/}"
        return
    fi
    if [[ $image == "$TARGET_REGISTRY/"* ]]; then
        echo "$image"
        return
    fi
    for prefix in $SOURCE_PREFIXES; do
        if [[ $image == "$prefix"* ]]; then
            echo "$TARGET_REGISTRY/${image#"$prefix"}"
            return
        fi
    done
    echo "no target mapping for image: $image" >&2
    return 1
}

bundle_commit() {
    local message=$1
    if [[ -n $(git -C "$BUNDLE_DIR" status --porcelain) ]]; then
        git -C "$BUNDLE_DIR" add -A
        git -C "$BUNDLE_DIR" commit -q -m "$message"
        echo "Committed: $message"
    fi
}

prepare() {
    require_env CK_VERSIONS
    local minor kube_version addons_branch addons_dir upstream_line
    rm -rf "$BUNDLE_DIR" "$STATE_DIR" cdk-addons-*
    mkdir -p "$STATE_DIR"
    git clone -q --depth 1 --branch main https://github.com/charmed-kubernetes/bundle.git "$BUNDLE_DIR"

    for minor in $CK_VERSIONS; do
        kube_version=$(resolve_kube_version "$minor")
        echo "$minor $kube_version" >> "$KUBE_VERSIONS_FILE"

        addons_dir=cdk-addons-$minor
        addons_branch=release-$minor
        if git ls-remote --exit-code --heads https://github.com/charmed-kubernetes/cdk-addons.git "$addons_branch" >/dev/null; then
            git clone -q --depth 1 --branch "$addons_branch" https://github.com/charmed-kubernetes/cdk-addons.git "$addons_dir"
        else
            echo "No cdk-addons $addons_branch branch; using the default branch."
            git clone -q --depth 1 https://github.com/charmed-kubernetes/cdk-addons.git "$addons_dir"
        fi

        upstream_line=$(make -s -C "$addons_dir" KUBE_VERSION="$kube_version" upstream-images | grep "^${kube_version}-upstream: ")
        set_image_line "$IMAGE_LIST" "$upstream_line"
        bundle_commit "Updating ${kube_version}-upstream: images"
    done
}

install_regsync() {
    curl -fsSL -o "$REGSYNC" "https://github.com/regclient/regclient/releases/download/${REGSYNC_VERSION}/regsync-linux-amd64"
    echo "$REGSYNC_SHA256  $REGSYNC" | sha256sum -c --quiet -
    chmod +x "$REGSYNC"
}

# jujud-operator tags for every Juju version published in the snap store.
jujud_operator_images() {
    snap info juju | grep -E '[0-9]+\.[0-9]+\.[0-9]+ ' | awk '{print "docker.io/jujusolutions/jujud-operator:" $2}' | sort -u
}

sync_images() {
    require_env GHCR_CREDS_USR GHCR_CREDS_PSW DOCKERHUB_CREDS_USR DOCKERHUB_CREDS_PSW
    local keys=(ci-static) minor kube_version images image target config
    while read -r minor kube_version; do
        keys+=("v${minor}-static" "${kube_version}-upstream")
    done < "$KUBE_VERSIONS_FILE"
    images=$({ jujud_operator_images; expand_images "${keys[@]}"; } | sort -u)

    config=$STATE_DIR/regsync.yaml
    cat > "$config" <<'EOF'
version: 1
creds:
  - registry: ghcr.io
    user: '{{ env "GHCR_CREDS_USR" }}'
    pass: '{{ env "GHCR_CREDS_PSW" }}'
  - registry: docker.io
    user: '{{ env "DOCKERHUB_CREDS_USR" }}'
    pass: '{{ env "DOCKERHUB_CREDS_PSW" }}'
sync:
EOF
    for image in $images; do
        is_hosted "$image" && continue
        target=$(published_ref "$image")
        printf '  - source: %s\n    target: %s\n    type: image\n' "$image" "$target" >> "$config"
    done

    install_regsync
    if is_dry_run; then
        "$REGSYNC" -c "$config" check
    else
        "$REGSYNC" -c "$config" once
    fi
}

# Per-release list of the published image references, e.g. container-images/v1.36.5.txt.
write_release_reports() {
    local minor kube_version images image report
    while read -r minor kube_version; do
        images=$(expand_images "v${minor}-static" "${kube_version}-upstream")
        report=$BUNDLE_DIR/container-images/${kube_version}.txt
        mkdir -p "$(dirname "$report")"
        : > "$report"
        for image in $images; do
            published_ref "$image" >> "$report"
        done
        sort -u -o "$report" "$report"
        bundle_commit "Updating container-images/${kube_version}.txt"
    done < "$KUBE_VERSIONS_FILE"
}

publish() {
    write_release_reports
    if [[ -z $(git -C "$BUNDLE_DIR" log --oneline origin/main..HEAD) ]]; then
        echo "No image list changes; nothing to push."
        return
    fi
    if is_dry_run; then
        echo "Dry run; would have pushed to charmed-kubernetes/bundle:"
        git -C "$BUNDLE_DIR" log --stat origin/main..HEAD
        return
    fi
    require_env GITHUB_CREDS_USR GITHUB_CREDS_PSW
    git -C "$BUNDLE_DIR" pull -q --rebase origin main
    git -C "$BUNDLE_DIR" push -q "https://${GITHUB_CREDS_USR}:${GITHUB_CREDS_PSW}@github.com/charmed-kubernetes/bundle.git" HEAD:main
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    case ${1:-} in
        prepare) prepare ;;
        sync) sync_images ;;
        publish) publish ;;
        *) usage ;;
    esac
fi
