# Terraform Study Guide: AWS Client VPN Setup

This document walks through the Terraform codebase used to deploy your AWS Client VPN. It explains what each file does, lists the complete source code, describes the purpose of each resource block and setting, and provides an end-to-end command reference.

---

## Workspace Map

Your Terraform files are divided logically into separate components:

```
aws-vpn/
├── providers.tf       # Provider configuration (AWS settings)
├── variables.tf       # Configurable inputs (regions, IP ranges, toggles)
├── main.tf            # Core network topology (VPC, subnets, route tables)
├── nat.tf             # NAT gateway/instance routing logic
├── vpn.tf             # Client VPN, ACM certificates, and auth rules
└── outputs.tf         # Useful deployment outputs (IDs, connection string)
```

---

## 1. providers.tf (Provider Configuration)

This file tells Terraform which cloud provider to use, what version of the provider is required, and what region to deploy resources into.

### Source Code
```hcl
terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}
```

### Resource Explanations
*   **`terraform { ... }`**: Defines metadata for Terraform itself.
    *   `required_version`: Enforces that you are using Terraform version 1.0.0 or higher.
    *   `required_providers`: Downloads the AWS plugin from the official HashiCorp registry. `~> 5.0` specifies that any version in the `5.x` series is acceptable.
*   **`provider "aws" { ... }`**: Configures the AWS provider. It pulls the deployment region dynamically from the `aws_region` variable defined in `variables.tf`.

---

## 2. variables.tf (Configurable Inputs)

This file defines the input parameters for the project, allowing you to customize settings without editing the main infrastructure files.

### Source Code
```hcl
variable "aws_region" {
  description = "The AWS Region to deploy resources in"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the new VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet (where NAT Gateway/Instance resides)"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private subnet (associated with Client VPN)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "client_cidr_block" {
  description = "IP range block for VPN clients. Must be at least a /22 and not overlap with the VPC CIDR."
  type        = string
  default     = "172.16.0.0/22"
}

variable "use_nat_gateway" {
  description = "If true, deploy a Managed NAT Gateway. If false, deploy a cost-effective EC2 NAT Instance."
  type        = bool
  default     = false
}

variable "nat_instance_type" {
  description = "EC2 Instance type for the NAT Instance (if use_nat_gateway is false)"
  type        = string
  default     = "t3.nano"
}
```

### Key Concepts
*   **`client_cidr_block`**: AWS Client VPN requires a subnet size of at least `/22` (providing 1024 IP addresses). This subnet range cannot overlap with the VPC CIDR (`10.0.0.0/16`).
*   **`use_nat_gateway`**: A boolean flag (`true`/`false`). We use this variable to conditionally toggle between a Managed NAT Gateway and a NAT Instance in `nat.tf` and `main.tf`.

---

## 3. main.tf (VPC Network Infrastructure)

This file defines the network architecture of the AWS VPC. It sets up subnets, the Internet Gateway, and configures how traffic is routed between them.

### Source Code
```hcl
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "aws-vpn-vpc"
  }
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "aws-vpn-igw"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  map_public_ip_on_launch = true
  availability_zone       = "${var.aws_region}a"

  tags = {
    Name = "aws-vpn-public-subnet"
  }
}

resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = "${var.aws_region}a"

  tags = {
    Name = "aws-vpn-private-subnet"
  }
}

# Public Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "aws-vpn-public-rt"
  }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.gw.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Private Route Table
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "aws-vpn-private-rt"
  }
}

# Route private traffic through Managed NAT Gateway (if use_nat_gateway is true)
resource "aws_route" "private_nat_gateway" {
  count                  = var.use_nat_gateway ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main[0].id
}

# Route private traffic through EC2 NAT Instance (if use_nat_gateway is false)
resource "aws_route" "private_nat_instance" {
  count                  = var.use_nat_gateway ? 0 : 1
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = aws_instance.nat[0].primary_network_interface_id
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}
```

### Resource Explanations
*   **`aws_vpc.main`**: Creates the VPC. We enable DNS support and hostnames, which are required for AWS Client VPN endpoints to function properly.
*   **`aws_internet_gateway.gw`**: Connects the VPC to the internet.
*   **`aws_subnet.public`**: The subnet that has a direct route to the Internet Gateway. NAT devices reside here. `map_public_ip_on_launch = true` ensures instances launched here get public IPs.
*   **`aws_subnet.private`**: The isolated subnet that routes to the NAT device. The Client VPN will associate with this subnet.
*   **`count = var.use_nat_gateway ? 1 : 0`**: A conditional parameter. It creates the resource *only* if the condition evaluates to true (1). Otherwise, it creates 0 instances of it.
*   **`aws_route.private_nat_instance`**: Adds a route to the private route table. The destination is the entire internet (`0.0.0.0/0`), and the target is the network interface ID (`eni-...`) of the NAT Instance.

