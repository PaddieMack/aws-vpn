# AWS Client VPN Setup (Terraform)

This project provisions an AWS Client VPN in a new VPC configured in **Full-Tunnel** mode. All your client machine's internet traffic will route through the VPN, making your public source IP appear as the Elastic IP of a cost-saving **NAT Instance** (running in `us-east-1` or your configured region).

---

## Workspace Structure

*   `generate_certs.sh`: Shell script to generate mutual authentication SSL certificates.
*   `manual_walkthrough.md`: Detailed guide for setting up the infrastructure manually in the AWS Console for learning purposes.
*   `providers.tf`, `variables.tf`, `main.tf`, `nat.tf`, `vpn.tf`, `outputs.tf`: Terraform configuration.

---

## Step-by-Step Deployment Instructions

### 1. Configure AWS Credentials

Before running Terraform, ensure your AWS CLI credentials are set up. If you have not set up your profile yet, you can run:

```bash
aws configure
```

This will prompt you for:
*   `AWS Access Key ID`
*   `AWS Secret Access Key`
*   `Default region name` (e.g., `us-east-1`)
*   `Default output format` (e.g., `json`)

Alternatively, you can manually create or edit the standard files `~/.aws/config` and `~/.aws/credentials`.

### 2. Generate SSL Certificates (Completed)

We use mutual certificate authentication. The local CA, server, and client certs are already generated in the `certs/` directory using:

```bash
./generate_certs.sh
```

Terraform will read these files directly and upload them to AWS Certificate Manager (ACM) automatically during deployment.

### 3. Deploy the Infrastructure

Initialize Terraform and apply the plan:

```bash
# Initialize Terraform and download providers
terraform init

# Preview changes
terraform plan

# Apply changes (enter 'yes' when prompted)
terraform apply
```

### 4. Build and Configure Your OpenVPN Profile

Once Terraform finishes, it will print several outputs. Follow these steps to build your client `.ovpn` file:

1.  **Export the client configuration template:**
    Run the command from the Terraform outputs:
    ```bash
    aws ec2 export-client-vpn-client-configuration \
      --client-vpn-endpoint-id <ENDPOINT_ID> \
      --output text \
      --region <REGION> > client-config.ovpn
    ```
    *(A convenience command is printed in the Terraform output `download_config_command`).*

2.  **Append Certificates & Private Keys:**
    Open the newly created `client-config.ovpn` in a text editor and append the client certificates to the end of the file:
    ```xml
    <cert>
    [Contents of certs/client1.domain.tld.crt]
    </cert>

    <key>
    [Contents of certs/client1.domain.tld.key]
    </key>
    ```

3.  **Bypass DNS Caching (Important):**
    Locate the line starting with `remote` (e.g. `remote cvpn-endpoint-xxx.prod.clientvpn.us-east-1.amazonaws.com 443`). Prepend a random string to the subdomain so it looks like:
    ```
    remote random.cvpn-endpoint-xxx.prod.clientvpn.us-east-1.amazonaws.com 443
    ```

4.  **Connect:**
    Import the `client-config.ovpn` file into your OpenVPN client (e.g., Tunnelblick or OpenVPN Connect) and connect!

### 5. Automated Setup with Python
As an alternative to running Terraform manually, you can run the interactive setup script:

```bash
python3 vpn_setup.py
```
This script will:
* Check for required CLI tools (`terraform` and `aws`) and verify your AWS credentials.
* Interactively prompt you for configuration values (region, CIDRs, NAT gateway options).
* Write them to `terraform.tfvars`.
* Generate keys/certificates (if missing) and automatically deploy all resources.
* Generate and configure the ready-to-use `client.ovpn` file.

---

## Model Context Protocol (MCP) Server

An MCP server (`mcp_server.py`) is provided so you can manage your VPN deployment programmatically through AI assistants (like Claude, Gemini, orCursor).

### Available Tools:
- **`configure_vpn`**: Configures variables and saves them to `terraform.tfvars`.
- **`deploy_vpn`**: Automates initialization, cert generation, resource creation, and client config building.
- **`get_vpn_status`**: Reads active Terraform output properties.
- **`get_client_config`**: Retrieves the generated `client.ovpn` profile contents.
- **`destroy_vpn`**: Completely destroys the AWS VPN infrastructure.

### Installation & Run:
To run the server, install the dependencies first:
```bash
pip install -r requirements.txt
python3 mcp_server.py
```

### Claude Desktop Integration:
Add the following configuration to your `claude_desktop_config.json` (typically located in `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "aws-vpn-manager": {
      "command": "python3",
      "args": ["/Users/pat/Gemini/aws-vpn/mcp_server.py"],
      "env": {
        "AWS_PROFILE": "default",
        "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
      }
    }
  }
}
```

---

## Clean Up (Destroying Resources)

To avoid recurring AWS charges after you are finished, tear down the infrastructure:

```bash
terraform destroy
```
Alternatively, you can run this via the Python MCP tool `destroy_vpn`.
This will automatically delete all VPC resources, the NAT instance, the Client VPN endpoint, and delete the certificates from AWS ACM.
