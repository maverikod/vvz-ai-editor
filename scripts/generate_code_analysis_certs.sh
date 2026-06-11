#!/bin/bash

# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
# Script to generate mTLS certificates for ai-editor-server

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CA_KEY_SIZE=4096
SERVER_KEY_SIZE=2048
CLIENT_KEY_SIZE=2048
VALIDITY_DAYS=3650  # 10 years

# Service name
SERVICE_NAME="ai-editor-server"
CLIENT_NAME="ai-editor"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CERT_DIR="$PROJECT_ROOT/mtls_certificates/mtls_certificates"

# Check if CA exists
if [ ! -f "$CERT_DIR/ca/ca.crt" ] || [ ! -f "$CERT_DIR/ca/ca.key" ]; then
    echo -e "${RED}❌ CA certificate not found at $CERT_DIR/ca/${NC}"
    echo -e "${YELLOW}Please ensure CA certificates exist before generating server certificates.${NC}"
    exit 1
fi

echo -e "${BLUE}🔐 Generating mTLS Certificates for ai-editor-server${NC}"
echo -e "${BLUE}========================================================${NC}"
echo ""

# Function to generate server certificate
generate_server_cert() {
    local service_name=$1
    echo -e "${YELLOW}🔧 Generating server certificate for: $service_name${NC}"
    
    # Generate server private key
    openssl genrsa -out "$CERT_DIR/server/${service_name}.key" $SERVER_KEY_SIZE
    chmod 600 "$CERT_DIR/server/${service_name}.key"
    
    # Generate server certificate signing request
    openssl req -new -key "$CERT_DIR/server/${service_name}.key" -out "$CERT_DIR/server/${service_name}.csr" \
        -subj "/C=UA/ST=Kyiv/L=Kyiv/O=MCP-Proxy/OU=Server/CN=${service_name}"
    
    # Generate server certificate
    openssl x509 -req -in "$CERT_DIR/server/${service_name}.csr" \
        -CA "$CERT_DIR/ca/ca.crt" -CAkey "$CERT_DIR/ca/ca.key" \
        -CAcreateserial -out "$CERT_DIR/server/${service_name}.crt" -days $VALIDITY_DAYS \
        -extensions v3_server -extfile <(
            echo '[v3_server]'
            echo 'basicConstraints = CA:FALSE'
            echo 'keyUsage = critical,digitalSignature,keyEncipherment'
            echo 'extendedKeyUsage = serverAuth'
            echo 'subjectAltName = @alt_names'
            echo '[alt_names]'
            echo "DNS.1 = ${service_name}"
            echo "DNS.2 = ${service_name}.local"
            echo "DNS.3 = localhost"
            echo "IP.1 = 127.0.0.1"
            echo "IP.2 = 172.20.0.1"
            echo "IP.3 = 172.24.0.1"
        )
    
    # Clean up CSR
    rm "$CERT_DIR/server/${service_name}.csr"
    
    echo -e "${GREEN}✅ Server certificate generated: server/${service_name}.crt${NC}"
}

# Function to generate client certificate
generate_client_cert() {
    local client_name=$1
    echo -e "${YELLOW}👤 Generating client certificate for: $client_name${NC}"
    
    # Generate client private key
    openssl genrsa -out "$CERT_DIR/client/${client_name}.key" $CLIENT_KEY_SIZE
    chmod 600 "$CERT_DIR/client/${client_name}.key"
    
    # Generate client certificate signing request
    openssl req -new -key "$CERT_DIR/client/${client_name}.key" -out "$CERT_DIR/client/${client_name}.csr" \
        -subj "/C=UA/ST=Kyiv/L=Kyiv/O=MCP-Proxy/OU=Client/CN=${client_name}-client"
    
    # Generate client certificate
    openssl x509 -req -in "$CERT_DIR/client/${client_name}.csr" \
        -CA "$CERT_DIR/ca/ca.crt" -CAkey "$CERT_DIR/ca/ca.key" \
        -CAcreateserial -out "$CERT_DIR/client/${client_name}.crt" -days $VALIDITY_DAYS \
        -extensions v3_client -extfile <(
            echo '[v3_client]'
            echo 'basicConstraints = CA:FALSE'
            echo 'keyUsage = critical,digitalSignature,keyEncipherment'
            echo 'extendedKeyUsage = clientAuth'
            echo 'subjectAltName = @alt_names'
            echo '[alt_names]'
            echo "DNS.1 = ${client_name}-client"
            echo "DNS.2 = ${client_name}.local"
        )
    
    # Clean up CSR
    rm "$CERT_DIR/client/${client_name}.csr"
    
    echo -e "${GREEN}✅ Client certificate generated: client/${client_name}.crt${NC}"
}

# Function to create combined certificates
create_combined_certs() {
    local service_name=$1
    local client_name=$2
    echo -e "${YELLOW}🔗 Creating combined certificates${NC}"
    
    # Server combined (cert + key)
    cat "$CERT_DIR/server/${service_name}.crt" "$CERT_DIR/server/${service_name}.key" > "$CERT_DIR/server/${service_name}.pem"
    chmod 600 "$CERT_DIR/server/${service_name}.pem"
    
    # Client combined (cert + key)
    cat "$CERT_DIR/client/${client_name}.crt" "$CERT_DIR/client/${client_name}.key" > "$CERT_DIR/client/${client_name}.pem"
    chmod 600 "$CERT_DIR/client/${client_name}.pem"
    
    echo -e "${GREEN}✅ Combined certificates created${NC}"
}

# Main execution
main() {
    echo -e "${BLUE}Starting certificate generation...${NC}"
    echo ""
    
    # Ensure directories exist
    mkdir -p "$CERT_DIR/server"
    mkdir -p "$CERT_DIR/client"
    
    # Generate server certificate
    generate_server_cert "$SERVICE_NAME"
    echo ""
    
    # Generate client certificate
    generate_client_cert "$CLIENT_NAME"
    echo ""
    
    # Create combined certificates
    create_combined_certs "$SERVICE_NAME" "$CLIENT_NAME"
    echo ""
    
    # Display certificate information
    echo -e "${BLUE}📋 Certificate Summary${NC}"
    echo -e "${BLUE}=====================${NC}"
    echo ""
    echo -e "${GREEN}✅ Server certificate:${NC}"
    echo -e "   $CERT_DIR/server/${SERVICE_NAME}.crt"
    echo -e "   $CERT_DIR/server/${SERVICE_NAME}.key"
    echo -e "   $CERT_DIR/server/${SERVICE_NAME}.pem"
    echo ""
    echo -e "${GREEN}✅ Client certificate:${NC}"
    echo -e "   $CERT_DIR/client/${CLIENT_NAME}.crt"
    echo -e "   $CERT_DIR/client/${CLIENT_NAME}.key"
    echo -e "   $CERT_DIR/client/${CLIENT_NAME}.pem"
    echo ""
    
    # Verify certificates
    echo -e "${BLUE}🔍 Verifying certificates...${NC}"
    if openssl verify -CAfile "$CERT_DIR/ca/ca.crt" "$CERT_DIR/server/${SERVICE_NAME}.crt" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Server certificate is valid${NC}"
    else
        echo -e "${RED}❌ Server certificate verification failed${NC}"
    fi
    
    if openssl verify -CAfile "$CERT_DIR/ca/ca.crt" "$CERT_DIR/client/${CLIENT_NAME}.crt" >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Client certificate is valid${NC}"
    else
        echo -e "${RED}❌ Client certificate verification failed${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}🎉 Certificate generation completed successfully!${NC}"
}

# Run main function
main
