#!/usr/bin/env python3
import os
import subprocess
import shutil
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("AWS-VPN-Manager")

def run_command(cmd):
    """Utility helper to run commands and capture outputs."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr

@mcp.tool()
def get_vpn_status() -> str:
    """Check the deployment status of the AWS Client VPN and retrieve output values."""
    if not shutil.which("terraform"):
        return "Error: 'terraform' CLI is not installed or not in PATH."
    
    success, stdout, stderr = run_command(["terraform", "output", "-json"])
    if not success:
        return "VPN is not deployed yet or state is empty."
    return f"Current Deployment Outputs:\n{stdout}"

@mcp.tool()
def configure_vpn(
    aws_region: str = "us-east-1",
    vpc_cidr: str = "10.0.0.0/16",
    public_subnet_cidr: str = "10.0.1.0/24",
    private_subnet_cidr: str = "10.0.2.0/24",
    client_cidr_block: str = "172.16.0.0/22",
    use_nat_gateway: bool = False,
    nat_instance_type: str = "t3.nano"
) -> str:
    """Configure the parameters for the AWS Client VPN and save them to terraform.tfvars.
    
    Parameters:
    - aws_region: AWS Region to deploy in (e.g. us-east-1)
    - vpc_cidr: CIDR block for the new VPC (e.g. 10.0.0.0/16)
    - public_subnet_cidr: CIDR block for the public subnet (e.g. 10.0.1.0/24)
    - private_subnet_cidr: CIDR block for the private subnet (e.g. 10.0.2.0/24)
    - client_cidr_block: IP range block for VPN clients (e.g. 172.16.0.0/22)
    - use_nat_gateway: If true, deploy a Managed NAT Gateway. If false, deploy a cost-effective EC2 NAT Instance.
    - nat_instance_type: EC2 Instance type for the NAT Instance (if use_nat_gateway is false)
    """
    tfvars_content = f"""aws_region          = "{aws_region}"
vpc_cidr            = "{vpc_cidr}"
public_subnet_cidr  = "{public_subnet_cidr}"
private_subnet_cidr = "{private_subnet_cidr}"
client_cidr_block   = "{client_cidr_block}"
use_nat_gateway     = {str(use_nat_gateway).lower()}
nat_instance_type   = "{nat_instance_type}"
"""
    try:
        with open("terraform.tfvars", "w") as f:
            f.write(tfvars_content)
        return "Configuration written to terraform.tfvars successfully."
    except Exception as e:
        return f"Error writing configuration: {str(e)}"

@mcp.tool()
def deploy_vpn() -> str:
    """Run terraform init, generate certs if missing, and deploy the VPN resources using terraform apply."""
    # 1. Check/generate certificates
    required_files = ["ca.crt", "ca.key", "server.crt", "server.key", "client1.domain.tld.crt", "client1.domain.tld.key"]
    certs_dir = "certs"
    certs_exist = os.path.exists(certs_dir) and all(os.path.exists(os.path.join(certs_dir, f)) for f in required_files)
    
    if not certs_exist:
        print("Certificates missing. Generating new certificates...")
        if os.path.exists("generate_certs.sh"):
            os.chmod("generate_certs.sh", 0o755)
            try:
                subprocess.run("./generate_certs.sh", input="y\n", text=True, check=True)
            except subprocess.CalledProcessError as e:
                return f"Error running generate_certs.sh: {e}"
        else:
            return "Error: generate_certs.sh not found and certificates are missing."
            
    # 2. Run terraform init
    print("Running terraform init...")
    success, stdout, stderr = run_command(["terraform", "init"])
    if not success:
        return f"Terraform init failed:\n{stderr}"
        
    # 3. Run terraform apply
    print("Running terraform apply (this may take several minutes)...")
    success, stdout, stderr = run_command(["terraform", "apply", "-auto-approve"])
    if not success:
        return f"Terraform apply failed:\n{stderr}"
        
    # 4. Generate the OVPN profile
    print("Generating client OVPN configuration...")
    if os.path.exists("configure_ovpn.sh"):
        os.chmod("configure_ovpn.sh", 0o755)
        ovpn_success, ovpn_stdout, ovpn_stderr = run_command(["./configure_ovpn.sh"])
        if not ovpn_success:
            return f"Terraform applied, but generating client.ovpn failed:\n{ovpn_stderr}"
            
    return f"VPN deployed successfully!\n\nOutputs:\n{stdout}"

@mcp.tool()
def get_client_config() -> str:
    """Retrieve the contents of the generated client.ovpn configuration file."""
    if not os.path.exists("client.ovpn"):
        return "Error: client.ovpn not found. Have you deployed the VPN and run configure_ovpn.sh?"
    try:
        with open("client.ovpn", "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading client.ovpn: {str(e)}"

@mcp.tool()
def destroy_vpn() -> str:
    """Tear down all deployed VPN resources on AWS using terraform destroy."""
    print("Running terraform destroy...")
    success, stdout, stderr = run_command(["terraform", "destroy", "-auto-approve"])
    if not success:
        return f"Terraform destroy failed:\n{stderr}"
    return f"VPN resources destroyed successfully:\n{stdout}"

if __name__ == "__main__":
    # Launch MCP server over stdin/stdout transport
    mcp.run()
