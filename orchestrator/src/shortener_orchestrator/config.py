from dataclasses import dataclass
from pathlib import Path
import os

@dataclass(frozen=True)
class Settings:
    repo: Path
    java_home: str = ""
    command_timeout: float = 300
    llm_timeout: float = 300
    max_retries: int = 3
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder:7b"
    runtime_root: Path | None = None

    def __post_init__(self):
        object.__setattr__(self, "repo", self.repo.resolve())
        if self.runtime_root is not None and not self.runtime_root.resolve().is_relative_to(self.repo / "orchestrator"):
            raise ValueError("Runtime artifacts must remain inside this project's orchestrator folder")
        if not 0 <= self.max_retries <= 3:
            raise ValueError("Retry limit must be between zero and three")
        if self.command_timeout <= 0 or self.llm_timeout <= 0:
            raise ValueError("Timeouts must be positive")

    @property
    def home(self) -> Path:
        return self.runtime_root.resolve() if self.runtime_root else self.repo / "orchestrator"

    @classmethod
    def discover(cls, repo: str | None = None):
        root = Path(repo).resolve() if repo else Path.cwd().resolve()
        if not repo:
            while not (root / ".git").is_dir() and root != root.parent:
                root = root.parent
        if not (root / ".git").is_dir():
            raise ValueError("Run from the main repository or pass --repo; a committed baseline is required")
        return cls(repo=root, java_home=os.environ.get("JAVA_HOME", ""),
                   llm_timeout=float(os.environ.get("ORCHESTRATOR_LLM_TIMEOUT", "300")),
                   runtime_root=Path(os.environ["ORCHESTRATOR_RUNTIME_ROOT"]) if os.environ.get("ORCHESTRATOR_RUNTIME_ROOT") else None,
                   ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
                   model=os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b"))
