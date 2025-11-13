# Makefile to automate VPC setup, testing, and cleanup for vpc

VPCCTL = ./vpcctl.py

.PHONY: all create-vpc add-subnets apply-policy peer cleanup test

all: create-vpc add-subnets apply-policy peer test

# 1. Create VPCs
create-vpc:
	@echo "=== Creating VPCs ==="
	$(VPCCTL) --create-vpc vpc1 10.0.0.0/16
	$(VPCCTL) --create-vpc vpc2 10.1.0.0/16

# 2. Add subnets
add-subnets:
	@echo "=== Adding Subnets ==="
	$(VPCCTL) --add-subnet vpc1 public 10.0.1.2/24 public
	$(VPCCTL) --add-subnet vpc1 private 10.0.2.2/24 private
	$(VPCCTL) --add-subnet vpc2 public 10.1.1.2/24 public
	$(VPCCTL) --add-subnet vpc2 private 10.1.2.2/24 private

# 3. Apply firewall policies
apply-policy:
	@echo "=== Applying Firewall Policies ==="
	$(VPCCTL) --apply-policy policies/example_policy.json

# 4. Peer VPCs
peer:
	@echo "=== Peering VPCs ==="
	$(VPCCTL) --peer-vpcs vpc1 vpc2

# 5. Test connectivity (basic ping/curl)
test:
	@echo "=== Running Basic Tests ==="
	ip netns exec vpc1-public ping -c 2 10.0.2.2 || true
	ip netns exec vpc1-public curl -s http://10.0.1.2:8000/ || true

# 6. Cleanup
cleanup:
	@echo "=== Cleaning up ==="
	$(VPCCTL) --cleanup
