#!/usr/bin/env bash
# Deploy the rex site: ships public/ to Cloudflare Pages project `rex`.
#
# The deploy reports success as soon as the upload lands, but a zone cache
# rule can keep the edge serving the previous build. Verify with a
# cache-busted fetch (curl 'https://rex.debridmediamanager.com/?cb=1').
set -euo pipefail
cd "$(dirname "$0")"
npx --yes wrangler@latest pages deploy "$PWD/public" \
  --project-name="${CF_PAGES_PROJECT:-rex}" --branch=main --commit-dirty=true
