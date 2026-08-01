"""YAML configuration with ``_defaults_`` inheritance.

Same convention as CheXVision: a config declares ``_defaults_: default.yaml``
and is deep-merged over its base. Nothing is hard-coded in source – if a number
influences training or export, it lives in ``ml/configs/``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"

#: Set ``SBR_ALLOW_LOCAL=1`` to bypass. Training belongs on a Kaggle GPU kernel;
#: the guard exists because the predecessor's notebook could not reproduce its
#: own model and nobody noticed until submission.
CLOUD_GUARD_ENV = "SBR_ALLOW_LOCAL"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto a copy of ``base``."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(name: str, directory: Path | None = None, _seen: set[str] | None = None) -> dict[str, Any]:
    """Load ``<name>.yaml``, resolving ``_defaults_`` chains."""
    directory = directory or CONFIG_DIR
    _seen = _seen or set()

    stem = Path(name).stem
    if stem in _seen:
        raise ValueError(f"circular _defaults_ chain through {stem!r}")
    _seen.add(stem)

    path = directory / f"{stem}.yaml"
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    parent_name = raw.pop("_defaults_", None)
    if parent_name is None:
        return raw

    parent = load_config(parent_name, directory, _seen)
    return deep_merge(parent, raw)


def assert_cloud() -> None:
    """Raise unless we are on a cloud kernel or explicitly allowed locally."""
    import os

    if os.environ.get(CLOUD_GUARD_ENV) == "1":
        return
    on_kaggle = Path("/kaggle").exists()
    if not on_kaggle:
        raise RuntimeError(
            "Training runs on Kaggle GPU kernels, not locally. "
            f"Dispatch with `python ml/scripts/dispatch.py push detector`, "
            f"or set {CLOUD_GUARD_ENV}=1 if you really mean it."
        )
