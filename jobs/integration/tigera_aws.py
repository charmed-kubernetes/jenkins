#!/usr/bin/env python3

import argparse
import ipaddress
import json
import os
import sys
import time
import yaml
import boto3
from subprocess import check_output, CalledProcessError

VPC_CIDR = "172.30.0.0/16"
SUBNET_CIDRS = ["172.30.0.0/24", "172.30.1.0/24"]
REGION = os.environ.get("JUJU_CLOUD", "us-east-2")
AVAILABILITY_ZONE = f"{REGION}a"
OWNER = os.environ.get("JUJU_OWNER", "k8sci")

BIRD_CONFIG_BASE = """
log syslog all;
debug protocols all;

router id %s;

protocol kernel {
  persist;
  scan time 20;
  export all;
}

protocol device {
  scan time 10;
}
"""
BIRD_CONFIG_PEER = """
protocol bgp {
  import all;
  local as 64512;
  neighbor %s as 64512;
  direct;
}
"""

session = boto3.Session(profile_name="default", region_name=REGION)
ec2 = session.client("ec2")


command_defs = {}


def def_command(name):
    def decorator(f):
        command_defs[name] = f

    return decorator


def log(msg):
    print(msg, flush=True)


def sh(*args, **kwargs):
    log("+ " + " ".join(args[0]))
    try:
        output = check_output(*args, **kwargs).decode("UTF-8")
    except CalledProcessError as e:
        log(e.output)
        raise
    log(output)
    return output


# def ec2(*args, ignore_errors=False):
#     cmd = ["aws", "--region", REGION, "--output", "json", "ec2"] + list(args)
#     try:
#         output = sh(cmd, env=os.environ.copy())
#     except CalledProcessError:
#         if ignore_errors:
#             return
#         else:
#             raise
#     try:
#         data = json.loads(output)
#         return data
#     except json.decoder.JSONDecodeError:
#         return


def tag_resource(resource_id):
    ec2.create_tags(Resources=[resource_id], Tags=[{"Key": "owner", "Value": OWNER}])


def juju_version():
    ver, _ = sh(["juju", "version"]).split("-", 1)
    return tuple(map(int, ver.split(".")))


def juju_base(series):
    """Retrieve juju 3.x base from series."""
    if juju_version() < (3, 1):
        return f"--series={series}"
    mapping = {
        "bionic": "ubuntu@18.04",
        "focal": "ubuntu@20.04",
        "jammy": "ubuntu@22.04",
        "noble": "ubuntu@24.04",
    }
    return f"--base={mapping[series]}"


def juju(cmd, *args, **kwargs):
    model = os.environ["JUJU_MODEL"]
    controller = os.environ["JUJU_CONTROLLER"]
    cmd = ["juju", cmd, "-m", f"{controller}:{model}"] + list(args)
    return sh(cmd, **kwargs)


def juju_wait(*args, **kwargs):
    model = os.environ["JUJU_MODEL"]
    controller = os.environ["JUJU_CONTROLLER"]
    cmd = ["juju-wait", "-m", f"{controller}:{model}"] + list(args)
    return sh(cmd, **kwargs)


def juju_json(cmd, *args):
    args = ["--format", "json"] + list(args)
    output = juju(cmd, *args)
    return json.loads(output)


def get_instance_id(machine_id):
    log("Getting instance ID for machine " + machine_id)
    while True:
        status = juju_json("status")
        machines = status["machines"]
        if machine_id not in machines:
            log("WARNING: machine %s disappeared" % machine_id)
            return None
        machine = machines[machine_id]
        if machine["instance-id"] == "pending":
            time.sleep(1)
            continue
        return machine["instance-id"]


