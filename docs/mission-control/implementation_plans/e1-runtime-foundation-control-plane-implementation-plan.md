# E1 Runtime Foundation And Local Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working local control plane for `CLAY Mission Control`: runtime states, service supervision, config validation, preflight, degraded mode, and a minimal browser shell for operating the system.

**Architecture:** The implementation uses a local `FastAPI` control plane plus a small `React` shell. The backend owns runtime state, service registry, config validation, preflight, degraded transitions, and event streaming. Managed services stay outside the control plane as supervised child processes or standalone workers registered in the service registry.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Uvicorn, pytest, React, TypeScript, Vite, Vitest, Testing Library, TOML config files, XDG base directories

---

## Repository Root

This plan assumes the code repository will live at:

`/home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app`

If the repository root changes later, keep the same relative file structure from this plan.

## File Structure

### Backend

- Create: `backend/pyproject.toml`
- Create: `backend/src/clay_mc/__init__.py`
- Create: `backend/src/clay_mc/api/main.py`
- Create: `backend/src/clay_mc/api/routes/runtime.py`
- Create: `backend/src/clay_mc/api/routes/services.py`
- Create: `backend/src/clay_mc/api/routes/health.py`
- Create: `backend/src/clay_mc/api/routes/configs.py`
- Create: `backend/src/clay_mc/api/routes/preflight.py`
- Create: `backend/src/clay_mc/api/routes/events.py`
- Create: `backend/src/clay_mc/runtime/states.py`
- Create: `backend/src/clay_mc/runtime/manager.py`
- Create: `backend/src/clay_mc/runtime/transitions.py`
- Create: `backend/src/clay_mc/services/models.py`
- Create: `backend/src/clay_mc/services/registry.py`
- Create: `backend/src/clay_mc/services/supervisor.py`
- Create: `backend/src/clay_mc/health/monitor.py`
- Create: `backend/src/clay_mc/config/models.py`
- Create: `backend/src/clay_mc/config/paths.py`
- Create: `backend/src/clay_mc/config/loader.py`
- Create: `backend/src/clay_mc/preflight/models.py`
- Create: `backend/src/clay_mc/preflight/service.py`
- Create: `backend/src/clay_mc/events/bus.py`
- Create: `backend/src/clay_mc/audit/writer.py`
- Create: `backend/src/clay_mc/scheduler/service.py`
- Create: `backend/tests/api/test_runtime_api.py`
- Create: `backend/tests/runtime/test_transitions.py`
- Create: `backend/tests/config/test_loader.py`
- Create: `backend/tests/services/test_registry.py`
- Create: `backend/tests/preflight/test_service.py`

### Frontend

- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/types/runtime.ts`
- Create: `frontend/src/components/status-badge.tsx`
- Create: `frontend/src/features/runtime/runtime-panel.tsx`
- Create: `frontend/src/features/services/services-table.tsx`
- Create: `frontend/src/features/alerts/alerts-panel.tsx`
- Create: `frontend/src/App.test.tsx`

### Repo-level

- Create: `Makefile`
- Create: `README.md`
- Create: `.gitignore`
- Create: `.env.example`

---

### Task 1: Bootstrap The Repository And Development Entry Points

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/clay_mc/__init__.py`
- Create: `backend/src/clay_mc/api/main.py`
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `Makefile`
- Create: `README.md`
- Create: `.gitignore`
- Create: `.env.example`
- Test: `backend/tests/api/test_runtime_api.py`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write the failing backend smoke test**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_runtime_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_runtime_state_endpoint_returns_bootstrap_state() -> None:
    client = TestClient(app)

    response = client.get("/runtime/state")

    assert response.status_code == 200
    assert response.json()["state"] == "background_monitoring"
```

- [ ] **Step 2: Run the backend test to verify it fails**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/api/test_runtime_api.py -v
```

Expected: FAIL because `clay_mc.api.main` does not exist yet.

- [ ] **Step 3: Create the minimal backend bootstrap**

