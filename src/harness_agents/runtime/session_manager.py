"""Central Session & Virtual Office State Manager."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from harness_agents.config import (
    AgentProfile,
    AgentStatus,
    FloorConfig,
    FurnitureItem,
    HarnessLevel,
    ProviderType,
    get_available_models,
    get_default_agents,
    get_default_floor_tiles,
    get_default_floors,
    get_default_furniture,
    get_provider_health,
    utc_now_iso,
)
from harness_agents.harness.ecc_loader import ECCArmoryLoader
from harness_agents.harness.injector import HarnessInjector
from harness_agents.harness.macros import MacroRunner
from harness_agents.memory.minilm_store import MiniLMMemoryStore
from harness_agents.orchestration.github_org import DEFAULT_GITHUB_ORG, GitHubOrgManager
from harness_agents.orchestration.kanban import KanbanBoard, KanbanStatus
from harness_agents.orchestration.message_bus import MessageBus
from harness_agents.providers.router import MultiModelRouter

BLOCKED_TOOL_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"format\s+[a-z]:",
    r"git\s+push\s+--force",
    r"del\s+/f\s+/s\s+/q\s+c:\\",
    r"drop\s+database",
]


class OfficeSessionManager:
    """Coordinates all virtual office agents, isometric coordinates, terminals, and 311 ECC skills."""

    def __init__(
        self,
        data_dir: Path | None = None,
        ecc_loader: ECCArmoryLoader | None = None,
    ) -> None:
        self.data_dir = data_dir or Path(
            "C:/Users/Legion/.gemini/antigravity/scratch/harness-agents/.harness_data"
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.ecc_loader = ecc_loader or ECCArmoryLoader()
        self.injector = HarnessInjector(self.ecc_loader)
        self.router = MultiModelRouter()
        self.memory = MiniLMMemoryStore(db_path=self.data_dir / "memory_minilm.db")
        self.message_bus = MessageBus(db_path=self.data_dir / "messages.db")
        self.kanban = KanbanBoard(db_path=self.data_dir / "kanban.db")
        self.github_org = GitHubOrgManager(org_name=DEFAULT_GITHUB_ORG)

        self.auto_mode: bool = True
        self.active_floor: int = 1
        self.floors: list[FloorConfig] = get_default_floors()
        self.furniture: list[FurnitureItem] = get_default_furniture()
        self.floor_tiles: dict[str, str] = get_default_floor_tiles()
        self.agents: dict[str, AgentProfile] = {a.id: a for a in get_default_agents()}

        self.terminal_logs: dict[str, list[str]] = {}
        self.traces: dict[str, list[dict[str, object]]] = {}
        self._event_listeners: list[Callable[[dict[str, object]], None]] = []
        self._watched_file_mtimes: dict[str, float] = {}

        for agent in self.agents.values():
            self.terminal_logs[agent.id] = self._build_welcome_banner(agent)
            self.traces[agent.id] = [
                {
                    "timestamp": utc_now_iso(),
                    "event": "session_init",
                    "detail": f"Initialized {agent.pty_id} ({agent.model_id}) with {len(agent.equipped_skills)} ECC skills.",
                }
            ]

    @staticmethod
    def _build_welcome_banner(agent: AgentProfile) -> list[str]:
        return [
            f"╭─ ⚡ Antigravity CLI • {agent.name.upper()} ({agent.model_id})",
            f"│ 📂 Workspace: {agent.workspace_path}",
            f"│ 🎒 Skills: {', '.join(agent.equipped_skills)}",
            "│ 💡 Ask me to build any app (e.g. 'build a python calculator')",
            "│    then click [<> IDE] or [📁 open] above to open the project!",
            "╰──────────────────────────────────────────────────────────────",
        ]

    def subscribe(self, callback: Callable[[dict[str, object]], None]) -> None:
        self._event_listeners.append(callback)

    def _emit(self, event_type: str, payload: dict[str, object]) -> None:
        packet = {"type": event_type, "timestamp": utc_now_iso(), "payload": payload}
        for cb in list(self._event_listeners):
            try:
                cb(packet)
            except (RuntimeError, ValueError, TypeError, OSError) as exc:
                self.traces.setdefault("system", []).append({"event": "listener_err", "detail": str(exc)})

    def is_command_blocked(self, agent: AgentProfile, prompt_or_cmd: str) -> bool:
        """Enforce block_tools safety guardrail on destructive operations."""
        for pattern in BLOCKED_TOOL_PATTERNS:
            if re.search(pattern, prompt_or_cmd, flags=re.IGNORECASE):
                return True
        return bool(
            agent.block_tools
            and any(
                kw in prompt_or_cmd.lower()
                for kw in ["rm ", "del ", "delete ", "drop ", "format ", "kill "]
            )
        )

    async def send_prompt(
        self,
        agent_id: str,
        prompt: str,
        is_steer: bool = False,
    ) -> dict[str, object]:
        """Dispatch a prompt or steering instruction to an agent and animate them in the office."""
        agent = self.agents.get(agent_id)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_id}")

        clean_prompt = prompt.strip()
        if not clean_prompt:
            return {"status": "ignored", "reason": "empty prompt"}

        # 1. Check Tool Block Guardrail
        if self.is_command_blocked(agent, clean_prompt):
            agent.status = AgentStatus.BLOCKED
            agent.speech_bubble = "Blocked by Safety Gate! 🚫"
            warn_line = f"\x1b[31m[BLOCK TOOLS GUARDRAIL]\x1b[0m Blocked destructive command: `{clean_prompt}`"
            self.terminal_logs[agent.id].append(warn_line)
            self._record_trace(agent.id, "tool_blocked", clean_prompt)
            self._emit("agent_updated", {"agent": agent.model_dump(), "log": warn_line})
            return {"status": "blocked", "agent": agent.model_dump(), "output": warn_line}

        # 2. Check Laya auto-skill recommendation and auto-equip any strongly matched ECC skill
        auto_skills = self.ecc_loader.auto_recommend_skills(clean_prompt, limit=2)
        for sk in auto_skills:
            if sk not in agent.equipped_skills and len(agent.equipped_skills) < 6:
                agent.equipped_skills.append(sk)

        # 3. Walk avatar to their assigned desk and set status to WORKING
        agent.target_x = float(agent.desk_x)
        agent.target_y = float(agent.desk_y)
        agent.current_x = float(agent.desk_x)
        agent.current_y = float(agent.desk_y)
        agent.status = AgentStatus.WORKING
        agent.collaborating_with = None
        prefix = "[STEER]" if is_steer else ">"
        agent.speech_bubble = "Steering..." if is_steer else f"Working: {clean_prompt[:16]}..."

        user_line = f"\n\x1b[33m{prefix} {clean_prompt}\x1b[0m"
        self.terminal_logs[agent.id].append(user_line)
        self._emit("agent_updated", {"agent": agent.model_dump(), "log": user_line})

        # 4. Recall relevant context from memory - minilm
        recalled = self.memory.recall(clean_prompt, limit=3)
        snippets = [str(item["content"]) for item in recalled]

        # 5. Assemble Harness Prompt (off | lite | full | ultra) + Real File Output Format
        sys_prompt = (
            self.injector.build_system_prompt(agent, memory_snippets=snippets)
            + "\n\nIMPORTANT CLI RULE: Never stop at just a plan or ask 'Do you approve this plan?'. "
            "Whenever the user asks to build, make, create, or plan an app, script, or project, "
            "write a brief 3-bullet plan AND immediately output the COMPLETE runnable code inside a fenced markdown "
            "code block (e.g. ```python ... ```) in the same reply."
        )

        effective_user_prompt = clean_prompt
        if self._extract_new_project_repo_slug(clean_prompt):
            effective_user_prompt = (
                f"{clean_prompt}\n\n"
                "[SYSTEM: Do NOT ask for plan approval. Provide a concise 3-bullet plan followed immediately by "
                "the complete, runnable source code in a fenced ```python (or appropriate language) code block.]"
            )

        # 6. Execute via MultiModelRouter
        gen = await self.router.generate(
            agent=agent,
            system_prompt=sys_prompt,
            user_prompt=effective_user_prompt,
        )

        # 6b. Materialize real project files to disk if code blocks or build intent are present!
        saved_summary = self._materialize_project_files(agent, clean_prompt, gen.text)
        full_cli_output = gen.text + (f"\n{saved_summary}" if saved_summary else "")

        # 7. Update Agent Telemetry & Memory
        agent.telemetry.tokens_in += gen.tokens_in
        agent.telemetry.tokens_out += gen.tokens_out
        agent.telemetry.turns += 1
        agent.telemetry.agent_time_sec = round(agent.telemetry.agent_time_sec + gen.elapsed_sec, 2)
        agent.telemetry.context_used_tokens = min(
            agent.telemetry.context_max_tokens,
            agent.telemetry.context_used_tokens + gen.tokens_in + gen.tokens_out,
        )
        agent.telemetry.tokens_per_sec = round(gen.tokens_out / max(0.05, gen.elapsed_sec), 1)

        self.terminal_logs[agent.id].append(full_cli_output)
        self.memory.remember(agent_id=agent.id, content=f"{clean_prompt} -> {gen.speech_summary}", topic=agent.department)
        self._record_trace(
            agent.id,
            "turn_completed",
            f"Model={gen.model_used} ({gen.provider_used}) +{gen.tokens_out} tok in {gen.elapsed_sec}s",
        )

        # 8. If Ramon (Hive Lead), silently record Hive coordination on the MessageBus without cluttering CLI
        if agent.is_hive_lead:
            for peer_id, track in (("ada", "UI track"), ("ken", "API track")):
                if peer_id in self.agents:
                    self.message_bus.send_message(
                        sender_id=agent.id,
                        recipient_id=peer_id,
                        content=f"[Hive Dispatch] Implement {track} for: {clean_prompt[:50]}",
                        channel="hive",
                    )

        # 8b. If prompt explicitly asks to push/create a GitHub repo, auto-create in JoeSecondBrainVault!
        repo_slug = self._extract_new_project_repo_slug(clean_prompt)
        if repo_slug and not agent.block_tools and "github" in clean_prompt.lower():
            vis = "public" if "public" in clean_prompt.lower() else "private"
            self.create_and_push_org_repo(
                repo_name=repo_slug,
                description=clean_prompt,
                agent_id=agent.id,
                visibility=vis,
                push_to_github=True,
            )

        # 9. Respect stop_after_step or return to IDLE
        agent.status = AgentStatus.IDLE
        agent.speech_bubble = gen.speech_summary

        # Process next queued prompt if stop_after_step is False
        if agent.prompt_queue and not agent.stop_after_step:
            next_queued = agent.prompt_queue.pop(0)
            await self.send_prompt(agent.id, next_queued)

        self._emit("agent_updated", {"agent": agent.model_dump(), "log": full_cli_output})
        return {
            "status": "ok",
            "agent": agent.model_dump(),
            "output": full_cli_output,
            "telemetry": agent.telemetry.model_dump(),
        }

    def enqueue_prompt(self, agent_id: str, prompt: str) -> AgentProfile:
        agent = self.agents[agent_id]
        agent.prompt_queue.append(prompt.strip())
        agent.speech_bubble = f"Queued ({len(agent.prompt_queue)})"
        self._record_trace(agent_id, "prompt_queued", prompt.strip())
        self._emit("agent_updated", {"agent": agent.model_dump()})
        return agent

    def send_1to1_message(
        self,
        sender_id: str,
        recipient_id: str,
        content: str,
        channel: str = "1:1",
    ) -> dict[str, object]:
        """Send a 1:1 or Hive note and physically walk the sender to the recipient's desk in the office."""
        msg = self.message_bus.send_message(
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=content,
            channel=channel,
        )
        sender = self.agents.get(sender_id)
        recipient = self.agents.get(recipient_id)

        if sender and recipient:
            if channel == "hive":
                # Keep both sender and recipient seated in their chairs at their computer desks!
                sender.target_x = float(sender.desk_x)
                sender.target_y = float(sender.desk_y)
                recipient.target_x = float(recipient.desk_x)
                recipient.target_y = float(recipient.desk_y)
            else:
                # For explicit 1:1 desk visit, walk to recipient's desk
                sender.target_x = float(max(1, recipient.desk_x - 1))
                sender.target_y = float(recipient.desk_y)
            sender.collaborating_with = recipient.id
            sender.speech_bubble = f"@{recipient.name}: {content[:18]}..."
            recipient.speech_bubble = f"Coding: {content[:16]}..."
            log_line = f"\x1b[35m[💬 {channel.upper()} {sender.name} -> {recipient.name}]\x1b[0m {content}"
            self.terminal_logs[sender.id].append(log_line)
            self.terminal_logs[recipient.id].append(log_line)
            self._record_trace(sender.id, f"msg_{channel}", f"To {recipient.name}: {content}")
        elif recipient:
            recipient.speech_bubble = f"Note: {content[:18]}..."
            log_line = f"\x1b[35m[💬 NOTE -> {recipient.name}]\x1b[0m {content}"
            self.terminal_logs[recipient.id].append(log_line)

        self._emit("message_sent", {"message": msg.model_dump()})
        return msg.model_dump()

    def equip_skill(self, agent_id: str, skill_id: str) -> AgentProfile:
        agent = self.agents[agent_id]
        if skill_id not in agent.equipped_skills:
            agent.equipped_skills.append(skill_id)
            agent.speech_bubble = f"+Skill: {skill_id}"
            log_line = f"\x1b[32m[ECC ARMORY]\x1b[0m Equipped skill cartridge `{skill_id}` on {agent.name}."
            self.terminal_logs[agent_id].append(log_line)
            self._record_trace(agent_id, "skill_equipped", skill_id)
            self._emit("agent_updated", {"agent": agent.model_dump(), "log": log_line})
        return agent

    def unequip_skill(self, agent_id: str, skill_id: str) -> AgentProfile:
        agent = self.agents[agent_id]
        if skill_id in agent.equipped_skills:
            agent.equipped_skills.remove(skill_id)
            log_line = f"\x1b[33m[ECC ARMORY]\x1b[0m Unequipped skill `{skill_id}` from {agent.name}."
            self.terminal_logs[agent_id].append(log_line)
            self._record_trace(agent_id, "skill_unequipped", skill_id)
            self._emit("agent_updated", {"agent": agent.model_dump(), "log": log_line})
        return agent

    def update_agent_settings(
        self,
        agent_id: str,
        model_id: str | None = None,
        provider: ProviderType | None = None,
        harness_level: HarnessLevel | None = None,
        block_tools: bool | None = None,
        stop_after_step: bool | None = None,
        floor: int | None = None,
        workspace_path: str | None = None,
        speech_bubble: str | None = None,
        target_x: float | None = None,
        target_y: float | None = None,
    ) -> AgentProfile:
        agent = self.agents[agent_id]
        if model_id is not None:
            agent.model_id = model_id
            # Match provider automatically from catalog if not explicitly provided
            if provider is None:
                for entry in get_available_models():
                    if entry.id == model_id:
                        agent.provider = entry.provider
                        break
            agent.speech_bubble = f"Model: {model_id}"
        if provider is not None:
            agent.provider = provider
        if harness_level is not None:
            agent.harness_level = harness_level
            agent.speech_bubble = f"Harness: {harness_level.value.upper()}"
        if block_tools is not None:
            agent.block_tools = block_tools
            agent.speech_bubble = "Tools Blocked 🚫" if block_tools else "Tools Unblocked ✓"
        if stop_after_step is not None:
            agent.stop_after_step = stop_after_step
        if floor is not None:
            agent.floor = floor
            agent.speech_bubble = f"Moved to Floor {floor}"
        if workspace_path is not None:
            agent.workspace_path = workspace_path
        if speech_bubble is not None:
            agent.speech_bubble = speech_bubble
        if target_x is not None and target_y is not None:
            agent.target_x = target_x
            agent.target_y = target_y
            agent.current_x = target_x
            agent.current_y = target_y

        self._record_trace(agent_id, "settings_updated", f"model={agent.model_id} harness={agent.harness_level.value}")
        self._emit("agent_updated", {"agent": agent.model_dump()})
        return agent

    def add_agent(
        self,
        name: str,
        role: str,
        department: str = "HarnessAgents",
        model_id: str = "gemini-3.8-flash",
        floor: int = 1,
        equipped_skills: list[str] | None = None,
    ) -> AgentProfile:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"agent-{len(self.agents) + 1}"
        if slug in self.agents:
            slug = f"{slug}-{secrets.token_hex(2)}"

        # Pick an unoccupied desk coordinate on the floor
        existing_on_floor = [a for a in self.agents.values() if a.floor == floor]
        idx = len(existing_on_floor)
        desk_x = 3 + (idx % 4) * 3
        desk_y = 3 + (idx // 4) * 3

        provider = ProviderType.GEMINI_PRO
        for entry in get_available_models():
            if entry.id == model_id:
                provider = entry.provider
                break

        palette = ["#10b981", "#f97316", "#6366f1", "#14b8a6", "#f43f5e", "#8b5cf6"]
        color = palette[idx % len(palette)]

        profile = AgentProfile(
            id=slug,
            name=name.lower(),
            display_title=f"{name.lower()} — {role.lower()}",
            role=role,
            department=department,
            workspace_path=str(Path("C:/Users/Legion/.gemini/antigravity/scratch").resolve()),
            floor=floor,
            desk_x=desk_x,
            desk_y=desk_y,
            current_x=float(desk_x),
            current_y=float(desk_y),
            target_x=float(desk_x),
            target_y=float(desk_y),
            avatar_color=color,
            shirt_color=color,
            star_color="#facc15",
            provider=provider,
            model_id=model_id,
            equipped_skills=equipped_skills or self.ecc_loader.auto_recommend_skills(role, limit=2),
            speech_bubble="Ready to work!",
            pty_id=f"pty-{slug}-{secrets.token_hex(3)}",
        )
        self.agents[profile.id] = profile
        self.terminal_logs[profile.id] = self._build_welcome_banner(profile)
        self.traces[profile.id] = [
            {
                "timestamp": utc_now_iso(),
                "event": "agent_spawned",
                "detail": f"Created {profile.name} on Floor {floor} at ({desk_x}, {desk_y}).",
            }
        ]
        # Add a desk for the new agent
        self.furniture.append(
            FurnitureItem(
                id=f"desk-{profile.id}",
                kind="desk",
                label=f"{profile.name.title()} Workstation",
                floor=floor,
                grid_x=desk_x,
                grid_y=desk_y,
                color=color,
                assigned_agent_id=profile.id,
            )
        )
        self._emit("agent_added", {"agent": profile.model_dump()})
        return profile

    def add_furniture(
        self,
        kind: str,
        label: str,
        floor: int,
        grid_x: int,
        grid_y: int,
        color: str = "#38bdf8",
        rotation: int = 0,
    ) -> FurnitureItem:
        item = FurnitureItem(
            id=f"item-{kind}-{secrets.token_hex(3)}",
            kind=kind,
            label=label,
            floor=floor,
            grid_x=grid_x,
            grid_y=grid_y,
            rotation=rotation % 4,
            color=color,
        )
        self.furniture.append(item)
        self._emit("furniture_added", {"item": item.model_dump()})
        return item

    def move_furniture(
        self,
        item_id: str,
        grid_x: int | None = None,
        grid_y: int | None = None,
        rotation: int | None = None,
        kind: str | None = None,
    ) -> FurnitureItem | None:
        for item in self.furniture:
            if item.id == item_id:
                if grid_x is not None:
                    item.grid_x = grid_x
                if grid_y is not None:
                    item.grid_y = grid_y
                if rotation is not None:
                    item.rotation = rotation % 4
                if kind is not None:
                    item.kind = kind
                # If this desk belongs to an agent, move the agent's assigned desk coordinates too!
                if item.assigned_agent_id and item.assigned_agent_id in self.agents:
                    ag = self.agents[item.assigned_agent_id]
                    ag.desk_x = item.grid_x
                    ag.desk_y = item.grid_y
                self._emit("furniture_moved", {"item": item.model_dump()})
                return item
        return None

    def rotate_furniture(self, item_id: str) -> FurnitureItem | None:
        for item in self.furniture:
            if item.id == item_id:
                if item.kind == "wall_ew":
                    item.kind = "wall_ns"
                elif item.kind == "wall_ns":
                    item.kind = "wall_ew"
                item.rotation = (item.rotation + 1) % 4
                self._emit("furniture_rotated", {"item": item.model_dump()})
                return item
        return None

    def set_floor_tile(self, floor: int, grid_x: int, grid_y: int, tile_style: str) -> str:
        key = f"{floor}:{grid_x},{grid_y}"
        if tile_style in ("wood", "default", ""):
            self.floor_tiles.pop(key, None)
        else:
            self.floor_tiles[key] = tile_style
        self._emit("floor_tile_updated", {"key": key, "style": tile_style})
        return tile_style

    def delete_furniture(self, item_id: str) -> bool:
        before = len(self.furniture)
        self.furniture = [f for f in self.furniture if f.id != item_id]
        deleted = len(self.furniture) < before
        if deleted:
            self._emit("furniture_deleted", {"id": item_id})
        return deleted

    def add_floor(self, name: str | None = None) -> FloorConfig:
        next_num = len(self.floors) + 1
        fl = FloorConfig(
            floor_number=next_num,
            name=name or f"Floor {next_num} — Expansion Lab",
            max_agents=15,
        )
        self.floors.append(fl)
        return fl

    def trigger_celebration(self, message: str = "SWELDO NA! 🎉") -> dict[str, object]:
        """Broadcast a celebration speech bubble across all agents on the active floor."""
        for agent in self.agents.values():
            agent.speech_bubble = message
        self._emit("celebration", {"message": message})
        return {"status": "ok", "message": message}

    def run_macro(self, agent_id: str, macro_name: str) -> dict[str, object]:
        agent = self.agents[agent_id]
        logs = self.terminal_logs.get(agent_id, [])
        res = MacroRunner.execute_macro(macro_name, agent, logs)

        if "terminal_output" in res:
            self.terminal_logs[agent_id].append(str(res["terminal_output"]))
        if "speech_bubble" in res:
            agent.speech_bubble = str(res["speech_bubble"])
        if macro_name.lower() == "board" and "tasks_created" in res:
            for title in res["tasks_created"]:  # type: ignore[union-attr]
                self.kanban.create_task(
                    title=str(title),
                    description=f"Auto-extracted from {agent.name} terminal via Board macro.",
                    assigned_agent_id=agent.id,
                    recommended_skills=agent.equipped_skills[:2],
                )

        self._record_trace(agent_id, f"macro_{macro_name}", str(res.get("summary", "")))
        self._emit("agent_updated", {"agent": agent.model_dump(), "macro_result": res})
        return res

    async def run_auto_kanban_tick(self) -> list[dict[str, object]]:
        """When Auto-Mode is ON, pull BACKLOG tasks and dispatch them to idle matching agents."""
        if not self.auto_mode:
            return []
        dispatched: list[dict[str, object]] = []
        tasks = self.kanban.list_tasks()
        for task in tasks:
            if task.status != KanbanStatus.BACKLOG:
                continue
            target_agent: AgentProfile | None = None
            if task.assigned_agent_id and task.assigned_agent_id in self.agents:
                cand = self.agents[task.assigned_agent_id]
                if cand.status == AgentStatus.IDLE:
                    target_agent = cand
            else:
                for cand in self.agents.values():
                    if cand.status == AgentStatus.IDLE:
                        target_agent = cand
                        break
            if target_agent:
                self.kanban.update_task(
                    task.id,
                    status=KanbanStatus.IN_PROGRESS,
                    assigned_agent_id=target_agent.id,
                )
                for sk in task.recommended_skills:
                    self.equip_skill(target_agent.id, sk)
                res = await self.send_prompt(
                    target_agent.id,
                    f"[Kanban #{task.id}] {task.title}: {task.description}",
                )
                self.kanban.update_task(task.id, status=KanbanStatus.DONE)
                dispatched.append({"task_id": task.id, "agent_id": target_agent.id, "result": res})
        return dispatched

    def _record_trace(self, agent_id: str, event: str, detail: str) -> None:
        self.traces.setdefault(agent_id, []).append(
            {
                "timestamp": utc_now_iso(),
                "event": event,
                "detail": detail,
            }
        )

    @staticmethod
    def _extract_new_project_repo_slug(prompt: str) -> str | None:
        """Detect 'create repo X', 'new project X', 'start a project for X', etc."""
        explicit = re.search(
            r"(?:create\s+repo|new\s+repo|github\s+repo|called|named)\s+([a-zA-Z0-9_-]{3,45})",
            prompt,
            flags=re.IGNORECASE,
        )
        if explicit:
            return explicit.group(1).lower()

        project_intent = re.search(
            r"(?:start|create|build|make|write)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:plan\s+for\s+it\s+i\s+want\s+you\s+to\s+build\s+a\s+)?(?:project|repo|repository|app|system|website|calculator|game|script|tool)?\s*(?:for\s+|about\s+|called\s+)?([a-zA-Z0-9\s_-]{3,45})",
            prompt,
            flags=re.IGNORECASE,
        )
        if project_intent:
            raw_words = re.findall(r"[a-z0-9]+", project_intent.group(0).lower())
            stop_words = {
                "a", "an", "the", "with", "using", "and", "in", "on", "to", "for", "that",
                "start", "create", "build", "make", "write", "new", "plan", "it", "i", "want", "you",
            }
            filtered = [w for w in raw_words if w not in stop_words][:4]
            if filtered:
                return "-".join(filtered)
        return None

    def _materialize_project_files(self, agent: AgentProfile, prompt: str, llm_output: str) -> str:
        """Extract code blocks from LLM response and save real runnable files into the project folder."""
        if agent.block_tools:
            return ""

        code_blocks = re.findall(
            r"(?:###\s*FILE:\s*([a-zA-Z0-9_./-]+)\s*\n)?```([a-zA-Z0-9_-]*)\n(.*?)(?:```|\Z)",
            llm_output,
            flags=re.DOTALL,
        )
        slug = self._extract_new_project_repo_slug(prompt)
        if not code_blocks and not slug:
            return ""

        projects_base = Path("C:/Users/Legion/.gemini/antigravity/scratch/projects").resolve()
        current_wp = Path(agent.workspace_path).resolve()
        if current_wp.parent == projects_base and current_wp != projects_base:
            project_dir = current_wp
            folder_slug = project_dir.name
        else:
            folder_slug = slug or "agent-workspace"
            project_dir = (projects_base / folder_slug).resolve()
        project_dir.mkdir(parents=True, exist_ok=True)

        # Point the agent (and squad) directly to this project folder so [<> IDE] & [📁 open] open it!
        agent.workspace_path = str(project_dir)
        for peer_id in ("ramon", "ada", "ken", "mira", "sentinel"):
            if peer_id in self.agents:
                self.agents[peer_id].workspace_path = str(project_dir)

        written_files: list[str] = []
        ext_map = {
            "python": "py",
            "py": "py",
            "javascript": "js",
            "js": "js",
            "typescript": "ts",
            "ts": "ts",
            "html": "html",
            "css": "css",
            "json": "json",
            "bash": "sh",
            "powershell": "ps1",
        }

        for idx, (explicit_name, lang, code_body) in enumerate(code_blocks):
            clean_code = code_body.strip()
            if not clean_code:
                continue
            if explicit_name:
                safe_name = Path(explicit_name.strip()).name
            else:
                ext = ext_map.get(lang.lower().strip(), "py")
                if "calculator" in folder_slug and idx == 0 and ext == "py":
                    safe_name = "calculator.py"
                elif ext == "html":
                    safe_name = "index.html"
                elif ext == "css":
                    safe_name = "styles.css"
                elif ext == "js":
                    safe_name = "app.js"
                else:
                    safe_name = f"main.{ext}" if idx == 0 else f"module_{idx + 1}.{ext}"

            file_path = project_dir / safe_name
            file_path.write_text(clean_code + "\n", encoding="utf-8")
            written_files.append(f"{safe_name} ({len(clean_code)} bytes)")

        # Always write a clean README.md with the full response/plan so the folder is self-contained
        readme_path = project_dir / "README.md"
        clean_ansi = re.sub(r"\x1b\[[0-9;]*m", "", llm_output)
        readme_path.write_text(
            f"# {folder_slug}\n\n> Generated by **{agent.name}** (`{agent.model_id}`)\n\n"
            f"## Prompt\n`{prompt}`\n\n## Agent Plan & Output\n\n{clean_ansi}\n",
            encoding="utf-8",
        )
        written_files.append("README.md")

        files_lines = "\n".join(f"│ ✔ Saved: \x1b[32m{f}\x1b[0m" for f in written_files)
        return (
            "\n\x1b[36m╭─ 📂 PROJECT SAVED TO DISK ─────────────────────────────────────────\x1b[0m\n"
            f"│ Folder: \x1b[33m{project_dir}\x1b[0m\n"
            f"{files_lines}\n"
            "│ 💡 Click \x1b[36m[<> IDE]\x1b[0m above to open in Antigravity/VS Code or \x1b[36m[📁 open]\x1b[0m for File Explorer!\n"
            "\x1b[36m╰────────────────────────────────────────────────────────────────────\x1b[0m"
        )

    def list_project_files(self, agent_id: str) -> dict[str, object]:
        """List and read source files inside the agent's current workspace folder for the In-Browser IDE."""
        agent = self.agents.get(agent_id) or next(iter(self.agents.values()))
        target_dir = Path(agent.workspace_path)
        target_dir.mkdir(parents=True, exist_ok=True)

        files_out: list[dict[str, object]] = []
        allowed_exts = {".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".txt", ".sh", ".ps1", ".bat", ".yaml", ".yml"}
        for p in sorted(target_dir.iterdir(), key=lambda x: (x.name == "README.md", x.name.lower())):
            if p.is_file() and (p.suffix.lower() in allowed_exts or p.stat().st_size < 120_000):
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    files_out.append(
                        {
                            "name": p.name,
                            "path": str(p),
                            "size": p.stat().st_size,
                            "content": content,
                        }
                    )
                except OSError:
                    continue
        return {"workspace_path": str(target_dir), "files": files_out}

    def save_project_file(self, agent_id: str, filename: str, content: str) -> dict[str, object]:
        """Save an edited file from the In-Browser IDE directly into the agent's project folder."""
        agent = self.agents.get(agent_id) or next(iter(self.agents.values()))
        target_dir = Path(agent.workspace_path)
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename.strip()).name
        if not safe_name:
            raise ValueError("Invalid filename")
        dest = (target_dir / safe_name).resolve()
        dest.write_text(content, encoding="utf-8")
        log_msg = f"\x1b[32m[<> IDE SAVE]\x1b[0m Saved `{dest}` ({len(content)} bytes)"
        self.terminal_logs[agent.id].append(log_msg)
        return {"saved": True, "path": str(dest), "size": len(content)}

    def run_project_file(self, agent_id: str, filename: str, stdin_text: str = "") -> dict[str, object]:
        """Execute a Python or script file inside the agent's project folder and return stdout/stderr."""
        agent = self.agents.get(agent_id) or next(iter(self.agents.values()))
        target_dir = Path(agent.workspace_path)
        safe_name = Path(filename.strip()).name
        script_path = (target_dir / safe_name).resolve()
        if not script_path.exists():
            return {"exit_code": 1, "output": f"File not found: {script_path}"}

        py_exe = str(Path("C:/Users/Legion/.gemini/antigravity/scratch/harness-agents/.venv/Scripts/python.exe"))
        if not os.path.exists(py_exe):
            py_exe = shutil.which("python") or "python"

        # Provide sample non-blocking stdin if interactive input() is used and no stdin_text was passed
        effective_stdin = stdin_text if stdin_text else "2 + 2\n10 * 5\nquit\n"
        try:
            proc = subprocess.run(
                [py_exe, str(script_path)],
                cwd=str(target_dir),
                input=effective_stdin,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            combined = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
            output = combined.strip() or "(Process exited with 0 and no stdout output)"
            code = proc.returncode
        except subprocess.TimeoutExpired:
            output = "Execution timed out after 8s (interactive loop waiting for input)."
            code = 124
        except OSError as exc:
            output = f"Execution error: {exc}"
            code = 1

        self.terminal_logs[agent.id].append(
            f"\x1b[36m[▶ RUN {safe_name}]\x1b[0m (exit {code})\n{output[:600]}"
        )
        return {"exit_code": code, "output": output, "path": str(script_path)}

    def open_agent_ide(self, agent_id: str) -> dict[str, object]:
        """Launch Desktop IDE (`Antigravity` / `VS Code`) in the foreground AND return project files for the In-Browser IDE."""
        agent = self.agents.get(agent_id)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_id}")
        target_dir = Path(agent.workspace_path)
        target_dir.mkdir(parents=True, exist_ok=True)

        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity\Antigravity.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity\bin\agy.cmd"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd"),
            shutil.which("agy"),
            shutil.which("antigravity"),
            shutil.which("code"),
        ]
        ide_bin = next((c for c in candidates if c and os.path.exists(c)), None)
        launched = "in-browser-ide"
        try:
            if ide_bin:
                cmd_bin = shutil.which("cmd.exe") or "cmd.exe"
                subprocess.Popen([cmd_bin, "/c", "start", "", ide_bin, str(target_dir)], shell=False)
                launched = Path(ide_bin).stem
        except OSError:
            launched = "in-browser-ide"

        files_payload = self.list_project_files(agent_id)
        log_msg = f"\x1b[36m[<> IDE]\x1b[0m Opened `{target_dir}` ({len(files_payload['files'])} files)"
        self.terminal_logs[agent.id].append(log_msg)
        return {
            "opened": True,
            "path": str(target_dir),
            "launcher": launched,
            "files": files_payload["files"],
        }

    def open_agent_folder(self, agent_id: str) -> dict[str, object]:
        """Open Windows File Explorer in the foreground at the agent's workspace path."""
        agent = self.agents.get(agent_id)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_id}")
        target_dir = Path(agent.workspace_path)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Native Win32 ShellExecuteW brings File Explorer to the foreground on Windows
        opened_native = False
        if hasattr(os, "startfile"):
            try:
                os.startfile(str(target_dir))  # type: ignore[attr-defined]
                opened_native = True
            except OSError:
                opened_native = False
        if not opened_native:
            cmd_bin = shutil.which("cmd.exe") or "cmd.exe"
            subprocess.Popen([cmd_bin, "/c", "start", "", "explorer.exe", str(target_dir)], shell=False)

        log_msg = f"\x1b[36m[📁 OPEN]\x1b[0m Opened folder `{target_dir}` in Windows File Explorer"
        self.terminal_logs[agent.id].append(log_msg)
        return {"opened": True, "path": str(target_dir)}

    def hr_recommend_skills(
        self,
        project_description: str,
        target_agent_id: str = "ramon",
        auto_equip_squad: bool = False,
    ) -> dict[str, object]:
        """Have Rogelio (HR & Recruitment) recommend the best ECC skills and a specialist agent to hire."""
        desc = project_description.strip() or "Full-stack software application with automated tests and security audit"
        top_skill_ids = self.ecc_loader.auto_recommend_skills(desc, limit=5)

        skill_details: list[dict[str, str]] = []
        for sid in top_skill_ids:
            entry = self.ecc_loader.get_skill(sid)
            if entry:
                skill_details.append(
                    {
                        "id": entry.id,
                        "name": entry.name,
                        "category": entry.category,
                        "description": entry.description,
                    }
                )
            else:
                skill_details.append(
                    {
                        "id": sid,
                        "name": sid,
                        "category": "Engineering",
                        "description": "Specialized ECC workflow cartridge.",
                    }
                )

        # Determine a tailored new specialist agent suggestion from the project description
        lower = desc.lower()
        if any(w in lower for w in ("ui", "frontend", "react", "next", "css", "html", "web", "design")):
            sug_name = "elena"
            sug_role = "Frontend & Interactive UI Specialist"
            sug_model = "qwen/qwen-2.5-coder-32b-instruct:free"
        elif any(w in lower for w in ("mobile", "android", "ios", "expo", "flutter", "game")):
            sug_name = "marco"
            sug_role = "Mobile & Cross-Platform App Engineer"
            sug_model = "gemini-3.8-flash"
        elif any(w in lower for w in ("security", "auth", "audit", "pentest", "crypto")):
            sug_name = "viktor"
            sug_role = "Application Security & OWASP Auditor"
            sug_model = "deepseek-r1-distill-llama-70b"
        elif any(w in lower for w in ("data", "ml", "ai", "analytics", "sql", "database", "bigquery")):
            sug_name = "sophia"
            sug_role = "Data Engineering & AI Pipeline Specialist"
            sug_model = "gemini-4-argon"
        else:
            sug_name = "carlo"
            sug_role = "Python & Full-Stack Automation Specialist"
            sug_model = "llama-3.3-70b-versatile"

        equipped_agents: list[str] = []
        if auto_equip_squad:
            target_ag = self.agents.get(target_agent_id)
            if target_ag:
                for sid in top_skill_ids[:4]:
                    if sid not in target_ag.equipped_skills:
                        target_ag.equipped_skills.append(sid)
                equipped_agents.append(target_ag.name)
            for aid in ("ramon", "ada", "ken", "mira", "sentinel"):
                ag = self.agents.get(aid)
                if ag:
                    role_picks = self.ecc_loader.auto_recommend_skills(f"{desc} {ag.role}", limit=3)
                    for sid in role_picks:
                        if sid not in ag.equipped_skills and len(ag.equipped_skills) < 6:
                            ag.equipped_skills.append(sid)
                    if ag.name not in equipped_agents:
                        equipped_agents.append(ag.name)

            rogelio = self.agents.get("rogelio")
            if rogelio:
                rogelio.speech_bubble = f"Equipped {len(top_skill_ids)} skills! 🧑‍💼"
            if target_ag:
                hr_box = (
                    "\n\x1b[35m╭─ 🧑‍💼 ROGELIO (HR & SKILL ADVISOR) ─────────────────────────────────\x1b[0m\n"
                    f"│ Goal: \x1b[33m{desc[:65]}\x1b[0m\n"
                    f"│ Auto-Equipped Skills on {target_ag.name}: \x1b[32m{', '.join(top_skill_ids[:4])}\x1b[0m\n"
                    f"│ Squad Synced: {', '.join(equipped_agents)}\n"
                    "\x1b[35m╰────────────────────────────────────────────────────────────────────\x1b[0m"
                )
                self.terminal_logs[target_ag.id].append(hr_box)
            self._emit("hr_equipped", {"skills": top_skill_ids, "agents": equipped_agents})

        return {
            "project_description": desc,
            "recommended_skills": skill_details,
            "auto_equipped_agents": equipped_agents,
            "suggested_agent": {
                "name": sug_name,
                "role": sug_role,
                "department": "Projects",
                "model_id": sug_model,
                "skills": top_skill_ids[:4],
            },
        }

    def start_new_project(
        self,
        project_name: str,
        description: str = "",
        auto_equip_hr: bool = True,
    ) -> dict[str, object]:
        """1-Click New Project: create a clean folder in scratch/projects, reset CLI logs, and auto-equip via HR."""
        slug = re.sub(r"[^a-z0-9-]+", "-", project_name.lower()).strip("-") or f"project-{secrets.token_hex(2)}"
        projects_base = Path("C:/Users/Legion/.gemini/antigravity/scratch/projects")
        project_dir = (projects_base / slug).resolve()
        project_dir.mkdir(parents=True, exist_ok=True)

        readme_path = project_dir / "README.md"
        if not readme_path.exists():
            readme_path.write_text(
                f"# {slug}\n\n> Created in DevLabs • HarnessAgents\n\n## Project Goal\n{description or project_name}\n",
                encoding="utf-8",
            )

        hr_result = self.hr_recommend_skills(
            project_description=f"{project_name} {description}".strip(),
            target_agent_id="ramon",
            auto_equip_squad=auto_equip_hr,
        )
        rec_ids = [s["id"] for s in hr_result["recommended_skills"]]  # type: ignore[index]

        for ag in self.agents.values():
            ag.workspace_path = str(project_dir)
            ag.department = slug
            ag.status = AgentStatus.IDLE
            ag.speech_bubble = f"New Project: {slug} 🚀"
            self.terminal_logs[ag.id] = [
                f"\x1b[36m╭─ 🚀 NEW PROJECT INITIALIZED: {slug.upper()} ─────────────────────────\x1b[0m",
                f"│ 📂 Folder: \x1b[33m{project_dir}\x1b[0m",
                f"│ 🎯 Goal: {description or project_name}",
                f"│ 🧑‍💼 Rogelio (HR) Auto-Equipped Skills: \x1b[32m{', '.join(rec_ids[:4])}\x1b[0m",
                "│ 💡 Type your prompt below to start building, or click [<> IDE] / [📁 open] above!",
                "\x1b[36m╰────────────────────────────────────────────────────────────────────\x1b[0m",
            ]

        self._emit("new_project_started", {"project_dir": str(project_dir), "slug": slug, "hr": hr_result})
        return {
            "status": "ok",
            "project_slug": slug,
            "workspace_path": str(project_dir),
            "hr_recommendations": hr_result,
        }

    def create_and_push_org_repo(
        self,
        repo_name: str,
        description: str = "",
        agent_id: str = "ramon",
        visibility: str = "private",
        push_to_github: bool = True,
    ) -> dict[str, object]:
        """Scaffold a real project workspace and create/push the repo to JoeSecondBrainVault."""
        agent = self.agents.get(agent_id) or next(iter(self.agents.values()))
        if agent.block_tools:
            raise PermissionError(f"Agent {agent.name} has block_tools enabled.")

        res = self.github_org.scaffold_and_push_repo(
            repo_name=repo_name,
            task_description=description or f"Multi-agent project built by {agent.name}",
            agent_name=agent.name,
            visibility=visibility,
            push_to_github=push_to_github,
        )

        # Update squad workspace path to point at the newly created repo
        for peer_id in ("ramon", "ada", "ken", "mira", "sentinel"):
            if peer_id in self.agents:
                self.agents[peer_id].workspace_path = res.local_path
                self.agents[peer_id].department = f"{res.org}/{res.repo_name}"
                self.terminal_logs[peer_id].append(res.terminal_log)

        agent.speech_bubble = f"Pushed {res.repo_name}! 🐙"
        self._record_trace(agent.id, "github_repo_created", f"{res.repo_url} ({res.status})")
        self._emit("repo_created", res.model_dump())
        return res.model_dump()

    @staticmethod
    def _route_file_or_task_to_agent_id(text_or_path: str) -> str:
        """Map a filename or task description from Antigravity to the matching AI teammate."""
        lower = text_or_path.lower()
        if any(w in lower for w in ("test_", "_test.", ".spec.", "pytest", "vitest", "qa", "test")):
            return "mira"
        if any(w in lower for w in (".gitignore", "security", "audit", "owasp", "secret", "bandit")):
            return "sentinel"
        if any(w in lower for w in (".html", ".css", ".js", ".jsx", ".ts", ".tsx", "ui", "frontend", "react", "canvas")):
            return "ada"
        if any(w in lower for w in (".py", ".sql", ".db", ".json", "api", "backend", "server", "route")):
            return "ken"
        if any(w in lower for w in ("skill", "hire", "recruit", "hr")):
            return "rogelio"
        return "ramon"

    def bridge_dispatch_from_antigravity(
        self,
        task_title: str,
        details: str = "",
        agent_id: str | None = None,
        file_path: str | None = None,
        status: str = "working",
        create_kanban_card: bool = True,
    ) -> dict[str, object]:
        """Receive a live task or file event directly from the Antigravity App and animate the AI team."""
        chosen_id = agent_id if (agent_id and agent_id in self.agents) else self._route_file_or_task_to_agent_id(file_path or task_title)
        agent = self.agents.get(chosen_id) or self.agents["ramon"]

        # Seat the agent at their computer desk and set working status
        agent.target_x = float(agent.desk_x)
        agent.target_y = float(agent.desk_y)
        agent.current_x = float(agent.desk_x)
        agent.current_y = float(agent.desk_y)
        agent.status = AgentStatus.IDLE if status.lower() in ("idle", "done", "completed") else AgentStatus.WORKING
        agent.speech_bubble = f"⚡ {task_title[:22]}"

        if file_path:
            p = Path(file_path)
            if p.is_absolute() and p.exists():
                target_dir = p.parent if p.is_file() else p
                for peer in self.agents.values():
                    peer.workspace_path = str(target_dir.resolve())

        log_block = (
            "\n\x1b[36m╭─ ⚡ ANTIGRAVITY LIVE BRIDGE -> "
            f"{agent.name.upper()} ({agent.role}) ────────────────\x1b[0m\n"
            f"│ 🎯 Task  : \x1b[33m{task_title}\x1b[0m\n"
            + (f"│ 📄 File  : \x1b[32m{file_path}\x1b[0m\n" if file_path else "")
            + (f"│ 📝 Detail: {details}\n" if details else "")
            + f"│ 🔄 Status: {agent.status.value.upper()}\n"
            "\x1b[36m╰────────────────────────────────────────────────────────────────────\x1b[0m"
        )
        self.terminal_logs[agent.id].append(log_block)
        if agent.id != "ramon" and "ramon" in self.agents:
            self.terminal_logs["ramon"].append(
                f"\x1b[36m[⚡ ANTIGRAVITY -> {agent.name.upper()}]\x1b[0m {task_title}"
                + (f" (`{Path(file_path).name}`)" if file_path else "")
            )

        agent.telemetry.turns += 1
        agent.telemetry.tokens_out += max(40, len(details or task_title) // 3)
        self._record_trace(agent.id, "antigravity_bridge", f"{task_title} ({file_path or 'direct'})")

        kanban_task_dict: dict[str, object] | None = None
        if create_kanban_card:
            rec_skills = self.ecc_loader.auto_recommend_skills(f"{task_title} {details}", limit=2)
            for sk in rec_skills:
                if sk not in agent.equipped_skills and len(agent.equipped_skills) < 6:
                    agent.equipped_skills.append(sk)
            kt = self.kanban.create_task(
                title=f"[Antigravity] {task_title[:65]}",
                description=details or f"Dispatched live from Antigravity to {agent.name}",
                assigned_agent_id=agent.id,
                recommended_skills=rec_skills,
                priority="high",
            )
            if status.lower() in ("done", "completed"):
                self.kanban.update_task(kt.id, status=KanbanStatus.DONE)
            else:
                self.kanban.update_task(kt.id, status=KanbanStatus.IN_PROGRESS)
            kanban_task_dict = kt.model_dump()

        self._emit(
            "bridge_activity",
            {
                "agent_id": agent.id,
                "agent": agent.model_dump(),
                "task_title": task_title,
                "file_path": file_path,
                "log": log_block,
            },
        )
        return {
            "status": "ok",
            "routed_to": agent.id,
            "agent_name": agent.name,
            "agent_role": agent.role,
            "workspace_path": agent.workspace_path,
            "kanban_task": kanban_task_dict,
        }

    def scan_antigravity_workspace_changes(self) -> list[dict[str, object]]:
        """Detect file creates/saves inside the active project workspace from Antigravity IDE and animate the matching specialist."""
        ramon = self.agents.get("ramon")
        if not ramon:
            return []
        target_dir = Path(ramon.workspace_path)
        if not target_dir.exists() or not target_dir.is_dir():
            return []

        events: list[dict[str, object]] = []
        first_scan = len(self._watched_file_mtimes) == 0
        allowed_exts = {".py", ".js", ".ts", ".tsx", ".html", ".css", ".json", ".md", ".sql", ".sh", ".ps1"}

        for p in target_dir.rglob("*"):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(target_dir).parts
            if any((part.startswith(".") and part != ".gitignore") or part in ("__pycache__", "node_modules", ".venv") for part in rel_parts):
                continue
            if p.suffix.lower() not in allowed_exts and p.name != ".gitignore":
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue

            key = str(p.resolve())
            prev_mtime = self._watched_file_mtimes.get(key)
            self._watched_file_mtimes[key] = mtime

            if not first_scan and (prev_mtime is None or mtime > prev_mtime + 0.05):
                action = "Created" if prev_mtime is None else "Updated"
                ev = self.bridge_dispatch_from_antigravity(
                    task_title=f"{action} {p.name} in Antigravity",
                    details=f"File `{p.name}` ({p.stat().st_size} bytes) synced from Antigravity IDE.",
                    file_path=key,
                    status="working",
                    create_kanban_card=False,
                )
                events.append(ev)
        return events

    def full_state_snapshot(self) -> dict[str, object]:
        return {
            "version": "2.0.0",
            "github_org": self.github_org.org_name,
            "github_org_url": f"https://github.com/{self.github_org.org_name}",
            "auto_mode": self.auto_mode,
            "active_floor": self.active_floor,
            "floors": [f.model_dump() for f in self.floors],
            "furniture": [item.model_dump() for item in self.furniture],
            "floor_tiles": self.floor_tiles,
            "agents": [a.model_dump() for a in self.agents.values()],
            "models": [m.model_dump() for m in get_available_models()],
            "provider_health": get_provider_health(),
            "ecc_stats": self.ecc_loader.stats(),
            "memory_count": self.memory.count(),
            "kanban": [t.model_dump() for t in self.kanban.list_tasks()],
            "recent_messages": self.message_bus.list_messages(limit=30),
        }
