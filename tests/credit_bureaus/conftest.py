"""
conftest for credit bureau tests.

Adds the project root to sys.path and patches the parent api package
to avoid importing FastAPI routes (which have heavy dependencies).
"""
import sys
import types
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Stub out the parent api package so `from api.credit_bureaus...` works
# without importing api/__init__.py (which triggers FastAPI deps).
if "api" not in sys.modules:
    api_stub = types.ModuleType("api")
    api_stub.__path__ = [str(Path(project_root) / "api")]
    sys.modules["api"] = api_stub
