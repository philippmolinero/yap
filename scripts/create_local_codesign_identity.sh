#!/bin/bash
set -euo pipefail

IDENTITY_NAME="${YAP_LOCAL_CODESIGN_IDENTITY:-Yap Local Codesign}"
KEYCHAIN="${YAP_LOCAL_CODESIGN_KEYCHAIN:-$HOME/Library/Keychains/login.keychain-db}"
DAYS="${YAP_LOCAL_CODESIGN_DAYS:-3650}"
ALLOW_TRUST=0

usage() {
    cat <<EOF
Usage: scripts/create_local_codesign_identity.sh --trust

Creates and trusts a self-signed local code-signing identity named:
  $IDENTITY_NAME

This is useful for local Yap builds without an Apple Developer account, but it
adds a trusted code-signing certificate to your login keychain. Only run this on
a machine you control.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --trust)
            ALLOW_TRUST=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if security find-identity -v -p codesigning "$KEYCHAIN" 2>/dev/null | grep -Fq "\"$IDENTITY_NAME\""; then
    echo "Code-signing identity already exists: $IDENTITY_NAME"
    exit 0
fi

if [[ "$ALLOW_TRUST" -ne 1 ]]; then
    usage
    echo ""
    echo "Refusing to modify Keychain trust settings without --trust."
    exit 1
fi

if [[ -n "$(security find-certificate -a -c "$IDENTITY_NAME" "$KEYCHAIN" 2>/dev/null)" ]]; then
    echo "Found certificate entries named '$IDENTITY_NAME', but none are valid code-signing identities." >&2
    echo "Remove the stale entries in Keychain Access, then rerun this script with --trust." >&2
    exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
IMPORT_PASSWORD="$(openssl rand -hex 24)"

cat >"$TMP_DIR/codesign.cnf" <<EOF
[ req ]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = ext

[ dn ]
CN = $IDENTITY_NAME

[ ext ]
basicConstraints = critical,CA:true
keyUsage = critical,digitalSignature,keyCertSign
extendedKeyUsage = critical,codeSigning
subjectKeyIdentifier = hash
EOF

openssl req \
    -new \
    -newkey rsa:2048 \
    -nodes \
    -x509 \
    -days "$DAYS" \
    -keyout "$TMP_DIR/codesign.key" \
    -out "$TMP_DIR/codesign.crt" \
    -config "$TMP_DIR/codesign.cnf"

openssl pkcs12 \
    -export \
    -name "$IDENTITY_NAME" \
    -inkey "$TMP_DIR/codesign.key" \
    -in "$TMP_DIR/codesign.crt" \
    -out "$TMP_DIR/codesign.p12" \
    -passout "pass:$IMPORT_PASSWORD"

security import "$TMP_DIR/codesign.p12" \
    -k "$KEYCHAIN" \
    -P "$IMPORT_PASSWORD" \
    -T /usr/bin/codesign \
    -T /usr/bin/security >/dev/null

security add-trusted-cert \
    -r trustRoot \
    -p codeSign \
    -k "$KEYCHAIN" \
    "$TMP_DIR/codesign.crt"

security find-identity -v -p codesigning "$KEYCHAIN" | grep -F "\"$IDENTITY_NAME\""

echo ""
echo "Created local code-signing identity: $IDENTITY_NAME"
echo "build.sh will auto-detect this identity on future builds."
echo "If macOS prompts for key access during signing, allow codesign to use it."
