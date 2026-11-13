from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import json
import sqlite3
import threading
import time
from ..governance.paths import validate_run_id, PolicyError
from ..governance.redaction import sanitize
from ..models import digest
from .artifacts import write_json, write_text

def utcnow():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, home: Path):
        self.home = home
        (home / ".state").mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(home / ".state/audit.sqlite", check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS runs(
                id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL,
                started REAL NOT NULL, finished REAL, stop INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
                at REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL,
                event_key TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS approvals(
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                kind TEXT NOT NULL, proposal_hash TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', created REAL NOT NULL,
                decided REAL, actor TEXT, reason TEXT);
            CREATE TABLE IF NOT EXISTS plan_revisions(
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                old_approval_id TEXT NOT NULL UNIQUE REFERENCES approvals(id),
                request TEXT NOT NULL, state TEXT NOT NULL, checkpoint_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', created REAL NOT NULL, completed REAL);
            CREATE TABLE IF NOT EXISTS patch_revisions(
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                old_approval_id TEXT NOT NULL UNIQUE REFERENCES approvals(id),
                request TEXT NOT NULL, state TEXT NOT NULL, checkpoint_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', created REAL NOT NULL, completed REAL);
        """)
        self.db.commit()

    def directory(self, run_id):
        validate_run_id(run_id)
        return self.home / "runs" / run_id

    def create(self, run_id, data):
        with self.lock:
            self.directory(run_id).mkdir(parents=True)
            self.db.execute("INSERT INTO runs(id,data,status,started) VALUES (?,?,?,?)",
                            (run_id, json.dumps(data), "CREATED", time.time()))
            self.db.commit()
            self.event(run_id, "run_created", data)

    def get(self, run_id):
        validate_run_id(run_id)
        with self.lock:
            row = self.db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown run {run_id}")
            return dict(row) | {"data": json.loads(row["data"])}

    def update(self, run_id, status, state=None, terminal=False):
        with self.lock:
            current = self.get(run_id)
            data = current["data"] | ({"state": state} if state is not None else {})
            self.db.execute("UPDATE runs SET status=?,data=?,finished=? WHERE id=?",
                            (status, json.dumps(data), time.time() if terminal else None, run_id))
            self.db.commit()
            self.export(run_id)

    def event(self, run_id, kind, data, key=None):
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO events(run_id,at,kind,data,event_key) VALUES (?,?,?,?,?)",
                            (run_id, time.time(), kind, json.dumps(sanitize(data)),
                             f"{run_id}:{key}" if key else None))
            self.db.commit()
            self.export(run_id)

    def events(self, run_id):
        with self.lock:
            return [dict(row) | {"data": json.loads(row["data"])}
                    for row in self.db.execute("SELECT * FROM events WHERE run_id=? ORDER BY seq", (run_id,))]

    def approval(self, run_id, kind, payload):
        proposal_hash = digest(payload)
        approval_id = f"{run_id}:{kind}:{proposal_hash[:16]}"
        with self.lock:
            self.db.execute("""INSERT OR IGNORE INTO approvals
                (id,run_id,kind,proposal_hash,payload,created) VALUES (?,?,?,?,?,?)""",
                            (approval_id, run_id, kind, proposal_hash, json.dumps(payload), time.time()))
            self.db.commit()
            self.event(run_id, "approval_requested",
                       {"approval_id": approval_id, "kind": kind, "proposal_hash": proposal_hash, "payload": payload},
                       key=approval_id)
            row = self.db.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            return dict(row) | {"payload": json.loads(row["payload"])}

    def pending(self, run_id):
        with self.lock:
            return [dict(row) | {"payload": json.loads(row["payload"])}
                    for row in self.db.execute("SELECT * FROM approvals WHERE run_id=? AND status='pending'", (run_id,))]

    def decide(self, run_id, decision):
        with self.lock:
            row = self.db.execute("SELECT * FROM approvals WHERE id=? AND run_id=?",
                                  (decision.approval_id, run_id)).fetchone()
            if row is None or row["status"] != "pending" or row["proposal_hash"] != decision.proposal_hash:
                raise PolicyError("Approval is unknown, stale, already decided, or has the wrong hash")
            if self.get(run_id)["status"] != "AWAITING_APPROVAL":
                raise PolicyError("Run is not waiting for this approval")
            self.db.execute("UPDATE approvals SET status=?,decided=?,actor=?,reason=? WHERE id=?",
                            (decision.decision, time.time(), decision.actor, decision.reason, decision.approval_id))
            self.db.commit()
            self.event(run_id, "approval_decided", decision.model_dump())

    def approval_status(self, approval_id):
        with self.lock:
            row = self.db.execute("SELECT status FROM approvals WHERE id=?", (approval_id,)).fetchone()
            return row["status"] if row else None

    def active_plan_revision(self, run_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM plan_revisions WHERE run_id=? AND status='pending'",
                                  (run_id,)).fetchone()
            return (dict(row) | {"request": json.loads(row["request"]), "state": json.loads(row["state"])}) if row else None

    def begin_plan_revision(self, run_id, revision_id, request, state, checkpoint_id):
        """Revoke old authority and journal recovery data in one SQLite transaction."""
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM approvals WHERE id=? AND run_id=?",
                                  (request["approval_id"], run_id)).fetchone()
            run = self.get(run_id)
            if (row is None or row["kind"] != "plan" or row["status"] != "pending"
                    or row["proposal_hash"] != request["proposal_hash"]):
                raise PolicyError("Plan approval is stale, decided, or has the wrong hash")
            if run["status"] != "AWAITING_APPROVAL" or run["stop"] or self.active_plan_revision(run_id):
                raise PolicyError("Run is not waiting for a revisable plan")
            now = time.time()
            self.db.execute("INSERT INTO plan_revisions(id,run_id,old_approval_id,request,state,checkpoint_id,created) VALUES (?,?,?,?,?,?,?)",
                            (revision_id, run_id, request["approval_id"], json.dumps(request), json.dumps(state), checkpoint_id, now))
            self.db.execute("UPDATE approvals SET status='superseded',decided=?,actor=?,reason=? WHERE id=?",
                            (now, request["actor"], request["reason"], request["approval_id"]))
            self.db.execute("UPDATE runs SET status='REVISING_PLAN' WHERE id=?", (run_id,))
            data = {"revision_id": revision_id, "request": request, "previous_checkpoint_id": checkpoint_id,
                    "provenance": state["plan_provenance"]}
            self.db.execute("INSERT INTO events(run_id,at,kind,data,event_key) VALUES (?,?,?,?,?)",
                            (run_id, now, "plan_revision_requested", json.dumps(sanitize(data)),
                             f"{run_id}:plan_revision_requested:{revision_id}"))
        self.export(run_id)

    def finish_plan_revision(self, run_id, revision_id, state, approval_id, proposal_hash, checkpoint_id):
        with self.lock, self.db:
            operation = self.active_plan_revision(run_id)
            if operation is None or operation["id"] != revision_id:
                raise PolicyError("No matching pending plan revision")
            row = self.db.execute("SELECT * FROM approvals WHERE id=? AND run_id=?",
                                  (approval_id, run_id)).fetchone()
            if row is None or row["status"] != "pending" or row["proposal_hash"] != proposal_hash:
                raise PolicyError("Revised plan has no pending approval")
            run = self.get(run_id)
            data = run["data"] | {"state": state}
            now = time.time()
            self.db.execute("UPDATE plan_revisions SET status='complete',completed=? WHERE id=?", (now, revision_id))
            self.db.execute("UPDATE runs SET status=?,data=? WHERE id=?",
                            ("STOPPED" if run["stop"] else "AWAITING_APPROVAL", json.dumps(data), run_id))
            event = {"revision_id": revision_id, "old_approval_id": operation["old_approval_id"],
                     "approval_id": approval_id, "proposal_hash": proposal_hash, "revision": state["revision"],
                     "checkpoint_id": checkpoint_id, "actor": operation["request"]["actor"],
                     "reason": operation["request"]["reason"]}
            self.db.execute("INSERT INTO events(run_id,at,kind,data,event_key) VALUES (?,?,?,?,?)",
                            (run_id, now, "plan_revised", json.dumps(sanitize(event)), f"{run_id}:plan_revised:{revision_id}"))
        self.export(run_id)

    def active_patch_revision(self, run_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM patch_revisions WHERE run_id=? AND status='pending'",
                                  (run_id,)).fetchone()
            return (dict(row) | {"request": json.loads(row["request"]), "state": json.loads(row["state"])}) if row else None

    def begin_patch_revision(self, run_id, revision_id, request, state, checkpoint_id):
        with self.lock, self.db:
            old = self.db.execute("SELECT * FROM approvals WHERE id=? AND run_id=?",
                                  (request["approval_id"], run_id)).fetchone()
            run = self.get(run_id)
            if (old is None or old["kind"] != "patch" or old["status"] != "pending"
                    or old["proposal_hash"] != request["proposal_hash"]):
                raise PolicyError("Patch approval is stale or has the wrong hash")
            if run["status"] != "AWAITING_APPROVAL" or run["stop"] or self.active_patch_revision(run_id):
                raise PolicyError("Run is not waiting for a revisable patch")
            if self.db.execute("SELECT 1 FROM approvals WHERE run_id=? AND status='pending' AND id<>?",
                               (run_id, request["approval_id"])).fetchone():
                raise PolicyError("Another approval is pending")
            now = time.time()
            self.db.execute("INSERT INTO patch_revisions(id,run_id,old_approval_id,request,state,checkpoint_id,created) VALUES (?,?,?,?,?,?,?)",
                            (revision_id, run_id, request["approval_id"], json.dumps(request),
                             json.dumps(state), checkpoint_id, now))
            self.db.execute("UPDATE approvals SET status='superseded',decided=?,actor=?,reason=? WHERE id=?",
                            (now, request["actor"], request["reason"], request["approval_id"]))
            self.db.execute("UPDATE runs SET status='REVISING_PATCH' WHERE id=?", (run_id,))
            self.db.execute("INSERT INTO events(run_id,at,kind,data,event_key) VALUES (?,?,?,?,?)",
                (run_id, now, "patch_revision_requested", json.dumps(sanitize(request | {"revision_id": revision_id})),
                 f"{run_id}:patch_revision_requested:{revision_id}"))
        self.export(run_id)

    def finish_patch_revision(self, run_id, revision_id, state, approval_id, proposal_hash, checkpoint_id):
        with self.lock, self.db:
            operation = self.active_patch_revision(run_id)
            if operation is None or operation["id"] != revision_id:
                raise PolicyError("No matching pending patch revision")
            row = self.db.execute("SELECT * FROM approvals WHERE id=? AND run_id=?",
                                  (approval_id, run_id)).fetchone()
            if row is None or row["kind"] != "patch" or row["status"] != "pending" or row["proposal_hash"] != proposal_hash:
                raise PolicyError("Revised patch has no matching pending approval")
            run = self.get(run_id)
            data = run["data"] | {"state": state}
            now = time.time()
            self.db.execute("UPDATE patch_revisions SET status='complete',completed=? WHERE id=?",
                            (now, revision_id))
            self.db.execute("UPDATE runs SET status=?,data=? WHERE id=?",
                            ("STOPPED" if run["stop"] else "AWAITING_APPROVAL", json.dumps(data), run_id))
            event = {"revision_id": revision_id, "old_approval_id": operation["old_approval_id"],
                     "approval_id": approval_id, "proposal_hash": proposal_hash,
                     "actor": operation["request"]["actor"], "reason": operation["request"]["reason"],
                     "checkpoint_id": checkpoint_id}
            self.db.execute("INSERT INTO events(run_id,at,kind,data,event_key) VALUES (?,?,?,?,?)",
                (run_id, now, "patch_revised", json.dumps(sanitize(event)), f"{run_id}:patch_revised:{revision_id}"))
        self.export(run_id)

    def request_stop(self, run_id):
        with self.lock:
            run = self.get(run_id)
            if run["status"] in {"READY", "REJECTED", "ROLLED_BACK", "FAILED"}:
                raise PolicyError("This run is terminal")
            self.db.execute("""UPDATE runs SET stop=1,
                status=CASE WHEN status IN ('AWAITING_APPROVAL','AWAITING_CLARIFICATION')
                THEN 'STOPPED' ELSE status END WHERE id=?""", (run_id,))
            self.db.commit()
            self.event(run_id, "stop_requested", {})

    def stopped(self, run_id):
        return bool(self.get(run_id)["stop"])

    def clear_stop(self, run_id):
        with self.lock:
            self.db.execute("UPDATE runs SET stop=0 WHERE id=?", (run_id,))
            self.db.commit()

    @contextmanager
    def claim(self, run_id):
        validate_run_id(run_id)
        with (self.home / ".state" / f"{run_id}.lock").open("a") as file:
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as ex:
                raise PolicyError("Another worker is executing this run") from ex
            try:
                yield
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)

    def export(self, run_id):
        # The RLock allows callers already inside an atomic event/decision operation.
        with self.lock:
            from .metrics import calculate
            run = self.get(run_id)
            events = self.events(run_id)
            approvals = [dict(row) for row in self.db.execute("SELECT * FROM approvals WHERE run_id=?", (run_id,))]
            directory = self.directory(run_id)
            write_json(directory / "manifest.json", sanitize(run))
            write_text(directory / "audit.jsonl", "".join(json.dumps(event) + "\n" for event in events))
            write_text(directory / "decisions.jsonl", "".join(json.dumps(event) + "\n" for event in events
                       if event["kind"] in {"replanned", "clarified", "approval_decided", "plan_revision_requested", "plan_revised", "coding_rework_requested", "patch_revision_requested", "patch_revised"}))
            write_text(directory / "approvals.jsonl", "".join(json.dumps(sanitize(row)) + "\n" for row in approvals))
            write_json(directory / "metrics.json", calculate(run, events, approvals))

    def aggregate(self):
        with self.lock:
            runs = [dict(row) for row in self.db.execute("SELECT * FROM runs")]
        successful = sum(run["status"] == "READY" for run in runs)
        failed = sum(run["status"] in {"ROLLED_BACK", "FAILED", "REJECTED"} for run in runs)
        return {"runs": len(runs), "successful": successful, "failed_terminal": failed,
                "success_rate": successful / (successful + failed) if successful + failed else None,
                "pending_or_stopped": len(runs) - successful - failed}
