#!/usr/bin/env python3
import os
import subprocess
import shutil
import time
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("AWS-VPN-Manager")

def run_command(cmd, cwd=None):
    """Utility helper to run commands and capture outputs."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr

@mcp.tool()
def get_vpn_status(vpn_type: str = "ec2") -> str:
    """Check the deployment status and output parameters of the VPN.
    
    Parameters:
    - vpn_type: Either 'ec2' (AWS Client VPN) or 'lightsail' (AWS Lightsail OpenVPN server)
    """
    if vpn_type not in ["ec2", "lightsail"]:
        return "Error: vpn_type must be either 'ec2' or 'lightsail'."

    if not shutil.which("terraform"):
        return "Error: 'terraform' CLI is not installed or not in PATH."
    
    cwd = "ec2" if vpn_type == "ec2" else "lightsail"
    success, stdout, stderr = run_command(["terraform", "output", "-json"], cwd=cwd)
    if not success:
        return f"VPN type '{vpn_type}' is not deployed yet or state is empty."
    return f"Current {vpn_type.upper()} Deployment Outputs:\n{stdout}"

@mcp.tool()
def configure_vpn(
    vpn_type: str = "ec2",
    aws_region: str = "us-east-1",
    vpc_cidr: str = "10.0.0.0/16",
    public_subnet_cidr: str = "10.0.1.0/24",
    private_subnet_cidr: str = "10.0.2.0/24",
    client_cidr_block: str = "172.16.0.0/22",
    use_nat_gateway: bool = False,
    nat_instance_type: str = "t3.nano",
    public_subnet_az: str = "us-east-1a",
    network_border_group: str = "",
    instance_name: str = "lightsail-vpn"
) -> str:
    """Configure the parameters for the selected VPN type.
    
    Parameters:
    - vpn_type: Either 'ec2' (AWS Client VPN) or 'lightsail' (AWS Lightsail OpenVPN)
    - aws_region: AWS Region to deploy in (e.g. us-east-1)
    
    EC2 Specific Parameters:
    - vpc_cidr: CIDR block for the new VPC (e.g. 10.0.0.0/16)
    - public_subnet_cidr: CIDR block for the public subnet (e.g. 10.0.1.0/24)
    - private_subnet_cidr: CIDR block for the private subnet (e.g. 10.0.2.0/24)
    - client_cidr_block: IP range block for VPN clients (e.g. 172.16.0.0/22)
    - use_nat_gateway: If true, deploy a Managed NAT Gateway. If false, deploy a cost-effective EC2 NAT Instance.
    - nat_instance_type: EC2 Instance type for the NAT Instance (if use_nat_gateway is false)
    - public_subnet_az: Availability Zone for the public subnet (e.g. us-east-1a, or us-east-1-dfw-2a for Dallas Local Zone)
    - network_border_group: Network Border Group for Elastic IP (e.g. us-east-1-dfw-2 for Dallas Local Zone, leave empty for default)
    
    Lightsail Specific Parameters:
    - instance_name: The name of the Lightsail instance (e.g. lightsail-vpn)
    """
    if vpn_type not in ["ec2", "lightsail"]:
        return "Error: vpn_type must be either 'ec2' or 'lightsail'."

    try:
        if vpn_type == "ec2":
            border_group_val = "null" if (not network_border_group or network_border_group.lower() in ["null", "none"]) else f'"{network_border_group}"'
            tfvars_content = f"""aws_region          = "{aws_region}"
vpc_cidr            = "{vpc_cidr}"
public_subnet_cidr  = "{public_subnet_cidr}"
private_subnet_cidr = "{private_subnet_cidr}"
client_cidr_block   = "{client_cidr_block}"
use_nat_gateway     = {str(use_nat_gateway).lower()}
nat_instance_type   = "{nat_instance_type}"
public_subnet_az    = "{public_subnet_az}"
network_border_group = {border_group_val}
"""
            with open("ec2/terraform.tfvars", "w") as f:
                f.write(tfvars_content)
            return "EC2 VPN Configuration written to ec2/terraform.tfvars successfully."
        else:
            lightsail_dir = "lightsail"
            os.makedirs(lightsail_dir, exist_ok=True)
            tfvars_content = f"""aws_region    = "{aws_region}"
