# 🧩 Linux-Based VPC Simulator (vpcctl)



## 📖 Overview
This project simulates **AWS Virtual Private Cloud (VPC)** behavior on any **Linux or EC2 instance** using native networking tools like `ip`, `bridge-utils`, and `iptables`.  
It provides a CLI (`vpcctl.py`) for creating VPCs, subnets, peering connections, and applying security group rules — all locally without needing AWS resources.

---


## ⚙️ Prerequisites
This project is designed for **Linux** 

### Install Dependencies
```bash
sudo yum install -y bridge-utils iproute iptables
```

Ensure you’re running as root or sudo user, since network configuration requires elevated privileges.

## Quick Start (on EC2 or Linux)

### Clone repository
```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

### Setup environment
```bash
make setup
```

### Run automated test sequence
```bash
make test
```

### (Optional) Apply security group policy
```bash
make policy
```

### Cleanup environment
```bash
make cleanup
```

## Example Commands

### Create a VPC
```bash
sudo ./vpcctl.py --create-vpc myvpc 10.0.0.0/16
```

### Add a public subnet
```bash
sudo ./vpcctl.py --add-subnet myvpc public1 10.0.1.0/24 public
```

### Peer two VPCs
```bash
sudo ./vpcctl.py --peer-vpcs myvpc othervpc
```

# Apply a firewall policy
```bash
sudo ./vpcctl.py --apply-policy ./policies/sg_policy.json
```

## Sample Security Policy (sg_policy.json)
```bash
{
    "subnet": "demo-vpc1-subnetA",
    "ingress": [
        {"protocol": "tcp", "port": 22, "action": "allow"},
        {"protocol": "tcp", "port": 80, "action": "deny"}
    ]
}
```

## Cleanup
To remove all VPCs, subnets, and bridges:

```bash
make cleanup
```

## Technical Highlights
Uses Linux namespaces for subnet isolation

Uses bridge interfaces to simulate routing

Uses veth pairs for interconnects

Simulates VPC peering using linked bridges

Enforces security rules with iptables