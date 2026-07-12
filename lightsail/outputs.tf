output "vpn_public_ip" {
  description = "The public static IP address of the Lightsail VPN server"
  value       = aws_lightsail_static_ip.vpn_ip.ip_address
}

output "instance_name" {
  description = "The name of the Lightsail instance"
  value       = aws_lightsail_instance.vpn.name
}

output "ssh_command" {
  description = "SSH command to connect to the server"
  value       = "ssh -i ${path.module}/lightsail_vpn.pem ubuntu@${aws_lightsail_static_ip.vpn_ip.ip_address}"
}

output "get_config_command" {
  description = "Command to download the OpenVPN configuration file"
  value       = "scp -i ${path.module}/lightsail_vpn.pem ubuntu@${aws_lightsail_static_ip.vpn_ip.ip_address}:~/client.ovpn ${path.module}/../client_lightsail_virginia.ovpn"
}