```toml
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/pyproject.toml
[project]
name = "clay-mission-control-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115,<1.0",
  "uvicorn[standard]>=0.30,<1.0",
  "pydantic>=2.8,<3.0",
  "pydantic-settings>=2.4,<3.0",
]

[dependency-groups]
dev = [
  "httpx>=0.27,<1.0",
  "pytest>=8.3,<9.0",
  "pytest-asyncio>=0.23,<1.0",
]

[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/__init__.py
__all__ = ["__version__"]

__version__ = "0.1.0"
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/main.py
from fastapi import FastAPI


app = FastAPI(title="CLAY Mission Control API")


@app.get("/runtime/state")
def get_runtime_state() -> dict[str, object]:
    return {
        "state": "background_monitoring",
        "allowed_transitions": ["pre_session", "degraded"],
    }
```

- [ ] **Step 4: Create the minimal frontend and repo entry points**

```json
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/package.json
{
  "name": "clay-mission-control-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@testing-library/react": "^16.0.1",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.2",
    "vitest": "^2.0.5"
  }
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/App.tsx
export function App() {
  return (
    <main>
      <h1>CLAY Mission Control</h1>
      <p>Runtime foundation shell</p>
    </main>
  );
}

export default App
```

```makefile
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/Makefile
.PHONY: backend-test frontend-test

backend-test:
	cd backend && uv run pytest

frontend-test:
	cd frontend && npm test
```

- [ ] **Step 5: Run the smoke tests and commit**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv sync
uv run pytest tests/api/test_runtime_api.py -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
npm install
npm test -- --run
```

Expected:
- backend smoke test PASS
- frontend test runner boots successfully after adding a matching test file

Commit:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add .
git commit -m "chore: bootstrap clay mission control app"
```

### Task 2: Implement Runtime State Contracts And Transition Rules

**Files:**
- Create: `backend/src/clay_mc/runtime/states.py`
- Create: `backend/src/clay_mc/runtime/transitions.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Test: `backend/tests/runtime/test_transitions.py`
- Test: `backend/tests/api/test_runtime_api.py`

- [ ] **Step 1: Write the failing runtime transition tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/runtime/test_transitions.py
import pytest

from clay_mc.runtime.states import RuntimeState
from clay_mc.runtime.transitions import InvalidTransitionError, get_allowed_transitions, validate_transition


def test_background_monitoring_allows_pre_session() -> None:
    assert RuntimeState.PRE_SESSION in get_allowed_transitions(RuntimeState.BACKGROUND_MONITORING)


def test_background_monitoring_rejects_active_session() -> None:
    with pytest.raises(InvalidTransitionError):
        validate_transition(RuntimeState.BACKGROUND_MONITORING, RuntimeState.ACTIVE_SESSION)
```

- [ ] **Step 2: Run the runtime tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/runtime/test_transitions.py -v
```

Expected: FAIL because runtime modules do not exist yet.

- [ ] **Step 3: Implement runtime states and transitions**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/runtime/states.py
from enum import StrEnum


class RuntimeState(StrEnum):
    BACKGROUND_MONITORING = "background_monitoring"
    PRE_SESSION = "pre_session"
    ACTIVE_SESSION = "active_session"
    PAUSED = "paused"
    REVIEW = "review"
    DEGRADED = "degraded"
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/runtime/transitions.py
from clay_mc.runtime.states import RuntimeState


class InvalidTransitionError(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[RuntimeState, set[RuntimeState]] = {
    RuntimeState.BACKGROUND_MONITORING: {RuntimeState.PRE_SESSION, RuntimeState.DEGRADED},
    RuntimeState.PRE_SESSION: {RuntimeState.ACTIVE_SESSION, RuntimeState.BACKGROUND_MONITORING, RuntimeState.DEGRADED},
    RuntimeState.ACTIVE_SESSION: {RuntimeState.PAUSED, RuntimeState.REVIEW, RuntimeState.DEGRADED},
    RuntimeState.PAUSED: {RuntimeState.ACTIVE_SESSION, RuntimeState.DEGRADED},
    RuntimeState.REVIEW: {RuntimeState.BACKGROUND_MONITORING, RuntimeState.DEGRADED},
    RuntimeState.DEGRADED: {RuntimeState.BACKGROUND_MONITORING, RuntimeState.PRE_SESSION},
}


def get_allowed_transitions(source: RuntimeState) -> list[RuntimeState]:
    return sorted(ALLOWED_TRANSITIONS[source], key=lambda state: state.value)


def validate_transition(source: RuntimeState, target: RuntimeState) -> None:
    if target not in ALLOWED_TRANSITIONS[source]:
        raise InvalidTransitionError(f"{source.value} -> {target.value} is not allowed")
```

