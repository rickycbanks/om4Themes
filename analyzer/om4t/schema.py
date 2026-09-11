"""
Dataclasses mirroring implementation-plan §14 — JSON schema for themes.json.

All timestamps are ISO-8601 with timezone (UTC).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string with timezone (Z suffix)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Leaf dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    id: str
    passed: bool
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {"id": self.id, "passed": self.passed, "note": self.note}

    @classmethod
    def from_dict(cls, d: dict) -> "CheckResult":
        return cls(id=d["id"], passed=d["passed"], note=d.get("note"))


@dataclass
class Compatibility:
    family: str
    level: int
    label: str
    tested_against: str
    omarchy_commit: str
    analyzed_at: str
    rules_version: str

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "level": self.level,
            "label": self.label,
            "tested_against": self.tested_against,
            "omarchy_commit": self.omarchy_commit,
            "analyzed_at": self.analyzed_at,
            "rules_version": self.rules_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Compatibility":
        # Validate required fields presence
        required = ["family", "level", "label", "tested_against", "omarchy_commit", "analyzed_at", "rules_version"]
        for k in required:
            if k not in d:
                raise ValueError(f"missing compatibility field: {k}")
        return cls(
            family=d["family"],
            level=d["level"],
            label=d["label"],
            tested_against=d["tested_against"],
            omarchy_commit=d["omarchy_commit"],
            analyzed_at=d["analyzed_at"],
            rules_version=d["rules_version"],
        )


@dataclass
class PaletteInfo:
    missing_canonical: list[str] = field(default_factory=list)
    resolved_via_alias: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "missing_canonical": list(self.missing_canonical),
            "resolved_via_alias": list(self.resolved_via_alias),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PaletteInfo":
        return cls(
            missing_canonical=list(d.get("missing_canonical", [])),
            resolved_via_alias=list(d.get("resolved_via_alias", [])),
        )


@dataclass
class OmarchyInfo:
    repo: str
    pin: str
    pin_source: str
    commit: str

    def to_dict(self) -> dict:
        return {"repo": self.repo, "pin": self.pin, "pin_source": self.pin_source, "commit": self.commit}

    @classmethod
    def from_dict(cls, d: dict) -> "OmarchyInfo":
        for k in ["repo", "pin", "pin_source", "commit"]:
            if k not in d:
                raise ValueError(f"missing omarchy field: {k}")
        return cls(repo=d["repo"], pin=d["pin"], pin_source=d["pin_source"], commit=d["commit"])


@dataclass
class RunSummary:
    discovered: int
    analyzed: int
    errors: int
    skipped_unchanged: int
    built_at: str = ""

    def to_dict(self) -> dict:
        return {
            "discovered": self.discovered,
            "analyzed": self.analyzed,
            "errors": self.errors,
            "skipped_unchanged": self.skipped_unchanged,
            "built_at": self.built_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RunSummary":
        return cls(
            discovered=d["discovered"],
            analyzed=d["analyzed"],
            errors=d["errors"],
            skipped_unchanged=d["skipped_unchanged"],
            built_at=d.get("built_at", ""),
        )


# ---------------------------------------------------------------------------
# ThemeRecord
# ---------------------------------------------------------------------------

@dataclass
class ThemeRecord:
    id: str
    repo_url: str
    creator: str
    description: str
    stars: int
    topics: list[str]
    default_branch: str
    commit_sha: str
    official: bool
    registry: bool
    preview: Optional[str]
    mode: str
    compatibility: Compatibility
    checks: list[CheckResult]
    badges: list[str]
    palette: PaletteInfo
    warnings: list[str]
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "repo_url": self.repo_url,
            "creator": self.creator,
            "description": self.description,
            "stars": self.stars,
            "topics": list(self.topics),
            "default_branch": self.default_branch,
            "commit_sha": self.commit_sha,
            "official": self.official,
            "registry": self.registry,
            "preview": self.preview,
            "mode": self.mode,
            "compatibility": self.compatibility.to_dict(),
            "checks": [c.to_dict() for c in self.checks],
            "badges": list(self.badges),
            "palette": self.palette.to_dict(),
            "warnings": list(self.warnings),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ThemeRecord":
        # Required compatibility handled via Compatibility.from_dict which validates
        if "compatibility" not in d:
            raise ValueError("missing compatibility field: compatibility")
        return cls(
            id=d["id"],
            repo_url=d["repo_url"],
            creator=d["creator"],
            description=d.get("description", ""),
            stars=d.get("stars", 0),
            topics=list(d.get("topics", [])),
            default_branch=d.get("default_branch", "main"),
            commit_sha=d.get("commit_sha", ""),
            official=d.get("official", False),
            registry=d.get("registry", False),
            preview=d.get("preview"),
            mode=d.get("mode", "dark"),
            compatibility=Compatibility.from_dict(d["compatibility"]),
            checks=[CheckResult.from_dict(c) for c in d.get("checks", [])],
            badges=list(d.get("badges", [])),
            palette=PaletteInfo.from_dict(d.get("palette", {})),
            warnings=list(d.get("warnings", [])),
            error=d.get("error"),
        )


# ---------------------------------------------------------------------------
# Top-level DB
# ---------------------------------------------------------------------------

@dataclass
class ThemesDB:
    schema_version: int
    generated_at: str
    rules_version: str
    omarchy: OmarchyInfo
    run: RunSummary
    themes: list[ThemeRecord]

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "rules_version": self.rules_version,
            "omarchy": self.omarchy.to_dict(),
            "run": self.run.to_dict(),
            "themes": [t.to_dict() for t in self.themes],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ThemesDB":
        if "schema_version" not in d:
            raise ValueError("missing field: schema_version")
        if "compatibility" in d:
            # erroneous top-level; ignore
            pass
        return cls(
            schema_version=d["schema_version"],
            generated_at=d["generated_at"],
            rules_version=d["rules_version"],
            omarchy=OmarchyInfo.from_dict(d["omarchy"]),
            run=RunSummary.from_dict(d["run"]),
            themes=[ThemeRecord.from_dict(t) for t in d.get("themes", [])],
        )

    def validate(self) -> None:
        """Raise on invalid data per spec."""
        if self.schema_version != 1:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        # Validate required top-level fields already via from_dict, but check presence
        if not self.generated_at:
            raise ValueError("missing field: generated_at")
        if not self.rules_version:
            raise ValueError("missing field: rules_version")
        # Validate each theme
        for t in self.themes:
            if t.compatibility is None:
                raise ValueError(f"theme {t.id}: missing compatibility")
            lvl = t.compatibility.level
            if lvl not in (0, 1, 2, 3, 4):
                raise ValueError(f"theme {t.id}: unknown level {lvl}")
            # missing compatibility fields already validated in Compatibility.from_dict,
            # but also check when constructed directly
            for k in ["family", "level", "label", "tested_against", "omarchy_commit", "analyzed_at", "rules_version"]:
                if not hasattr(t.compatibility, k) or getattr(t.compatibility, k) is None:
                    # allow 0 for level; check presence
                    if k == "level" and lvl == 0:
                        continue
                    if getattr(t.compatibility, k) is None:
                        raise ValueError(f"theme {t.id}: missing compatibility field: {k}")

    def to_json(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            f.write("\n")

    @classmethod
    def from_json(cls, path: str | Path) -> "ThemesDB":
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        obj = cls.from_dict(data)
        return obj
