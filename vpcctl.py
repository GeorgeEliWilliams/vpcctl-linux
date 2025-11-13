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
import os
import sys

# UTILITY FUNCTIONS
# ==========================================================
def run(cmd, check=True):
    """
    Execute a shell command with logging and error handling.
    Args:
        cmd (str): Shell command to execute.
        check (bool): Whether to exit if the command fails.
    """
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
    """Check if a given network namespace exists."""
    result = subprocess.run(f"ip netns list | grep -w {ns}", shell=True, capture_output=True, text=True)
    return ns in result.stdout


def exists_bridge(bridge):
    """Check if a given bridge exists."""
    result = subprocess.run(f"brctl show | grep -w {bridge}", shell=True, capture_output=True, text=True)
    return bridge in result.stdout


def cleanup_veth(veth_name):
    """Remove a veth interface if it already exists (ensures idempotency)."""
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
    """
    Create a new VPC represented as a Linux bridge.
    Example:
        python3 vpcctl.py --create-vpc myvpc 10.0.0.0/16
    """
    bridge = f"{vpc_name}-br"
    print(f"[INFO] Creating VPC '{vpc_name}' with bridge '{bridge}' and CIDR {cidr_block}")
    
    # Create bridge only if it doesn't already exist
    if not exists_bridge(bridge):
        run(f"ip link add name {bridge} type bridge")
        run(f"ip link set {bridge} up")
        print(f"[SUCCESS] VPC '{vpc_name}' created.")
    else:
        print(f"[INFO] Bridge {bridge} already exists — skipping creation.")


def delete_vpc(vpc_name):
    """
    Delete a VPC and all its connected namespaces and interfaces.
    Example:
        python3 vpcctl.py --delete-vpc myvpc
    """
    bridge = f"{vpc_name}-br"
    print(f"[INFO] Deleting VPC '{vpc_name}' and associated resources...")
    
    # Delete namespaces connected to this VPC
    result = subprocess.run("ip netns list", shell=True, capture_output=True, text=True)
    for ns in result.stdout.strip().split("\n"):
        if ns.startswith(vpc_name):
            print(f"[INFO] Removing namespace {ns}")
            run(f"ip netns delete {ns}", check=False)
    
    # Delete the VPC bridge
    if exists_bridge(bridge):
        run(f"ip link set {bridge} down", check=False)
        run(f"ip link del {bridge}", check=False)
        print(f"[SUCCESS] VPC '{vpc_name}' deleted successfully.")
    else:
        print(f"[WARN] Bridge {bridge} not found — skipping deletion.")


def add_subnet(vpc_name, subnet_name, cidr, subnet_type="private"):
    """
    Add a subnet (namespace) and attach it to a VPC bridge.
    Example:
        python3 vpcctl.py --add-subnet myvpc subnetA 10.0.1.0/24 public
    """
    bridge = f"{vpc_name}-br"
    ns = f"{vpc_name}-{subnet_name}"

    # Generate shortened veth names (max 15 chars)
    veth_host = short_name("vh", vpc_name, subnet_name)
    veth_ns = short_name("vn", vpc_name, subnet_name)

    print(f"[INFO] Adding subnet '{subnet_name}' ({subnet_type}) with CIDR {cidr}")
    
    # Ensure namespace exists
    if not exists_ns(ns):
        run(f"ip netns add {ns}")
    else:
        print(f"[INFO] Namespace {ns} already exists.")
    
    # Create and connect veth pairs
    cleanup_veth(veth_host)
    run(f"ip link add {veth_host} type veth peer name {veth_ns}")
    run(f"ip link set {veth_host} master {bridge}")
    run(f"ip link set {veth_host} up")
    run(f"ip link set {veth_ns} netns {ns}")
    run(f"ip netns exec {ns} ip link set {veth_ns} up")

    # Assign IP address inside namespace (using base IP in CIDR)
    base_ip = cidr.split("/")[0]
    run(f"ip netns exec {ns} ip addr add {base_ip} dev {veth_ns}")
    
    # Default route via VPC bridge gateway (assuming .1)
    gateway = f"{base_ip[:-1]}1"
    run(f"ip netns exec {ns} ip rout
