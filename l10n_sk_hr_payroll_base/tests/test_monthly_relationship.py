# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from copy import deepcopy

from odoo.tests import BaseCase, tagged

from ..fund_sources import same_monthly_relationship


@tagged("post_install", "-at_install")
class TestMonthlyRelationship(BaseCase):
    def test_complete_cooperative_key_and_legacy_version_policy(self):
        old = {
            "version": 1,
            "contract_period": {"start": "2026-01-01", "end": None},
            "relationship": {
                "employee": 2,
                "company": 3,
                "contract_period": {"start": "2026-01-01", "end": None},
                "external_identifier": "assigned-relationship-1",
            },
        }
        current = deepcopy(old)
        current["version"] = 4
        self.assertTrue(same_monthly_relationship(old, current))
        for name, value in (
            ("external_identifier", "assigned-relationship-2"),
            ("company", 5),
            ("employee", 6),
        ):
            changed = deepcopy(current)
            changed["relationship"][name] = value
            self.assertFalse(same_monthly_relationship(old, changed))
        legacy = deepcopy(old)
        legacy.pop("relationship")
        self.assertTrue(same_monthly_relationship(legacy, old))
        self.assertFalse(same_monthly_relationship(legacy, current))
        self.assertFalse(same_monthly_relationship(False, current))
