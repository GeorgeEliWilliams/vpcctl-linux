#!/bin/bash
# test_vpcctl.sh - Integration test for Linux VPC simulator.
# Runs through all major functionalities in sequence.

set -e  # Exit immediately if a command fails

SCRIPT="./vpcctl.py"
VPC1="demo-vpc1"
VPC2="demo-vpc2"

echo "=========================================="
echo "🚀 Starting VPC Simulator Test Sequence..."
echo "=========================================="

# --- Step 1: Create two VPCs ---
echo "[TEST] Creating VPCs..."
sudo $SCRIPT --create-vpc $VPC1 10.0.0.0/16
sudo $SCRIPT --create-vpc $VPC2 10.1.0.0/16

# --- Step 2: Add subnets ---
echo "[TEST] Adding subnets..."
sudo $SCRIPT --add-subnet $VPC1 subnetA 10.0.1.0/24 public
sudo $SCRIPT --add-subnet $VPC2 subnetB 10.1.1.0/24 private

# --- Step 3: Peer the VPCs ---
echo "[TEST] Peering VPCs..."
sudo $SCRIPT --peer-vpcs $VPC1 $VPC2

# --- Step 4: Apply firewall/security policy ---
echo "[TEST] Applying firewall policy..."
sudo $SCRIPT --apply-policy ./policies/sg_policy.json

# --- Step 5: Validate namespaces and bridges ---
echo "[TEST] Verifying environment..."
ip netns list
brctl show

# --- Step 6: Cleanup ---
echo "[TEST] Cleaning up..."
sudo $SCRIPT --cleanup

echo "=========================================="
echo "✅ Test sequence completed successfully!"
echo "=========================================="
