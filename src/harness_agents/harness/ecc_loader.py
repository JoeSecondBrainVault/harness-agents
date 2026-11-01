"""Dynamic O(1) loader for the 311 ECC Armory Skills and 71 Specialized Subagents."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class SkillCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str
    description: str
    source: str  # "obsidian-core", "ecc-armory", "ecc-rule"
    path: str


class SubagentCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    path: str


class ECCArmoryLoader:
    """Indexes the local ECC Armory (311 skills & 71 subagents) + Obsidian Second Brain skills."""

    def __init__(
        self,
        ecc_root: Path | None = None,
        obsidian_skills_root: Path | None = None,
    ) -> None:
        self.ecc_root = ecc_root or Path("C:/Users/Legion/.gemini/antigravity/scratch/ECC")
        self.obsidian_skills_root = obsidian_skills_root or Path(
            "C:/Users/Legion/Documents/Obsidian Vault/11 - Skills & Evolution Lab/skills"
        )
        self._skills: dict[str, SkillCard] = {}
        self._subagents: dict[str, SubagentCard] = {}
        self.reload()

    def reload(self) -> None:
        """Scan Obsidian fused skills, ECC skills, ECC rules, and ECC subagents."""
        self._skills.clear()
        self._subagents.clear()

        # 1. Load Obsidian Second Brain Fused Core Skills first (Highest Priority)
        if self.obsidian_skills_root.exists():
            for skill_md in sorted(self.obsidian_skills_root.glob("*/SKILL.md")):
                skill_id = skill_md.parent.name
                meta = self._parse_frontmatter(skill_md)
                self._skills[skill_id] = SkillCard(
                    id=skill_id,
                    name=meta.get("name", skill_id),
                    category=self._infer_category(skill_id, meta.get("description", "")),
                    description=meta.get("description", f"Obsidian Core Skill: {skill_id}")[:220],
                    source="obsidian-core",
                    path=str(skill_md),
                )

        # 2. Load ECC Armory Skills (scratch/ECC/skills/*/SKILL.md or *.md)
        ecc_skills_dir = self.ecc_root / "skills"
        if ecc_skills_dir.exists():
            for skill_md in sorted(ecc_skills_dir.rglob("SKILL.md")):
                skill_id = skill_md.parent.name
                if skill_id in self._skills:
                    continue
                meta = self._parse_frontmatter(skill_md)
                desc = meta.get("description", f"ECC Armory Skill: {skill_id}")
                self._skills[skill_id] = SkillCard(
                    id=skill_id,
                    name=meta.get("name", skill_id),
                    category=self._infer_category(skill_id, desc),
                    description=desc[:220],
                    source="ecc-armory",
                    path=str(skill_md),
                )

        # 3. Also index ECC language/framework rules & commands so all 200-311 items are browsable
        for extra_folder, source_tag in [("rules", "ecc-rule"), ("commands", "ecc-command")]:
            folder_path = self.ecc_root / extra_folder
            if folder_path.exists():
                for md_file in sorted(folder_path.rglob("*.md")):
                    if md_file.name.lower() == "readme.md":
                        continue
                    rel_stem = md_file.stem
                    parent_prefix = (
                        f"{md_file.parent.name}-"
                        if md_file.parent != folder_path
                        else ""
                    )
                    skill_id = f"{parent_prefix}{rel_stem}".lower().replace(" ", "-")
                    if skill_id in self._skills:
                        continue
                    meta = self._parse_frontmatter(md_file)
                    desc = meta.get(
                        "description",
                        f"ECC {extra_folder[:-1].title()} ({md_file.parent.name}): {rel_stem}",
                    )
                    self._skills[skill_id] = SkillCard(
                        id=skill_id,
                        name=meta.get("name", skill_id),
                        category=self._infer_category(skill_id, desc),
                        description=desc[:220],
                        source=source_tag,
                        path=str(md_file),
                    )

        # Ensure fallback core skills exist even in isolated CI environments
        if not self._skills:
            for fallback_id, cat, desc in [
                ("tdd-workflow", "Testing & QA", "Red-Green-Refactor TDD verification loop"),
                ("systematic-debugging", "Debugging", "Root-cause isolation and Bug Ledger logging"),
                ("backend-patterns", "Backend & API", "FastAPI, Laravel, Node & SQL secure architecture"),
                ("frontend-patterns", "Frontend & UI", "Next.js, React 19, TypeScript & Electron patterns"),
                ("code-review-gate", "Security & Audit", "OWASP ASVS 5.0.0 & Anti-Slop code review shield"),
                ("polish-project", "Release & Ops", "End-to-end security audit, graph sync & polish"),
                ("wrap-up", "Obsidian Brain", "Session summary, Graphify update & vault sync"),
                ("harness2", "AI Harness", "Recursive Propose-Probe-Compose agent optimization"),
            ]:
                self._skills[fallback_id] = SkillCard(
                    id=fallback_id,
                    name=fallback_id,
                    category=cat,
                    description=desc,
                    source="obsidian-core",
                    path="",
                )

        # 4. Load ECC Specialized Subagents (71+ agents in scratch/ECC/agents/*.md)
        ecc_agents_dir = self.ecc_root / "agents"
        if ecc_agents_dir.exists():
            for agent_md in sorted(ecc_agents_dir.rglob("*.md")):
                if agent_md.name.lower() == "readme.md":
                    continue
                agent_id = agent_md.stem.lower()
                meta = self._parse_frontmatter(agent_md)
                self._subagents[agent_id] = SubagentCard(
                    id=agent_id,
                    name=meta.get("name", agent_id),
                    description=meta.get("description", f"Specialized Subagent: {agent_id}")[:220],
                    path=str(agent_md),
                )

        if not self._subagents:
            for sub_id, desc in [
                ("planner", "Decomposes complex goals into dependency-ordered Kanban tasks"),
                ("architect", "Designs high-craft system boundaries and TypeScript/Python contracts"),
                ("code-reviewer", "Reviews diffs for bugs, regressions, and anti-slop compliance"),
                ("security-reviewer", "Audits code against OWASP ASVS 5.0.0 and Bandit/secret rules"),
                ("build-error-resolver", "Diagnoses and fixes compiler, typecheck, and import errors"),
                ("tdd-guide", "Enforces Red-Green-Refactor unit and integration test coverage"),
                ("harness-optimizer", "Refines agent prompts, skills, and memory via Harness2"),
            ]:
                self._subagents[sub_id] = SubagentCard(
                    id=sub_id, name=sub_id, description=desc, path=""
                )

    def list_skills(
        self, query: str | None = None, category: str | None = None
    ) -> list[SkillCard]:
        """Filter and return indexed skills."""
        items = list(self._skills.values())
        if category and category.lower() != "all":
            items = [s for s in items if s.category.lower() == category.lower()]
        if query:
            q = query.lower().strip()
            items = [
                s
                for s in items
                if q in s.id.lower()
                or q in s.name.lower()
                or q in s.description.lower()
                or q in s.category.lower()
            ]
        return items

    def list_subagents(self) -> list[SubagentCard]:
        return list(self._subagents.values())

    def get_skill(self, skill_id: str) -> SkillCard | None:
        return self._skills.get(skill_id)

    def read_skill_Snippet(self, skill_id: str, max_chars: int = 1200) -> str:
        """Load O(1) compact excerpt of a skill file only when equipped by an agent."""
        card = self._skills.get(skill_id)
        if not card or not card.path:
            return f"[Skill: {skill_id}] {card.description if card else ''}"
        try:
            text = Path(card.path).read_text(encoding="utf-8", errors="replace")
            return text[:max_chars]
        except OSError:
            return f"[Skill: {skill_id}] {card.description}"

    def auto_recommend_skills(self, task_text: str, limit: int = 3) -> list[str]:
        """Laya-style <1ms reflex matcher that picks the best 1-3 ECC skills for a task."""
        tokens = set(re.findall(r"[a-z0-9]+", task_text.lower()))
        scored: list[tuple[int, str]] = []
        for skill_id, card in self._skills.items():
            score = 0
            skill_words = set(re.findall(r"[a-z0-9]+", f"{skill_id} {card.category} {card.description}".lower()))
            overlap = tokens.intersection(skill_words)
            score += len(overlap) * 3
            if any(t in skill_id.lower() for t in tokens if len(t) > 2):
                score += 8
            if card.source == "obsidian-core":
                score += 1
            if score > 1:
                scored.append((score, skill_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = [skill_id for _, skill_id in scored[:limit]]
        return selected or ["tdd-workflow"]

    def stats(self) -> dict[str, int]:
        categories: dict[str, int] = {}
        for s in self._skills.values():
            categories[s.category] = categories.get(s.category, 0) + 1
        return {
            "total_skills": len(self._skills),
            "total_subagents": len(self._subagents),
            "obsidian_core_count": sum(
                1 for s in self._skills.values() if s.source == "obsidian-core"
            ),
            "ecc_armory_count": sum(
                1 for s in self._skills.values() if s.source != "obsidian-core"
            ),
            "categories_count": len(categories),
        }

    @staticmethod
    def _parse_frontmatter(path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return result
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        result[k.strip().lower()] = v.strip().strip('"').strip("'")
                body = parts[2].strip()
                if "description" not in result and body:
                    first_para = next(
                        (
                            ln.lstrip("# ").strip()
                            for ln in body.splitlines()
                            if ln.strip() and not ln.strip().startswith("#")
                        ),
                        "",
                    )
                    if first_para:
                        result["description"] = first_para
        else:
            for ln in raw.splitlines():
                stripped = ln.strip()
                if stripped and not stripped.startswith("#"):
                    result["description"] = stripped
                    break
        return result

    @staticmethod
    def _infer_category(skill_id: str, description: str) -> str:
        text = f"{skill_id} {description}".lower()
        if any(k in text for k in ["react", "next", "frontend", "tailwind", "ui", "css", "expo", "vue", "svelte"]):
            return "Frontend & UI"
        if any(k in text for k in ["security", "owasp", "audit", "auth", "secret", "vuln", "pentest", "shield"]):
            return "Security & Audit"
        if any(k in text for k in ["test", "tdd", "pytest", "playwright", "vitest", "qa", "e2e", "benchmark"]):
            return "Testing & QA"
        if any(k in text for k in ["python", "fastapi", "django", "flask", "laravel", "php", "api", "backend", "node", "go", "rust", "java", "spring"]):
            return "Backend & API"
        if any(k in text for k in ["sql", "postgres", "prisma", "database", "redis", "mongo", "supabase", "migration"]):
            return "Database & Storage"
        if any(k in text for k in ["docker", "k8s", "deploy", "ci", "git", "devops", "cloud", "aws", "terraform"]):
            return "DevOps & Git"
        if any(k in text for k in ["ai", "llm", "prompt", "harness", "agent", "rag", "embedding", "brain", "graphify", "laya"]):
            return "AI & Harness"
        return "General Engineering"