instance_name = "{instance_name}"
"""
            with open(os.path.join(lightsail_dir, "terraform.tfvars"), "w") as f:
                f.write(tfvars_content)
            return "Lightsail VPN Configuration written to lightsail/terraform.tfvars successfully."
    except Exception as e:
        return f"Error writing configuration: {str(e)}"

@mcp.tool()
def deploy_vpn(vpn_type: str = "ec2") -> str:
    """Run terraform init and terraform apply to deploy the selected VPN.
    
    Parameters:
    - vpn_type: Either 'ec2' (AWS Client VPN) or 'lightsail' (AWS Lightsail OpenVPN)
    """
    if vpn_type not in ["ec2", "lightsail"]:
        return "Error: vpn_type must be either 'ec2' or 'lightsail'."

    if vpn_type == "ec2":
        # 1. Check/generate certificates
        required_files = ["ca.crt", "ca.key", "server.crt", "server.key", "client1.domain.tld.crt", "client1.domain.tld.key"]
        certs_dir = "ec2/certs"
        certs_exist = os.path.exists(certs_dir) and all(os.path.exists(os.path.join(certs_dir, f)) for f in required_files)
        
        if not certs_exist:
            if os.path.exists("ec2/generate_certs.sh"):
                os.chmod("ec2/generate_certs.sh", 0o755)
                try:
                    subprocess.run("./generate_certs.sh", cwd="ec2", input="y\n", text=True, check=True)
                except subprocess.CalledProcessError as e:
                    return f"Error running generate_certs.sh: {e}"
            else:
                return "Error: generate_certs.sh not found and certificates are missing."
                
        # 2. Run terraform init
        success, stdout, stderr = run_command(["terraform", "init"], cwd="ec2")
        if not success:
            return f"Terraform init failed:\n{stderr}"
            
        # 3. Run terraform apply
        success, stdout, stderr = run_command(["terraform", "apply", "-auto-approve"], cwd="ec2")
        if not success:
            return f"Terraform apply failed:\n{stderr}"
            
        # 4. Generate the OVPN profile
        if os.path.exists("ec2/configure_ovpn.sh"):
            os.chmod("ec2/configure_ovpn.sh", 0o755)
            ovpn_success, ovpn_stdout, ovpn_stderr = run_command(["./configure_ovpn.sh"], cwd="ec2")
            if not ovpn_success:
                return f"Terraform applied, but generating client.ovpn failed:\n{ovpn_stderr}"
                
        return f"EC2 Client VPN deployed successfully!\n\nOutputs:\n{stdout}"

    else:
        # Lightsail deployment
        lightsail_dir = "lightsail"
        
        # 1. Run terraform init
        success, stdout, stderr = run_command(["terraform", "init"], cwd=lightsail_dir)
        if not success:
            return f"Terraform init failed in lightsail/ folder:\n{stderr}"
            
        # 2. Run terraform apply
        success, stdout, stderr = run_command(["terraform", "apply", "-auto-approve"], cwd=lightsail_dir)
        if not success:
            return f"Terraform apply failed in lightsail/ folder:\n{stderr}"
            
        # 3. Get static IP
        success_ip, stdout_ip, stderr_ip = run_command(["terraform", "output", "-raw", "vpn_public_ip"], cwd=lightsail_dir)
        if not success_ip:
            return f"Terraform applied, but failed to fetch public IP output:\n{stderr_ip}"
        vpn_ip = stdout_ip.strip()

        # 4. Securely download the configuration profile
        scp_cmd = [
            "scp",
            "-i", os.path.join(lightsail_dir, "lightsail_vpn.pem"),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            f"ubuntu@{vpn_ip}:~/client.ovpn",
            "client_lightsail.ovpn"
        ]

        ovpn_downloaded = False
        # Retry loop for up to 3 minutes (18 * 10 seconds)
        for attempt in range(1, 19):
            time.sleep(10)
            success_scp, _, _ = run_command(scp_cmd)
            if success_scp:
                ovpn_downloaded = True
                break

        if not ovpn_downloaded:
            return (f"Lightsail VPN instance deployed at static IP {vpn_ip}, but client configuration retrieval timed out.\n"
                    f"The server is likely still installing OpenVPN. You can try downloading it manually later using:\n"
                    f"  scp -i lightsail/lightsail_vpn.pem ubuntu@{vpn_ip}:~/client.ovpn client_lightsail.ovpn")
        
        return f"Lightsail OpenVPN server deployed successfully! Client profile downloaded to 'client_lightsail.ovpn'.\n\nOutputs:\n{stdout}"

@mcp.tool()
def get_client_config(vpn_type: str = "ec2") -> str:
    """Retrieve the contents of the OpenVPN client profile.
    
    Parameters:
    - vpn_type: Either 'ec2' (AWS Client VPN) or 'lightsail' (AWS Lightsail OpenVPN)
    """
    if vpn_type not in ["ec2", "lightsail"]:
        return "Error: vpn_type must be either 'ec2' or 'lightsail'."

    filename = "client.ovpn" if vpn_type == "ec2" else "client_lightsail.ovpn"
    if not os.path.exists(filename):
        return f"Error: {filename} not found. Have you deployed the '{vpn_type}' VPN?"
    
    try:
        with open(filename, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading {filename}: {str(e)}"

@mcp.tool()
def destroy_vpn(vpn_type: str = "ec2") -> str:
    """Tear down all deployed resources for the selected VPN.
    
    Parameters:
    - vpn_type: Either 'ec2' (AWS Client VPN) or 'lightsail' (AWS Lightsail OpenVPN)
    """
    if vpn_type not in ["ec2", "lightsail"]:
        return "Error: vpn_type must be either 'ec2' or 'lightsail'."

    cwd = "ec2" if vpn_type == "ec2" else "lightsail"
    success, stdout, stderr = run_command(["terraform", "destroy", "-auto-approve"], cwd=cwd)
    if not success:
        return f"Terraform destroy failed for '{vpn_type}':\n{stderr}"
    return f"VPN resources for '{vpn_type}' destroyed successfully:\n{stdout}"

if __name__ == "__main__":
    # Launch MCP server over stdin/stdout transport
    mcp.run()