@def_command("create-vpc")
def create_vpc():
    # Create VPC
    vpc = ec2.create_vpc(
        CidrBlock=VPC_CIDR,
        AmazonProvidedIpv6CidrBlock=True,
    )["Vpc"]
    vpc_id = vpc["VpcId"]
    tag_resource(vpc_id)
    # poll the IPv6 CIDR block until it's available
    for attempt in range(10):
        ipv6_cidr_block = vpc["Ipv6CidrBlockAssociationSet"][0]["Ipv6CidrBlock"]
        if ipv6_cidr_block:
            break
        else:
            time.sleep(5)
            vpc = ec2.describe_vpcs(VpcIds=[vpc_id])["Vpcs"][0]
    else:
        raise ValueError(
            "Unable to get IPv6 CIDR block from VPC {}: {}".format(
                vpc_id,
                vpc["Ipv6CidrBlockAssociationSet"],
            )
        )

    # AWS gives us a larger CIDR block than we can use directly, so we have to chop it down
    # "A subnet's IPv6 CIDR block is a fixed prefix length of /64."
    # https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Subnets.html#vpc-sizing-ipv6
    ipv6_network = ipaddress.IPv6Network(ipv6_cidr_block)
    ipv6_subnets = ipv6_network.subnets(64 - ipv6_network.prefixlen)
    ipv6_subnet_cidrs = [str(subnet) for subnet in ipv6_subnets]

    # Must be done in separate requests per doc
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
    ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})

    # Create subnets
    num_subnets = os.environ.get("NUM_SUBNETS")
    num_subnets = int(num_subnets) if num_subnets else 1
    for i in range(num_subnets):
        subnet_cidr = SUBNET_CIDRS[i]
        subnet_ipv6_cidr = ipv6_subnet_cidrs[i]
        subnet_id = ec2.create_subnet(
            VpcId=vpc_id,
            CidrBlock=subnet_cidr,
            Ipv6CidrBlock=subnet_ipv6_cidr,
            AvailabilityZone=AVAILABILITY_ZONE,
        )["Subnet"]["SubnetId"]
        tag_resource(subnet_id)
        ec2.modify_subnet_attribute(
            SubnetId=subnet_id, MapPublicIpOnLaunch={"Value": True}
        )

    # Create gateway
    gateway_id = ec2.create_internet_gateway()["InternetGateway"]["InternetGatewayId"]
    tag_resource(gateway_id)
    ec2.attach_internet_gateway(VpcId=vpc_id, InternetGatewayId=gateway_id)

    # Create route
    route_table_ids = []
    route_tables = ec2.describe_route_tables()["RouteTables"]
    for route_table in route_tables:
        if route_table["VpcId"] == vpc_id:
            route_table_id = route_table["RouteTableId"]
            tag_resource(route_table_id)
            route_table_ids.append(route_table_id)
    for route_table_id in route_table_ids:
        ec2.create_route(
            RouteTableId=route_table_id,
            DestinationCidrBlock="0.0.0.0/0",
            GatewayId=gateway_id,
        )
        ec2.create_route(
            RouteTableId=route_table_id,
            DestinationIpv6CidrBlock="::/0",
            GatewayId=gateway_id,
        )

    log("Successfully created VPC " + vpc_id)