- [ ] **Step 4: Wire the API endpoint to the enum-based model**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/main.py
from fastapi import FastAPI

from clay_mc.runtime.states import RuntimeState
from clay_mc.runtime.transitions import get_allowed_transitions


app = FastAPI(title="CLAY Mission Control API")


@app.get("/runtime/state")
def get_runtime_state() -> dict[str, object]:
    current_state = RuntimeState.BACKGROUND_MONITORING
    return {
        "state": current_state.value,
        "allowed_transitions": [state.value for state in get_allowed_transitions(current_state)],
    }
```

- [ ] **Step 5: Run the transition tests and commit**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/runtime/test_transitions.py tests/api/test_runtime_api.py -v
```

Expected: PASS

Commit:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend
git commit -m "feat: add runtime states and transition rules"
```

### Task 3: Implement XDG Paths, Config Schemas, Validation, And Rollback

**Files:**
- Create: `backend/src/clay_mc/config/paths.py`
- Create: `backend/src/clay_mc/config/models.py`
- Create: `backend/src/clay_mc/config/loader.py`
- Create: `backend/tests/config/test_loader.py`

- [ ] **Step 1: Write the failing config loader tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/config/test_loader.py
from pathlib import Path

import pytest

from clay_mc.config.loader import ConfigLoader


def test_loader_uses_xdg_runtime_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    loader = ConfigLoader()

    assert "clay-mission-control" in str(loader.paths.config_dir)


def test_invalid_config_rolls_back_to_last_valid_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    loader = ConfigLoader()
    loader.write_default_configs()
    loader.apply_raw_text("runtime", 'mode = "broken"')

    with pytest.raises(ValueError):
        loader.load_all()

    assert loader.restore_last_valid("runtime").exists()
```

- [ ] **Step 2: Run the config tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/config/test_loader.py -v
```

Expected: FAIL because config modules do not exist yet.

- [ ] **Step 3: Implement XDG-aware paths and config models**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/config/paths.py
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class XdgPaths:
    config_dir: Path
    data_dir: Path
    state_dir: Path
    cache_dir: Path


def build_xdg_paths() -> XdgPaths:
    home = Path.home()
    root_name = "clay-mission-control"
    return XdgPaths(
        config_dir=Path(os.getenv("XDG_CONFIG_HOME", home / ".config")) / root_name,
        data_dir=Path(os.getenv("XDG_DATA_HOME", home / ".local/share")) / root_name,
        state_dir=Path(os.getenv("XDG_STATE_HOME", home / ".local/state")) / root_name,
        cache_dir=Path(os.getenv("XDG_CACHE_HOME", home / ".cache")) / root_name,
    )
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/config/models.py
from pydantic import BaseModel, Field


class RuntimeConfig(BaseModel):
    work_window_start: str = "09:00"
    work_window_end: str = "22:00"
    default_state: str = "background_monitoring"


class RiskConfig(BaseModel):
    confidence_warning_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    degraded_confidence_penalty: float = Field(default=0.2, ge=0.0, le=1.0)
```

- [ ] **Step 4: Implement config loader with last-valid rollback**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/config/loader.py
from pathlib import Path
import shutil
import tomllib

from clay_mc.config.models import RiskConfig, RuntimeConfig
from clay_mc.config.paths import XdgPaths, build_xdg_paths


class ConfigLoader:
    def __init__(self, paths: XdgPaths | None = None) -> None:
        self.paths = paths or build_xdg_paths()
        self.paths.config_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.paths.config_dir / ".last_valid"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def write_default_configs(self) -> None:
        (self.paths.config_dir / "runtime.toml").write_text('work_window_start = "09:00"\nwork_window_end = "22:00"\ndefault_state = "background_monitoring"\n')
        (self.paths.config_dir / "risk.toml").write_text("confidence_warning_threshold = 0.6\ndegraded_confidence_penalty = 0.2\n")

    def apply_raw_text(self, scope: str, text: str) -> Path:
        target = self.paths.config_dir / f"{scope}.toml"
        target.write_text(text)
        return target

    def load_all(self) -> dict[str, object]:
        runtime_path = self.paths.config_dir / "runtime.toml"
        risk_path = self.paths.config_dir / "risk.toml"
        runtime_data = tomllib.loads(runtime_path.read_text())
        risk_data = tomllib.loads(risk_path.read_text())
        runtime = RuntimeConfig.model_validate(runtime_data)
        risk = RiskConfig.model_validate(risk_data)
        shutil.copy2(runtime_path, self.backup_dir / "runtime.toml")
        shutil.copy2(risk_path, self.backup_dir / "risk.toml")
        return {"runtime": runtime, "risk": risk}

    def restore_last_valid(self, scope: str) -> Path:
        backup = self.backup_dir / f"{scope}.toml"
        target = self.paths.config_dir / f"{scope}.toml"
        shutil.copy2(backup, target)
        return target
