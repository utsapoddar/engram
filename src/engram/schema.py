from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
import uuid

TYPES = {"preference", "decision", "project_state", "environment", "pattern", "failure", "fact"}
STATUSES = {"confirmed", "inferred", "conflicted", "superseded"}


class NoteValidationError(ValueError):
    pass


def validate_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise NoteValidationError("id must be a safe identifier")
    return value


def _timestamp(value, field_name, *, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str):
        raise NoteValidationError(f"{field_name} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise NoteValidationError(f"{field_name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise NoteValidationError(f"{field_name} must include a timezone")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemoryNote:
    id: str
    type: str
    status: str
    created_at: str
    updated_at: str
    last_verified: str | None
    source_refs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    body: str = ""

    def __post_init__(self) -> None:
        validate_id(self.id)
        if not isinstance(self.type, str) or self.type not in TYPES:
            raise NoteValidationError(f"invalid memory type: {self.type}")
        if not isinstance(self.status, str) or self.status not in STATUSES:
            raise NoteValidationError(f"invalid memory status: {self.status}")
        _timestamp(self.created_at, "created_at")
        _timestamp(self.updated_at, "updated_at")
        _timestamp(self.last_verified, "last_verified", nullable=True)
        for name, value in (("source_refs", self.source_refs), ("tags", self.tags)):
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise NoteValidationError(f"{name} must be a list of strings")
        if not isinstance(self.body, str):
            raise NoteValidationError("body must be text")

    @classmethod
    def new(cls, type: str, body: str, *, status: str = "confirmed", source_refs=None,
            tags=None, id: str | None = None) -> "MemoryNote":
        now = utcnow()
        return cls(id or uuid.uuid4().hex, type, status, now, now,
                   now if status == "confirmed" else None, list(source_refs or []), list(tags or []), body.strip())

    def to_markdown(self) -> str:
        values = {
            "id": self.id, "type": self.type, "status": self.status,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "last_verified": self.last_verified, "source_refs": self.source_refs, "tags": self.tags,
        }
        lines = ["---"] + [f"{key}: {json.dumps(value)}" for key, value in values.items()] + ["---", "", self.body, ""]
        return "\n".join(lines)


def parse_note(text: str) -> MemoryNote:
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not match:
        raise NoteValidationError("missing memory frontmatter")
    data = {}
    for line in match.group(1).splitlines():
        key, sep, raw = line.partition(":")
        if not sep:
            raise NoteValidationError(f"invalid frontmatter line: {line}")
        try:
            data[key.strip()] = json.loads(raw.strip())
        except json.JSONDecodeError:
            data[key.strip()] = raw.strip()
    fields = {"id", "type", "status", "created_at", "updated_at", "last_verified", "source_refs", "tags"}
    required = fields - data.keys()
    if required:
        raise NoteValidationError(f"missing required fields: {', '.join(sorted(required))}")
    try:
        return MemoryNote(body=match.group(2).strip(), **{key: value for key, value in data.items() if key in fields})
    except (TypeError, ValueError) as exc:
        if isinstance(exc, NoteValidationError):
            raise
        raise NoteValidationError(str(exc)) from exc