@def_command("cleanup")
def cleanup():
    sys.stdout.write(
        "WARNING: This will clean up long-lived VPCs and, if executed, may require the creation of new VPCs and updates to the hard-coded VPC IDs in the calico and tigera-secure-ee job specs. Are you sure? (y/n): "
    )
    while True:
        answer = input().lower()
        if answer == "y":
            break
        elif answer == "n":
            return
        else:
            sys.stdout.write("Please enter y or n (y/n): ")

    network_interfaces = ec2.describe_network_interfaces()["NetworkInterfaces"]
    for network_interface in network_interfaces:
        for tag in network_interface.get("TagSet", []):
            if tag["Key"] == "owner" and tag["Value"] == OWNER:
                network_interface_id = network_interface["NetworkInterfaceId"]
                ec2.delete_network_interface(
                    NetworkInterfaceId=network_interface_id,
                )
                break

    gateways = ec2.describe_internet_gateways()["InternetGateways"]
    for gateway in gateways:
        for tag in gateway.get("Tags", []):
            if tag["Key"] == "owner" and tag["Value"] == OWNER:
                gateway_id = gateway["InternetGatewayId"]
                for attachment in gateway["Attachments"]:
                    ec2.detach_internet_gateway(
                        InternetGatewayId=gateway_id,
                        VpcId=attachment["VpcId"],
                    )
                ec2.delete_internet_gateway(
                    InternetGatewayId=gateway_id,
                )
                break

    subnets = ec2.describe_subnets()["Subnets"]
    for subnet in subnets:
        for tag in subnet.get("Tags", []):
            if tag["Key"] == "owner" and tag["Value"] == OWNER:
                ec2.delete_subnet(
                    SubnetId=subnet["SubnetId"],
                )
                break

    vpcs = ec2.describe_vpcs()["Vpcs"]
    for vpc in vpcs:
        for tag in vpc.get("Tags", []):
            if tag["Key"] == "owner" and tag["Value"] == OWNER:
                ec2.delete_vpc(VpcId=vpc["VpcId"])
                break


def disable_source_dest_check_on_instance(instance_id):
    log("Getting network interfaces for instance " + instance_id)
    network_interface_ids = []
    reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    for reservation in reservations:
        instances = reservation["Instances"]
        for instance in instances:
            for network_interface in instance["NetworkInterfaces"]:
                network_interface_id = network_interface["NetworkInterfaceId"]
                network_interface_ids.append(network_interface_id)

    for network_interface_id in network_interface_ids:
        log("Disabling source/dest checks on " + network_interface_id)

        ec2.modify_network_interface_attribute(
            NetworkInterfaceId=network_interface_id, SourceDestCheck={"Value": False}
        )


@def_command("disable-source-dest-check")
def disable_source_dest_check():
    status = juju_json("status")

    if status["model"]["cloud"] != "aws":
        log("Cloud is not AWS, doing nothing")
        return

    apps = ["calico", "tigera-secure-ee"]
    if not any(app in status["applications"] for app in apps):
        log("No apps need source dest check disabled, doing nothing")
        return

    global REGION
    REGION = status["model"]["region"]

    status = juju_json("status")
    for machine_id in status["machines"]:
        instance_id = get_instance_id(machine_id)
        if instance_id:
            disable_source_dest_check_on_instance(instance_id)


def assign_ipv6_addr_on_instance(instance_id):
    log("Getting network interfaces for instance " + instance_id)
    network_interface_ids = []
    reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    for reservation in reservations:
        instances = reservation["Instances"]
        for instance in instances:
            for network_interface in instance["NetworkInterfaces"]:
                network_interface_id = network_interface["NetworkInterfaceId"]
                ipv6_addrs = network_interface["Ipv6Addresses"]
                if not ipv6_addrs:
                    network_interface_ids.append(network_interface_id)

    for network_interface_id in network_interface_ids:
        log("Assigning IPv6 address to " + network_interface_id)

        ec2.assign_ipv6_addresses(
            NetworkInterfaceId=network_interface_id,
            Ipv6AddressCount=1,
        )


@def_command("assign-ipv6-addrs")
def assign_ipv6_addrs():
    status = juju_json("status")

    if status["model"]["cloud"] != "aws":
        log("Cloud is not AWS, doing nothing")
        return

    apps = ["calico", "tigera-secure-ee"]
    if not any(app in status["applications"] for app in apps):
        log("No apps need source dest check disabled, doing nothing")
        return

    global REGION
    REGION = status["model"]["region"]

    status = juju_json("status")
    for machine_id in status["machines"]:
        instance_id = get_instance_id(machine_id)
        if instance_id:
            assign_ipv6_addr_on_instance(instance_id)


def get_model_vpc_id():
    log("Getting VPC ID")
    model_config = juju_json("model-config")
    vpc_id = model_config["vpc-id"]["Value"]
    return vpc_id


