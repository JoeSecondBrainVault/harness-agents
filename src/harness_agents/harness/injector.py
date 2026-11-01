"""Harness Level Prompt Injector (off | lite | full | ultra)."""

from __future__ import annotations

from harness_agents.config import AgentProfile, HarnessLevel
from harness_agents.harness.ecc_loader import ECCArmoryLoader

GOLDEN_RULES_SUMMARY = (
    "1. Pure 7-bit ASCII in .ps1 scripts.\n"
    "2. Filter $_.ProcessId -ne $PID before process cleanup.\n"
    "3. Zero hardcoded secrets (os.environ.get only, Bandit B105).\n"
    "4. Validate https:// scheme and timeout=15 before network requests (B310).\n"
    "5. Strict TypeScript (no any) and Pydantic v2 validation.\n"
    "6. Always use timezone-aware UTC (datetime.now(UTC)).\n"
    "7. Keep Ollama Flash Attention & q8_0 KV cache enabled for 8GB RTX 4060."
)


class HarnessInjector:
    """Wraps user prompts with the selected DevLabs/Harness2 intensity level."""

    def __init__(self, ecc_loader: ECCArmoryLoader) -> None:
        self.ecc_loader = ecc_loader

    def build_system_prompt(
        self,
        agent: AgentProfile,
        memory_snippets: list[str] | None = None,
    ) -> str:
        """Assemble the system prompt according to off | lite | full | ultra."""
        if agent.harness_level == HarnessLevel.OFF:
            return f"You are {agent.name} ({agent.role}). Respond concisely."

        parts: list[str] = [
            f"# Agent Identity: {agent.name.upper()} ({agent.display_title})",
            f"- Role: {agent.role}",
            f"- Department / Scope: {agent.department}",
            f"- Workspace Path: {agent.workspace_path}",
            f"- Assigned Model: {agent.model_id} ({agent.provider.value})",
            f"- Subagent Persona: {agent.subagent_persona}",
        ]

        if agent.harness_level == HarnessLevel.LITE:
            if agent.equipped_skills:
                parts.append(
                    f"- Active Skills: {', '.join(agent.equipped_skills)}"
                )
            return "\n".join(parts)

        # FULL and ULTRA include Equipped ECC Skills + Golden Rules + Memory
        if agent.equipped_skills:
            skill_blocks: list[str] = []
            for skill_id in agent.equipped_skills:
                snippet = self.ecc_loader.read_skill_Snippet(skill_id, max_chars=600)
                skill_blocks.append(f"### Skill Cartridge: `{skill_id}`\n{snippet}")
            parts.append("\n## Equipped ECC Armory Skills (O(1) Active Loadout)\n" + "\n\n".join(skill_blocks))

        parts.append("\n## Obsidian Second Brain Golden Prevention Rules\n" + GOLDEN_RULES_SUMMARY)

        if memory_snippets:
            parts.append(
                "\n## Shared Semantic Memory (`memory - minilm`)\n"
                + "\n".join(f"- {m}" for m in memory_snippets[:5])
            )

        parts.append(
            "\n## Inter-Agent Collaboration Protocol\n"
            "- Use `@agent_id: <message>` to send a 1:1 note to a teammate (ramon, ada, ken, mira, sentinel, rogelio).\n"
            "- Keep outputs high-craft with zero placeholder TODOs."
        )

        if agent.harness_level == HarnessLevel.ULTRA:
            parts.append(
                "\n## ULTRA Harness Verification Gate (Mandatory Before Done)\n"
                "1. Verify syntax compilation (`py_compile` / `tsc --noEmit`).\n"
                "2. Verify unit tests pass (`pytest` / `vitest`).\n"
                "3. Verify OWASP ASVS 5.0.0 security rules (no secrets, parameterized queries, auth checks).\n"
                "4. Provide a structured Verification Summary at the end of your turn."
            )

        return "\n".join(parts)
