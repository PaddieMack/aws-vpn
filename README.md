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

---

## Clean Up (Destroying Resources)

To avoid recurring AWS charges after you are finished, tear down the infrastructure:

```bash
terraform destroy
```
This will automatically delete all VPC resources, the NAT instance, the Client VPN endpoint, and delete the certificates from AWS ACM.
