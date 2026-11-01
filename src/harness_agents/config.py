"""Strict configuration and domain models for HarnessAgents."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


def bootstrap_local_credentials() -> dict[str, str]:
    """Safely load keys into os.environ from local .env, E.V.E/.env, and `gh auth token` without hardcoding."""
    sources: dict[str, str] = {}
    env_candidates = [
        Path("C:/Users/Legion/.gemini/antigravity/scratch/harness-agents/.env"),
        Path("C:/Users/Legion/Documents/E.V.E/.env"),
    ]
    for env_path in env_candidates:
        if not env_path.exists():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                key = k.strip()
                val = v.strip().strip('"').strip("'")
                if val and key in {
                    "GEMINI_API_KEY",
                    "GOOGLE_API_KEY",
                    "GROQ_API_KEY",
                    "GITHUB_TOKEN",
                    "GH_TOKEN",
                    "EVE_GEMINI_API_KEY",
                    "EVE_GROQ_API_KEY",
                }:
                    if key == "EVE_GEMINI_API_KEY" and not os.environ.get("GEMINI_API_KEY"):
                        os.environ["GEMINI_API_KEY"] = val
                        sources["GEMINI_API_KEY"] = f"Loaded from {env_path.parent.name}/.env"
                    elif key == "EVE_GROQ_API_KEY" and not os.environ.get("GROQ_API_KEY"):
                        os.environ["GROQ_API_KEY"] = val
                        sources["GROQ_API_KEY"] = f"Loaded from {env_path.parent.name}/.env"
                    elif not os.environ.get(key):
                        os.environ[key] = val
                        sources[key] = f"Loaded from {env_path.parent.name}/.env"
        except OSError:
            continue

    # Auto-detect GitHub Student Pack token from `gh auth token` CLI if not in env
    if not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")):
        gh_bin = shutil.which("gh")
        if gh_bin:
            try:
                proc = subprocess.run(
                    [gh_bin, "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                tok = proc.stdout.strip()
                if proc.returncode == 0 and tok:
                    os.environ["GITHUB_TOKEN"] = tok
                    sources["GITHUB_TOKEN"] = "Loaded from `gh auth token` CLI"
            except (OSError, subprocess.SubprocessError):
                pass

    return sources


CREDENTIAL_SOURCES = bootstrap_local_credentials()


class HarnessLevel(str, Enum):
    OFF = "off"
    LITE = "lite"
    FULL = "full"
    ULTRA = "ultra"


class ProviderType(str, Enum):
    GEMINI_PRO = "gemini_pro"
    GITHUB_STUDENT = "github_student"
    GROQ = "groq"
    OLLAMA_LOCAL = "ollama_local"


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    COLLABORATING = "collaborating"
    BLOCKED = "blocked"
    ERROR = "error"


class ModelCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    provider: ProviderType
    context_window: int = 128000
    speed_label: str = "Fast"
    cost_per_1k: float = 0.0
    description: str = ""


class FurnitureItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str  # desk, war_table, server_rack, ph_flag, water_cooler, ping_pong, sofa, treadmill, plant
    label: str
    floor: int = 1
    grid_x: int
    grid_y: int
    width: int = 1
    depth: int = 1
    rotation: int = 0  # 0, 1, 2, 3 (90-degree increments)
    color: str = "#38bdf8"
    assigned_agent_id: str | None = None


class AgentTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    turns: int = 0
    agent_time_sec: float = 0.0
    context_used_tokens: int = 8000
    context_max_tokens: int = 1000000
    tokens_per_sec: float = 0.0


class AgentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    display_title: str
    role: str
    department: str
    workspace_path: str
    floor: int = 1
    desk_x: int = 4
    desk_y: int = 4
    current_x: float = 4.0
    current_y: float = 4.0
    target_x: float = 4.0
    target_y: float = 4.0
    avatar_color: str = "#22c55e"
    shirt_color: str = "#3b82f6"
    hair_color: str = "#1e293b"
    star_color: str = "#facc15"
    status: AgentStatus = AgentStatus.IDLE
    provider: ProviderType = ProviderType.GEMINI_PRO
    model_id: str = "gemini-4-argon"
    harness_level: HarnessLevel = HarnessLevel.FULL
    equipped_skills: list[str] = Field(default_factory=list)
    subagent_persona: str = "architect"
    block_tools: bool = False
    stop_after_step: bool = False
    bypass_permissions: bool = True
    is_hive_lead: bool = False
    speech_bubble: str = ""
    speech_expires_at: str | None = None
    collaborating_with: str | None = None
    pty_id: str = ""
    telemetry: AgentTelemetry = Field(default_factory=AgentTelemetry)
    prompt_queue: list[str] = Field(default_factory=list)


class FloorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    floor_number: int
    name: str
    max_agents: int = 15
    grid_width: int = 20
    grid_height: int = 14


def get_available_models() -> list[ModelCatalogEntry]:
    """Return the full catalog of zero-extra-cost models owned by the user."""
    return [
        # 1. Gemini Pro Multi-Model Suite
        ModelCatalogEntry(
            id="gemini-4-argon",
            label="Gemini 4 Argon (Gemini Pro Suite)",
            provider=ProviderType.GEMINI_PRO,
            context_window=1000000,
            speed_label="Deep Reasoning",
            cost_per_1k=0.0,
            description="Lead architecture, multi-file planning, and full-repo context.",
        ),
        ModelCatalogEntry(
            id="claude-opus-5.5",
            label="Claude Opus 5.5 (via Gemini Pro / Antigravity)",
            provider=ProviderType.GEMINI_PRO,
            context_window=1000000,
            speed_label="Medium Effort",
            cost_per_1k=0.0,
            description="High-craft complex refactoring and deep architectural synthesis.",
        ),
        ModelCatalogEntry(
            id="claude-sonnet-5.5",
            label="Claude Sonnet 5.5 (Gemini Pro / Copilot)",
            provider=ProviderType.GEMINI_PRO,
            context_window=400000,
            speed_label="High Speed",
            cost_per_1k=0.0,
            description="Frontend UI, React/Next.js, TypeScript, and surgical edits.",
        ),
        ModelCatalogEntry(
            id="gemini-3.8-flash",
            label="Gemini 3.8 Flash (Gemini Pro Suite)",
            provider=ProviderType.GEMINI_PRO,
            context_window=1000000,
            speed_label="Ultra Fast",
            cost_per_1k=0.0,
            description="Rapid worker loops, multimodal UI inspection, and high-throughput coding.",
        ),
        ModelCatalogEntry(
            id="gpt-oss-120b",
            label="GPT-OSS 120B (Gemini Pro Suite)",
            provider=ProviderType.GEMINI_PRO,
            context_window=256000,
            speed_label="Fast",
            cost_per_1k=0.0,
            description="Alternative open-weights reasoning model for cross-verification.",
        ),
        # 2. GitHub Student Developer Pack (Copilot Pro + GitHub Models)
        ModelCatalogEntry(
            id="github-copilot-sonnet",
            label="Copilot Pro Claude Sonnet (GitHub Student Pack)",
            provider=ProviderType.GITHUB_STUDENT,
            context_window=200000,
            speed_label="Fast",
            cost_per_1k=0.0,
            description="Zero-cost student pack coding model via GitHub Copilot / Models API.",
        ),
        ModelCatalogEntry(
            id="github-o3-mini",
            label="OpenAI o3-mini / GPT-4o (GitHub Student Models)",
            provider=ProviderType.GITHUB_STUDENT,
            context_window=200000,
            speed_label="Reasoning",
            cost_per_1k=0.0,
            description="Algorithmic logic and test synthesis via models.inference.ai.azure.com.",
        ),
        # 3. Groq LPU API
        ModelCatalogEntry(
            id="llama-3.3-70b-versatile",
            label="Groq Llama 3.3 70B (840 tok/s LPU)",
            provider=ProviderType.GROQ,
            context_window=128000,
            speed_label="840 tok/s",
            cost_per_1k=0.0,
            description="Instantaneous tool loops, TDD test analysis, and Kanban task triage.",
        ),
        ModelCatalogEntry(
            id="qwen-qwq-32b",
            label="Groq Qwen-QwQ 32B Reasoning (650 tok/s)",
            provider=ProviderType.GROQ,
            context_window=128000,
            speed_label="650 tok/s",
            cost_per_1k=0.0,
            description="Ultra-fast reasoning for backend debugging and code review gates.",
        ),
        ModelCatalogEntry(
            id="deepseek-r1-distill-llama-70b",
            label="Groq DeepSeek-R1 Distill 70B (Security Gate)",
            provider=ProviderType.GROQ,
            context_window=128000,
            speed_label="600 tok/s",
            cost_per_1k=0.0,
            description="Chain-of-thought security auditing and vulnerability verification.",
        ),
        # 4. Local RTX 4060 (8GB VRAM Ollama + Laya Router)
        ModelCatalogEntry(
            id="qwen7b-rtx:latest",
            label="Local RTX 4060 qwen7b-rtx:latest (100% Offline)",
            provider=ProviderType.OLLAMA_LOCAL,
            context_window=32768,
            speed_label="Local GPU",
            cost_per_1k=0.0,
            description="Your custom RTX 4060 8GB VRAM model (Flash Attention + q8_0 KV).",
        ),
        ModelCatalogEntry(
            id="qwen2.5-coder:7b",
            label="Local RTX 4060 qwen2.5-coder:7b (100% Offline)",
            provider=ProviderType.OLLAMA_LOCAL,
            context_window=32768,
            speed_label="Local GPU",
            cost_per_1k=0.0,
            description="Installed 7B local coding model for Ops, Memory & Obsidian sync.",
        ),
        ModelCatalogEntry(
            id="qwen2.5-coder:14b",
            label="Local RTX 4060 qwen2.5-coder:14b (Deep Local)",
            provider=ProviderType.OLLAMA_LOCAL,
            context_window=32768,
            speed_label="Local Heavy",
            cost_per_1k=0.0,
            description="Installed 14B local coding model on your Ollama daemon.",
        ),
    ]


def get_default_agents() -> list[AgentProfile]:
    """Create the default 6 specialized agents on Floor 1 matching the user's screenshot & stack."""
    default_workspace = str(Path("C:/Users/Legion/.gemini/antigravity/scratch").resolve())
    return [
        AgentProfile(
            id="ramon",
            name="ramon",
            display_title="ramon — hive lead & architect",
            role="Hive Coordinator & System Architect",
            department="hive",
            workspace_path=default_workspace,
            floor=1,
            desk_x=15,
            desk_y=2,
            current_x=15.0,
            current_y=2.0,
            target_x=15.0,
            target_y=2.0,
            avatar_color="#ef4444",
            shirt_color="#dc2626",
            hair_color="#18181b",
            star_color="#facc15",
            status=AgentStatus.IDLE,
            provider=ProviderType.GEMINI_PRO,
            model_id="gemini-4-argon",
            harness_level=HarnessLevel.FULL,
            equipped_skills=["tdd-workflow", "backend-patterns", "model-handoff"],
            subagent_persona="planner",
            is_hive_lead=True,
            speech_bubble="Boss Office Ready!",
            pty_id="pty-ramon-hive-lead-91ax01",
        ),
        AgentProfile(
            id="ada",
            name="ada",
            display_title="ada — frontend & ui specialist",
            role="Frontend, Next.js, React & Electron Engineer",
            department="HarnessAgents",
            workspace_path=default_workspace,
            floor=1,
            desk_x=3,
            desk_y=6,
            current_x=3.0,
            current_y=6.0,
            target_x=3.0,
            target_y=6.0,
            avatar_color="#ec4899",
            shirt_color="#db2777",
            hair_color="#451a03",
            star_color="#f472b6",
            status=AgentStatus.IDLE,
            provider=ProviderType.GEMINI_PRO,
            model_id="claude-sonnet-5.5",
            harness_level=HarnessLevel.FULL,
            equipped_skills=["frontend-patterns", "code-review-gate"],
            subagent_persona="architect",
            pty_id="pty-ada-frontend-ui-82bx02",
        ),
        AgentProfile(
            id="ken",
            name="ken",
            display_title="ken — backend & api engineer",
            role="Python FastAPI, Laravel & Database Engineer",
            department="HarnessAgents",
            workspace_path=default_workspace,
            floor=1,
            desk_x=6,
            desk_y=6,
            current_x=6.0,
            current_y=6.0,
            target_x=6.0,
            target_y=6.0,
            avatar_color="#38bdf8",
            shirt_color="#0284c7",
            hair_color="#0f172a",
            star_color="#38bdf8",
            status=AgentStatus.IDLE,
            provider=ProviderType.GEMINI_PRO,
            model_id="gemini-4-argon",
            harness_level=HarnessLevel.FULL,
            equipped_skills=["backend-patterns", "systematic-debugging"],
            subagent_persona="build-error-resolver",
            pty_id="pty-ken-backend-api-73cx03",
        ),
        AgentProfile(
            id="mira",
            name="mira",
            display_title="mira — qa & tdd test runner",
            role="Automated Testing, Pytest & Bug Isolation",
            department="HarnessAgents",
            workspace_path=default_workspace,
            floor=1,
            desk_x=3,
            desk_y=9,
            current_x=3.0,
            current_y=9.0,
            target_x=3.0,
            target_y=9.0,
            avatar_color="#eab308",
            shirt_color="#ca8a04",
            hair_color="#27272a",
            star_color="#fde047",
            status=AgentStatus.IDLE,
            provider=ProviderType.GROQ,
            model_id="llama-3.3-70b-versatile",
            harness_level=HarnessLevel.FULL,
            equipped_skills=["tdd-workflow", "systematic-debugging"],
            subagent_persona="tdd-guide",
            pty_id="pty-mira-qa-tdd-64dx04",
        ),
        AgentProfile(
            id="sentinel",
            name="sentinel",
            display_title="sentinel — security & anti-slop gate",
            role="OWASP ASVS 5.0.0 & Bandit/Secret Auditor",
            department="HarnessAgents",
            workspace_path=default_workspace,
            floor=1,
            desk_x=6,
            desk_y=9,
            current_x=6.0,
            current_y=9.0,
            target_x=6.0,
            target_y=9.0,
            avatar_color="#a855f7",
            shirt_color="#7e22ce",
            hair_color="#1e1b4b",
            star_color="#c084fc",
            status=AgentStatus.IDLE,
            provider=ProviderType.GROQ,
            model_id="deepseek-r1-distill-llama-70b",
            harness_level=HarnessLevel.ULTRA,
            equipped_skills=["code-review-gate", "polish-project"],
            subagent_persona="security-reviewer",
            pty_id="pty-sentinel-sec-gate-55ex05",
        ),
        AgentProfile(
            id="rogelio",
            name="rogelio",
            display_title="rogelio — hr, ops & second brain",
            role="HR, Recruitment, Obsidian Brain & Graphify Sync",
            department="F:\\.Folder Redirection\\Video\\SAMPLE",
            workspace_path=default_workspace,
            floor=1,
            desk_x=10,
            desk_y=3,
            current_x=10.0,
            current_y=3.0,
            target_x=10.0,
            target_y=3.0,
            avatar_color="#22d3ee",
            shirt_color="#0891b2",
            hair_color="#3f3f46",
            star_color="#67e8f9",
            status=AgentStatus.IDLE,
            provider=ProviderType.OLLAMA_LOCAL,
            model_id="qwen2.5-coder:7b",
            harness_level=HarnessLevel.FULL,
            equipped_skills=["wrap-up", "evolve-brain", "harness2"],
            subagent_persona="harness-optimizer",
            speech_bubble="SWELDO NA!",
            pty_id="pty-rogelio-hr-recruitment-mvvn88s6",
        ),
    ]


