# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Stable, compact fingerprints of calculation facts, shared by engines."""

import hashlib
import json


def source_fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def same_monthly_relationship(retained, current):
    """Share monthly limits across versions of one proved legal relationship.

    New evidence compares the entire cooperative relationship key, including
    identifiers supplied by optional bridges. Historical evidence without it
    remains usable for the same native version and retained contract dates;
    a different version is never guessed to be its successor.
    """
    if not isinstance(retained, dict) or not isinstance(current, dict):
        return False
    old_key, new_key = retained.get("relationship"), current.get("relationship")
    if isinstance(old_key, dict) and isinstance(new_key, dict):
        period = new_key.get("contract_period")
        if isinstance(period, dict) and period.get("start"):
            return old_key == new_key
    return bool(
        retained.get("version")
        and retained.get("version") == current.get("version")
        and retained.get("contract_period") == current.get("contract_period")
    )
