"""Project-wide environment configuration.

The module loads the repository-local `.env` once, regardless of the current
working directory used to launch the CLI.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def load_project_env(env_file: Path = ENV_FILE) -> bool:
    """Load an env file without overwriting explicitly exported shell values."""
    return load_dotenv(env_file, override=False)


def get_env(key: str, default: str | None = None) -> str | None:
    """Read a project setting after the repository-local env file is loaded."""
    return os.getenv(key, default)


load_project_env()
