#!/usr/bin/env bash
# Deploy the rex site: ships public/ plus its translations (built into dist/) to Cloudflare Pages project `rex`.
# A push to main already does this (.github/workflows/publish.yml); this is for doing it by hand.
#
# The deploy reports success as soon as the upload lands, but a zone cache
# rule can keep the edge serving the previous build. Verify with a
# cache-busted fetch (curl 'https://rex.debridmediamanager.com/?cb=1').
set -euo pipefail
cd "$(dirname "$0")"
# Pages under /<lang>/ from the translations in i18n/cache; text not translated yet stays English.
python3 i18n/translate.py html --src public --out dist --host rex.debridmediamanager.com || [ $? -eq 3 ]
# wrangler 4.151 turns `pages` commands into a Workers deploy; 4.40.0 still deploys Pages.
npx --yes wrangler@4.40.0 pages deploy "$PWD/dist" \
  --project-name="${CF_PAGES_PROJECT:-rex}" --branch=main --commit-dirty=true
