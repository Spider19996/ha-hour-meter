"""Path validation helpers for hour_meter integration."""

from __future__ import annotations

from pathlib import Path


def is_safe_config_path(config_dir: str, configured_path: str) -> bool:
    """Return True when ``configured_path`` is absolute and inside ``config_dir``.

    Paths are compared resolved (symlinks and ``..`` segments) so that nothing
    outside the Home Assistant config directory can be targeted.
    """
    raw = Path(configured_path.strip())
    if not raw.is_absolute():
        return False
    resolved = raw.resolve()
    base = Path(config_dir).resolve()
    return resolved.is_relative_to(base)
