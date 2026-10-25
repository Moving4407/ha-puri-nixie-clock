"""Sanity checks for the integration manifest."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
MANIFEST = json.loads((ROOT / "custom_components/puri_nixie_clock/manifest.json").read_text())


def test_manifest_domain_matches_folder() -> None:
    assert MANIFEST["domain"] == "puri_nixie_clock"


def test_manifest_requires_sun_and_no_packages() -> None:
    assert MANIFEST["dependencies"] == ["sun"]
    assert MANIFEST["requirements"] == []


def test_hacs_minimum_version() -> None:
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["homeassistant"] == "2026.10.0"
