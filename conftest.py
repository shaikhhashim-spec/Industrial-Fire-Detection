"""Ensures the project root is importable as `config`/`src.*` regardless of
which directory pytest is invoked from."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
