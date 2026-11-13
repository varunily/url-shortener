import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import time
from ..governance.policy import command
from ..governance.paths import PolicyError
from ..governance.redaction import redact
from ..models import TestResult
from .test_reports import parse_reports

class Stopped(RuntimeError):
    pass

class CommandRunner:
    def __init__(self, settings, store):
        self.settings = settings
        self.store = store

    def environment(self):
        # Do not pass application credentials or paid-provider keys to generated test code.
        keys = ["PATH", "HOME", "USER", "LANG", "LC_ALL", "DOCKER_HOST", "DOCKER_CONFIG",
                "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE"]
        env = {key: os.environ[key] for key in keys if key in os.environ}
        if self.settings.java_home:
            env["JAVA_HOME"] = self.settings.java_home
            env["PATH"] = self.settings.java_home + "/bin:" + env.get("PATH", "")
        return env

    def run(self, run_id, workspace, attempt, profile="verify"):
        argv = list(command(profile))
        executable = shutil.which(argv[0])
        if not executable:
            raise PolicyError("Maven is not installed")
        argv[0] = executable
        log = self.store.directory(run_id) / "tests" / f"{attempt}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        self.store.event(run_id, "command_started", {"argv": argv, "cwd": str(workspace), "attempt": attempt})
        process = subprocess.Popen(argv, cwd=workspace, env=self.environment(), shell=False,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        chunks, size, classification, stopped = [], 0, "passed", False
        try:
            while selector.get_map() or process.poll() is None:
                if self.store.stopped(run_id):
                    stopped = True
                    classification = "stopped"
                    self._terminate(process)
                if time.monotonic() - started > self.settings.command_timeout:
                    classification = "timeout"
                    self._terminate(process)
                for key, _ in selector.select(timeout=0.1):
                    raw = os.read(key.fileobj.fileno(), 65536)
                    if not raw:
                        selector.unregister(key.fileobj)
                    else:
                        size += len(raw)
                        if size <= 5_000_000:
                            chunks.append(raw)
                        else:
                            classification = "output_limit"
                            self._terminate(process)
            code = process.wait(timeout=5)
        finally:
            selector.close()
            process.stdout.close()
            if process.poll() is None:
                self._terminate(process)
        text = redact(b"".join(chunks).decode("utf-8", errors="replace"))
        log.write_text(text)
        if stopped:
            raise Stopped("Run stopped during command execution")
        counts = parse_reports(Path(workspace))
        passed = classification == "passed" and code == 0 and counts["unit_tests"] > 0 and counts["integration_tests"] > 0 \
            and not any(counts[key] for key in ["failures", "errors", "skipped"])
        if not passed and classification == "passed":
            classification = "environment" if any(value in text for value in [
                "Could not find a valid Docker environment", "requireJavaVersion",
                "Could not resolve", "Cannot connect to the Docker daemon"]) else "validation"
        result = TestResult(passed=passed, returncode=code, **counts, classification=classification,
                            log_path=str(log), duration_seconds=time.monotonic() - started)
        self.store.event(run_id, "command_finished", result.model_dump())
        return result

    @staticmethod
    def _terminate(process):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        finally:
            # Also reap descendants if the group leader exited before its children.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)
