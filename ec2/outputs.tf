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

output "public_subnet_az" {
  description = "The Availability Zone of the public subnet"
  value       = var.public_subnet_az
}
