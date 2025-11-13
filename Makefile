# Makefile for Linux-based VPC Simulator
# Automates setup, execution, and cleanup of VPC operations.
# Author: George Elikplim Williams

PYTHON := python3
SCRIPT := ./vpcctl.py
TEST_SCRIPT := ./tests/test_vpcctl.sh
POLICY_FILE := ./policies/sg_policy.json

# Default target
help:
	@echo ""
	@echo "Available commands:"
	@echo "  make setup        - Install dependencies and ensure required tools are available"
	@echo "  make test         - Run the test script for VPC simulation"
	@echo "  make cleanup      - Clean up all created VPCs and namespaces"
	@echo "  make policy       - Apply sample security group policy"
	@echo "  make help         - Show this help message"
	@echo ""

# Install dependencies (for Amazon Linux or Ubuntu)
setup:
	sudo yum install -y bridge-utils iproute iptables || sudo apt install -y bridge-utils iproute2 iptables
	chmod +x $(SCRIPT)
	chmod +x $(TEST_SCRIPT)
	@echo "[INFO] Setup complete."

# Run functional test
test:
	sudo bash $(TEST_SCRIPT)

# Apply policy example
policy:
	sudo $(PYTHON) $(SCRIPT) --apply-policy $(POLICY_FILE)

# Full cleanup
cleanup:
	sudo $(PYTHON) $(SCRIPT) --cleanup
	@echo "[INFO] Cleanup complete."

.PHONY: help setup test cleanup policy
