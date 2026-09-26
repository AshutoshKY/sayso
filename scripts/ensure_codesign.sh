#!/bin/zsh
# Stable self-signed identity so TCC (mic/speech) survives rebuilds.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
dir="$root/.codesign"
kc="$dir/laya.keychain-db"
pass="laya-opener-codesign"
name="Laya Opener"

mkdir -p "$dir"
if [[ ! -f "$kc" ]]; then
  security create-keychain -p "$pass" "$kc"
fi
security set-keychain-settings -u "$kc" >/dev/null 2>&1 || true
security unlock-keychain -p "$pass" "$kc"

# NOTE: no -v here — the self-signed cert is NOT_TRUSTED, so `find-identity -v`
# reports 0 valid and this block would re-import a duplicate identity every run.
if ! security find-identity -p codesigning "$kc" 2>/dev/null | grep -q "$name"; then
  cnf="$dir/codesign.cnf"
  cat > "$cnf" <<'EOF'
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_codesign
prompt = no
[req_distinguished_name]
CN = Laya Opener
O = Laya
[v3_codesign]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
EOF
  openssl req -new -x509 -days 3650 -nodes \
    -newkey rsa:2048 \
    -keyout "$dir/laya.key" \
    -out "$dir/laya.crt" \
    -config "$cnf" >/dev/null 2>&1
  openssl pkcs12 -export \
    -inkey "$dir/laya.key" \
    -in "$dir/laya.crt" \
    -out "$dir/laya.p12" \
    -passout pass:"$pass" \
    -name "$name" >/dev/null 2>&1
  security import "$dir/laya.p12" -k "$kc" -P "$pass" -A -T /usr/bin/codesign -T /usr/bin/security >/dev/null
  security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$pass" "$kc" >/dev/null
fi

# Echo the cert hash, not the name: codesign --sign <hash> is immune to
# duplicate-name ambiguity.
hash="$(security find-identity -p codesigning "$kc" | awk -v n="\"$name\"" '$0 ~ n {print $2; exit}')"
echo "$kc|$hash"