def get_default_floors() -> list[FloorConfig]:
    """Return the 6 default office floors shown in the bottom bar."""
    return [
        FloorConfig(floor_number=1, name="Floor 1 — Core AI & Engineering HQ", max_agents=15),
        FloorConfig(floor_number=2, name="Floor 2 — QA, Security & Red Team Lab", max_agents=15),
        FloorConfig(floor_number=3, name="Floor 3 — Product, Design & Mobile Studio", max_agents=15),
        FloorConfig(floor_number=4, name="Floor 4 — Data Science & Bio-Compute", max_agents=15),
        FloorConfig(floor_number=5, name="Floor 5 — DevOps, Cloud & Infra", max_agents=15),
        FloorConfig(floor_number=6, name="Floor 6 — HR, Ops & Executive Suite", max_agents=15),
    ]


def get_default_furniture() -> list[FurnitureItem]:
    """Return the default isometric furniture layout for Floor 1."""
    return [
        # 6 Agent Workstations (Ramon in his Executive Boss Office at 15,2; Rogelio in HR Cubicle at 10,3)
        FurnitureItem(
            id="desk-ramon",
            kind="desk",
            label="Ramon Executive Boss Desk",
            floor=1,
            grid_x=15,
            grid_y=2,
            color="#ef4444",
            assigned_agent_id="ramon",
        ),
        FurnitureItem(
            id="desk-ada",
            kind="desk",
            label="Ada UI Workstation",
            floor=1,
            grid_x=3,
            grid_y=6,
            color="#ec4899",
            assigned_agent_id="ada",
        ),
        FurnitureItem(
            id="desk-ken",
            kind="desk",
            label="Ken API Workstation",
            floor=1,
            grid_x=6,
            grid_y=6,
            color="#38bdf8",
            assigned_agent_id="ken",
        ),
        FurnitureItem(
            id="desk-mira",
            kind="desk",
            label="Mira QA Workstation",
            floor=1,
            grid_x=3,
            grid_y=9,
            color="#eab308",
            assigned_agent_id="mira",
        ),
        FurnitureItem(
            id="desk-sentinel",
            kind="desk",
            label="Sentinel Security Station",
            floor=1,
            grid_x=6,
            grid_y=9,
            color="#a855f7",
            assigned_agent_id="sentinel",
        ),
        FurnitureItem(
            id="desk-rogelio",
            kind="desk",
            label="Rogelio HR & Ops Cubicle",
            floor=1,
            grid_x=10,
            grid_y=3,
            color="#22d3ee",
            assigned_agent_id="rogelio",
        ),
        # Special Office Landmarks from the Screenshot
        FurnitureItem(
            id="flag-ph",
            kind="ph_flag",
            label="Philippine Flag 🇵🇭",
            floor=1,
            grid_x=1,
            grid_y=5,
            color="#fbbf24",
        ),
        FurnitureItem(
            id="server-minilm-1",
            kind="server_rack",
            label="MiniLM & RTX 4060 Server Rack A",
            floor=1,
            grid_x=1,
            grid_y=7,
            color="#10b981",
        ),
        FurnitureItem(
            id="server-minilm-2",
            kind="server_rack",
            label="ECC 311-Skill Vault Rack B",
            floor=1,
            grid_x=1,
            grid_y=8,
            color="#06b6d4",
        ),
        FurnitureItem(
            id="water-cooler-1",
            kind="water_cooler",
            label="Teal Water Dispenser",
            floor=1,
            grid_x=2,
            grid_y=2,
            color="#14b8a6",
        ),
        FurnitureItem(
            id="war-table-1",
            kind="war_table",
            label="Hive War Room Round Table",
            floor=1,
            grid_x=5,
            grid_y=1,
            width=2,
            depth=2,
            color="#d97706",
        ),
        FurnitureItem(
            id="war-table-2",
            kind="war_table",
            label="Collaboration Round Table",
            floor=1,
            grid_x=13,
            grid_y=5,
            width=2,
            depth=2,
            color="#b45309",
        ),
        FurnitureItem(
            id="ping-pong-1",
            kind="ping_pong",
            label="Breakroom Ping-Pong Table",
            floor=1,
            grid_x=9,
            grid_y=11,
            width=2,
            depth=1,
            color="#10b981",
        ),
        FurnitureItem(
            id="sofa-lounge-1",
            kind="sofa",
            label="Break Lounge Couches",
            floor=1,
            grid_x=12,
            grid_y=8,
            width=2,
            depth=1,
            color="#6366f1",
        ),
        FurnitureItem(
            id="gym-treadmill-1",
            kind="treadmill",
            label="Agent Fitness Treadmill 1",
            floor=1,
            grid_x=15,
            grid_y=8,
            color="#64748b",
        ),
        FurnitureItem(
            id="gym-treadmill-2",
            kind="treadmill",
            label="Agent Fitness Treadmill 2",
            floor=1,
            grid_x=16,
            grid_y=8,
            color="#64748b",
        ),
        FurnitureItem(
            id="exec-suite-1",
            kind="server_rack",
            label="Private Exec Lab Terminal",
            floor=1,
            grid_x=15,
            grid_y=11,
            color="#3b82f6",
        ),
        FurnitureItem(
            id="plant-ramon-boss",
            kind="plant",
            label="Executive Monstera Plant",
            floor=1,
            grid_x=17,
            grid_y=1,
            color="#22c55e",
        ),
        FurnitureItem(
            id="plant-lobby-1",
            kind="plant",
            label="Office Ficus Plant",
            floor=1,
            grid_x=8,
            grid_y=6,
            color="#22c55e",
        ),
        FurnitureItem(
            id="chair-guest-ramon",
            kind="chair",
            label="Executive Visitor Chair",
            floor=1,
            grid_x=14,
            grid_y=3,
            color="#64748b",
        ),
        # =====================================================================
        # EDITABLE ROOM WALLS (Every wall can now be dragged, rotated, or deleted!)
        # 1. Ramon's Executive Boss Office Walls (x=13..18, y=0..4, Door at 13,3)
        # =====================================================================
        *[
            FurnitureItem(
                id=f"wall-boss-w-{gy}",
                kind="wall_ns",
                label="Executive Wall",
                floor=1,
                grid_x=13,
                grid_y=gy,
                color="#b45309",
            )
            for gy in (0, 1, 2, 4)
        ],
        *[
            FurnitureItem(
                id=f"wall-boss-s-{gx}",
                kind="wall_ew",
                label="Executive Wall",
                floor=1,
                grid_x=gx,
                grid_y=5,
                color="#b45309",
            )
            for gx in range(13, 19)
        ],
        # =====================================================================
        # 2. Rogelio's HR & Ops Cubicle Walls (x=9..11, y=2..4, Door at 10..11,4)
        # =====================================================================
        *[
            FurnitureItem(
                id=f"wall-hr-w-{gy}",
                kind="wall_ns",
                label="Cubicle Partition Wall",
                floor=1,
                grid_x=9,
                grid_y=gy,
                color="#9ca3af",
            )
            for gy in (2, 3, 4)
        ],
        *[
            FurnitureItem(
                id=f"wall-hr-n-{gx}",
                kind="wall_ew",
                label="Cubicle Partition Wall",
                floor=1,
                grid_x=gx,
                grid_y=2,
                color="#9ca3af",
            )
            for gx in (9, 10, 11)
        ],
        FurnitureItem(
            id="wall-hr-s-9",
            kind="wall_ew",
            label="Cubicle Partition Wall",
            floor=1,
            grid_x=9,
            grid_y=5,
            color="#9ca3af",
        ),
        # =====================================================================
        # 3. Gym & Server Suite Walls (x=13..18, y=7..12, Doors at 13,8 & 13,11)
        # =====================================================================
        *[
            FurnitureItem(
                id=f"wall-gym-n-{gx}",
                kind="wall_ew",
                label="Suite Wall",
                floor=1,
                grid_x=gx,
                grid_y=7,
                color="#94a3b8",
            )
            for gx in range(13, 19)
        ],
        *[
            FurnitureItem(
                id=f"wall-gym-mid-{gx}",
                kind="wall_ew",
                label="Suite Divider Wall",
                floor=1,
                grid_x=gx,
                grid_y=10,
                color="#94a3b8",
            )
            for gx in range(13, 19)
        ],
        *[
            FurnitureItem(
                id=f"wall-gym-w-{gy}",
                kind="wall_ns",
                label="Suite Wall",
                floor=1,
                grid_x=13,
                grid_y=gy,
                color="#94a3b8",
            )
            for gy in (7, 9, 10, 12)
        ],
    ]


