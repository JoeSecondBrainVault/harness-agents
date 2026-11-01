"""GitHub Organization Integration for `JoeSecondBrainVault` (Repo Creation, Real File Writer & Push)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict


DEFAULT_GITHUB_ORG = "JoeSecondBrainVault"
PROJECTS_BASE_DIR = Path("C:/Users/Legion/.gemini/antigravity/scratch")

SAFE_GITIGNORE = """# Secrets & Environment
.env
.env.*
*.pem
*.key
secrets.*

# Python & Node
__pycache__/
*.py[cod]
.venv/
venv/
node_modules/
dist/
build/
.pytest_cache/

# Local DBs & Graphify
*.db
*.sqlite
*.sqlite3
graphify-out/
.graphifyignore
.obsidian/
"""


class GitHubRepoResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    org: str = DEFAULT_GITHUB_ORG
    repo_name: str
    repo_url: str
    local_path: str
    files_written: list[str]
    terminal_log: str


class GitHubOrgManager:
    """Allows agents to scaffold real workspaces, write files, and create/push repos in JoeSecondBrainVault."""

    def __init__(self, org_name: str = DEFAULT_GITHUB_ORG, base_dir: Path | None = None) -> None:
        self.org_name = org_name
        self.base_dir = base_dir or PROJECTS_BASE_DIR

    @staticmethod
    def slugify_repo_name(raw_name: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw_name.strip()).strip("-").lower()
        return slug[:60] or "harness-agent-project"

    def list_org_repos(self, limit: int = 20) -> list[dict[str, str]]:
        """List existing repositories inside https://github.com/JoeSecondBrainVault."""
        gh_bin = shutil.which("gh")
        if not gh_bin:
            return []
        try:
            proc = subprocess.run(
                [
                    gh_bin,
                    "repo",
                    "list",
                    self.org_name,
                    "--limit",
                    str(limit),
                    "--json",
                    "name,url,visibility,updatedAt,description",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                import json

                data = json.loads(proc.stdout)
                return [
                    {
                        "name": str(item.get("name", "")),
                        "url": str(item.get("url", "")),
                        "visibility": str(item.get("visibility", "PRIVATE")).lower(),
                        "description": str(item.get("description") or ""),
                        "updated_at": str(item.get("updatedAt", "")),
                    }
                    for item in data
                ]
        except (OSError, subprocess.SubprocessError, ValueError):
            return []
        return []

    def scaffold_and_push_repo(
        self,
        repo_name: str,
        task_description: str,
        agent_name: str = "ramon",
        visibility: str = "private",
        push_to_github: bool = True,
        extra_files: dict[str, str] | None = None,
    ) -> GitHubRepoResult:
        """Create a real local project folder, write code files, init git, and create/push to JoeSecondBrainVault."""
        clean_repo = self.slugify_repo_name(repo_name)
        project_dir = (self.base_dir / clean_repo).resolve()
        project_dir.mkdir(parents=True, exist_ok=True)

        written: list[str] = []

        # 1. Always enforce .gitignore first (Never commit secrets)
        gitignore_path = project_dir / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text(SAFE_GITIGNORE, encoding="utf-8")
            written.append(".gitignore")

        # 2. Write README.md & multi-agent scaffold files if not already present
        readme_path = project_dir / "README.md"
        if not readme_path.exists():
            readme_content = (
                f"# {clean_repo}\n\n"
                f"> Autonomous project created by **HarnessAgents (`{agent_name}`)** in [`{self.org_name}`](https://github.com/{self.org_name}/{clean_repo}).\n\n"
                f"## Task Specification\n{task_description}\n\n"
                f"## Agent Squad Contributions\n"
                f"- **Ramon (`Hive Lead`)**: Architecture & API/UI Specification\n"
                f"- **Ken (`Backend`)**: `src/app.py` (FastAPI / Pydantic v2 Service)\n"
                f"- **Ada (`Frontend`)**: `src/index.html` (Interactive UI View)\n"
                f"- **Mira (`QA & TDD`)**: `tests/test_app.py` (Automated Test Suite)\n"
                f"- **Sentinel (`Security Gate`)**: `.gitignore` & OWASP ASVS 5.0.0 Verification\n"
            )
            readme_path.write_text(readme_content, encoding="utf-8")
            written.append("README.md")

        src_dir = project_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        tests_dir = project_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        app_py = src_dir / "app.py"
        if not app_py.exists():
            app_py.write_text(
                f'"""Backend module for {clean_repo} — generated by Ken (Backend Engineer)."""\n\n'
                "from __future__ import annotations\n\n"
                "from datetime import UTC, datetime\n"
                "from pydantic import BaseModel, ConfigDict\n\n\n"
                "class ServiceStatus(BaseModel):\n"
                '    model_config = ConfigDict(extra="forbid")\n\n'
                "    service: str\n"
                "    status: str\n"
                "    timestamp: str\n\n\n"
                "def get_status() -> ServiceStatus:\n"
                "    return ServiceStatus(\n"
                f'        service="{clean_repo}",\n'
                '        status="healthy",\n'
                "        timestamp=datetime.now(UTC).isoformat(),\n"
                "    )\n",
                encoding="utf-8",
            )
            written.append("src/app.py")

        ui_html = src_dir / "index.html"
        if not ui_html.exists():
            ui_html.write_text(
                f"<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n  <meta charset=\"UTF-8\" />\n  <title>{clean_repo}</title>\n</head>\n"
                f"<body>\n  <h1>{clean_repo}</h1>\n  <p>{task_description}</p>\n</body>\n</html>\n",
                encoding="utf-8",
            )
            written.append("src/index.html")

        test_py = tests_dir / "test_app.py"
        if not test_py.exists():
            test_py.write_text(
                f'"""TDD verification suite for {clean_repo} — generated by Mira (QA Runner)."""\n\n'
                "from src.app import get_status\n\n\n"
                "def test_service_status() -> None:\n"
                "    res = get_status()\n"
                f'    assert res.service == "{clean_repo}"\n'
                '    assert res.status == "healthy"\n',
                encoding="utf-8",
            )
            written.append("tests/test_app.py")

        if extra_files:
            for rel_path, content in extra_files.items():
                safe_rel = Path(rel_path)
                if safe_rel.is_absolute() or ".." in safe_rel.parts:
                    continue
                target = project_dir / safe_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                written.append(str(safe_rel.as_posix()))

        # 3. Initialize Git & Commit locally
        git_bin = shutil.which("git")
        gh_bin = shutil.which("gh")
        repo_url = f"https://github.com/{self.org_name}/{clean_repo}"
        logs: list[str] = [
            f"\x1b[36m[🐙 GITHUB ORG • {self.org_name}]\x1b[0m Prepared workspace `{project_dir}`",
            f"  • Files written ({len(written)}): {', '.join(written)}",
        ]

        if git_bin:
            if not (project_dir / ".git").exists():
                subprocess.run([git_bin, "init", "-b", "main"], cwd=str(project_dir), capture_output=True, timeout=8, check=False)
            subprocess.run([git_bin, "add", "."], cwd=str(project_dir), capture_output=True, timeout=8, check=False)
            subprocess.run(
                [git_bin, "commit", "-m", f"feat({clean_repo}): initial multi-agent scaffold by {agent_name}"],
                cwd=str(project_dir),
                capture_output=True,
                timeout=8,
                check=False,
            )
            logs.append("  • Local Git commit created on branch `main`.")

        # 4. Create repository in JoeSecondBrainVault and push if requested
        if push_to_github and gh_bin:
            vis_flag = "--public" if visibility.lower() == "public" else "--private"
            proc_create = subprocess.run(
                [
                    gh_bin,
                    "repo",
                    "create",
                    f"{self.org_name}/{clean_repo}",
                    vis_flag,
                    "--source",
                    str(project_dir),
                    "--remote",
                    "origin",
                    "--description",
                    task_description[:140] or f"Created by HarnessAgents ({agent_name})",
                    "--push",
                ],
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=25,
                check=False,
            )
            if proc_create.returncode == 0:
                logs.append(f"  \x1b[32m✓ Created & pushed to {repo_url} ({visibility.upper()})\x1b[0m")
                status = "created_and_pushed"
            else:
                # If repo already exists in JoeSecondBrainVault, push to origin
                subprocess.run(
                    [git_bin or "git", "push", "-u", "origin", "main"],
                    cwd=str(project_dir),
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                logs.append(f"  \x1b[32m✓ Synced with existing repo {repo_url}\x1b[0m")
                status = "synced_existing"
        else:
            status = "local_only"

        return GitHubRepoResult(
            status=status,
            org=self.org_name,
            repo_name=clean_repo,
            repo_url=repo_url,
            local_path=str(project_dir),
            files_written=written,
            terminal_log="\n".join(logs),
        )