---

## 4. nat.tf (Egress NAT Logic)

This file provisions the NAT device. By default, it sets up an EC2 NAT Instance, writes its firewall forwarding script, disables source/destination checks, and assigns an Elastic IP.

### Source Code
```hcl
# Elastic IP for Managed NAT Gateway (if use_nat_gateway is true)
resource "aws_eip" "nat_gw_eip" {
  count  = var.use_nat_gateway ? 1 : 0
  domain = "vpc"

  tags = {
    Name = "aws-vpn-nat-gw-eip"
  }
}

# Managed NAT Gateway (if use_nat_gateway is true)
resource "aws_nat_gateway" "main" {
  count         = var.use_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat_gw_eip[0].id
  subnet_id     = aws_subnet.public.id

  tags = {
    Name = "aws-vpn-nat-gateway"
  }

  depends_on = [aws_internet_gateway.gw]
}

# ----------------------------------------------------
# Cost-Saving NAT Instance (if use_nat_gateway is false)
# ----------------------------------------------------

# Find the latest Amazon Linux 2023 AMI
data "aws_ami" "amazon_linux_2023" {
  count       = var.use_nat_gateway ? 0 : 1
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-kernel-6.1-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Security Group for the NAT Instance
resource "aws_security_group" "nat_sg" {
  count       = var.use_nat_gateway ? 0 : 1
  name        = "aws-vpn-nat-sg"
  description = "Allow inbound traffic from VPC for NAT routing"
  vpc_id      = aws_vpc.main.id

  # Allow all inbound traffic from VPC CIDR
  ingress {
    description = "Allow all inbound from VPC CIDR"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  # Allow all inbound traffic from VPN client CIDR
  ingress {
    description = "Allow all inbound from VPN clients"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.client_cidr_block]
  }

  # Allow all outbound traffic to internet
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "aws-vpn-nat-sg"
  }
}

# Elastic IP for NAT Instance
resource "aws_eip" "nat_instance_eip" {
  count  = var.use_nat_gateway ? 0 : 1
  domain = "vpc"

  tags = {
    Name = "aws-vpn-nat-instance-eip"
  }
}

# Associate EIP with NAT Instance
resource "aws_eip_association" "nat_assoc" {
  count         = var.use_nat_gateway ? 0 : 1
  instance_id   = aws_instance.nat[0].id
  allocation_id = aws_eip.nat_instance_eip[0].id
}

# EC2 NAT Instance
resource "aws_instance" "nat" {
  count         = var.use_nat_gateway ? 0 : 1
  ami           = data.aws_ami.amazon_linux_2023[0].id
  instance_type = var.nat_instance_type
  subnet_id     = aws_subnet.public.id

  # Disable source/destination checks for NAT routing
  source_dest_check      = false
  vpc_security_group_ids = [aws_security_group.nat_sg[0].id]

  user_data = <<-EOF
              #!/bin/bash
              # Enable IP forwarding
              sysctl -w net.ipv4.ip_forward=1
              echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf

              # Install iptables services to persist rules
              dnf install -y iptables-services
              systemctl enable iptables
              systemctl start iptables

              # Flush default forwarding rules which block routing
              iptables -F FORWARD
              iptables -P FORWARD ACCEPT

              # Get default network interface name (normally eth0)
              INTERFACE=$(ip route | grep default | awk '{print $5}')

              # Set up NAT masquerading for VPC CIDR and Client VPN CIDR
              iptables -t nat -A POSTROUTING -o $INTERFACE -j MASQUERADE
              service iptables save
              EOF

  tags = {
    Name = "aws-vpn-nat-instance"
  }

  # Ensure the Internet Gateway is active before starting
  depends_on = [aws_internet_gateway.gw]
}
```