def get_default_floor_tiles() -> dict[str, str]:
    """Return initial customizable floor tile map ('floor:gx,gy' -> tile_style)."""
    tiles: dict[str, str] = {}
    # Ramon's Boss Office: Royal Crimson Carpet
    for gx in range(13, 19):
        for gy in range(0, 5):
            tiles[f"1:{gx},{gy}"] = "crimson_boss"
    # Rogelio's HR Cubicle: Slate Grey Tile
    for gx in range(9, 12):
        for gy in range(2, 5):
            tiles[f"1:{gx},{gy}"] = "slate_cubicle"
    # Gym & Server Suite: Dark Carbon Floor
    for gx in range(13, 19):
        for gy in range(7, 14):
            tiles[f"1:{gx},{gy}"] = "dark_gym"
    # Doorway Accent Tiles
    for gx, gy in [(13, 3), (10, 4), (11, 4), (13, 8), (13, 11)]:
        tiles[f"1:{gx},{gy}"] = "gold_doorway"
    return tiles


def get_provider_health() -> dict[str, dict[str, object]]:
    """Inspect environment variables and local endpoints without exposing any secret values."""
    bootstrap_local_credentials()
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    has_github = bool(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
    has_groq = bool(os.environ.get("GROQ_API_KEY"))
    return {
        ProviderType.GEMINI_PRO.value: {
            "name": "Gemini Pro Suite (Argon / Opus 5.5 / Sonnet 5.5 / Flash)",
            "configured": has_gemini,
            "env_key_present": has_gemini,
            "source": CREDENTIAL_SOURCES.get("GEMINI_API_KEY", "Environment / In-App"),
            "models_count": 5,
            "cost": "$0.00 (Included)",
        },
        ProviderType.GITHUB_STUDENT.value: {
            "name": "GitHub Student Developer Pack (Copilot Pro / GitHub Models)",
            "configured": has_github,
            "env_key_present": has_github,
            "source": CREDENTIAL_SOURCES.get("GITHUB_TOKEN", "gh auth token CLI"),
            "models_count": 2,
            "cost": "$0.00 (Student Pack)",
        },
        ProviderType.GROQ.value: {
            "name": "Groq LPU High-Speed API (840 tok/s)",
            "configured": has_groq,
            "env_key_present": has_groq,
            "source": CREDENTIAL_SOURCES.get("GROQ_API_KEY", "Environment / In-App"),
            "models_count": 3,
            "cost": "$0.00 (Free Tier)",
        },
        ProviderType.OLLAMA_LOCAL.value: {
            "name": "Local RTX 4060 Ollama (qwen7b-rtx / qwen2.5-coder:7b & 14b)",
            "configured": True,
            "env_key_present": True,
            "source": "Local Daemon (127.0.0.1:11434)",
            "host": os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
            "models_count": 3,
            "cost": "$0.00 (100% Offline GPU)",
        },
    }


def utc_now_iso() -> str:
    """Return timezone-aware UTC ISO-8601 timestamp."""
    return datetime.now(UTC).isoformat()