def get_subnets_in_vpc(vpc_id):
    log("Getting subnets in VPC " + vpc_id)
    subnets = ec2.describe_subnets()["Subnets"]
    subnets = [subnet for subnet in subnets if subnet["VpcId"] == vpc_id]
    log(f'  SubnetIds: {",".join(s["SubnetId"] for s in subnets)}')
    return subnets


def get_instance_ips(instance_id):
    log("Getting IPs for instance " + instance_id)
    ips = set()
    reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    for reservation in reservations:
        for instance in reservation["Instances"]:
            for interface in instance["NetworkInterfaces"]:
                ip = interface["PrivateIpAddress"]
                ips.add(ip)
    return ips


def get_machine_id(unit_name):
    log("Getting machine ID for unit " + unit_name)
    application = unit_name.split("/")[0]
    while True:
        status = juju_json("status")
        machine_id = status["applications"][application]["units"][unit_name].get(
            "machine"
        )
        if machine_id:
            return machine_id
        time.sleep(1)


@def_command("deploy-bgp-router")
def deploy_bgp_router():
    vpc_id = get_model_vpc_id()
    subnets = get_subnets_in_vpc(vpc_id)

    log("Deploying router to first subnet")
    series = juju_base(os.environ.get("SERIES"))
    subnet = "subnet=" + subnets[0]["CidrBlock"]
    juju("deploy", "ubuntu", "router", series, "--to", subnet)
    machine_id = get_machine_id("router/0")
    instance_id = get_instance_id(machine_id)

    log("Getting instance security groups")
    security_groups = set()
    reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    for reservation in reservations:
        for instance in reservation["Instances"]:
            for group in instance["SecurityGroups"]:
                security_groups.add(group["GroupId"])

    log("Adding router to remaining subnets")
    for i in range(1, len(subnets)):
        subnet = subnets[i]
        subnet_id = subnet["SubnetId"]
        result = ec2.create_network_interface(
            SubnetId=subnet_id,
            Groups=list(security_groups),
        )
        time.sleep(15)
        network_interface_id = result["NetworkInterface"]["NetworkInterfaceId"]
        tag_resource(network_interface_id)
        attachment_id = ec2.attach_network_interface(
            NetworkInterfaceId=network_interface_id,
            InstanceId=instance_id,
            DeviceIndex=i,
        )["AttachmentId"]
        ec2.modify_network_interface_attribute(
            NetworkInterfaceId=network_interface_id,
            Attachment={"AttachmentId": attachment_id, "DeleteOnTermination": True},
        )

    log("Waiting for router to come up")
    juju_wait(timeout=15 * 60)

    log("Enabling secondary network interfaces")
    expected_nics = {f"ens{i + 5}" for i in range(1, len(subnets))}
    max_retries, current_nics = 10, set()
    while not expected_nics.issubset(current_nics) and max_retries:
        time.sleep(10 - max_retries)
        current_nics = {
            line.split("  ", 1)[0]
            for line in juju(
                "ssh", "router/0", "ip", "-br", "link", "show"
            ).splitlines()
        }
        max_retries -= 1

    if not expected_nics.issubset(current_nics):
        log(
            "Failed to find all nics\n"
            f"  expected: {', '.join(expected_nics)}\n"
            f"  current : {', '.join(current_nics)}"
        )
        raise TimeoutError()

    for interface in expected_nics:
        # Setting IF_METRIC=101 lowers the priority of the routes for this network
        # interface. We need the primary network's default route to be higher
        # priority so that the public/elastic IP, which is bound to the primary
        # network interface, continues to work.
        juju(
            "ssh",
            "router/0",
            "sudo",
            "dhclient",
            interface,
            "-e",
            "IF_METRIC=101",
        )

    log("Installing BIRD")
    juju("ssh", "router/0", "sudo", "apt", "update")
    juju("ssh", "router/0", "sudo", "apt", "install", "-y", "bird")

    log("Getting VPC CIDR")
    vpc = ec2.describe_vpcs(VpcIds=[vpc_id])["Vpcs"][0]
    vpc_cidr = vpc["CidrBlock"]

    log("Getting router IPs")
    router_ips = get_instance_ips(instance_id)

    log("Configuring cloudinit-userdata to modify route tables")
    cmd = "for ip in %s; do ip route add %s via $ip || true; done" % (
        " ".join(router_ips),
        vpc_cidr,
    )
    juju("model-config", 'cloudinit-userdata={postruncmd: ["%s"]}' % cmd)