### Key Parameter Explanations
*   **`data "aws_ami" "amazon_linux_2023"`**: Dynamically queries the AWS marketplace to find the latest official Amazon Linux 2023 machine image.
*   **`source_dest_check = false`**: By default, AWS EC2 instances only accept or send traffic where the source or destination IP matches the instance's own IP. Because this instance functions as a NAT router, we must disable this check.
*   **`user_data`**: A shell script that runs once during the initial boot to enable kernel IP forwarding and clear firewall forward drops.

---

## 5. vpn.tf (Client VPN & ACM Cryptography)

This file reads your local certificate files, imports them to AWS ACM, and constructs the VPN server endpoint in full-tunnel mode.

### Source Code
```hcl
# Upload local certificates to ACM
resource "aws_acm_certificate" "server" {
  private_key       = file("${path.module}/certs/server.key")
  certificate_body  = file("${path.module}/certs/server.crt")
  certificate_chain = file("${path.module}/certs/ca.crt")

  tags = {
    Name = "aws-vpn-server-cert"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate" "client" {
  private_key       = file("${path.module}/certs/client1.domain.tld.key")
  certificate_body  = file("${path.module}/certs/client1.domain.tld.crt")
  certificate_chain = file("${path.module}/certs/ca.crt")

  tags = {
    Name = "aws-vpn-client-cert"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Client VPN Endpoint
resource "aws_ec2_client_vpn_endpoint" "main" {
  description            = "AWS Client VPN for Full-Tunnel Internet Browsing"
  server_certificate_arn = aws_acm_certificate.server.arn
  client_cidr_block      = var.client_cidr_block
  split_tunnel           = false # Route ALL traffic through the VPN (Full Tunnel)
  dns_servers            = ["1.1.1.1", "8.8.8.8"]

  authentication_options {
    type                           = "certificate-authentication"
    root_certificate_chain_arn = aws_acm_certificate.client.arn
  }

  connection_log_options {
    enabled = false
  }

  tags = {
    Name = "aws-vpn-endpoint"
  }
}

# Subnet Association (VPN endpoint associates with private subnet)
resource "aws_ec2_client_vpn_network_association" "private" {
  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.main.id
  subnet_id              = aws_subnet.private.id

  lifecycle {
    create_before_destroy = false
  }
}

# Authorization Rule (Allows client traffic to reach the internet 0.0.0.0/0)
resource "aws_ec2_client_vpn_authorization_rule" "internet" {
  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.main.id
  target_network_cidr    = "0.0.0.0/0"
  authorize_all_groups   = true
}

# Authorization Rule (Allows client traffic to reach local VPC CIDR)
resource "aws_ec2_client_vpn_authorization_rule" "vpc" {
  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.main.id
  target_network_cidr    = var.vpc_cidr
  authorize_all_groups   = true
}

# Route 0.0.0.0/0 traffic from VPN endpoint to private subnet association
resource "aws_ec2_client_vpn_route" "internet" {
  client_vpn_endpoint_id = aws_ec2_client_vpn_endpoint.main.id
  destination_cidr_block = "0.0.0.0/0"
  target_vpc_subnet_id   = aws_ec2_client_vpn_network_association.private.subnet_id

  depends_on = [
    aws_ec2_client_vpn_network_association.private
  ]
}
```

### Key Parameter Explanations
*   **`split_tunnel = false`**: Enforces a Full-Tunnel VPN, pushing a default route (`0.0.0.0/0`) over the VPN connection.
*   **`aws_ec2_client_vpn_authorization_rule`**: Explicitly permits network traffic from clients. We authorize both the internet (`0.0.0.0/0`) and internal VPC subnet (`10.0.0.0/16`).
*   **`depends_on`**: Prevents race conditions by waiting for the association to complete before pushing routing table entries.

---

## 6. outputs.tf (Deployment Outputs)

This file returns data calculated at deploy-time, which is essential to construct your client configuration profile.

### Source Code
```hcl
output "vpc_id" {
  description = "The ID of the created VPC"
  value       = aws_vpc.main.id
}

output "client_vpn_endpoint_id" {
  description = "The ID of the Client VPN endpoint"
  value       = aws_ec2_client_vpn_endpoint.main.id
}

output "client_vpn_dns_name" {
  description = "The DNS name of the Client VPN endpoint"
  value       = aws_ec2_client_vpn_endpoint.main.dns_name
}

output "nat_public_ip" {
  description = "The public IP of the VPN egress NAT device. Your internet browsing source IP will show as this."
  value       = var.use_nat_gateway ? aws_eip.nat_gw_eip[0].public_ip : aws_eip.nat_instance_eip[0].public_ip
}

output "download_config_command" {
  description = "AWS CLI command to download the client configuration file"
  value       = "aws ec2 export-client-vpn-client-configuration --client-vpn-endpoint-id ${aws_ec2_client_vpn_endpoint.main.id} --output text --region ${var.aws_region} > client-config.ovpn"
}
```

