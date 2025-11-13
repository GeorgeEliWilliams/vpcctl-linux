#!/usr/bin/env python3
"""
vpcctl.py - A lightweight Linux-based VPC simulator CLI for Linux hosts or EC2 instances.

Simulates AWS-like VPC components using Linux networking tools:
- Virtual Private Clouds (VPCs) via Linux bridges
- Subnets as network namespaces
- Routing and NAT configuration
- VPC peering between virtual networks
- Security group/firewall rules from JSON
- Idempotent cleanup operations

"""

import argparse
import subprocess
import json
import sys

# ==========================================================
# UTILITY FUNCTIONS
# ==========================================================
def run(cmd, check=True):
    """Execute a shell command with logging and error handling."""
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
    """Check if a network namespace exists."""
    result = subprocess.run(f"ip netns list | grep -w {ns}", shell=True, capture_output=True, text=True)
    return ns in result.stdout

def exists_bridge(bridge):
    """Check if a bridge exists."""
    result = subprocess.run(f"brctl show | grep -w {bridge}", shell=True, capture_output=True, text=True)
    return bridge in result.stdout

def cleanup_veth(veth_name):
    """Remove a veth interface if it exists (idempotent)."""
    run(f"ip link del {veth_name}", check=False)

def short_name(prefix, *parts, max_len=15):
    """
    Generate a short, valid Linux interface name.
    - Keeps total name length <= 15 characters.
    - Removes unsupported characters like '-' or '_'.
    """
    safe_parts = "".join(p.replace("-", "")[:4] for p in parts)
    name = f"{prefix}{safe_parts}"[:max_len]
    return name

# ==========================================================
# CORE FUNCTIONS
# ==========================================================
def create_vpc(vpc_name, cidr_block):
    """Create a new VPC represented as a Linux bridge."""
    bridge = f"{vpc_name}-br"
    print(f"[INFO] Creating VPC '{vpc_name}' with bridge '{bridge}' and CIDR {cidr_block}")
    if not exists_bridge(bridge):
        run(f"ip link add name {bridge} type bridge")
        run(f"ip link set {bridge} up")
        print(f"[SUCCESS] VPC '{vpc_name}' created.")
    else:
        print(f"[INFO] Bridge {bridge} already exists — skipping creation.")

def delete_vpc(vpc_name):
    """Delete a VPC and its connected namespaces and interfaces."""
    bridge = f"{vpc_name}-br"
    print(f"[INFO] Deleting VPC '{vpc_name}' and associated resources...")
    result = subprocess.run("ip netns list", shell=True, capture_output=True, text=True)
    for ns in result.stdout.strip().split("\n"):
        if ns.startswith(vpc_name):
            print(f"[INFO] Removing namespace {ns}")
            run(f"ip netns delete {ns}", check=False)
    if exists_bridge(bridge):
        run(f"ip link set {bridge} down", check=False)
        run(f"ip link del {bridge}", check=False)
        print(f"[SUCCESS] VPC '{vpc_name}' deleted successfully.")
    else:
        print(f"[WARN] Bridge {bridge} not found — skipping deletion.")

def add_subnet(vpc_name, subnet_name, cidr, subnet_type="private"):
    """Add a subnet (namespace) and attach it to a VPC bridge with proper gateway."""
    bridge = f"{vpc_name}-br"
    ns = f"{vpc_name}-{subnet_name}"

    # Shortened veth names to avoid Linux limits
    veth_host = short_name("vh", vpc_name, subnet_name)
    veth_ns = short_name("vn", vpc_name, subnet_name)

    print(f"[INFO] Adding subnet '{subnet_name}' ({subnet_type}) with CIDR {cidr}")

    # Ensure namespace exists
    if not exists_ns(ns):
        run(f"ip netns add {ns}")
    else:
        print(f"[INFO] Namespace {ns} already exists.")

    # Delete old veth if exists
    cleanup_veth(veth_host)

    # Create veth pair
    run(f"ip link add {veth_host} type veth peer name {veth_ns}")
    run(f"ip link set {veth_host} master {bridge}")
    run(f"ip link set {veth_host} up")
    run(f"ip link set {veth_ns} netns {ns}")
    run(f"ip netns exec {ns} ip link set {veth_ns} up")

    # Calculate gateway and host IPs
    base_ip = cidr.split("/")[0]          # e.g., "10.0.1.0"
    octets = base_ip.split(".")
    gateway_ip = f"{octets[0]}.{octets[1]}.{octets[2]}.1"
    host_ip = f"{octets[0]}.{octets[1]}.{octets[2]}.2"

    # Assign gateway IP to bridge if not already assigned
    run(f"ip addr add {gateway_ip}/{cidr.split('/')[1]} dev {bridge}", check=False)

    # Assign IP to namespace veth
    run(f"ip netns exec {ns} ip addr add {host_ip}/{cidr.split('/')[1]} dev {veth_ns}")

    # Set default route in namespace
    run(f"ip netns exec {ns} ip route add default via {gateway_ip}")

    print(f"[SUCCESS] Subnet '{subnet_name}' added successfully to VPC '{vpc_name}'.")

def configure_nat(subnet_ns, internet_iface):
    """Enable NAT for a subnet (public) to access the internet."""
    print(f"[INFO] Configuring NAT for namespace '{subnet_ns}' via interface '{internet_iface}'")
    run(f"ip netns exec {subnet_ns} iptables -t nat -A POSTROUTING -o {internet_iface} -j MASQUERADE")
    print(f"[SUCCESS] NAT configured for '{subnet_ns}'.")

def peer_vpcs(vpc1, vpc2):
    """Peer two VPCs by connecting their bridges."""
    br1 = f"{vpc1}-br"
    br2 = f"{vpc2}-br"
    peer0 = short_name("p0", vpc1, vpc2)
    peer1 = short_name("p1", vpc1, vpc2)
    print(f"[INFO] Creating VPC peering connection between '{vpc1}' and '{vpc2}'")
    cleanup_veth(peer0)
    run(f"ip link add {peer0} type veth peer name {peer1}")
    run(f"ip link set {peer0} master {br1}")
    run(f"ip link set {peer1} master {br2}")
    run(f"ip link set {peer0} up")
    run(f"ip link set {peer1} up")
    print(f"[SUCCESS] VPCs '{vpc1}' and '{vpc2}' peered successfully.")

def apply_policy(policy_file):
    """Apply firewall/security rules from a JSON policy file."""
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
    print(f"[SUCCESS] Security policy applied to subnet '{subnet}'.")

# ==========================================================
# CLI ENTRYPOINT
# ==========================================================
def main():
    parser = argparse.ArgumentParser(description="vpcctl - Linux VPC Simulation CLI")
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
        print("[INFO] Performing full cleanup of all virtual VPCs and namespaces...")
        run("ip netns list | xargs -n1 ip netns delete", check=False)
        run("brctl show | tail -n +2 | awk '{print $1}' | xargs -n1 ip link del", check=False)
        print("[SUCCESS] Cleanup completed.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
