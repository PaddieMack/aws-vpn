# Generate SSH Private Key
resource "tls_private_key" "vpn_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# Save Private Key Locally
resource "local_file" "private_key" {
  content         = tls_private_key.vpn_key.private_key_pem
  filename        = "${path.module}/lightsail_vpn.pem"
  file_permission = "0600"
}

# Upload Public Key to Lightsail
resource "aws_lightsail_key_pair" "vpn_key_pair" {
  name       = "${var.instance_name}-key"
  public_key = tls_private_key.vpn_key.public_key_openssh
}

# Deploy Lightsail Instance
resource "aws_lightsail_instance" "vpn" {
  name              = var.instance_name
  availability_zone = "${var.aws_region}a"
  blueprint_id      = "ubuntu_22_04"
  bundle_id         = "nano_3_0" # $5.00/mo plan (IPv4 + IPv6)
  key_pair_name     = aws_lightsail_key_pair.vpn_key_pair.name

  # Run script to install OpenVPN
  user_data = <<-EOF
              #!/bin/bash
              # Wait for internet connectivity
              until ping -c 1 8.8.8.8; do sleep 1; done
              
              # Download installer
              curl -O https://raw.githubusercontent.com/angristan/openvpn-install/master/openvpn-install.sh
              chmod +x openvpn-install.sh
              
              # Install OpenVPN non-interactively
              AUTO_INSTALL=y ./openvpn-install.sh
              
              # Create a passwordless client named 'client'
              ./openvpn-install.sh --non-interactive --create client
              
              # Move the client configuration file to ubuntu's home directory so it's accessible via SSH
              mv /root/client.ovpn /home/ubuntu/client.ovpn
              chown ubuntu:ubuntu /home/ubuntu/client.ovpn
              EOF

  tags = {
    Name = var.instance_name
  }
}

# Allocate and attach Static IP
resource "aws_lightsail_static_ip" "vpn_ip" {
  name = "${var.instance_name}-static-ip"
}

resource "aws_lightsail_static_ip_attachment" "vpn_ip_attach" {
  static_ip_name = aws_lightsail_static_ip.vpn_ip.name
  instance_name  = aws_lightsail_instance.vpn.name
}

# Configure firewall rules for the Lightsail Instance
resource "aws_lightsail_instance_public_ports" "vpn_ports" {
  instance_name = aws_lightsail_instance.vpn.name

  port_info {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidrs       = ["0.0.0.0/0"] # Allow SSH for pulling the config
  }

  port_info {
    from_port   = 1194
    to_port     = 1194
    protocol    = "udp" # OpenVPN default port
    cidrs       = ["0.0.0.0/0"]
  }
}
