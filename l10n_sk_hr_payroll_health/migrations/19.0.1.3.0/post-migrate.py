# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.company"]._l10n_sk_migrate_health_payer_settings()
    env["hr.version"]._l10n_sk_migrate_legacy_insurers()
    env["l10n.sk.health"]._l10n_sk_migrate_legacy_payer_numbers()
