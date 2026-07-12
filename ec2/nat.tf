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
