#!/bin/sh
set -eux

VPC_CIDR=172.30.0.0/24
SUBNET0_CIDR=172.30.0.0/24

alias aws="aws --output text"

# Pre-deploy: Create a single-subnet VPC
VPC_ID=$(aws ec2 create-vpc --cidr $VPC_CIDR | cut -f 7)
SUBNET0_ID=$(aws ec2 create-subnet --vpc-id $VPC_ID --cidr-block $SUBNET0_CIDR --availability-zone us-east-1b | cut -f 9)
aws ec2 modify-subnet-attribute --subnet-id $SUBNET0_ID --map-public-ip-on-launch
GATEWAY_ID=$(aws ec2 create-internet-gateway | cut -f 2)
aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway $GATEWAY_ID
ROUTE_TABLE_ID=$(aws --output text ec2 describe-route-tables | grep $VPC_ID | cut -f 2)
aws ec2 create-route --route-table-id $ROUTE_TABLE_ID --destination-cidr-block 0.0.0.0/0 --gateway-id $GATEWAY_ID
aws ec2 modify-vpc-attribute --vpc-id=$VPC_ID --enable-dns-support
aws ec2 modify-vpc-attribute --vpc-id=$VPC_ID --enable-dns-hostnames

# For convenience, create a cleanup script for this VPC
cat > cleanup-$VPC_ID.sh << EOF
set -ux
aws ec2 detach-internet-gateway --internet-gateway-id $GATEWAY_ID --vpc-id $VPC_ID
aws ec2 delete-internet-gateway --internet-gateway-id $GATEWAY_ID
aws ec2 delete-subnet --subnet-id $SUBNET0_ID
aws ec2 delete-vpc --vpc-id $VPC_ID
EOF
chmod +x cleanup-$VPC_ID.sh
cp cleanup-$VPC_ID.sh cleanup-vpc.sh

# Bootstrap juju controller
juju bootstrap aws aws-test-vpc --config vpc-id=$VPC_ID --to subnet=$SUBNET0_CIDR --config test-mode=true
juju model-defaults vpc-id=$VPC_ID test-mode=true