```

- [ ] **Step 5: Run the config tests and commit**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/config/test_loader.py -v
```

Expected: PASS

Commit:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend
git commit -m "feat: add xdg config loader with rollback"
```

### Task 4: Implement The Service Registry And Process Supervisor

**Files:**
- Create: `backend/src/clay_mc/services/models.py`
- Create: `backend/src/clay_mc/services/registry.py`
- Create: `backend/src/clay_mc/services/supervisor.py`
- Create: `backend/tests/services/test_registry.py`

- [ ] **Step 1: Write the failing registry tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/services/test_registry.py
from clay_mc.services.models import ServiceCriticality, ServiceStatus
from clay_mc.services.registry import ServiceRegistry


def test_registry_exposes_registered_services() -> None:
    registry = ServiceRegistry()
    registry.register(
        service_id="market-data-service",
        service_type="worker",
        criticality=ServiceCriticality.CRITICAL,
        startup_policy="background-critical",
    )

    services = registry.list_services()

    assert len(services) == 1
    assert services[0].status == ServiceStatus.STOPPED


def test_registry_can_mark_service_degraded() -> None:
    registry = ServiceRegistry()
    registry.register(
        service_id="control-api",
        service_type="api",
        criticality=ServiceCriticality.CRITICAL,
        startup_policy="always-on",
    )

    registry.update_status("control-api", ServiceStatus.DEGRADED)

    assert registry.get("control-api").status == ServiceStatus.DEGRADED
```

- [ ] **Step 2: Run the registry tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/services/test_registry.py -v
```

Expected: FAIL because service registry modules do not exist yet.

- [ ] **Step 3: Implement service models and registry**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/services/models.py
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import StrEnum


class ServiceStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    ERROR = "error"
    STOPPING = "stopping"


class ServiceCriticality(StrEnum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    OPTIONAL = "optional"


@dataclass
class ServiceRecord:
    service_id: str
    service_type: str
    criticality: ServiceCriticality
    startup_policy: str
    status: ServiceStatus = ServiceStatus.STOPPED
    last_heartbeat_at: datetime | None = field(default=None)
    last_error: str | None = field(default=None)

    def heartbeat(self) -> None:
        self.last_heartbeat_at = datetime.now(UTC)
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/services/registry.py
from clay_mc.services.models import ServiceCriticality, ServiceRecord, ServiceStatus


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, ServiceRecord] = {}

    def register(self, service_id: str, service_type: str, criticality: ServiceCriticality, startup_policy: str) -> ServiceRecord:
        record = ServiceRecord(
            service_id=service_id,
            service_type=service_type,
            criticality=criticality,
            startup_policy=startup_policy,
        )
        self._services[service_id] = record
        return record

    def get(self, service_id: str) -> ServiceRecord:
        return self._services[service_id]

    def list_services(self) -> list[ServiceRecord]:
        return sorted(self._services.values(), key=lambda item: item.service_id)

    def update_status(self, service_id: str, status: ServiceStatus, error: str | None = None) -> ServiceRecord:
        record = self._services[service_id]
        record.status = status
        record.last_error = error
        return record
```

- [ ] **Step 4: Implement the minimal process supervisor contract**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/services/supervisor.py
from clay_mc.services.models import ServiceStatus
from clay_mc.services.registry import ServiceRegistry


class ProcessSupervisor:
    def __init__(self, registry: ServiceRegistry) -> None:
        self.registry = registry

    def start(self, service_id: str) -> None:
        self.registry.update_status(service_id, ServiceStatus.STARTING)
        self.registry.update_status(service_id, ServiceStatus.HEALTHY)

    def stop(self, service_id: str) -> None:
        self.registry.update_status(service_id, ServiceStatus.STOPPING)
        self.registry.update_status(service_id, ServiceStatus.STOPPED)

    def restart(self, service_id: str) -> None:
        self.stop(service_id)
        self.start(service_id)
