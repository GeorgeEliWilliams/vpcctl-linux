#!/usr/bin/env python3
"""
vpcctl.py - A lightweight Linux-based VPC simulator CLI for Linux hosts.
Implements:
- Virtual VPCs with bridges
- Subnets as network namespaces
- Routing between subnets
- NAT gateway for public subnets
- VPC peering
- Firewall/security group enforcement via JSON
- Cleanup and idempotent operations

Author: George
"""

import argparse
import subprocess
import json
import os
import sys

# Utility functions
def run(cmd, check=True):
    """Run shell command with logging"""
    print(f"[CMD] {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.stderr.strip():
            print(result.stderr.strip())
        return result
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Command failed: {cmd}\n{e.stderr}")
        if check:
            sys.exit(1)
        return e

def exists_ns(ns):
    """Check if namespace exists"""
    result = subprocess.run(f"ip netns list | grep -w {ns}", shell=True, capture_output=True, text=True)
    return ns in result.stdout

def exists_bridge(bridge):
    """Check if bridge exists"""
    result = subprocess.run(f"brctl show | grep -w {bridge}", shell=True, capture_output=True, text=True)
    return bridge in result.stdout

def cleanup_veth(veth_name):
    """Remove veth if it exists"""
    run(f"ip link del {veth_name}", check=False)

# Core Functions
def create_vpc(vpc_name, cidr_block):
    """Create a new VPC with a bridge"""
    bridge = f"{vpc_name}-br"
    print(f"[INFO] Creating VPC '{vpc_name}' with bridge '{bridge}' and CIDR {cidr_block}")
    
    # Create bridge if it doesn't exist
    if not exists_bridge(bridge):
        run(f"ip link add name {bridge} type bridge")
        run(f"ip link set {bridge} up")
    else:
        print(f"[INFO] Bridge {bridge} already exists, skipping creation.")

def delete_vpc(vpc_name):
    """Delete a VPC with all its subnets"""
    bridge = f"{vpc_name}-br"
    print(f"[INFO] Deleting VPC '{vpc_name}'")
    
    # Remove namespaces connected to this bridge
    result = subprocess.run(f"ip netns list", shell=True, capture_output=True, text=True)
    for ns in result.stdout.strip().split("\n"):
        if ns.startswith(vpc_name):
            print(f"[INFO] Deleting namespace {ns}")
            run(f"ip netns delete {ns}", check=False)
    
    # Remove bridge
    if exists_bridge(bridge):
        run(f"ip link set {bridge} down")
        run(f"ip link del {bridge}", check=False)

def add_subnet(vpc_name, subnet_name, cidr, subnet_type="private"):
    """Add a subnet namespace and attach it to VPC bridge"""
    bridge = f"{vpc_name}-br"
    ns = f"{vpc_name}-{subnet_name}"
    veth_host = f"veth-{ns}"
    veth_ns = f"veth-{ns}-ns"
    
    print(f"[INFO] Adding subnet '{ns}' ({subnet_type}) with CIDR {cidr}")
    
    # Create namespace if not exists
    if not exists_ns(ns):
        run(f"ip netns add {ns}")
    else:
        print(f"[INFO] Namespace {ns} already exists.")
    
    # Create veth pair
    cleanup_veth(veth_host)  # ensure idempotency
    run(f"ip link add {veth_host} type veth peer name {veth_ns}")
    
    # Attach host side to bridge
    run(f"ip link set {veth_host} master {bridge}")
    run(f"ip link set {veth_host} up")
    
    # Attach ns side to namespace
    run(f"ip link set {veth_ns} netns {ns}")
    run(f"ip netns exec {ns} ip link set {veth_ns} up")
    
    # Assign IP address
    ip_base = cidr.split("/")[0]
    run(f"ip netns exec {ns} ip addr add {ip_base} dev {veth_ns}")
    
    # Set default route via bridge (assumes .1 as gateway)
    run(f"ip netns exec {ns} ip route add default via {ip_base[:-1]}1")

def configure_nat(subnet_ns, internet_iface):
    """Enable NAT for public subnet to access the internet"""
    print(f"[INFO] Configuring NAT for namespace {subnet_ns} via {internet_iface}")
    run(f"ip netns exec {subnet_ns} iptables -t nat -A POSTROUTING -o {internet_iface} -j MASQUERADE")

def peer_vpcs(vpc1, vpc2):
    """Create VPC peering between two VPC bridges"""
    br1 = f"{vpc1}-br"
    br2 = f"{vpc2}-br"
    peer0 = f"peer-{vpc1}-{vpc2}-0"
    peer1 = f"peer-{vpc1}-{vpc2}-1"
    
    print(f"[INFO] Peering VPC '{vpc1}' with VPC '{vpc2}'")
    
    cleanup_veth(peer0)
    run(f"ip link add {peer0} type veth peer name {peer1}")
    run(f"ip link set {peer0} master {br1}")
    run(f"ip link set {peer1} master {br2}")
    run(f"ip link set {peer0} up")
    run(f"ip link set {peer1} up")

def apply_policy(policy_file):
    """Apply firewall/security group rules from JSON"""
    print(f"[INFO] Applying policy from {policy_file}")
    with open(policy_file) as f:
        policy = json.load(f)
    
    subnet = policy["subnet"]
    ingress = policy.get("ingress", [])
    
    for rule in ingress:
        port = rule["port"]
        proto = rule["protocol"]
        action = rule["action"]
        if action == "allow":
            run(f"ip netns exec {subnet} iptables -A INPUT -p {proto} --dport {port} -j ACCEPT")
        else:
            run(f"ip netns exec {subnet} iptables -A INPUT -p {proto} --dport {port} -j DROP")

# CLI Interface
def main():
    parser = argparse.ArgumentParser(description="vpcctl - Linux VPC CLI")
    parser.add_argument("--create-vpc", nargs=2, metavar=("VPC_NAME", "CIDR_BLOCK"))
    parser.add_argument("--delete-vpc", metavar="VPC_NAME")
    parser.add_argument("--add-subnet", nargs=4, metavar=("VPC_NAME", "SUBNET_NAME", "CIDR", "TYPE"))
    parser.add_argument("--peer-vpcs", nargs=2, metavar=("VPC1", "VPC2"))
    parser.add_argument("--apply-policy", metavar="JSON_FILE")
    parser.add_argument("--cleanup", action="store_true")
    
    args = parser.parse_args()
    
    if args.create_vpc:
        create_vpc(*args.create_vpc)
    elif args.delete_vpc:
        delete_vpc(args.delete_vpc)
    elif args.add_subnet:
        add_subnet(*args.add_subnet)
    elif args.peer_vpcs:
        peer_vpcs(*args.peer_vpcs)
    elif args.apply_policy:
        apply_policy(args.apply_policy)
    elif args.cleanup:
        print("[INFO] Running full cleanup of all VPCs")
        # Optionally, you can iterate over all known VPCs and delete
        # Here, just an example placeholder
        run("ip netns list | xargs -n1 ip netns delete", check=False)
        run("brctl show | tail -n +2 | awk '{print $1}' | xargs -n1 ip link set down; ip link del", check=False)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
