#!/usr/bin/env bash
set -euo pipefail

# Requires curl and Python 3. Does not follow redirects or contact the destination.
base_url="${BASE_URL:-http://localhost:8080}"
base_url="${base_url%/}"
original_url='https://example.com/demo?source=url-shortener'
work_dir="$(mktemp -d)"
# Only temporary files created by this script are removed.
trap 'rm -rf "$work_dir"' EXIT

request() {
  local expected="$1"
  shift
  local actual
  actual="$(curl --silent --show-error --max-time 15 \
    --dump-header "$work_dir/headers" --output "$work_dir/body" --write-out '%{http_code}' "$@")"
  if [[ "$actual" != "$expected" ]]; then
    printf 'FAIL: expected HTTP %s, got %s\n' "$expected" "$actual" >&2
    cat "$work_dir/body" >&2
    exit 1
  fi
}

request 200 "$base_url/actuator/health/readiness"
request 201 -X POST "$base_url/api/v1/urls" -H 'Content-Type: application/json' \
  --data '{"originalUrl":"https://example.com/demo?source=url-shortener"}'
code="$(python3 - "$work_dir/body" "$base_url" "$original_url" <<'PY'
import json, re, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
assert set(data) == {"shortCode", "shortUrl", "originalUrl", "createdAt", "expiresAt", "status"}, data
assert re.fullmatch(r"[A-Za-z0-9]{7}", data["shortCode"]), data
assert data["shortUrl"] == sys.argv[2] + "/" + data["shortCode"], data
assert data["originalUrl"] == sys.argv[3], data
assert data["expiresAt"] is None and data["status"] == "ACTIVE", data
print(data["shortCode"])
PY
)"
printf 'PASS create: %s/%s\n' "$base_url" "$code"

request 200 "$base_url/api/v1/urls/$code"
request 302 "$base_url/$code"
python3 - "$work_dir/headers" "$original_url" <<'PY'
import sys
with open(sys.argv[1]) as f:
    headers = {line.split(":", 1)[0].lower(): line.split(":", 1)[1].strip()
               for line in f if ":" in line}
assert headers.get("location") == sys.argv[2], headers
assert headers.get("cache-control") == "no-store", headers
PY
printf 'PASS redirect: HTTP 302 with correct Location\n'

request 200 "$base_url/api/v1/urls/$code/stats"
python3 - "$work_dir/body" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
assert data["totalClicks"] == 1 and data["lastAccessedAt"] is not None, data
assert sum(day["clicks"] for day in data["dailyClicks"]) == 1, data
PY
printf 'PASS stats: exactly one click\n'

request 200 -X PATCH "$base_url/api/v1/urls/$code/disable"
request 410 "$base_url/$code"
request 200 "$base_url/api/v1/urls/$code/stats"
python3 - "$work_dir/body" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
assert data["status"] == "DISABLED" and data["totalClicks"] == 1, data
PY
printf 'PASS disable: HTTP 410; click count remains one\n'
printf 'Acceptance flow passed.\n'
