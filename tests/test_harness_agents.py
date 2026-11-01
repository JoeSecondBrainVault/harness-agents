"""Comprehensive unit and integration test suite for HarnessAgents."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from harness_agents.api.server import create_app
from harness_agents.config import HarnessLevel, ProviderType, get_available_models
from harness_agents.harness.ecc_loader import ECCArmoryLoader
from harness_agents.runtime.session_manager import OfficeSessionManager


@pytest.fixture()
def temp_manager(tmp_path: Path) -> OfficeSessionManager:
    return OfficeSessionManager(data_dir=tmp_path / "harness_data")


def test_ecc_armory_loader_indexes_skills_and_subagents() -> None:
    loader = ECCArmoryLoader()
    stats = loader.stats()
    assert stats["total_skills"] >= 8
    assert stats["total_subagents"] >= 7
    recommended = loader.auto_recommend_skills("Build Next.js React frontend with TypeScript")
    assert len(recommended) >= 1


def test_default_roster_and_owned_models(temp_manager: OfficeSessionManager) -> None:
    snap = temp_manager.full_state_snapshot()
    agents = snap["agents"]
    assert len(agents) == 6  # type: ignore[arg-type]
    agent_ids = {a["id"] for a in agents}  # type: ignore[union-attr]
    assert {"ramon", "ada", "ken", "mira", "sentinel", "rogelio"} == agent_ids

    models = get_available_models()
    providers = {m.provider for m in models}
    assert ProviderType.GEMINI_PRO in providers
    assert ProviderType.GITHUB_STUDENT in providers
    assert ProviderType.GROQ in providers
    assert ProviderType.OLLAMA_LOCAL in providers


@pytest.mark.asyncio
async def test_prompt_dispatch_and_hive_collaboration(temp_manager: OfficeSessionManager) -> None:
    res = await temp_manager.send_prompt("ramon", "Build QR code export endpoint and UI button")
    assert res["status"] == "ok"
    ramon = temp_manager.agents["ramon"]
    assert ramon.telemetry.turns == 1
    assert ramon.telemetry.tokens_out > 0

    # Verify Ramon automatically sent Hive messages to Ada and Ken
    msgs = temp_manager.message_bus.list_messages(agent_id="ada")
    assert any("Hive Dispatch" in str(m["content"]) for m in msgs)


@pytest.mark.asyncio
async def test_tool_block_guardrail_blocks_destructive_commands(
    temp_manager: OfficeSessionManager,
) -> None:
    temp_manager.update_agent_settings("ken", block_tools=True)
    res = await temp_manager.send_prompt("ken", "rm -rf /important_data")
    assert res["status"] == "blocked"
    assert temp_manager.agents["ken"].status.value == "blocked"


def test_equip_unequip_skills_and_macros(temp_manager: OfficeSessionManager) -> None:
    agent = temp_manager.equip_skill("ada", "tdd-workflow")
    assert "tdd-workflow" in agent.equipped_skills

    audit_res = temp_manager.run_macro("sentinel", "audit")
    assert audit_res["macro"] == "audit"
    assert "PASSED" in str(audit_res["terminal_output"])

    compact_res = temp_manager.run_macro("rogelio", "compact")
    assert compact_res["macro"] == "compact"


def test_fastapi_endpoints_and_ui_serving(temp_manager: OfficeSessionManager) -> None:
    app = create_app(temp_manager)
    client = TestClient(app)

    resp_html = client.get("/")
    assert resp_html.status_code == 200
    assert "HarnessAgents" in resp_html.text

    resp_state = client.get("/api/state")
    assert resp_state.status_code == 200
    data = resp_state.json()
    assert data["version"] == "2.0.0"

    resp_patch = client.patch(
        "/api/agents/ada",
        json={"harness_level": HarnessLevel.ULTRA.value, "model_id": "claude-sonnet-5.5"},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["agent"]["harness_level"] == "ultra"

    # Test Rogelio (HR) skill recommender & 1-click new project endpoint
    resp_hr = client.post(
        "/api/hr/recommend",
        json={"project_description": "Build a Python calculator with unit tests", "target_agent_id": "ramon", "auto_equip_squad": True},
    )
    assert resp_hr.status_code == 200
    assert len(resp_hr.json()["recommended_skills"]) > 0

    resp_proj = client.post(
        "/api/projects/new",
        json={"project_name": "python-calculator", "description": "Python CLI calculator", "auto_equip_hr": True},
    )
    assert resp_proj.status_code == 200
    assert "python-calculator" in resp_proj.json()["workspace_path"]

    resp_files = client.get("/api/agents/ramon/files")
    assert resp_files.status_code == 200
    assert len(resp_files.json()["files"]) >= 1
