# API examples

## Complete curl flow

Requires curl and Python 3. Do not use curl -L to inspect redirect behavior: it follows the destination and hides the original 302.

~~~bash
BASE_URL=http://localhost:8080
created="$(curl --fail-with-body -sS -X POST "$BASE_URL/api/v1/urls" \
  -H 'Content-Type: application/json' \
  -d '{"originalUrl":"https://example.com/articles?id=42"}')"
printf '%s\n' "$created"
code="$(printf '%s' "$created" | python3 -c 'import json,sys; print(json.load(sys.stdin)["shortCode"])')"

curl -i "$BASE_URL/$code"
curl -sS "$BASE_URL/api/v1/urls/$code"
curl -sS "$BASE_URL/api/v1/urls/$code/stats"
curl -i -X PATCH "$BASE_URL/api/v1/urls/$code/disable"
curl -i "$BASE_URL/$code"
curl -sS "$BASE_URL/api/v1/urls/$code/stats"
~~~

Expected: 201 create; 302 redirect with Location; 200 metadata/stats; 200 disable; 410 subsequent redirect. Stats remain at one click. Automated assertions:

~~~bash
bash scripts/smoke-test.sh
~~~

## Expiration

~~~bash
curl -i -X POST http://localhost:8080/api/v1/urls \
  -H 'Content-Type: application/json' \
  -d '{"originalUrl":"https://example.com","expiresAt":"2099-01-01T00:00:00Z"}'
~~~

Expiration must be later than creation and include a UTC Z or explicit offset. Null/omitted expiration means no expiry.

## Example statistics

~~~json
{
  "shortCode": "abc1234",
  "shortUrl": "http://localhost:8080/abc1234",
  "originalUrl": "https://example.com",
  "createdAt": "2026-11-11T23:00:00Z",
  "expiresAt": null,
  "status": "ACTIVE",
  "totalClicks": 3,
  "lastAccessedAt": "2026-11-12T10:00:00Z",
  "dailyClicks": [
    {"date": "2026-11-11", "clicks": 2},
    {"date": "2026-11-12", "clicks": 1}
  ]
}
~~~

## Errors

Application errors use application/problem+json, with standard Problem Details fields plus code, requestId, and UTC timestamp. The ID also appears in X-Request-Id. Validation errors list field/message pairs without submitted values.

~~~json
{
  "type": "urn:url-shortener:error:url-disabled",
  "title": "Gone",
  "status": 410,
  "detail": "The short URL has been disabled.",
  "code": "URL_DISABLED",
  "requestId": "b2ed48e4-f8cb-4a58-8632-a4b3be49bb6f",
  "timestamp": "2026-11-11T23:05:00Z"
}
~~~

Framework-handled responses may add an instance path. Invalid HTTP framing rejected before Spring MVC is outside this JSON contract.

| Condition | HTTP | Code |
|---|---|---|
| Invalid fields/non-future expiration | 400 | INVALID_REQUEST |
| Malformed JSON/unknown fields | 400 | HTTP_400 |
| Unknown/malformed code | 404 | URL_NOT_FOUND |
| Expired redirect | 410 | URL_EXPIRED |
| Disabled redirect | 410 | URL_DISABLED |
| Unsupported method | 405 | HTTP_405 |
| Wrong content type | 415 | HTTP_415 |
| Creation quota exhausted | 429 | RATE_LIMIT_EXCEEDED |
| Limiter client capacity exhausted | 503 | RATE_LIMIT_CAPACITY |
| All six candidates collide | 503 | CODE_GENERATION_EXHAUSTED |
| Database/transaction failure | 503 | DATABASE_UNAVAILABLE |
| Unexpected application error | 500 | INTERNAL_ERROR |

Rate-limit and limiter-capacity responses include Retry-After seconds. Metadata/stats remain readable after disable/expiry. Phase 1 has no authentication.
