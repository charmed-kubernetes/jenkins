# CI Infrastructure
Provides support tasks for maintaining Jenkins
## Ansible

Ansible playbook is run nightly to make sure each system is kept updated,
reset to a reasonable working state (we aren't immutable yet) and cleaning
up any cloud resources.

The playbook used is located in `jobs/infra/playbook-jenkins.yml`.

Credentials used in the playbook are pulled from the Jenkins Credentials
store, attempting to run this locally would require that those credential
environment variables are met (seen in `jobs/ci-master.yaml` under `-
wrapper` section.

