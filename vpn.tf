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
    # Subnet associations take several minutes to create or destroy
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
