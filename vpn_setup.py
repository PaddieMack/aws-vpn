#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
import time

def check_command(cmd):
    return shutil.which(cmd) is not None

def run_command(cmd, cwd=None, shell=False):
    try:
        result = subprocess.run(cmd, cwd=cwd, shell=shell, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return True, result.stdout, ""
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr

def get_input(prompt, default_val):
    user_input = input(f"{prompt} [{default_val}]: ").strip()
    return user_input if user_input else default_val

def check_aws_credentials():
    print("Checking AWS CLI credentials...")
    success, stdout, stderr = run_command(["aws", "sts", "get-caller-identity"])
    if not success:
        print("❌ Error: AWS credentials not configured or invalid.")
        print(stderr)
        return False
    print("✅ AWS credentials verified successfully.")
    return True

def generate_certificates():
    certs_dir = "ec2/certs"
    required_files = ["ca.crt", "ca.key", "server.crt", "server.key", "client1.domain.tld.crt", "client1.domain.tld.key"]
    
    certs_exist = os.path.exists(certs_dir) and all(os.path.exists(os.path.join(certs_dir, f)) for f in required_files)
    
    if certs_exist:
        print("✅ Certificates already exist in 'ec2/certs/'. Skipping generation.")
        return True

    print("Generating client and server certificates...")
    # Make generate_certs.sh executable and run it
    if os.path.exists("ec2/generate_certs.sh"):
        os.chmod("ec2/generate_certs.sh", 0o755)
        # Pass 'y' to prompt if directory exists
        try:
            subprocess.run("./generate_certs.sh", cwd="ec2", input="y\n", text=True, check=True)
            print("✅ Certificates generated successfully.")
            return True
        except subprocess.CalledProcessError as e:
            print("❌ Failed to generate certificates via generate_certs.sh.")
            print(e)
    
    # Fallback to direct openssl commands
    print("Running openssl commands directly...")
    try:
        os.makedirs(certs_dir, exist_ok=True)
        os.chdir(certs_dir)
        subprocess.run("openssl genrsa -out ca.key 2048", shell=True, check=True)
        subprocess.run("openssl req -new -x509 -days 3650 -key ca.key -out ca.crt -subj '/CN=AWS-Client-VPN-CA'", shell=True, check=True)
        subprocess.run("openssl genrsa -out server.key 2048", shell=True, check=True)
        subprocess.run("openssl req -new -key server.key -out server.csr -subj '/CN=vpn-server.local'", shell=True, check=True)
        subprocess.run("openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt", shell=True, check=True)
        subprocess.run("openssl genrsa -out client1.domain.tld.key 2048", shell=True, check=True)
        subprocess.run("openssl req -new -key client1.domain.tld.key -out client1.domain.tld.csr -subj '/CN=client1.domain.tld'", shell=True, check=True)
        subprocess.run("openssl x509 -req -days 365 -in client1.domain.tld.csr -CA ca.crt -CAkey ca.key -CAserial ca.srl -out client1.domain.tld.crt", shell=True, check=True)
        os.chdir("../..")
        print("✅ Certificates generated successfully.")
        return True
    except Exception as e:
        print(f"❌ Failed to generate certificates directly: {e}")
        return False

def setup_ec2_vpn():
    print("\n--- AWS Client VPN (EC2 NAT NAT-based) Configuration ---")
    
    aws_region = get_input("AWS Region", "us-east-1")
    vpc_cidr = get_input("VPC CIDR Block", "10.0.0.0/16")
    public_subnet_cidr = get_input("Public Subnet CIDR Block", "10.0.1.0/24")
    private_subnet_cidr = get_input("Private Subnet CIDR Block", "10.0.2.0/24")
    client_cidr_block = get_input("Client VPN CIDR Block", "172.16.0.0/22")
    
    use_nat_gw_str = get_input("Use Managed NAT Gateway (otherwise cost-saving EC2 instance)? (yes/no)", "no")
    use_nat_gateway = use_nat_gw_str.lower() in ["y", "yes", "true"]
    
    sub_region = "none"
    if aws_region == "us-east-1":
        sub_region = get_input("Deploy public subnet egress to a Texas Local Zone? (options: none, dallas, houston)", "none").strip().lower()

    public_subnet_az = f"{aws_region}a"
    network_border_group = "null"
    nat_instance_type = "t3.nano"

    if sub_region == "dallas":
        public_subnet_az = "us-east-1-dfw-2a"
        network_border_group = '"us-east-1-dfw-2"'
        if not use_nat_gateway:
            print("💡 Note: t3.nano is not supported in the Dallas Local Zone. Defaulting to c6i.large.")
            nat_instance_type = get_input("EC2 NAT Instance type", "c6i.large")
    elif sub_region == "houston":
        public_subnet_az = "us-east-1-iah-2a"
        network_border_group = '"us-east-1-iah-2"'
        if not use_nat_gateway:
            print("💡 Note: t3.nano is not supported in the Houston Local Zone. Defaulting to c6i.large.")
            nat_instance_type = get_input("EC2 NAT Instance type", "c6i.large")
    else:
        if not use_nat_gateway:
            nat_instance_type = get_input("EC2 NAT Instance type", "t3.nano")

    print("\nWriting configuration to ec2/terraform.tfvars...")
    tfvars_content = f"""aws_region          = "{aws_region}"
vpc_cidr            = "{vpc_cidr}"
public_subnet_cidr  = "{public_subnet_cidr}"
private_subnet_cidr = "{private_subnet_cidr}"
client_cidr_block   = "{client_cidr_block}"
use_nat_gateway     = {str(use_nat_gateway).lower()}
nat_instance_type   = "{nat_instance_type}"
public_subnet_az    = "{public_subnet_az}"
network_border_group = {network_border_group}
"""
    with open("ec2/terraform.tfvars", "w") as f:
        f.write(tfvars_content)
    print("✅ Configuration written successfully.")

    if not generate_certificates():
        sys.exit(1)

    deploy_now = get_input("Do you want to deploy the EC2 VPN to AWS now? (yes/no)", "yes")
    if deploy_now.lower() not in ["y", "yes", "true"]:
        print("Skipping deployment. You can run 'terraform apply' manually in the ec2/ folder when ready.")
        return

    print("\nInitializing Terraform for EC2...")
    success, stdout, stderr = run_command(["terraform", "init"], cwd="ec2")
    if not success:
        print("❌ Terraform init failed in ec2/ folder.")
        print(stderr)
        sys.exit(1)

    print("\nApplying Terraform configuration (this may take several minutes)...")
    try:
        process = subprocess.Popen(["terraform", "apply", "-auto-approve"], cwd="ec2", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(line, end="")
        process.wait()
        if process.returncode != 0:
            print("❌ Terraform apply failed.")
            sys.exit(1)
        print("✅ Terraform apply completed successfully.")
    except Exception as e:
        print(f"❌ Failed to run terraform apply: {e}")
        sys.exit(1)

    print("\nGenerating OpenVPN client profile...")
    if os.path.exists("ec2/configure_ovpn.sh"):
        os.chmod("ec2/configure_ovpn.sh", 0o755)
        success, stdout, stderr = run_command(["./configure_ovpn.sh"], cwd="ec2")
        if success:
            print(stdout)
        else:
            print("❌ Failed to run configure_ovpn.sh.")
            print(stderr)
            sys.exit(1)
    else:
        print("❌ Error: configure_ovpn.sh not found.")
        sys.exit(1)

    print("\n🎉 Setup complete! Import 'client.ovpn' into OpenVPN to connect.")

def setup_lightsail_vpn():
    print("\n--- AWS Lightsail VPN (Self-hosted OpenVPN) Configuration ---")
    
    aws_region = get_input("AWS Region", "us-east-1")
    instance_name = get_input("Lightsail Instance Name", "lightsail-vpn")

    lightsail_dir = "lightsail"
    os.makedirs(lightsail_dir, exist_ok=True)

    print("\nWriting configuration to lightsail/terraform.tfvars...")
    tfvars_content = f"""aws_region    = "{aws_region}"
instance_name = "{instance_name}"
"""
    with open(os.path.join(lightsail_dir, "terraform.tfvars"), "w") as f:
        f.write(tfvars_content)
    print("✅ Configuration written successfully.")

    deploy_now = get_input("Do you want to deploy the Lightsail VPN to AWS now? (yes/no)", "yes")
    if deploy_now.lower() not in ["y", "yes", "true"]:
        print("Skipping deployment. You can run 'terraform apply' manually in the lightsail/ folder when ready.")
        return

    print("\nInitializing Terraform for Lightsail...")
    success, stdout, stderr = run_command(["terraform", "init"], cwd=lightsail_dir)
    if not success:
        print("❌ Terraform init failed in lightsail/ folder.")
        print(stderr)
        sys.exit(1)

    print("\nApplying Lightsail configuration...")
    try:
        process = subprocess.Popen(["terraform", "apply", "-auto-approve"], cwd=lightsail_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(line, end="")
        process.wait()
        if process.returncode != 0:
            print("❌ Terraform apply failed.")
            sys.exit(1)
        print("✅ Terraform apply completed successfully.")
    except Exception as e:
        print(f"❌ Failed to run terraform apply: {e}")
        sys.exit(1)

    # Fetch public IP output
    success, stdout, stderr = run_command(["terraform", "output", "-raw", "vpn_public_ip"], cwd=lightsail_dir)
    if not success:
        print("❌ Failed to get vpn_public_ip output from Terraform.")
        sys.exit(1)
    vpn_ip = stdout.strip()

    print(f"\nVPN Server deployed at static IP: {vpn_ip}")
    print("Waiting for OpenVPN server setup to complete on the Lightsail instance...")
    print("This takes 1-2 minutes on first boot as the user-data script installs OpenVPN.")

    # Loop to download client.ovpn via SCP
    ovpn_downloaded = False
    scp_cmd = [
        "scp",
        "-i", os.path.join(lightsail_dir, "lightsail_vpn.pem"),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"ubuntu@{vpn_ip}:~/client.ovpn",
        "client_lightsail.ovpn"
    ]

    for attempt in range(1, 25): # Try for 4 minutes (24 * 10 seconds)
        print(f"Attempt {attempt}/24: Checking if client.ovpn is ready on the server...")
        success, stdout, stderr = run_command(scp_cmd)
        if success:
            print("✅ Success! OpenVPN profile downloaded to 'client_lightsail.ovpn'.")
            ovpn_downloaded = True
            break
        time.sleep(10)

    if not ovpn_downloaded:
        print("\n❌ Warning: OpenVPN profile could not be retrieved yet.")
        print("The server might still be completing its initial setup or SSH is starting up.")
        print("You can try downloading the configuration file manually later by running:")
        print(f"  scp -i lightsail/lightsail_vpn.pem ubuntu@{vpn_ip}:~/client.ovpn client_lightsail.ovpn")
    else:
        print("\n🎉 Setup complete! Import 'client_lightsail.ovpn' into OpenVPN to connect.")

def main():
    print("==========================================================")
    print("           AWS VPN Interactive Dual Installer")
    print("==========================================================")

    if not check_command("terraform"):
        print("❌ Error: 'terraform' CLI is not installed. Please install it to continue.")
        sys.exit(1)
        
    if not check_command("aws"):
        print("❌ Error: 'aws' CLI is not installed. Please install it to continue.")
        sys.exit(1)

    if not check_aws_credentials():
        sys.exit(1)

    print("\nPlease choose which VPN option you want to manage:")
    print("  [1] AWS Client VPN (EC2 NAT-based, highly secure, pay-per-hour)")
    print("  [2] AWS Lightsail VPN (Self-hosted OpenVPN, flat $5.00/mo rate)")
    
    choice = get_input("Enter choice (1 or 2)", "1")
    if choice == "1":
        setup_ec2_vpn()
    elif choice == "2":
        setup_lightsail_vpn()
    else:
        print("❌ Invalid choice. Aborting.")
        sys.exit(1)

if __name__ == "__main__":
    main()
