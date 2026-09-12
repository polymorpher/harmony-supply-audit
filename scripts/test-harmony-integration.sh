#!/usr/bin/env bash

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HARMONY_REVISION=8292e786db513186faff5b397fdf864c0c189ac1
MCL_REVISION=ac6b73317f5321b33fc877a4dd7218e1815693d8
BLS_REVISION=2b7e49894c0f15f5c40cf74046505b7f74946e52
WORK=$(mktemp -d "${TMPDIR:-/tmp}/harmony-supply-audit-integration.XXXXXX")

cleanup() {
  rm -rf "$WORK"
}
trap cleanup EXIT

clone_at_revision() {
  local source=$1
  local destination=$2
  local revision=$3

  git clone --no-checkout "$source" "$destination"
  git -C "$destination" checkout --detach "$revision"
  test -z "$(git -C "$destination" status --porcelain)"
  test "$(git -C "$destination" rev-parse HEAD)" = "$revision"
}

HARMONY_SOURCE=${HARMONY_SRC:-https://github.com/polymorpher/harmony.git}
MCL_SOURCE=${MCL_SRC:-https://github.com/harmony-one/mcl.git}
BLS_SOURCE=${BLS_SRC:-https://github.com/harmony-one/bls.git}

clone_at_revision "$HARMONY_SOURCE" "$WORK/harmony" "$HARMONY_REVISION"
clone_at_revision "$MCL_SOURCE" "$WORK/mcl" "$MCL_REVISION"
clone_at_revision "$BLS_SOURCE" "$WORK/bls" "$BLS_REVISION"

if command -v brew >/dev/null 2>&1; then
  for formula in gmp openssl@1.1; do
    if prefix=$(brew --prefix "$formula" 2>/dev/null); then
      export LIBRARY_PATH="$prefix/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
      export CPATH="$prefix/include${CPATH:+:$CPATH}"
    fi
  done
fi

make -C "$WORK/mcl" -j"${JOBS:-4}"
make -C "$WORK/bls" -j"${JOBS:-4}" BLS_SWAP_G=1

export CGO_ENABLED=1
export CGO_CFLAGS="-I$WORK/bls/include -I$WORK/mcl/include"
export CGO_LDFLAGS="-L$WORK/bls/lib"
export LIBRARY_PATH="$WORK/bls/lib:$WORK/mcl/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
export LD_LIBRARY_PATH="$LIBRARY_PATH"
export DYLD_FALLBACK_LIBRARY_PATH="$LIBRARY_PATH"

cd "$WORK/harmony"
go test ./consensus -run '^TestFakeValidatorWrapper' -count=1

echo "Harmony integration test passed at $HARMONY_REVISION"
