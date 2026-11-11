# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Keep an insurer with the native historical employment version."""

from odoo import api, fields, models
from odoo.exceptions import AccessError

from .res_company import HEALTH_INSURER_CODES


class HrVersion(models.Model):
    _inherit = "hr.version"

    l10n_sk_health_insurer_code = fields.Selection(
        HEALTH_INSURER_CODES,
        string="Health insurer (SK)",
        groups="hr.group_hr_user",
        tracking=True,
        help="Insurer applicable to this employment version. A new employee uses "
        "the company's configured insurer as its initial value. Review historical "
        "versions separately; changing today's insurer does not change them.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        versions = super().create(vals_list)
        for version, vals in zip(versions, vals_list):
            if "l10n_sk_health_insurer_code" not in vals and version.employee_id:
                version.l10n_sk_health_insurer_code = (
                    version.company_id.l10n_sk_health_insurer_code
                )
        return versions

    def _l10n_sk_health_profile(self, day):
        result = super()._l10n_sk_health_profile(day)
        self.check_access("read")
        result.update(
            insurer_code=self.l10n_sk_health_insurer_code or None,
            op_claim=bool(getattr(self, "l10n_sk_health_oop_claim", False)),
            op_eligible=self.l10n_sk_employment_form() == "none",
            minimum_exempt=(
                result["calendar"]["minimum_days"] == 0
                if result["calendar"]
                else self.l10n_sk_health_minimum_is_exempt()
            ),
        )
        return result

    @api.model
    def _l10n_sk_migrate_legacy_insurers(self):
        """Preserve the old employee value on its current version only.

        The old physical column remains readable during a post-migration even
        though the field is now delegated. Never invent historical insurers or
        overwrite an already reviewed version. Repeating the migration is safe.
        """
        if not self.env.su:
            raise AccessError("Insurer migration requires the upgrade environment.")
        self.env.cr.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'hr_employee' "
            "AND column_name = 'l10n_sk_health_insurer_code'"
        )
        if not self.env.cr.fetchone():
            return 0
        self.env.cr.execute(
            "SELECT id, l10n_sk_health_insurer_code FROM hr_employee "
            "WHERE l10n_sk_health_insurer_code IS NULL "
            "OR l10n_sk_health_insurer_code IN %s",
            [tuple(code for code, _label in HEALTH_INSURER_CODES)],
        )
        changed = 0
        for employee_id, insurer in self.env.cr.fetchall():
            employee = self.env["hr.employee"].with_context(active_test=False).browse(
                employee_id
            )
            version = employee.version_id
            effective_insurer = insurer or employee.company_id.l10n_sk_health_insurer_code
            if version and not version.l10n_sk_health_insurer_code and effective_insurer:
                version.l10n_sk_health_insurer_code = effective_insurer
                changed += 1
        return changed
