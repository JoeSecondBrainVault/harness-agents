"""Local Semantic Memory Store (`memory - minilm`) backed by SQLite + Cosine Similarity."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path

from harness_agents.config import utc_now_iso


class MiniLMMemoryStore:
    """Persistent cross-agent semantic memory (`memory - minilm`) using SQLite + lightweight n-gram vectors."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path("C:/Users/Legion/.gemini/antigravity/scratch/harness-agents/.harness_data/memory_minilm.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
            cursor = conn.execute("SELECT COUNT(*) FROM memory_entries")
            count = cursor.fetchone()[0]
            if count == 0:
                self._seed_initial_memories()

    def _seed_initial_memories(self) -> None:
        seeds = [
            (
                "ramon",
                "architecture",
                "Use O(1) Context Router loading + 311 ECC Skill cartridges per agent to prevent token bloat.",
            ),
            (
                "ada",
                "frontend",
                "Enforce strict TypeScript (no any), complete UI states (Loading/Empty/Error/Success), and Isometric 60FPS canvas rendering.",
            ),
            (
                "ken",
                "backend",
                "Use Pydantic v2 models, timezone-aware UTC timestamps, and parameterized SQLite queries.",
            ),
            (
                "sentinel",
                "security",
                "Run Invoke-SecurityAudit.ps1, Bandit, and secret checks before moving Kanban tasks to DONE.",
            ),
            (
                "rogelio",
                "ops",
                "Sync project milestones to Obsidian Second Brain and celebrate milestones with SWELDO NA!",
            ),
        ]
        for agent_id, topic, content in seeds:
            self.remember(agent_id=agent_id, content=content, topic=topic)

    @staticmethod
    def embed_text(text: str, dims: int = 64) -> list[float]:
        """Deterministic fast local embedding projection (MiniLM hash-projection compatible offline)."""
        vec = [0.0] * dims
        tokens = re.findall(r"[a-z0-9_]+", text.lower())
        if not tokens:
            return vec
        for tok in tokens:
            h = sum((idx + 1) * ord(ch) for idx, ch in enumerate(tok))
            bucket = h % dims
            sign = 1.0 if (h // dims) % 2 == 0 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [round(v / norm, 5) for v in vec]

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        return sum(x * y for x, y in zip(a, b))

    def remember(self, agent_id: str, content: str, topic: str = "general") -> int:
        vec = self.embed_text(f"{topic} {content}")
        now = utc_now_iso()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO memory_entries (agent_id, topic, content, vector_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (agent_id, topic, content, json.dumps(vec), now),
            )
            conn.commit()
            return int(cur.lastrowid or 0)

    def recall(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        q_vec = self.embed_text(query)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, agent_id, topic, content, vector_json, created_at FROM memory_entries ORDER BY id DESC LIMIT 200"
            ).fetchall()
        scored: list[tuple[float, dict[str, object]]] = []
        for row_id, agent_id, topic, content, vec_json, created_at in rows:
            try:
                vec = json.loads(vec_json)
            except ValueError:
                vec = []
            sim = self.cosine_similarity(q_vec, vec)
            if query.lower() in content.lower():
                sim += 0.35
            scored.append(
                (
                    sim,
                    {
                        "id": row_id,
                        "agent_id": agent_id,
                        "topic": topic,
                        "content": content,
                        "score": round(sim, 3),
                        "created_at": created_at,
                    },
                )
            )
        scored.sort(key=lambda item: -item[0])
        return [item[1] for item in scored[:limit]]

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0])
