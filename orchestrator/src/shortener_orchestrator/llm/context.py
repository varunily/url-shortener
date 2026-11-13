"""Bound local-model inputs without truncating approved code or validation evidence."""
import json
from ..governance.paths import PolicyError

MAX_CONTEXT_CHARACTERS = 18_000
MAX_CODING_CONTEXT_CHARACTERS = 32_000

def prepare_context(agent, context):
    fields = ["run_id", "scenario", "request", "requirements", "clarification", "revision",
              "task", "failure", "test_result", "static_result", "actual_diff", "failure_log_tail",
              "previous_execution_error", "coding_feedback"]
    result = {key: context[key] for key in fields if key in context}
    if agent == "requirement":
        # A previous draft can contain questions already answered by the operator.
        # Re-evaluate the request against clarification instead of inviting an echo.
        result.pop("requirements", None)
    result["writable_policy"] = {
        "java": "src/main/java/com/varun/shortener/ and src/test/java/com/varun/shortener/",
        "migrations": "New src/main/resources/db/migration/V3__name.sql or later; preserve existing migrations",
        "other": ["src/main/resources/application.yml", "docs/*.md"],
        "protected": ["pom.xml", "mvnw", ".git", "orchestrator/", ".env"],
        "planning": "Use exact repository-relative paths. Prefer small tasks with at most three files each.",
    }
    repository = context.get("repository")
    if not isinstance(repository, dict) or "files" not in repository:
        # Also supports adapter contract tests without a real repository snapshot.
        result.update({key: value for key, value in context.items() if key not in result})
        return result
    files = repository["files"]
    result["repository"] = {"baseline": repository.get("baseline"), "file_index": sorted(files), "files": {}}

    if agent == "coding":
        # Coding follows the approved task and human clarification; the preliminary
        # requirement draft is redundant and can otherwise distract a small model.
        result.pop("requirements", None)
        for name in context["task"]["files"]:
            result["repository"]["files"][name] = files.get(name, {"sha256": None, "content": None})
        tasks = {task["id"]: task for task in context.get("plan", {}).get("tasks", [])}
        upstream = set(context["task"].get("depends_on", []))
        while tasks:
            expanded = upstream | {parent for key in upstream for parent in tasks[key]["depends_on"]}
            if expanded == upstream:
                break
            upstream = expanded
        dependency_paths = {name for key in upstream for name in tasks[key]["files"]} if tasks else None
        dependencies = [item for item in context.get("proposed_dependencies", [])
                        if dependency_paths is None or item["path"] in dependency_paths]
        result["dependency_index"] = [item["path"] for item in dependencies]
        # Preserve whole production contracts. Other task outputs are indexed, not
        # copied wholesale into every later prompt (especially regression suites).
        result["proposed_dependencies"] = [item for item in dependencies if item["path"].startswith("src/main/")]
        references = {"V1__create_urls.sql", "V2__create_click_events.sql"}
        if any("/integration/" in name for name in context["task"]["files"]):
            references |= {"PostgresIntegrationTest.java", "MutableClock.java", "UrlLifecycleIT.java",
                           "CreateUrlRequest.java", "UrlResponse.java", "UrlStatsResponse.java", "DailyClickResponse.java"}
        for name, body in files.items():
            if name.rsplit("/", 1)[-1] in references:
                result["repository"]["files"].setdefault(name, body)
        result["repository"]["context_note"] = (
            "Write targets and selected reference files are complete. Production dependencies are complete. "
            "Non-production dependency outputs are indexed only; no claim is made about unseen test bodies. "
            "The approved current task and operator clarification govern this proposal."
        )
    elif agent == "planning":
        priority = ["ShortUrl.java", "RedirectService.java", "UrlService.java", "UrlRepository.java",
                    "V1__create_urls.sql", "V2__create_click_events.sql", "UrlShortenerApplication.java",
                    "PersistenceAndMigrationIT.java", "application.yml", "ErrorCode.java", "CreateUrlRequest.java"]
        def rank(name):
            filename = name.rsplit("/", 1)[-1]
            return (priority.index(filename) if filename in priority else len(priority), name)
        for name in sorted(files, key=rank):
            result["repository"]["files"][name] = files[name]
            if len(json.dumps(result)) > MAX_CONTEXT_CHARACTERS - 1500:
                del result["repository"]["files"][name]
        result["repository"]["context_note"] = (
            "The file index is complete; source bodies are selected whole files, not excerpts. "
            "Omitted bodies are not evidence of absent functionality."
        )
    # Requirement analysis needs request/decisions and an index. Review/documentation
    # receive the complete actual diff and real test evidence instead of a duplicated tree.
    budget = MAX_CODING_CONTEXT_CHARACTERS if agent == "coding" else MAX_CONTEXT_CHARACTERS
    if len(json.dumps(result)) > budget:
        raise PolicyError("Required model context exceeds the local budget; split the task instead of truncating evidence")
    return result
