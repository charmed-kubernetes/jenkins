#!/bin/bash

set -ex
source ./maintenance/helpers-lxc-node.sh

container=${NODE_NAME:-"juju-client-box"}

lxc launch ubuntu:16.04 $container

while ! lxc info $container | grep -qE 'eth0:\sinet\s'; do
    sleep 3
done

RUN add-apt-repository -y ppa:juju/stable
RUN apt update -yq
RUN apt install -y juju unzip python3-pip python-pip charm-tools squashfuse snapd
RUN pip2 install 'git+https://github.com/juju-solutions/bundletester' \
                 'git+https://github.com/juju-solutions/cloud-weather-report' \
                 'git+https://github.com/juju/juju-crashdump'
RUN pip3 install 'git+https://github.com/juju/python-libjuju' \
                 'git+https://github.com/juju-solutions/matrix' \
                 'git+https://github.com/juju/amulet'


RUN pip2 install -U charm-tools pyopenssl
RUN pip3 install -U pytest  pytest-asyncio asyncio_extras juju requests pyyaml kubernetes
RUN snap install conjure-up --classic

RUN mkdir -p /srv/artifacts
RUN mkdir -p /root/.local/share/juju

PUSH ~/.local/share/juju/accounts.yaml /root/.local/share/juju/
PUSH ~/.local/share/juju/models.yaml /root/.local/share/juju/
PUSH ~/.local/share/juju/controllers.yaml /root/.local/share/juju/
PUSH ~/.local/share/juju/credentials.yaml /root/.local/share/juju/ 

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
