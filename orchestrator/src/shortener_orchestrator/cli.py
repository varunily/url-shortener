import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from .config import Settings
from .governance.redaction import redact
from .llm.ollama import OllamaProvider
from .service import Service

def parser():
    result = argparse.ArgumentParser(prog="orchestrator", description="Local governed engineering workflows")
    result.add_argument("--repo", help="Main repository root; paths with spaces are supported")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    commands.add_parser("metrics")
    start = commands.add_parser("run")
    start.add_argument("scenario", choices=["greenfield", "brownfield", "ambiguous", "retry_rollback"])
    start.add_argument("--provider", choices=["fake", "ollama"], default=os.environ.get("ORCHESTRATOR_PROVIDER", "fake"))
    start.add_argument("--model", help="Ollama model name; overrides OLLAMA_MODEL and is persisted for resumption")
    start.add_argument("--fault", choices=["once", "always"])
    for command in ["inspect", "resume", "stop"]:
        item = commands.add_parser(command)
        item.add_argument("run_id")
    for command in ["approve", "reject"]:
        item = commands.add_parser(command)
        item.add_argument("run_id")
        item.add_argument("--approval-id", required=True)
        item.add_argument("--proposal-hash", required=True)
        item.add_argument("--actor", required=True)
        item.add_argument("--reason", default="")
    clarify = commands.add_parser("clarify")
    clarify.add_argument("run_id")
    inputs = clarify.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--answers-file")
    inputs.add_argument("--answers-json")
    clarify.add_argument("--actor", required=True)
    revise = commands.add_parser("revise-plan", help="Supersede an undecided plan and pause for a new approval")
    revise.add_argument("run_id")
    revise.add_argument("--plan-file", required=True)
    revise.add_argument("--approval-id", required=True)
    revise.add_argument("--proposal-hash", required=True)
    revise.add_argument("--actor", required=True)
    revise.add_argument("--reason", required=True)
    rework = commands.add_parser("rework-coding", help="Requeue an unapplied task after recorded review feedback")
    rework.add_argument("run_id")
    rework.add_argument("--task-id", required=True)
    rework.add_argument("--feedback-file", required=True)
    rework.add_argument("--actor", required=True)
    patch_revision = commands.add_parser("revise-patch", help="Supersede a pending patch and request a new approval")
    patch_revision.add_argument("run_id")
    patch_revision.add_argument("--proposal-file", required=True)
    patch_revision.add_argument("--approval-id", required=True)
    patch_revision.add_argument("--proposal-hash", required=True)
    patch_revision.add_argument("--actor", required=True)
    patch_revision.add_argument("--reason", required=True)
    api = commands.add_parser("serve")
    api.add_argument("--port", type=int, default=8090)
    return result

def doctor(settings):
    from .tools.repository import baseline
    from importlib.metadata import version
    data = {"repo": str(settings.repo), "baseline": baseline(settings.repo),
            "python": sys.version.split()[0], "langgraph": version("langgraph"),
            "java_home": settings.java_home or "not selected", "maven": shutil.which("mvn"),
            "ollama_cli": shutil.which("ollama"), "model": settings.model}
    try:
        data["ollama_models"] = sorted(OllamaProvider(settings).available())
        data["ollama_ready"] = True
    except Exception as error:
        data["ollama_ready"] = False
        data["ollama_error"] = redact(str(error))
    return data

def main(argv=None):
    args = parser().parse_args(argv)
    service = None
    try:
        settings = Settings.discover(args.repo)
        if args.command == "run" and args.model:
            if args.provider != "ollama":
                raise ValueError("--model applies only to the Ollama provider")
            settings = replace(settings, model=args.model)
        if args.command == "doctor":
            output = doctor(settings)
        elif args.command == "serve":
            import uvicorn
            from .api import create_app
            uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port)
            return 0
        else:
            service = Service(settings)
            if args.command == "run":
                output = service.start(args.scenario, args.provider, args.fault)
            elif args.command in {"inspect", "resume", "stop"}:
                output = getattr(service, args.command)(args.run_id)
            elif args.command in {"approve", "reject"}:
                output = service.decide(args.run_id, args.approval_id, args.proposal_hash,
                                        args.actor, args.command, args.reason)
            elif args.command == "clarify":
                if args.answers_file:
                    path = Path(args.answers_file).resolve()
                    if not path.is_relative_to(settings.repo) or path.stat().st_size > 10000:
                        raise ValueError("Answers file must be a small JSON file inside the project")
                    answers = json.loads(path.read_text())
                else:
                    answers = json.loads(args.answers_json)
                output = service.clarify(args.run_id, answers, args.actor)
            elif args.command == "revise-plan":
                path = Path(args.plan_file).resolve()
                if not path.is_relative_to(settings.repo) or not path.is_file() or path.stat().st_size > 100_000:
                    raise ValueError("Plan file must be a small JSON file inside the project")
                output = service.revise_plan(args.run_id, {
                    "approval_id": args.approval_id, "proposal_hash": args.proposal_hash,
                    "actor": args.actor, "reason": args.reason, "plan": json.loads(path.read_text())})
            elif args.command == "rework-coding":
                path = Path(args.feedback_file).resolve()
                if not path.is_relative_to(settings.repo) or not path.is_file() or path.stat().st_size > 12000:
                    raise ValueError("Feedback must be a small text file inside the project")
                output = service.rework_coding(args.run_id, args.task_id, path.read_text(), args.actor)
            elif args.command == "revise-patch":
                path = Path(args.proposal_file).resolve()
                if not path.is_relative_to(settings.repo) or not path.is_file() or path.stat().st_size > 500_000:
                    raise ValueError("Patch proposal must be a JSON file up to 500 KB inside the project")
                output = service.revise_patch(args.run_id, {
                    "approval_id": args.approval_id, "proposal_hash": args.proposal_hash,
                    "actor": args.actor, "reason": args.reason, "proposal": json.loads(path.read_text())})
            else:
                output = service.store.aggregate()
        print(json.dumps(output, indent=2))
        if output.get("status") in {"FAILED", "SAFE_STOPPED", "REJECTED"}:
            return 1
        return 0
    except Exception as error:
        print(json.dumps({"error": type(error).__name__, "detail": redact(str(error))}), file=sys.stderr)
        return 1
    finally:
        if service:
            service.close()

if __name__ == "__main__":
    raise SystemExit(main())