```

- [ ] **Step 5: Run the registry tests and commit**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/services/test_registry.py -v
```

Expected: PASS

Commit:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend
git commit -m "feat: add service registry and process supervisor"
```

### Task 5: Implement The Runtime Manager, Health Monitor, And Scheduler

**Files:**
- Modify: `backend/src/clay_mc/runtime/manager.py`
- Create: `backend/src/clay_mc/health/monitor.py`
- Create: `backend/src/clay_mc/scheduler/service.py`
- Modify: `backend/tests/runtime/test_transitions.py`

- [ ] **Step 1: Extend the failing runtime tests for managed transitions**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/runtime/test_transitions.py
from clay_mc.runtime.manager import RuntimeManager
from clay_mc.runtime.states import RuntimeState
from clay_mc.services.models import ServiceCriticality, ServiceStatus
from clay_mc.services.registry import ServiceRegistry


def test_runtime_manager_can_enter_pre_session_when_critical_services_are_healthy() -> None:
    registry = ServiceRegistry()
    registry.register("control-api", "api", ServiceCriticality.CRITICAL, "always-on")
    registry.update_status("control-api", ServiceStatus.HEALTHY)
    manager = RuntimeManager(registry=registry)

    manager.transition_to(RuntimeState.PRE_SESSION)

    assert manager.state is RuntimeState.PRE_SESSION
```

- [ ] **Step 2: Run the runtime tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/runtime/test_transitions.py -v
```

Expected: FAIL because `RuntimeManager` is not implemented yet.

- [ ] **Step 3: Implement runtime manager**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/runtime/manager.py
from clay_mc.runtime.states import RuntimeState
from clay_mc.runtime.transitions import validate_transition
from clay_mc.services.models import ServiceStatus
from clay_mc.services.registry import ServiceRegistry


class RuntimeManager:
    def __init__(self, registry: ServiceRegistry) -> None:
        self.registry = registry
        self.state = RuntimeState.BACKGROUND_MONITORING

    def transition_to(self, target: RuntimeState) -> RuntimeState:
        validate_transition(self.state, target)
        if target is RuntimeState.PRE_SESSION:
            self._assert_critical_services_ready()
        self.state = target
        return self.state

    def enter_degraded(self) -> RuntimeState:
        self.state = RuntimeState.DEGRADED
        return self.state

    def _assert_critical_services_ready(self) -> None:
        for service in self.registry.list_services():
            if service.criticality == "critical" and service.status not in {ServiceStatus.HEALTHY, ServiceStatus.DEGRADED}:
                raise RuntimeError(f"critical service {service.service_id} is not ready")
```

- [ ] **Step 4: Implement health monitor and scheduler**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/health/monitor.py
from datetime import datetime, UTC, timedelta

from clay_mc.services.models import ServiceStatus
from clay_mc.services.registry import ServiceRegistry


class HealthMonitor:
    def __init__(self, registry: ServiceRegistry, stale_after_seconds: int = 60) -> None:
        self.registry = registry
        self.stale_after = timedelta(seconds=stale_after_seconds)

    def refresh(self) -> None:
        now = datetime.now(UTC)
        for service in self.registry.list_services():
            if service.last_heartbeat_at and now - service.last_heartbeat_at > self.stale_after:
                self.registry.update_status(service.service_id, ServiceStatus.STALE)
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/scheduler/service.py
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkWindow:
    start: str = "09:00"
    end: str = "22:00"
```

- [ ] **Step 5: Run the runtime tests and commit**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/runtime/test_transitions.py tests/services/test_registry.py -v
```

Expected: PASS

