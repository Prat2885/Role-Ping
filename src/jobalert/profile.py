import json
from pathlib import Path

from jobalert.cvtext import infer_profile, read_cv
from jobalert.llm_scan import scan_cv
from jobalert.models import ConfigError


def profile_path(config_dir: Path) -> Path:
    return config_dir / "data" / "profile.json"


def save_profile(config_dir: Path, cv_path: Path) -> dict:
    text = read_cv(cv_path)
    profile = infer_profile(text, cv_path.name)
    scanned = scan_cv(text, config_dir / ".env")
    if scanned is not None:
        profile["level"] = scanned["level"]
        profile["queries"] = scanned["queries"]
        if scanned["years"] is not None:
            profile["years"] = round(scanned["years"], 1)
        if scanned.get("summary"):
            profile["summary"] = scanned["summary"]
        profile["scanner"] = "llm"
    else:
        profile["scanner"] = "related-roles"
    destination = profile_path(config_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return profile


def load_profile(config_dir: Path) -> dict | None:
    path = profile_path(config_dir)
    if not path.is_file():
        return None
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Could not read {path}. Upload the CV again.") from exc
    if not isinstance(profile, dict) or "level" not in profile or "queries" not in profile:
        raise ConfigError(f"Profile file is incomplete: {path}. Upload the CV again.")
    return profile


def format_profile(profile: dict) -> str:
    years = profile.get("years")
    experience = "unknown" if years is None else f"{years} years"
    queries = "; ".join(profile.get("queries") or [])
    titles = profile.get("titles") or []
    latest = titles[0] if titles else ""
    return (
        f"Level: {profile.get('level')}\n"
        f"Experience: {experience}\n"
        f"Latest title: {latest}\n"
        f"Searches: {queries}\n"
        f"Scanner: {profile.get('scanner', 'related-roles')}"
    )
