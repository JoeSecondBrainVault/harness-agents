"""1:1 and Hive Inter-Agent Message Bus with SQLite persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from harness_agents.config import utc_now_iso


class AgentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    sender_id: str
    recipient_id: str  # agent_id or "hive"
    channel: str  # "1:1", "hive", "steer", "user"
    content: str
    created_at: str


class MessageBus:
    """Manages 1:1 direct agent handoffs, steering notes, and Ramon's Hive broadcasts."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Path(
            "C:/Users/Legion/.gemini/antigravity/scratch/harness-agents/.harness_data/messages.db"
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM agent_messages").fetchone()[0]
            if count == 0:
                self.send_message(
                    sender_id="ramon",
                    recipient_id="hive",
                    channel="hive",
                    content="Floor 1 initialized: 311 ECC Skills & 71 Subagents online. Auto-mode ready.",
                )
                self.send_message(
                    sender_id="rogelio",
                    recipient_id="hive",
                    channel="hive",
                    content="SWELDO NA! Local RTX 4060 + MiniLM semantic memory synced.",
                )

    def send_message(
        self,
        sender_id: str,
        recipient_id: str,
        content: str,
        channel: str = "1:1",
    ) -> AgentMessage:
        now = utc_now_iso()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO agent_messages (sender_id, recipient_id, channel, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sender_id, recipient_id, channel, content, now),
            )
            conn.commit()
            msg_id = int(cur.lastrowid or 0)
        return AgentMessage(
            id=msg_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            channel=channel,
            content=content,
            created_at=now,
        )

    def list_messages(
        self, agent_id: str | None = None, limit: int = 50
    ) -> list[dict[str, object]]:
        with sqlite3.connect(self.db_path) as conn:
            if agent_id:
                rows = conn.execute(
                    """
                    SELECT id, sender_id, recipient_id, channel, content, created_at
                    FROM agent_messages
                    WHERE sender_id = ? OR recipient_id = ? OR recipient_id = 'hive'
                    ORDER BY id DESC LIMIT ?
                    """,
                    (agent_id, agent_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, sender_id, recipient_id, channel, content, created_at
                    FROM agent_messages
                    ORDER BY id DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [
            {
                "id": r[0],
                "sender_id": r[1],
                "recipient_id": r[2],
                "channel": r[3],
                "content": r[4],
                "created_at": r[5],
            }
            for r in reversed(rows)
        ]
