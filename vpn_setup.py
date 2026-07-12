#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

def check_command(cmd):
    return shutil.which(cmd) is not None

def run_command(cmd, shell=False):
    try:
        result = subprocess.run(cmd, shell=shell, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
    certs_dir = "certs"
    required_files = ["ca.crt", "ca.key", "server.crt", "server.key", "client1.domain.tld.crt", "client1.domain.tld.key"]
    
    certs_exist = os.path.exists(certs_dir) and all(os.path.exists(os.path.join(certs_dir, f)) for f in required_files)
    
    if certs_exist:
        print("✅ Certificates already exist in 'certs/'. Skipping generation.")
        return True

    print("Generating client and server certificates...")
    # Make generate_certs.sh executable and run it
    if os.path.exists("generate_certs.sh"):
        os.chmod("generate_certs.sh", 0o755)
        # We simulate hitting 'y' or running directly
        success, stdout, stderr = run_command("./generate_certs.sh", shell=True)
        if success:
            print("✅ Certificates generated successfully.")
            return True
        else:
            print("❌ Failed to generate certificates via generate_certs.sh.")
            print(stderr)
    
    # Fallback to direct openssl commands if script execution fails
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
        os.chdir("..")
        print("✅ Certificates generated successfully.")
        return True
    except Exception as e:
        print(f"❌ Failed to generate certificates directly: {e}")
        return False

def main():
    print("==========================================================")
    print("        AWS Client VPN Interactive Installer")
    print("==========================================================")

    if not check_command("terraform"):
        print("❌ Error: 'terraform' CLI is not installed. Please install it to continue.")
        sys.exit(1)
        
    if not check_command("aws"):
        print("❌ Error: 'aws' CLI is not installed. Please install it to continue.")
        sys.exit(1)

    if not check_aws_credentials():
        sys.exit(1)

    # 1. Ask user for settings
    print("\nPlease configure your VPN parameters:")
    aws_region = get_input("AWS Region", "us-east-1")
    vpc_cidr = get_input("VPC CIDR Block", "10.0.0.0/16")
    public_subnet_cidr = get_input("Public Subnet CIDR Block", "10.0.1.0/24")
    private_subnet_cidr = get_input("Private Subnet CIDR Block", "10.0.2.0/24")
    client_cidr_block = get_input("Client VPN CIDR Block", "172.16.0.0/22")
    
    use_nat_gw_str = get_input("Use Managed NAT Gateway (otherwise cost-saving EC2 instance)? (yes/no)", "no")
    use_nat_gateway = use_nat_gw_str.lower() in ["y", "yes", "true"]
    
    nat_instance_type = "t3.nano"
    if not use_nat_gateway:
        nat_instance_type = get_input("EC2 NAT Instance type", "t3.nano")

    # 2. Write to terraform.tfvars
    print("\nWriting configuration to terraform.tfvars...")
    tfvars_content = f"""aws_region          = "{aws_region}"
vpc_cidr            = "{vpc_cidr}"
public_subnet_cidr  = "{public_subnet_cidr}"
private_subnet_cidr = "{private_subnet_cidr}"
client_cidr_block   = "{client_cidr_block}"
use_nat_gateway     = {str(use_nat_gateway).lower()}
nat_instance_type   = "{nat_instance_type}"
"""
    with open("terraform.tfvars", "w") as f:
        f.write(tfvars_content)
    print("✅ Configuration written successfully.")

    # 3. Generate certificates
    if not generate_certificates():
        sys.exit(1)

    # 4. Prompt to apply
    deploy_now = get_input("Do you want to deploy the VPN to AWS now? (yes/no)", "yes")
    if deploy_now.lower() not in ["y", "yes", "true"]:
        print("Skipping deployment. You can run 'terraform apply' manually when ready.")
        sys.exit(0)

    # 5. Initialize and apply
    print("\nInitializing Terraform...")
    success, stdout, stderr = run_command(["terraform", "init"])
    if not success:
        print("❌ Terraform init failed.")
        print(stderr)
        sys.exit(1)
    print("✅ Terraform initialized.")

    print("\nApplying Terraform configuration (this may take several minutes)...")
    # Using Popen to stream logs
    try:
        process = subprocess.Popen(["terraform", "apply", "-auto-approve"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
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

    # 6. Run configure_ovpn.sh to export client configuration
    print("\nGenerating OpenVPN client profile...")
    if os.path.exists("configure_ovpn.sh"):
        os.chmod("configure_ovpn.sh", 0o755)
        success, stdout, stderr = run_command(["./configure_ovpn.sh"])
        if success:
            print(stdout)
        else:
            print("❌ Failed to run configure_ovpn.sh.")
            print(stderr)
            sys.exit(1)
    else:
        print("❌ Error: configure_ovpn.sh not found. Cannot generate OpenVPN profile.")
        sys.exit(1)

    print("\n🎉 Setup complete! Import 'client.ovpn' into OpenVPN to connect.")

if __name__ == "__main__":
    main()
