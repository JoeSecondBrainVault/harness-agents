"""FastAPI REST & WebSocket server powering the Isometric 2.5D Virtual Office & Inspector UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from harness_agents.config import HarnessLevel, ProviderType
from harness_agents.harness.macros import MacroRunner
from harness_agents.orchestration.kanban import KanbanStatus
from harness_agents.runtime.session_manager import OfficeSessionManager


class PromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    is_steer: bool = False
    queue_only: bool = False


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sender_id: str
    recipient_id: str
    content: str
    channel: str = "1:1"


class SkillToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str


class AgentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str | None = None
    provider: ProviderType | None = None
    harness_level: HarnessLevel | None = None
    block_tools: bool | None = None
    stop_after_step: bool | None = None
    floor: int | None = None
    workspace_path: str | None = None
    speech_bubble: str | None = None
    target_x: float | None = None
    target_y: float | None = None


class CreateAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: str
    department: str = "HarnessAgents"
    model_id: str = "gemini-3.8-flash"
    floor: int = 1
    equipped_skills: list[str] | None = None


class CreateFurnitureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    label: str
    floor: int = 1
    grid_x: int = 8
    grid_y: int = 8
    rotation: int = 0
    color: str = "#38bdf8"


class MoveFurnitureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_x: int | None = None
    grid_y: int | None = None
    rotation: int | None = None
    kind: str | None = None


class PaintFloorTileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    floor: int = 1
    grid_x: int
    grid_y: int
    tile_style: str


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str = ""
    assigned_agent_id: str | None = None
    priority: str = "medium"


class UpdateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: KanbanStatus | None = None
    assigned_agent_id: str | None = None


class CreateGitHubRepoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repo_name: str
    description: str = ""
    agent_id: str = "ramon"
    visibility: str = "private"
    push_to_github: bool = True


def create_app(manager: OfficeSessionManager | None = None) -> FastAPI:
    app = FastAPI(
        title="HarnessAgents Virtual Office & Multi-Agent Orchestrator",
        version="2.0.0",
    )
    session_mgr = manager or OfficeSessionManager()
    app.state.manager = session_mgr

    ui_dir = Path(__file__).resolve().parent.parent / "ui"
    if ui_dir.exists():
        app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def serve_index() -> FileResponse:
        index_file = ui_dir / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=404, detail="UI index.html not found")
        return FileResponse(index_file)

    @app.get("/api/state")
    async def get_state() -> dict[str, object]:
        return session_mgr.full_state_snapshot()

    @app.post("/api/auto-mode")
    async def toggle_auto_mode() -> dict[str, object]:
        session_mgr.auto_mode = not session_mgr.auto_mode
        dispatched = []
        if session_mgr.auto_mode:
            dispatched = await session_mgr.run_auto_kanban_tick()
        return {"auto_mode": session_mgr.auto_mode, "dispatched": dispatched}

    @app.post("/api/celebrate")
    async def celebrate(message: str = "SWELDO NA! 🎉") -> dict[str, object]:
        return session_mgr.trigger_celebration(message=message)

    @app.get("/api/agents/{agent_id}/inspector")
    async def get_agent_inspector(agent_id: str) -> dict[str, object]:
        agent = session_mgr.agents.get(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        git_info = MacroRunner.run_git_status_and_diff(agent.workspace_path)
        return {
            "agent": agent.model_dump(),
            "terminal_logs": session_mgr.terminal_logs.get(agent_id, [])[-100:],
            "git_info": git_info,
            "messages": session_mgr.message_bus.list_messages(agent_id=agent_id, limit=40),
            "traces": session_mgr.traces.get(agent_id, [])[-50:],
        }

    @app.post("/api/agents")
    async def create_agent(req: CreateAgentRequest) -> dict[str, object]:
        created = session_mgr.add_agent(
            name=req.name,
            role=req.role,
            department=req.department,
            model_id=req.model_id,
            floor=req.floor,
            equipped_skills=req.equipped_skills,
        )
        return {"agent": created.model_dump()}

    @app.patch("/api/agents/{agent_id}")
    async def update_agent(agent_id: str, req: AgentUpdateRequest) -> dict[str, object]:
        if agent_id not in session_mgr.agents:
            raise HTTPException(status_code=404, detail="Agent not found")
        updated = session_mgr.update_agent_settings(
            agent_id=agent_id,
            model_id=req.model_id,
            provider=req.provider,
            harness_level=req.harness_level,
            block_tools=req.block_tools,
            stop_after_step=req.stop_after_step,
            floor=req.floor,
            workspace_path=req.workspace_path,
            speech_bubble=req.speech_bubble,
            target_x=req.target_x,
            target_y=req.target_y,
        )
        return {"agent": updated.model_dump()}

    @app.post("/api/agents/{agent_id}/prompt")
    async def send_agent_prompt(agent_id: str, req: PromptRequest) -> dict[str, object]:
        if agent_id not in session_mgr.agents:
            raise HTTPException(status_code=404, detail="Agent not found")
        if req.queue_only:
            updated = session_mgr.enqueue_prompt(agent_id, req.prompt)
            return {"status": "queued", "agent": updated.model_dump()}
        return await session_mgr.send_prompt(
            agent_id=agent_id,
            prompt=req.prompt,
            is_steer=req.is_steer,
        )

    @app.post("/api/agents/{agent_id}/skills/equip")
    async def equip_agent_skill(agent_id: str, req: SkillToggleRequest) -> dict[str, object]:
        if agent_id not in session_mgr.agents:
            raise HTTPException(status_code=404, detail="Agent not found")
        updated = session_mgr.equip_skill(agent_id, req.skill_id)
        return {"agent": updated.model_dump()}

    @app.post("/api/agents/{agent_id}/skills/unequip")
    async def unequip_agent_skill(agent_id: str, req: SkillToggleRequest) -> dict[str, object]:
        if agent_id not in session_mgr.agents:
            raise HTTPException(status_code=404, detail="Agent not found")
        updated = session_mgr.unequip_skill(agent_id, req.skill_id)
        return {"agent": updated.model_dump()}

    @app.post("/api/agents/{agent_id}/macros/{macro_name}")
    async def run_agent_macro(agent_id: str, macro_name: str) -> dict[str, object]:
        if agent_id not in session_mgr.agents:
            raise HTTPException(status_code=404, detail="Agent not found")
        return session_mgr.run_macro(agent_id, macro_name)

    @app.post("/api/agents/{agent_id}/open-ide")
    async def open_agent_ide_route(agent_id: str) -> dict[str, object]:
        if agent_id not in session_mgr.agents:
            raise HTTPException(status_code=404, detail="Agent not found")
        return session_mgr.open_agent_ide(agent_id)

    @app.post("/api/agents/{agent_id}/open-folder")
    async def open_agent_folder_route(agent_id: str) -> dict[str, object]:
        if agent_id not in session_mgr.agents:
            raise HTTPException(status_code=404, detail="Agent not found")
        return session_mgr.open_agent_folder(agent_id)

    @app.post("/api/messages")
    async def post_message(req: MessageRequest) -> dict[str, object]:
        return session_mgr.send_1to1_message(
            sender_id=req.sender_id,
            recipient_id=req.recipient_id,
            content=req.content,
            channel=req.channel,
        )

    @app.get("/api/skills")
    async def list_ecc_skills(
        q: str | None = None, category: str | None = None
    ) -> dict[str, object]:
        skills = session_mgr.ecc_loader.list_skills(query=q, category=category)
        subagents = session_mgr.ecc_loader.list_subagents()
        return {
            "stats": session_mgr.ecc_loader.stats(),
            "skills": [s.model_dump() for s in skills],
            "subagents": [sa.model_dump() for sa in subagents],
        }

    @app.get("/api/kanban")
    async def get_kanban() -> dict[str, object]:
        return {"tasks": [t.model_dump() for t in session_mgr.kanban.list_tasks()]}

    @app.post("/api/kanban")
    async def create_kanban_task(req: CreateTaskRequest) -> dict[str, object]:
        skills = session_mgr.ecc_loader.auto_recommend_skills(f"{req.title} {req.description}", limit=2)
        task = session_mgr.kanban.create_task(
            title=req.title,
            description=req.description,
            assigned_agent_id=req.assigned_agent_id,
            recommended_skills=skills,
            priority=req.priority,
        )
        return {"task": task.model_dump()}

    @app.patch("/api/kanban/{task_id}")
    async def update_kanban_task(task_id: int, req: UpdateTaskRequest) -> dict[str, object]:
        updated = session_mgr.kanban.update_task(
            task_id=task_id,
            status=req.status,
            assigned_agent_id=req.assigned_agent_id,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"task": updated.model_dump()}

    @app.post("/api/kanban/auto-dispatch")
    async def trigger_auto_dispatch() -> dict[str, object]:
        dispatched = await session_mgr.run_auto_kanban_tick()
        return {"dispatched": dispatched}

    @app.post("/api/furniture")
    async def add_office_furniture(req: CreateFurnitureRequest) -> dict[str, object]:
        item = session_mgr.add_furniture(
            kind=req.kind,
            label=req.label,
            floor=req.floor,
            grid_x=req.grid_x,
            grid_y=req.grid_y,
            color=req.color,
            rotation=req.rotation,
        )
        return {"item": item.model_dump()}

    @app.patch("/api/furniture/{item_id}")
    async def move_office_furniture(item_id: str, req: MoveFurnitureRequest) -> dict[str, object]:
        moved = session_mgr.move_furniture(
            item_id,
            grid_x=req.grid_x,
            grid_y=req.grid_y,
            rotation=req.rotation,
            kind=req.kind,
        )
        if not moved:
            raise HTTPException(status_code=404, detail="Furniture item not found")
        return {"item": moved.model_dump()}

    @app.post("/api/furniture/{item_id}/rotate")
    async def rotate_office_furniture(item_id: str) -> dict[str, object]:
        rotated = session_mgr.rotate_furniture(item_id)
        if not rotated:
            raise HTTPException(status_code=404, detail="Furniture item not found")
        return {"item": rotated.model_dump()}

    @app.delete("/api/furniture/{item_id}")
    async def delete_office_furniture(item_id: str) -> dict[str, object]:
        ok = session_mgr.delete_furniture(item_id)
        return {"deleted": ok, "id": item_id}

    @app.post("/api/floor-tiles")
    async def paint_floor_tile(req: PaintFloorTileRequest) -> dict[str, object]:
        style = session_mgr.set_floor_tile(
            floor=req.floor,
            grid_x=req.grid_x,
            grid_y=req.grid_y,
            tile_style=req.tile_style,
        )
        return {"floor": req.floor, "grid_x": req.grid_x, "grid_y": req.grid_y, "tile_style": style}

    @app.post("/api/floors")
    async def add_office_floor() -> dict[str, object]:
        fl = session_mgr.add_floor()
        return {"floor": fl.model_dump()}

    @app.get("/api/memory")
    async def search_memory(q: str = "architecture") -> dict[str, object]:
        return {
            "count": session_mgr.memory.count(),
            "results": session_mgr.memory.recall(q, limit=10),
        }

    @app.get("/api/github/repos")
    async def list_github_org_repos() -> dict[str, object]:
        return {
            "org": session_mgr.github_org.org_name,
            "org_url": f"https://github.com/{session_mgr.github_org.org_name}",
            "repos": session_mgr.github_org.list_org_repos(limit=25),
        }

    @app.post("/api/github/repos")
    async def create_github_org_repo(req: CreateGitHubRepoRequest) -> dict[str, object]:
        try:
            return session_mgr.create_and_push_org_repo(
                repo_name=req.repo_name,
                description=req.description,
                agent_id=req.agent_id,
                visibility=req.visibility,
                push_to_github=req.push_to_github,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        await ws.send_json({"type": "initial_state", "payload": session_mgr.full_state_snapshot()})
        try:
            while True:
                data = await ws.receive_json()
                if data.get("action") == "ping":
                    await ws.send_json({"type": "pong"})
        except WebSocketDisconnect:
            return

    return app
