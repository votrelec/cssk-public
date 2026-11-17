# Copyright 2026 votrelec
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Income exclusions under Act 580/2004 section 10b(1)(a), not state status."""

from .applicability import (
    DOBPS,
    DOPC,
    DOVP,
    PENSION_TYPES,
    DISABILITY,
    DISABILITY_OVER_70,
    DISABILITY_AT_AGE,
    DISABILITY_SERVICE,
)

INVALIDITY_PROFILES = (
    DISABILITY,
    DISABILITY_OVER_70,
    DISABILITY_AT_AGE,
    DISABILITY_SERVICE,
)


def pension_health_disabled(pension_type):
    """Section 12(2), footnote 48: recognised invalidity under 461/328.

    An invalidity pension establishes that fact without an additional ZTP-card
    checkbox. Ordinary old-age/service-at-age pensions do not establish it.
    """
    return pension_type in INVALIDITY_PROFILES


def agreement_health_exempt(employment_form, pension_type):
    """An ordinary employment pensioner still pays health premiums.

    SERVICE_AT_AGE already represents the reviewed retirement-age condition;
    a service pension before that age must not be classified as that profile.
    Other grounds, such as foreign insurance, require a separate reviewed fact.
    """
    return employment_form == DOBPS or (
        employment_form in (DOPC, DOVP) and pension_type in PENSION_TYPES
    )


def pension_state_insured(pension_type):
    """Known pension profiles meet section 11(7)(b), relevant to the minimum.

    This is not a determination that ordinary employment income is excluded.
    Widow/orphan-only pensions are not among these employment-profile values.
    """
    return pension_type in PENSION_TYPES
