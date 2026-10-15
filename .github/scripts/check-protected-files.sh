#!/usr/bin/env bash
# Fail-closed verifier for the repository's five protected files.
#
# Usage:
#   bash .github/scripts/check-protected-files.sh [ROOT] [PIN_FILE]
#
#   ROOT      directory holding the files + the pin file (default: .)
#   PIN_FILE  pin file path relative to ROOT (default: .github/protected-files.txt)
#
# The expected set of protected paths is fixed here on purpose: the guard must
# fail if the pin file omits any of them, so the set can never be derived from
# the very file under test.
#
# Exit status is non-zero (and the step fails) when:
#   * the pin file is missing or empty;
#   * an entry is malformed, not a 40-char lowercase hex SHA-1, or duplicated;
#   * an expected path is absent from the pin file;
#   * a protected file is absent from the checkout;
#   * a protected file's current `git hash-object` blob differs from its pin;
#   * the pin file lists a path outside the expected set.
#
# Note on pending changes: the five paths currently carry uncommitted Phase 3.8
# content, so a CI run against an *earlier* commit will report a mismatch until
# that change set is committed together with these pins -- that is the intended
# fail-closed behaviour (see the header of .github/protected-files.txt).
set -euo pipefail

root="${1:-.}"
pin_rel="${2:-.github/protected-files.txt}"

cd -- "$root"
pin="$pin_rel"

expected_paths=(
  backend/app/schemas/features.py
  backend/app/services/features.py
  backend/tests/test_feature_contract.py
  backend/tests/test_feature_real_artifacts.py
  docs/historical-data-coverage.md
)

fail() {
  echo "::error::$1"
  exit 1
}

# 1. Pin file must exist and be non-empty.
[ -f "$pin" ] || fail "protected pin file '$pin_rel' is missing"
[ -s "$pin" ] || fail "protected pin file '$pin_rel' is empty"

# 2. Parse and validate every entry before comparing anything.
declare -A seen_path=()
declare -A pinned_hash=()

while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    '' | '#'*) continue ;;
  esac

  hash=""
  path=""
  extra=""
  read -r hash path extra <<<"$line" || true

  if [ -z "$hash" ] || [ -z "$path" ] || [ -n "$extra" ]; then
    fail "malformed pin entry (expected '<sha1> <path>'): '$line'"
  fi
  case "$hash" in
    *[!0-9a-f]*) fail "pin hash is not lowercase hex: '$line'" ;;
  esac
  if [ "${#hash}" -ne 40 ]; then
    fail "pin hash is not 40 hex characters: '$line'"
  fi
  if [ -n "${seen_path[$path]:-}" ]; then
    fail "duplicate pin entry for '$path'"
  fi

  seen_path[$path]=1
  pinned_hash[$path]="$hash"
done <"$pin"

failed=0

# 3. Every expected protected path must be pinned, present, and unchanged.
for path in "${expected_paths[@]}"; do
  if [ -z "${pinned_hash[$path]:-}" ]; then
    echo "::error::$path is missing from '$pin_rel'"
    failed=1
    continue
  fi
  if [ ! -e "$path" ]; then
    echo "::error::protected file '$path' is absent from the checkout"
    failed=1
    continue
  fi
  actual="$(git hash-object -- "$path")"
  if [ "$actual" != "${pinned_hash[$path]}" ]; then
    echo "::error file=$path::protected file changed (expected ${pinned_hash[$path]}, got $actual)"
    failed=1
  else
    echo "ok: $path"
  fi
done

# 4. Reject pins for unexpected paths (e.g. a renamed/extra protected file).
for path in "${!pinned_hash[@]}"; do
  is_expected=0
  for expected in "${expected_paths[@]}"; do
    if [ "$path" = "$expected" ]; then
      is_expected=1
      break
    fi
  done
  if [ "$is_expected" -eq 0 ]; then
    echo "::error::unexpected pin entry for '$path'"
    failed=1
  fi
done

exit "$failed"