@def_command("configure-bgp")
def configure_bgp():
    # Get subnets
    vpc_id = get_model_vpc_id()
    subnets = get_subnets_in_vpc(vpc_id)

    # Get Router IP for each subnet
    router_machine_id = get_machine_id("router/0")
    router_instance_id = get_instance_id(router_machine_id)
    router_ips = get_instance_ips(router_instance_id)

    # Get kubernetes-control-plane IPs
    master_ips = set()
    for unit_name in ["kubernetes-control-plane/0", "kubernetes-control-plane/1"]:
        machine_id = get_machine_id(unit_name)
        instance_id = get_instance_id(machine_id)
        ips = get_instance_ips(instance_id)
        master_ips.update(ips)

    # Get kubernetes-control-plane calico unit IDs
    master_calico_units = []
    for unit_name in ["kubernetes-control-plane/0", "kubernetes-control-plane/1"]:
        log("Getting calico unit attached to " + unit_name)
        while True:
            status = juju_json("status")
            unit = status["applications"]["kubernetes-control-plane"]["units"][
                unit_name
            ]
            subordinate_names = [
                name
                for name in unit.get("subordinates", [])
                if name.startswith("calico/")
            ]
            if subordinate_names:
                master_calico_units.append(subordinate_names[0])
                break
            time.sleep(1)

    # Configure Calico
    subnet_bgp_peers = {}
    for subnet in subnets:
        cidr = subnet["CidrBlock"]
        network = ipaddress.ip_network(cidr)
        ips = [ipaddress.ip_address(ip) for ip in router_ips]
        ips = [ip for ip in ips if ip in network]
        ips = [str(ip) for ip in ips]
        assert len(ips) == 1, "WHUT? %s" % ips
        ip = ips[0]
        subnet_bgp_peers[cidr] = [{"address": ip, "as-number": 64512}]

    unit_numbers = [int(unit_name.split("/")[1]) for unit_name in master_calico_units]
    route_reflector_cluster_ids = {
        unit_number: "0.0.0.0" for unit_number in unit_numbers
    }

    global_bgp_peers = [
        {"address": address, "as-number": 64512} for address in master_ips
    ]

    juju(
        "config",
        "calico",
        "subnet-bgp-peers=" + yaml.dump(subnet_bgp_peers),
        "route-reflector-cluster-ids=" + yaml.dump(route_reflector_cluster_ids),
        "global-bgp-peers=" + yaml.dump(global_bgp_peers),
        "node-to-node-mesh=false",
    )

    # Get all Calico IPs
    calico_ips = set()
    calico_ips.update(master_ips)
    status = juju_json("status")
    for unit_name in status["applications"]["kubernetes-worker"]["units"]:
        machine_id = get_machine_id(unit_name)
        instance_id = get_instance_id(machine_id)
        ips = get_instance_ips(instance_id)
        calico_ips.update(ips)

    # Configure BIRD
    bird_conf: str = BIRD_CONFIG_BASE % list(router_ips)[0]
    for ip in calico_ips:
        bird_conf += BIRD_CONFIG_PEER % ip
    juju("ssh", "router/0", "cat > bird.conf", input=bird_conf.encode())
    juju("ssh", "router/0", "sudo", "cp", "bird.conf", "/etc/bird/bird.conf")
    juju("ssh", "router/0", "sudo", "service", "bird", "restart")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=command_defs)
    args = parser.parse_args()
    command_defs[args.command]()


if __name__ == "__main__":
    main()
