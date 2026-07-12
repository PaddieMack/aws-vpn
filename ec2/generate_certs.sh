#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

# Define directories
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTS_DIR="${WORKSPACE_DIR}/certs"

echo "=========================================================="
echo " AWS Client VPN Certificate Generator"
echo "=========================================================="

if [ -d "${CERTS_DIR}" ]; then
    echo "Warning: ${CERTS_DIR} directory already exists."
    read -p "Do you want to overwrite existing certificates? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborting certificate generation. Existing certificates preserved."
        exit 0
    fi
fi

# Recreate certs directory
rm -rf "${CERTS_DIR}"
mkdir -p "${CERTS_DIR}"
cd "${CERTS_DIR}"

echo "1. Generating Certificate Authority (CA) key and certificate..."
openssl genrsa -out ca.key 2048
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt -subj "/CN=AWS-Client-VPN-CA"

echo "2. Generating Server private key and CSR..."
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr -subj "/CN=vpn-server.local"

echo "3. Signing Server certificate using CA..."
openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt

echo "4. Generating Client private key and CSR..."
openssl genrsa -out client1.domain.tld.key 2048
openssl req -new -key client1.domain.tld.key -out client1.domain.tld.csr -subj "/CN=client1.domain.tld"

echo "5. Signing Client certificate using CA..."
openssl x509 -req -days 365 -in client1.domain.tld.csr -CA ca.crt -CAkey ca.key -CAserial ca.srl -out client1.domain.tld.crt

echo "=========================================================="
echo " Certificates successfully generated in:"
echo " ${CERTS_DIR}"
echo "=========================================================="
echo "Files created:"
echo " - ca.key / ca.crt (Certificate Authority)"
echo " - server.key / server.crt (Server Certificate)"
echo " - client1.domain.tld.key / client1.domain.tld.crt (Client Certificate)"
echo "=========================================================="