Commit:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend
git commit -m "feat: add runtime manager health monitor and scheduler"
```

### Task 6: Implement Preflight, Degraded Mode, Audit, And Control API Routes

**Files:**
- Create: `backend/src/clay_mc/preflight/models.py`
- Create: `backend/src/clay_mc/preflight/service.py`
- Create: `backend/src/clay_mc/events/bus.py`
- Create: `backend/src/clay_mc/audit/writer.py`
- Create: `backend/src/clay_mc/api/routes/runtime.py`
- Create: `backend/src/clay_mc/api/routes/services.py`
- Create: `backend/src/clay_mc/api/routes/health.py`
- Create: `backend/src/clay_mc/api/routes/configs.py`
- Create: `backend/src/clay_mc/api/routes/preflight.py`
- Create: `backend/src/clay_mc/api/routes/events.py`
- Modify: `backend/src/clay_mc/api/main.py`
- Create: `backend/tests/preflight/test_service.py`
- Modify: `backend/tests/api/test_runtime_api.py`

- [ ] **Step 1: Write the failing preflight tests**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/preflight/test_service.py
from clay_mc.preflight.service import PreflightService
from clay_mc.services.models import ServiceCriticality, ServiceStatus
from clay_mc.services.registry import ServiceRegistry


def test_preflight_returns_pass_when_critical_services_are_healthy() -> None:
    registry = ServiceRegistry()
    registry.register("control-api", "api", ServiceCriticality.CRITICAL, "always-on")
    registry.update_status("control-api", ServiceStatus.HEALTHY)

    result = PreflightService(registry).run()

    assert result.status == "pass"


def test_preflight_returns_hard_fail_when_critical_service_is_down() -> None:
    registry = ServiceRegistry()
    registry.register("control-api", "api", ServiceCriticality.CRITICAL, "always-on")

    result = PreflightService(registry).run()

    assert result.status == "hard_fail"
```

- [ ] **Step 2: Run the preflight tests to verify they fail**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/preflight/test_service.py -v
```

Expected: FAIL because preflight modules do not exist yet.

- [ ] **Step 3: Implement preflight and audit primitives**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/preflight/models.py
from pydantic import BaseModel


class PreflightResult(BaseModel):
    status: str
    checks: list[dict[str, str]]
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/preflight/service.py
from clay_mc.preflight.models import PreflightResult
from clay_mc.services.models import ServiceCriticality, ServiceStatus
from clay_mc.services.registry import ServiceRegistry


class PreflightService:
    def __init__(self, registry: ServiceRegistry) -> None:
        self.registry = registry

    def run(self) -> PreflightResult:
        checks: list[dict[str, str]] = []
        hard_fail = False
        for service in self.registry.list_services():
            if service.criticality == ServiceCriticality.CRITICAL:
                status = "ok" if service.status == ServiceStatus.HEALTHY else "hard_fail"
                checks.append({"service_id": service.service_id, "status": status})
                hard_fail = hard_fail or status == "hard_fail"
        return PreflightResult(status="hard_fail" if hard_fail else "pass", checks=checks)
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/audit/writer.py
import json
from datetime import datetime, UTC
from pathlib import Path


class AuditWriter:
    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "audit.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_type: str, payload: dict[str, object]) -> None:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
```

- [ ] **Step 4: Expose the control API route groups**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/routes/runtime.py
from fastapi import APIRouter

from clay_mc.runtime.states import RuntimeState
from clay_mc.runtime.transitions import get_allowed_transitions


router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/state")
def get_runtime_state() -> dict[str, object]:
    state = RuntimeState.BACKGROUND_MONITORING
    return {"state": state.value, "allowed_transitions": [item.value for item in get_allowed_transitions(state)]}
```

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/src/clay_mc/api/main.py
from fastapi import FastAPI

from clay_mc.api.routes.runtime import router as runtime_router


app = FastAPI(title="CLAY Mission Control API")
app.include_router(runtime_router)
```

- [ ] **Step 5: Run API and preflight tests and commit**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest tests/preflight/test_service.py tests/api/test_runtime_api.py -v
```

Expected: PASS

Commit:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add backend
git commit -m "feat: add preflight degraded scaffolding and control api routes"
```

### Task 7: Build The Minimal Runtime Shell Frontend

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/types/runtime.ts`
- Create: `frontend/src/components/status-badge.tsx`
- Create: `frontend/src/features/runtime/runtime-panel.tsx`
- Create: `frontend/src/features/services/services-table.tsx`
- Create: `frontend/src/features/alerts/alerts-panel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write the failing frontend shell test**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/App.test.tsx
import { render, screen } from "@testing-library/react"

import App from "./App"


