"""CLI entry point for HarnessAgents (`serve`, `status`, `skills`)."""

from __future__ import annotations

import argparse
import json

import uvicorn

from harness_agents.api.server import create_app
from harness_agents.runtime.session_manager import OfficeSessionManager


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="harness-agents",
        description="HarnessAgents — Isometric 2.5D Virtual Office & Multi-Agent Orchestrator",
    )
    sub = parser.add_subparsers(dest="command")

    serve_p = sub.add_parser("serve", help="Launch the Virtual Office & Inspector Web Server")
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    serve_p.add_argument("--port", type=int, default=8420, help="Bind port (default: 8420)")

    sub.add_parser("status", help="Print agent roster, provider status & ECC skill stats")

    skills_p = sub.add_parser("skills", help="Search the 311 ECC Armory Skills")
    skills_p.add_argument("--query", "-q", default="", help="Search keyword")

    args = parser.parse_args()
    mgr = OfficeSessionManager()

    if args.command == "status":
        snap = mgr.full_state_snapshot()
        print(json.dumps(
            {
                "ecc_stats": snap["ecc_stats"],
                "provider_health": snap["provider_health"],
                "agents": [
                    {
                        "id": a["id"],
                        "role": a["role"],
                        "model": a["model_id"],
                        "provider": a["provider"],
                        "skills": a["equipped_skills"],
                    }
                    for a in snap["agents"]  # type: ignore[union-attr]
                ],
            },
            indent=2,
        ))
        return

    if args.command == "skills":
        matched = mgr.ecc_loader.list_skills(query=args.query or None)
        print(f"Found {len(matched)} skills (Total Armory: {mgr.ecc_loader.stats()}):")
        for s in matched[:30]:
            print(f"  - [{s.category}] {s.id} ({s.source}): {s.description[:80]}")
        return

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8420)
    app = create_app(mgr)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
