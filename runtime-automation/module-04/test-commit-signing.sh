#!/bin/bash
set -e

# Test script for programmatic git commit signing with RHTAS and Keycloak
# This script authenticates user1 and signs a commit using gitsign

echo "========================================="
echo "Testing Programmatic Commit Signing"
echo "========================================="

# Load provisioned data
USER_DATA_FILE="/user_data/user_data.yml"
if [ ! -f "$USER_DATA_FILE" ]; then
  echo "ERROR: User data file not found: $USER_DATA_FILE"
  exit 1
fi

echo "Loading provisioned data from $USER_DATA_FILE"

# Extract values from user_data.yml (JSON format)
KEYCLOAK_URL=$(grep '"keycloak_admin_console"' $USER_DATA_FILE | cut -d'"' -f4 | sed 's|https://||')
USERNAME=$(grep '"openshift_cluster_account_name"' $USER_DATA_FILE | cut -d'"' -f4)
PASSWORD=$(grep '"openshift_cluster_account_password"' $USER_DATA_FILE | cut -d'"' -f4)
CLUSTER_DOMAIN=$(grep '"openshift_cluster_ingress_domain"' $USER_DATA_FILE | cut -d'"' -f4)
CLIENT_ID=$(grep '"tas_chains_client_id"' $USER_DATA_FILE | cut -d'"' -f4)

# Static variables
TAS_NAMESPACE="tssc-tas"
KEYCLOAK_REALM="tas-chains"

echo "Loaded configuration:"
echo "  Username: $USERNAME"
echo "  Keycloak: https://$KEYCLOAK_URL"
echo "  Client ID: $CLIENT_ID"
echo "  Cluster domain: $CLUSTER_DOMAIN"

# Get RHTAS service URLs
echo ""
echo "Getting RHTAS service URLs..."
FULCIO_URL=$(oc get securesign trusted-artifact-signer -n $TAS_NAMESPACE -o jsonpath='{.status.fulcio.url}' 2>/dev/null || echo "")
REKOR_URL=$(oc get securesign trusted-artifact-signer -n $TAS_NAMESPACE -o jsonpath='{.status.rekor.url}' 2>/dev/null || echo "")
TUF_URL=$(oc get securesign trusted-artifact-signer -n $TAS_NAMESPACE -o jsonpath='{.status.tuf.url}' 2>/dev/null || echo "")

echo "Fulcio URL: $FULCIO_URL"
echo "Rekor URL: $REKOR_URL"
echo "TUF URL: $TUF_URL"

# Validate Keycloak URL
echo ""
if [ -z "$KEYCLOAK_URL" ]; then
  echo "ERROR: Could not get Keycloak URL from user data"
  exit 1
fi
echo "Keycloak URL: https://$KEYCLOAK_URL"

# Build token endpoint
TOKEN_ENDPOINT="https://$KEYCLOAK_URL/realms/$KEYCLOAK_REALM/protocol/openid-connect/token"
echo "Token endpoint: $TOKEN_ENDPOINT"

# Get access token for user1
echo ""
echo "Authenticating user1 and getting access token..."
TOKEN_RESPONSE=$(curl -k -s -X POST "$TOKEN_ENDPOINT" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=$CLIENT_ID" \
  -d "username=$USERNAME" \
  -d "password=$PASSWORD" \
  -d "grant_type=password" \
  -d "scope=openid email profile")

# Check if we got a token
ACCESS_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token // empty')
if [ -z "$ACCESS_TOKEN" ]; then
  echo "ERROR: Failed to get access token"
  echo "Response: $TOKEN_RESPONSE"
  exit 1
fi

echo "✓ Access token obtained (length: ${#ACCESS_TOKEN})"
ID_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.id_token // empty')
echo "✓ ID token obtained (length: ${#ID_TOKEN})"

# Decode and display token info
echo ""
echo "Token claims:"
echo "$ID_TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq -r '.email, .preferred_username, .sub' | head -3

# Test gitsign configuration
echo ""
echo "========================================="
echo "Testing gitsign with obtained token"
echo "========================================="

# Clone a test repo to /tmp
TEST_REPO="/tmp/test-commit-signing-$$"
echo "Creating test repository: $TEST_REPO"
mkdir -p $TEST_REPO
cd $TEST_REPO
git init

# Configure git for test
git config user.email "user1@example.com"
git config user.name "User 1"

# Configure gitsign
echo ""
echo "Configuring gitsign..."
git config --local commit.gpgsign true
git config --local tag.gpgsign true
git config --local gpg.x509.program gitsign
git config --local gpg.format x509

# Set gitsign environment variables
export GITSIGN_CONNECTOR_ID="https://$KEYCLOAK_URL/realms/$KEYCLOAK_REALM"
export GITSIGN_OIDC_ISSUER="https://$KEYCLOAK_URL/realms/$KEYCLOAK_REALM"
export GITSIGN_OIDC_CLIENT_ID="$CLIENT_ID"
export GITSIGN_FULCIO_URL="$FULCIO_URL"
export GITSIGN_REKOR_URL="$REKOR_URL"

# The key part - provide the ID token to gitsign
export GITSIGN_OIDC_TOKEN="$ID_TOKEN"

echo "GITSIGN_CONNECTOR_ID: $GITSIGN_CONNECTOR_ID"
echo "GITSIGN_OIDC_ISSUER: $GITSIGN_OIDC_ISSUER"
echo "GITSIGN_FULCIO_URL: $GITSIGN_FULCIO_URL"
echo "GITSIGN_REKOR_URL: $REKOR_URL"

# Create a test file and commit
echo ""
echo "Creating test commit..."
echo "Test content" > test.txt
git add test.txt

# Attempt to commit with signature
echo "Attempting signed commit..."
if git commit -m "Test signed commit" 2>&1 | tee /tmp/commit-output.txt; then
  echo ""
  echo "✓ Commit succeeded!"

  # Verify the signature
  echo ""
  echo "Verifying commit signature..."
  git log --show-signature -1

  echo ""
  echo "========================================="
  echo "SUCCESS: Commit signing works!"
  echo "========================================="
else
  echo ""
  echo "✗ Commit failed"
  echo "Output:"
  cat /tmp/commit-output.txt
  exit 1
fi

# Cleanup
cd /
rm -rf $TEST_REPO