test("renders runtime foundation shell", () => {
  render(<App />)

  expect(screen.getByText("Runtime state")).toBeInTheDocument()
  expect(screen.getByText("Services")).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the frontend test to verify it fails**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
npm test -- --run
```

Expected: FAIL because UI sections are not implemented yet.

- [ ] **Step 3: Implement typed API client and status badge**

```ts
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/types/runtime.ts
export type RuntimeState =
  | "background_monitoring"
  | "pre_session"
  | "active_session"
  | "paused"
  | "review"
  | "degraded"

export interface RuntimePayload {
  state: RuntimeState
  allowed_transitions: RuntimeState[]
}
```

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/components/status-badge.tsx
type Props = {
  label: string
}

export function StatusBadge({ label }: Props) {
  return <span data-status={label}>{label}</span>
}
```

- [ ] **Step 4: Implement the runtime shell layout**

```tsx
// /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend/src/App.tsx
import { StatusBadge } from "./components/status-badge"

function App() {
  return (
    <main>
      <h1>CLAY Mission Control</h1>
      <section>
        <h2>Runtime state</h2>
        <StatusBadge label="background_monitoring" />
      </section>
      <section>
        <h2>Services</h2>
        <p>Service registry will appear here.</p>
      </section>
      <section>
        <h2>Alerts</h2>
        <p>No active alerts.</p>
      </section>
    </main>
  )
}

export default App
```

- [ ] **Step 5: Run frontend tests and commit**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
npm test -- --run
npm run build
```

Expected:
- frontend tests PASS
- production build PASS

Commit:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add frontend
git commit -m "feat: add runtime shell frontend"
```

### Task 8: Add End-To-End E1 Validation And Operating Docs

**Files:**
- Modify: `README.md`
- Modify: `Makefile`
- Modify: `.env.example`
- Modify: `backend/tests/api/test_runtime_api.py`
- Modify: `backend/tests/preflight/test_service.py`

- [ ] **Step 1: Add a failing integration smoke test**

```python
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend/tests/api/test_runtime_api.py
from fastapi.testclient import TestClient

from clay_mc.api.main import app


def test_runtime_state_exposes_allowed_transitions() -> None:
    client = TestClient(app)
    response = client.get("/runtime/state")

    assert response.status_code == 200
    assert "allowed_transitions" in response.json()
```

- [ ] **Step 2: Run the full backend and frontend test suites**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/backend
uv run pytest -v

cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/frontend
npm test -- --run
```

Expected: at least one failure while docs and scripts are still incomplete.

- [ ] **Step 3: Document the developer and operator workflow**

````markdown
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/README.md
# CLAY Mission Control App

## E1 Scope

This repository currently implements:

- runtime state model
- local control API
- service registry
- config validation and rollback
- preflight scaffolding
- degraded-mode scaffolding
- minimal runtime shell

## Run Backend

```bash
cd backend
uv sync
uv run uvicorn clay_mc.api.main:app --reload
```

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

## Run Tests

```bash
make backend-test
make frontend-test
```
````

- [ ] **Step 4: Update repo-level scripts and environment examples**

```env
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/.env.example
CLAY_API_HOST=127.0.0.1
CLAY_API_PORT=8000
CLAY_XDG_NAMESPACE=clay-mission-control
```

```makefile
# /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app/Makefile
.PHONY: backend-test frontend-test backend-run frontend-run

backend-test:
	cd backend && uv run pytest -v

frontend-test:
	cd frontend && npm test -- --run

backend-run:
	cd backend && uv run uvicorn clay_mc.api.main:app --reload

frontend-run:
	cd frontend && npm run dev
```

- [ ] **Step 5: Run the full validation suite and commit**

Run:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
make backend-test
make frontend-test
```

Expected: PASS

Commit:

```bash
cd /home/emma/Documents/Obsidian/CachyOS/Trading/CLAY_Mission_Control/app
git add .
git commit -m "docs: add e1 validation workflow and operator docs"
```

## Validation

- Backend tests:
  - `tests/runtime/test_transitions.py`
  - `tests/config/test_loader.py`
  - `tests/services/test_registry.py`
  - `tests/preflight/test_service.py`
  - `tests/api/test_runtime_api.py`
- Frontend tests:
  - `src/App.test.tsx`
- Manual checks:
  - runtime state visible in browser
  - service registry visible in browser
  - invalid config rolls back
  - preflight returns structured result
  - degraded mode can be surfaced in UI

## Open Questions

- Should `E1` spawn managed services directly with Python subprocesses, or should the first production-like version already delegate starts/stops to `systemd --user`?
- Should the event stream in `E1` use plain SSE from `FastAPI`, or do we want to reserve WebSocket semantics immediately even before `E3`?
- Should `audit.jsonl` remain file-backed through `E2`, or should audit move to PostgreSQL as soon as the historical store lands?