---

## 7. End-to-End Deployment Workflow (Terraform Commands)

Once you have written all your configuration files, you use the Terraform CLI to manage the lifecycle of your infrastructure. Below are the sequential commands used to deploy, manage, and destroy this VPN gateway.

### Step 1: Initialize Terraform (terraform init)
Downloads the provider plugins (in this case, `hashicorp/aws`) and sets up the local configuration.
*   **Command:**
    ```bash
    terraform init
    ```
*   **Example Output:**
    ```text
    Initializing the backend...
    Initializing provider plugins...
    - Finding hashicorp/aws versions matching "~> 5.0"...
    - Installing hashicorp/aws v5.100.0...
    - Installed hashicorp/aws v5.100.0 (signed by HashiCorp)
    Terraform has been successfully initialized!
    ```

### Step 2: Format & Validate Configurations (terraform fmt & terraform validate)
Ensures your code is styled according to HashiCorp standards and is syntactically valid.
*   **Commands:**
    ```bash
    # Automatically formats all .tf files in the directory
    terraform fmt
    
    # Validates configuration syntax and logical connections
    terraform validate
    ```
*   **Example Output:**
    ```text
    Success! The configuration is valid.
    ```

### Step 3: Plan the Deployment (terraform plan)
Generates an execution plan, showing you exactly what resources will be created, modified, or destroyed before making any changes in AWS.
*   **Command:**
    ```bash
    terraform plan
    ```
*   **Example Output:**
    ```text
    Terraform will perform the following actions:
      # aws_vpc.main will be created
      + resource "aws_vpc" "main" { ... }
      # aws_instance.nat[0] will be created
      + resource "aws_instance" "nat" { ... }
      # aws_ec2_client_vpn_endpoint.main will be created
      + resource "aws_ec2_client_vpn_endpoint" "main" { ... }

    Plan: 21 to add, 0 to change, 0 to destroy.
    ```

### Step 4: Apply the Changes (terraform apply)
Executes the plan, provisioning the resources in your AWS account. It will prompt you for confirmation unless you pass the `-auto-approve` flag.
*   **Command:**
    ```bash
    terraform apply
    ```
*   **Example Output:**
    ```text
    Do you want to perform these actions?
      Terraform will perform the actions described above.
      Only 'yes' will be accepted to approve.

      Enter a value: yes

    aws_vpc.main: Creating...
    aws_vpc.main: Creation complete after 3s [id=vpc-09ec7a1293a98c8d4]
    ...
    aws_ec2_client_vpn_endpoint.main: Creating...
    aws_ec2_client_vpn_endpoint.main: Creation complete after 6m57s [id=cvpn-endpoint-0055a29e68e830388]

    Apply complete! Resources: 21 added, 0 changed, 0 destroyed.
    ```

### Step 5: Read Outputs (terraform output)
Retrieves the outputs declared in `outputs.tf`. You can query all outputs or target a specific output using the `-raw` flag.
*   **Commands:**
    ```bash
    # Print all outputs
    terraform output
    
    # Extract the client VPN endpoint ID raw string
    terraform output -raw client_vpn_endpoint_id
    ```
*   **Example Output:**
    ```text
    client_vpn_endpoint_id = "cvpn-endpoint-0055a29e68e830388"
    nat_public_ip = "32.193.231.76"
    ```

### Step 6: Clean Up Resources (terraform destroy)
Tears down all the resources managed by this workspace in your AWS account. It prompts for confirmation to prevent accidental deletion.
*   **Command:**
    ```bash
    terraform destroy
    ```
*   **Example Output:**
    ```text
    Terraform will perform the following actions:
      - destroy resource aws_ec2_client_vpn_endpoint.main
      - destroy resource aws_instance.nat[0]
      - destroy resource aws_vpc.main

    Plan: 0 to add, 0 to change, 21 to destroy.
    Do you want to perform these actions?
      Enter a value: yes
      
    aws_instance.nat[0]: Destroying...
    aws_vpc.main: Destroying...
    Destroy complete! Resources: 21 destroyed.
    ```
