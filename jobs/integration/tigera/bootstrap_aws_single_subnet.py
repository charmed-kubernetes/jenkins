#!/usr/bin/env python3

import json
import os
from subprocess import check_output, check_call
from pprint import pprint

VPC_CIDR = "172.30.0.0/24"
SUBNET0_CIDR = "172.30.0.0/24"
REGION = "us-east-1"
AVAILABILITY_ZONE = "us-east-1b"


def aws(*args):
    cmd = ['aws', '--region', REGION, '--output', 'json'] + list(args)
    print('+ ' + ' '.join(cmd))
    output = check_output(cmd)
    try:
        data = json.loads(output)
        pprint(data)
        return data
    except json.decoder.JSONDecodeError:
        if output:
            print(output)
        return


def tag_resource(resource_id):
    aws(
        'ec2', 'create-tags',
        '--resource', resource_id,
        '--tags', 'Key=created-by,Value=test-calico'
    )


cleanup_file = os.path.dirname(__file__) + '/cleanup-vpc.sh'
with open(cleanup_file, 'w') as f:
    f.write('if [ $? = 0 ]; then rm %s; fi' % cleanup_file)
os.chmod(cleanup_file, 0o775)


def add_cleanup(cmd):
    with open(cleanup_file) as f:
        contents = f.read()
    contents = cmd + '\n' + contents
    with open(cleanup_file, 'w') as f:
        f.write(contents)


def add_ec2_cleanup(cmd):
    add_cleanup('aws ec2 --region ' + REGION + ' ' + cmd)


# Create VPC
vpc_id = aws('ec2', 'create-vpc', '--cidr', VPC_CIDR)['Vpc']['VpcId']
tag_resource(vpc_id)
add_ec2_cleanup('delete-vpc --vpc-id ' + vpc_id)
aws('ec2', 'modify-vpc-attribute', '--vpc-id', vpc_id, '--enable-dns-support')
aws(
    'ec2', 'modify-vpc-attribute',
    '--vpc-id', vpc_id,
    '--enable-dns-hostnames'
)

# Create subnet
subnet_id = aws(
    'ec2', 'create-subnet',
    '--vpc-id', vpc_id,
    '--cidr-block', SUBNET0_CIDR,
    '--availability-zone', AVAILABILITY_ZONE
)['Subnet']['SubnetId']
tag_resource(subnet_id)
add_ec2_cleanup('delete-subnet --subnet-id ' + subnet_id)
aws(
    'ec2', 'modify-subnet-attribute',
    '--subnet-id', subnet_id,
    '--map-public-ip-on-launch'
)

# Create gateway
gateway_id = aws(
    'ec2', 'create-internet-gateway'
)['InternetGateway']['InternetGatewayId']
tag_resource(gateway_id)
add_ec2_cleanup('delete-internet-gateway --internet-gateway-id ' + gateway_id)
aws(
    'ec2', 'attach-internet-gateway',
    '--vpc-id', vpc_id,
    '--internet-gateway', gateway_id
)
add_ec2_cleanup(
    'detach-internet-gateway --internet-gateway-id %s --vpc-id %s' % (
        gateway_id, vpc_id
    )
)

# Create route
route_tables = aws('ec2', 'describe-route-tables')['RouteTables']
for route_table in route_tables:
    if route_table['VpcId'] == vpc_id:
        route_table_id = route_table['RouteTableId']
        break
tag_resource(route_table_id)
aws(
    'ec2', 'create-route',
    '--route-table-id', route_table_id,
    '--destination-cidr-block', '0.0.0.0/0',
    '--gateway-id', gateway_id
)

# Juju bootstrap
controller_name = os.environ.get('CONTROLLER', 'aws-' + vpc_id)
check_call([
    'juju', 'bootstrap',
    'aws/' + REGION, controller_name,
    '--config', 'vpc-id=' + vpc_id,
    '--to', 'subnet=' + SUBNET0_CIDR,
    '--config', 'test-mode=true'
])
add_cleanup('juju kill-controller -y ' + controller_name)
check_call(['juju', 'model-defaults', 'vpc-id=' + vpc_id, 'test-mode=true'])
