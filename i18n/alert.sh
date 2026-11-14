#!/usr/bin/env bash
# Posts to Discord #platform-alerts when a publish run needs a look: OpenRouter failed, a language kept more
# than 3 sections in English (the model or a check went wrong), or a step of the run failed.
# Usage (from the workflow): i18n/alert.sh <site> <translate exit code> <job status> <translate log>
set -uo pipefail
site=$1 code=$2 status=$3 log=$4
if [ -z "${PLATFORM_ALERTS_WEBHOOK:-}" ]; then echo "::warning::PLATFORM_ALERTS_WEBHOOK is not set"; exit 0; fi
lines=()
[ "$code" = 4 ] && lines+=("OpenRouter failed (key, monthly limit or outage). The site shipped with cached translations only.")
many=$(grep -oE '^[a-z]{2}: [0-9]+ pages, [0-9]+ requests, [0-9]+ left English' "$log" 2>/dev/null |
  awk '$6 > 3 { printf "%s%s %s", sep, substr($1, 1, 2), $6; sep = ", " }')
[ -n "$many" ] && lines+=("More than 3 sections left in English: $many.")
[ "$status" != success ] && lines+=("A step of the publish run failed.")
[ ${#lines[@]} -eq 0 ] && exit 0
why=$(grep -oE '\[[a-z]{2}\] left English: [^:]*' "$log" 2>/dev/null | sort | uniq -c | sort -rn | head -5 | sed 's/^ */  /')
text=$(printf '⚠️ **%s translations**\n%s\n%s\n%s' "$site" "$(printf '%s\n' "${lines[@]}")" "$why" \
  "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID")
jq -n --arg c "${text:0:1900}" '{content: $c}' | curl -fsS -H "Content-Type: application/json" -d @- "$PLATFORM_ALERTS_WEBHOOK"
