#!/bin/bash

set -ex
source ./maintenance/helpers-lxc-node.sh

container=${NODE_NAME:-"juju-client-box"}

lxc launch ubuntu:16.04 $container

while ! lxc info $container | grep -qE 'eth0:\sinet\s'; do
    sleep 3
done

PUSH integration-tests/install-deps.sh /root/
RUN /root/install-deps.sh

PUSH microk8s/install-deps.sh /root/
RUN /root/install-deps.sh

RUN mkdir -p /root/.local/share/juju

PUSH ~/.local/share/juju/accounts.yaml /root/.local/share/juju/
PUSH ~/.local/share/juju/models.yaml /root/.local/share/juju/
PUSH ~/.local/share/juju/controllers.yaml /root/.local/share/juju/
PUSH ~/.local/share/juju/credentials.yaml /root/.local/share/juju/ 
RUN mkdir -p /var/lib/jenkins/.local/share/juju
PUSH ~/.local/share/juju/foo.json /var/lib/jenkins/.local/share/juju/

# libjuju needs this
PUSH ~/.go-cookies /root/.go-cookies

# Allow ssh access
RUN mkdir -p /root/.ssh
PUSH ~/.ssh/id_rsa.pub /root/.ssh/authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys
RUN chown root:root /root/.ssh/authorized_keys

# Jenkins agent needs java
RUN apt-get install -y default-jre

RUN mkdir -p /root/bin
RUN wget https://ci.kubernetes.juju.solutions/jnlpJars/slave.jar
RUN mv slave.jar /root/bin

echo "Your lxc container is ready to be added as jenkins node."
echo "Go to Manage Jenkins -> Manage Nodes -> New Node and select"
echo "Launch agent via execution of command on the master and enter the following:"
echo "ssh -o StrictHostKeyChecking=no -v root@<container_ip> java -jar ~/bin/slave.jar"
lxc list
