"""SQLite-backed Kanban Board with Auto-Mode task assignment & ECC Skill recommendations."""

from __future__ import annotations

import json
import sqlite3
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from harness_agents.config import utc_now_iso


class KanbanStatus(str, Enum):
    BACKLOG = "backlog"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class KanbanTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    description: str
    status: KanbanStatus = KanbanStatus.BACKLOG
    assigned_agent_id: str | None = None
    recommended_skills: list[str] = Field(default_factory=list)
    priority: str = "medium"
    created_at: str


class KanbanBoard:
    """Manages project tasks across Backlog -> In Progress -> Review -> Done."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path(
            "C:/Users/Legion/.gemini/antigravity/scratch/harness-agents/.harness_data/kanban.db"
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kanban_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assigned_agent_id TEXT,
                    skills_json TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM kanban_tasks").fetchone()[0]
            if count == 0:
                self._seed_tasks()

    def _seed_tasks(self) -> None:
        initial = [
            (
                "Architect Multi-Model Failover Router",
                "Wire Gemini Pro + GitHub Student Pack + Groq LPU + Local RTX 4060 Ollama",
                KanbanStatus.DONE,
                "ramon",
                ["backend-patterns", "model-handoff"],
                "high",
            ),
            (
                "Build Isometric 2.5D Office Canvas & A* Pathfinding",
                "Render Floor 1 desks, War Room, 🇵🇭 flag, Ping-Pong table, Gym & speech bubbles",
                KanbanStatus.IN_PROGRESS,
                "ada",
                ["frontend-patterns"],
                "high",
            ),
            (
                "Index 311 ECC Armory Skills & 71 Subagents",
                "Provide O(1) dynamic skill cartridge loader for every agent",
                KanbanStatus.DONE,
                "ken",
                ["backend-patterns", "harness2"],
                "high",
            ),
            (
                "Run Pytest Suite & OWASP ASVS 5.0.0 Security Audit",
                "Verify 0 Bandit/secret issues across all modules before release",
                KanbanStatus.REVIEW,
                "sentinel",
                ["code-review-gate", "tdd-workflow"],
                "high",
            ),
            (
                "Sync Session & Graphify to Obsidian Second Brain",
                "Update project note and Global Bug Prevention Ledger via Local Qwen-7B-RTX",
                KanbanStatus.BACKLOG,
                "rogelio",
                ["wrap-up", "evolve-brain"],
                "medium",
            ),
        ]
        for title, desc, status, agent_id, skills, prio in initial:
            self.create_task(
                title=title,
                description=desc,
                status=status,
                assigned_agent_id=agent_id,
                recommended_skills=skills,
                priority=prio,
            )

    def create_task(
        self,
        title: str,
        description: str = "",
        status: KanbanStatus = KanbanStatus.BACKLOG,
        assigned_agent_id: str | None = None,
        recommended_skills: list[str] | None = None,
        priority: str = "medium",
    ) -> KanbanTask:
        now = utc_now_iso()
        skills = recommended_skills or ["tdd-workflow"]
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO kanban_tasks (title, description, status, assigned_agent_id, skills_json, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (title, description, status.value, assigned_agent_id, json.dumps(skills), priority, now),
            )
            conn.commit()
            task_id = int(cur.lastrowid or 0)
        return KanbanTask(
            id=task_id,
            title=title,
            description=description,
            status=status,
            assigned_agent_id=assigned_agent_id,
            recommended_skills=skills,
            priority=priority,
            created_at=now,
        )

    def update_task(
        self,
        task_id: int,
        status: KanbanStatus | None = None,
        assigned_agent_id: str | None = None,
    ) -> KanbanTask | None:
        with sqlite3.connect(self.db_path) as conn:
            if status is not None:
                conn.execute(
                    "UPDATE kanban_tasks SET status = ? WHERE id = ?",
                    (status.value, task_id),
                )
            if assigned_agent_id is not None:
                conn.execute(
                    "UPDATE kanban_tasks SET assigned_agent_id = ? WHERE id = ?",
                    (assigned_agent_id, task_id),
                )
            conn.commit()
        return self.get_task(task_id)

    def get_task(self, task_id: int) -> KanbanTask | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, title, description, status, assigned_agent_id, skills_json, priority, created_at FROM kanban_tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_task(row)

    def list_tasks(self) -> list[KanbanTask]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, description, status, assigned_agent_id, skills_json, priority, created_at FROM kanban_tasks ORDER BY id ASC"
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    @staticmethod
    def _row_to_task(row: tuple[object, ...]) -> KanbanTask:
        try:
            skills = json.loads(str(row[5]))
        except ValueError:
            skills = []
        return KanbanTask(
            id=int(row[0]),  # type: ignore[arg-type]
            title=str(row[1]),
            description=str(row[2]),
            status=KanbanStatus(str(row[3])),
            assigned_agent_id=str(row[4]) if row[4] is not None else None,
            recommended_skills=skills,
            priority=str(row[6]),
            created_at=str(row[7]),
        )
