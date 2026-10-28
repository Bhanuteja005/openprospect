#!/usr/bin/env bash
# Schedule the daily jobs with cron (Linux / macOS).
#
#   bash scripts/schedule-cron.sh            print the crontab lines
#   bash scripts/schedule-cron.sh --install  add them to your crontab (replaces earlier OpenProspect lines)
#
# Times are this machine's local time; override with env vars:
#   AGENCY_TIME=06:00  the agency track: replies -> scrape -> enrich -> verify -> score -> CRM -> send
#   JOBS_TIME=13:00    the job & freelance track: find openings -> write drafts -> send
#
# Running on a server with Docker only? The `runner` compose profile (`openprospect daemon`)
# does the same without cron; see docs/deployment.md.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
uv_bin="$(command -v uv || true)"
[ -n "$uv_bin" ] || { echo "uv not found on PATH" >&2; exit 1; }

agency="${AGENCY_TIME:-06:00}"
jobs="${JOBS_TIME:-13:00}"
a_h="${agency%%:*}"; a_m="${agency##*:}"
j_h="${jobs%%:*}";   j_m="${jobs##*:}"

# cron starts jobs with a minimal PATH (/usr/bin:/bin), so docker (the scraper), uv and claude
# (the job-track writer) would not be found. Build a PATH from the usual install folders plus
# wherever those tools live on this machine. It is set inside each OpenProspect line only (a
# global PATH= line would change your other cron jobs too).
cron_path="/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin"
for tool in uv claude docker; do
  found="$(command -v "$tool" || true)"
  if [ -n "$found" ]; then cron_path="$cron_path:$(dirname "$found")"; fi
done
cron_path="$cron_path:/usr/bin:/bin"

tag="# openprospect"
lines="$((10#$a_m)) $((10#$a_h)) * * * cd \"$repo\" && mkdir -p data/logs && PATH=\"$cron_path\" \"$uv_bin\" run openprospect run >> data/logs/run_\$(date +\\%Y\\%m\\%d).log 2>&1 $tag
$((10#$j_m)) $((10#$j_h)) * * * cd \"$repo\" && mkdir -p data/logs && PATH=\"$cron_path\" \"$uv_bin\" run openprospect jobs daily >> data/logs/jobs_\$(date +\\%Y\\%m\\%d).log 2>&1 $tag"

if [ "${1:-}" = "--install" ]; then
  { crontab -l 2>/dev/null | grep -v "$tag" || true; echo "$lines"; } | crontab -
  echo "Installed. Agency track daily at $agency, job track daily at $jobs. Check with: crontab -l"
else
  echo "$lines"
  echo
  echo "Add these with:  bash scripts/schedule-cron.sh --install"
fi
