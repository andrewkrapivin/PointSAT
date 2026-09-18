#!/usr/bin/env bash
set -euo pipefail
patch_dir="$(cd "$(dirname "$0")" && pwd)"
source_dir="${1:-direct/vendor/localizer}"
patch_file="${2:-$patch_dir/upstream.patch}"
if [ "$(git -C "$source_dir" rev-parse HEAD)" != "5b07dd9df283b2438a6dc23e03ea5ef5c4ea55cb" ]; then
    echo "Expected Localizer commit 5b07dd9df283b2438a6dc23e03ea5ef5c4ea55cb" >&2
    exit 1
fi
if git -C "$source_dir" apply --reverse --check "$patch_file" 2>/dev/null; then
    echo "Patch is already applied."
else
    git -C "$source_dir" apply --check "$patch_file"
    git -C "$source_dir" apply "$patch_file"
fi
make -C "$source_dir/src" all test
