# Minimal local FastAPI interface

Start from the repository root:

~~~bash
./orchestrator/run serve --port 8090
~~~

The server listens on 127.0.0.1. OpenAPI: http://127.0.0.1:8090/docs. CLI remains the primary demo.

~~~bash
curl -sS -X POST http://127.0.0.1:8090/runs \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"brownfield","provider":"fake"}'

curl -sS http://127.0.0.1:8090/runs/RUN_ID

curl -sS -X POST http://127.0.0.1:8090/runs/RUN_ID/decision \
  -H 'Content-Type: application/json' \
  -d '{"approval_id":"ID_FROM_INSPECTION","proposal_hash":"HASH_FROM_INSPECTION","decision":"approve","actor":"varun","reason":"Reviewed proposal"}'

curl -sS -X POST http://127.0.0.1:8090/runs/RUN_ID/resume

curl -sS -X POST http://127.0.0.1:8090/runs/RUN_ID/clarify \
  -H 'Content-Type: application/json' \
  -d '{"actor":"varun","answers":{"url_policy":"http_https","max_expiration_days":30,"cleanup":"archive"}}'

curl -sS -X POST http://127.0.0.1:8090/runs/RUN_ID/stop
curl -sS http://127.0.0.1:8090/metrics
~~~

Replace IDs and hashes with the current pending approval. Decision recording and resumption are separate operations. Unapproved resumes, stale decisions, and concurrent workers return conflict responses. Requests execute until a checkpoint or completion; there is no separate job queue.

This local prototype does not authenticate actor strings. Do not expose it outside a trusted workstation.

## Revising an undecided plan

`POST /runs/{run_id}/revise-plan` uses the same checks and checkpoint operation as
the CLI. Its JSON body contains `approval_id`, `proposal_hash` (the full current
hash), `actor`, `reason`, and `plan` (the complete Plan with the next revision).
It returns the new pending plan approval; it grants no approval. Invalid or stale
requests return 409; malformed request bodies return 422. The CLI remains the
primary interface; see the README for its complete command.
