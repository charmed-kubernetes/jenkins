# Name

- **Job**: `aws-iam-docker`

# Description

Build aws-iam-authenticator from source and published the image. The default values pull from
github.com/kubernetes-sigs/aws-iam-authenticator and push to
rocks.canonical.com:5000/cdk/aws-iam-authenticator. By default, the source will be changed
to the latest release tag and the image will be tagged the same.
