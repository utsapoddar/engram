#!/usr/bin/env python3
"""Install Claude and Codex integration files without replacing unrelated data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import shutil
import sys
import tomllib


BEGIN = "<!-- BEGIN SHARED_AGENT_MEMORY -->"
END = "<!-- END SHARED_AGENT_MEMORY -->"
MARKER_BLOCK = f"""{BEGIN}
## Shared agent memory

- Route plain `remember this` requests to Engram via `engram remember`.
- Recall prior decisions, preferences, failures, and project history before answering.
- Treat only confirmed notes as truth; open the full note, never rely on a search snippet.
{END}"""


class Installer:
    def __init__(self, home: Path, repo: Path, dry_run: bool):
        self.home = home.expanduser().resolve()
        self.repo = repo.expanduser().resolve()
        self.dry_run = dry_run

    def log(self, action: str, path: Path):
        print(f"{'would ' if self.dry_run else ''}{action}: {path}")

    def backup(self, path: Path):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = path.with_name(f"{path.name}.bak.{stamp}")
        self.log("backup", destination)
        if not self.dry_run:
            shutil.copy2(path, destination)

    def write(self, path: Path, content: str):
        if path.is_file() and path.read_text() == content:
            return
        self.log("write", path)
        if self.dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            self.backup(path)
        path.write_text(content)

    def symlink(self, path: Path, target: Path):
        if path.is_symlink():
            if path.resolve(strict=False) == target.resolve(strict=False):
                return
            print(f"engram: preserving unrelated symlink {path}", file=sys.stderr)
            return
        if path.exists():
            print(f"engram: preserving unrelated path {path}", file=sys.stderr)
            return
        self.log("symlink", path)
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target)

    def load_json(self, path: Path) -> dict:
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text())
            return value if isinstance(value, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def command(self, script: str, agent: str | None = None) -> str:
        parts = [self.repo / ".venv/bin/python", self.repo / "integrations/hooks" / script]
        rendered = " ".join(shlex.quote(str(part)) for part in parts)
        return rendered + (f" --agent {agent}" if agent else "")

    @staticmethod
    def add_hook(hooks: dict, event: str, command: str):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            groups = []
            hooks[event] = groups
        for group in groups:
            if not isinstance(group, dict):
                continue
            handlers = group.get("hooks")
            if isinstance(handlers, list) and any(
                isinstance(handler, dict) and handler.get("command") == command
                for handler in handlers
            ):
                return
        groups.append({"hooks": [{"type": "command", "command": command}]})

    def install_json_hooks(self):
        claude_path = self.home / ".claude/settings.json"
        claude = self.load_json(claude_path)
        hooks = claude.get("hooks")
        if not isinstance(hooks, dict):
            hooks = {}
            claude["hooks"] = hooks
        self.add_hook(hooks, "SessionStart", self.command("session_start.py"))
        capture_claude = self.command("capture_session.py", "claude")
        self.add_hook(hooks, "PreCompact", capture_claude)
        self.add_hook(hooks, "SessionEnd", capture_claude)
        self.write(claude_path, json.dumps(claude, indent=2) + "\n")

        codex_path = self.home / ".codex/hooks.json"
        codex = self.load_json(codex_path)
        codex_hooks = codex.get("hooks")
        if not isinstance(codex_hooks, dict):
            codex_hooks = {}
            codex["hooks"] = codex_hooks
        self.add_hook(codex_hooks, "SessionStart", self.command("session_start.py"))
        self.add_hook(codex_hooks, "Stop", self.command("capture_session.py", "codex"))
        self.write(codex_path, json.dumps(codex, indent=2) + "\n")

    @staticmethod
    def enable_hooks(text: str) -> str:
        try:
            parsed = tomllib.loads(text) if text.strip() else {}
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"invalid Codex config.toml: {exc}") from exc

        lines = text.splitlines(keepends=True)
        name = r'(?:features|"features"|\'features\')'
        hook_name = r'(?:hooks|"hooks"|\'hooks\')'
        feature_header = re.compile(
            rf"^\s*\[\s*{name}\s*\]\s*(?:#.*)?(?:\r?\n)?$"
        )
        start = next((i for i, line in enumerate(lines) if feature_header.match(line)), None)

        if start is not None:
            if not lines[start].endswith(("\n", "\r")):
                lines[start] += "\n"
            end = next((i for i in range(start + 1, len(lines))
                        if re.match(r"^\s*\[", lines[i])), len(lines))
            matches = [i for i in range(start + 1, end)
                       if re.match(rf"^\s*{hook_name}\s*=", lines[i])]
            if matches:
                first, *duplicates = matches
                lines[first] = re.sub(
                    rf"^(\s*{hook_name}\s*=\s*)(?:true|false)",
                    r"\g<1>true",
                    lines[first],
                )
                for index in reversed(duplicates):
                    del lines[index]
            else:
                if end > start + 1 and not lines[end - 1].endswith(("\n", "\r")):
                    lines[end - 1] += "\n"
                lines.insert(end, "hooks = true\n")
        else:
            dotted_hook = re.compile(
                rf"^(\s*{name}\s*\.\s*{hook_name}\s*=\s*)(?:true|false)",
            )
            dotted_features = re.compile(rf"^\s*{name}\s*\.")
            hook_matches = [i for i, line in enumerate(lines) if dotted_hook.match(line)]
            feature_matches = [i for i, line in enumerate(lines) if dotted_features.match(line)]
            inline_features = re.compile(
                rf"^(?P<prefix>\s*{name}\s*=\s*\{{)(?P<body>.*)(?P<suffix>\}}\s*(?:#.*)?(?:\r?\n)?)$"
            )
            inline_index = next(
                (i for i, line in enumerate(lines) if inline_features.match(line)), None
            )

            if hook_matches:
                first, *duplicates = hook_matches
                lines[first] = dotted_hook.sub(r"\g<1>true", lines[first], count=1)
                for index in reversed(duplicates):
                    del lines[index]
            elif feature_matches:
                index = feature_matches[-1] + 1
                if not lines[index - 1].endswith(("\n", "\r")):
                    lines[index - 1] += "\n"
                lines.insert(index, "features.hooks = true\n")
            elif inline_index is not None:
                match = inline_features.match(lines[inline_index])
                body = match.group("body")
                hook_assignment = re.compile(
                    rf"(?P<prefix>(?:^|,)\s*{hook_name}\s*=\s*)(?:true|false)"
                )
                if hook_assignment.search(body):
                    body = hook_assignment.sub(r"\g<prefix>true", body, count=1)
                else:
                    trimmed = body.rstrip()
                    spacing = body[len(trimmed):]
                    body = trimmed + (", " if trimmed.strip() else " ") + "hooks = true" + spacing
                lines[inline_index] = match.group("prefix") + body + match.group("suffix")
            elif "features" in parsed:
                raise ValueError("unsupported features representation in Codex config.toml")
            else:
                separator = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
                lines = [text + separator + "[features]\nhooks = true\n"]

        rendered = "".join(lines)
        try:
            updated = tomllib.loads(rendered)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"installer produced invalid Codex config.toml: {exc}") from exc
        if updated.get("features", {}).get("hooks") is not True:
            raise ValueError("failed to enable Codex hooks")
        return rendered

    def install_config(self):
        path = self.home / ".codex/config.toml"
        existing = path.read_text() if path.is_file() else ""
        self.write(path, self.enable_hooks(existing))

    @staticmethod
    def marked(text: str) -> str:
        pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
        if pattern.search(text):
            return pattern.sub(MARKER_BLOCK, text, count=1)
        separator = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
        return text + separator + MARKER_BLOCK + "\n"

    def install_markers(self):
        for path in (self.home / "AGENTS.md", self.home / ".claude/CLAUDE.md"):
            existing = path.read_text() if path.is_file() else ""
            self.write(path, self.marked(existing))

    def install_skills(self):
        claude_skills = self.home / ".claude/skills"
        self.symlink(claude_skills / "engram", self.repo / "integrations/skill")
        codex_skills = self.home / ".codex/skills"
        if not codex_skills.exists() and not codex_skills.is_symlink():
            self.symlink(codex_skills, claude_skills)
        elif codex_skills.is_dir() and not codex_skills.is_symlink():
            self.symlink(codex_skills / "engram", self.repo / "integrations/skill")
        elif codex_skills.is_symlink() and codex_skills.resolve(strict=False) != claude_skills.resolve(strict=False):
            print(f"engram: preserving unrelated Codex skills link {codex_skills}", file=sys.stderr)

    def install_cli(self):
        path = self.home / ".local/bin/engram"
        self.symlink(path, self.repo / ".venv/bin/engram")

    def run(self):
        self.install_skills()
        self.install_json_hooks()
        self.install_config()
        self.install_markers()
        self.install_cli()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    Installer(args.home, args.repo_root, args.dry_run).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
