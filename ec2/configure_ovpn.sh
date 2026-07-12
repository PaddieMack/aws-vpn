#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${WORKSPACE_DIR}"

# Fetch variables from Terraform output
echo "Fetching configuration from Terraform..."
ENDPOINT_ID=$(terraform output -raw client_vpn_endpoint_id)
REGION=$(aws configure get region || echo "us-east-1")

echo "=========================================================="
echo " Generating Client OpenVPN Profile"
echo "=========================================================="
echo "VPN Endpoint ID: ${ENDPOINT_ID}"
echo "Region:          ${REGION}"
echo "=========================================================="

# Export the configuration
echo "1. Exporting configuration template from AWS..."
aws ec2 export-client-vpn-client-configuration \
  --client-vpn-endpoint-id "${ENDPOINT_ID}" \
  --output text \
  --region "${REGION}" > ../client.ovpn

# Append certificate and key
echo "2. Appending client certificate and key..."
{
  echo ""
  echo "<cert>"
  cat certs/client1.domain.tld.crt
  echo "</cert>"
  echo "<key>"
  cat certs/client1.domain.tld.key
  echo "</key>"
} >> ../client.ovpn

# Modify the remote address to prepend a random subdomain (prevents DNS caching issues)
echo "3. Prepending random subdomain to bypass DNS caching..."
if [[ "$OSTYPE" == "darwin"* ]]; then
  sed -i '' 's/remote \(.*cvpn-endpoint.*\)/remote random.\1/g' ../client.ovpn
else
  sed -i 's/remote \(.*cvpn-endpoint.*\)/remote random.\1/g' ../client.ovpn
fi

echo "=========================================================="
echo " Done! Profile saved as: ../client.ovpn"
echo "=========================================================="
echo " You can now import client.ovpn from the root folder into your OpenVPN client"
echo " (like Tunnelblick or OpenVPN Connect) and connect."
echo "=========================================================="
