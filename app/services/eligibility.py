from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.models.user import User


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reason: str | None = None


def _get_user_value(user: User, field: str) -> Any:
    if field == "email":
        return user.email
    if field == "email_domain":
        return (user.email.split("@", 1)[-1] if user.email and "@" in user.email else None)
    if field == "role":
        return user.role.value if user.role else None
    if field == "is_active":
        return user.is_active
    if field == "full_name":
        return user.full_name
    return None


def _eval_condition(user: User, cond: dict[str, Any]) -> bool:
    field = cond.get("field")
    op = cond.get("op")
    value = cond.get("value")
    values = cond.get("in")
    uval = _get_user_value(user, field)

    if op == "eq":
        return uval == value
    if op == "neq":
        return uval != value
    if op == "in":
        return uval in (values or [])
    if op == "contains":
        return (value in uval) if isinstance(uval, str) and isinstance(value, str) else False
    if op == "endswith":
        return uval.endswith(value) if isinstance(uval, str) and isinstance(value, str) else False
    return False


def _eval_rules(user: User, rules: dict[str, Any]) -> bool:
    if "all" in rules and isinstance(rules["all"], list):
        return all(_eval_rules(user, r) if isinstance(r, dict) and ("all" in r or "any" in r) else _eval_condition(user, r) for r in rules["all"])
    if "any" in rules and isinstance(rules["any"], list):
        return any(_eval_rules(user, r) if isinstance(r, dict) and ("all" in r or "any" in r) else _eval_condition(user, r) for r in rules["any"])
    # single condition form
    return _eval_condition(user, rules)


def check_eligibility(user: User, eligibility_rules: str | None) -> EligibilityResult:
    """
    eligibility_rules is JSON text stored on drive, e.g.
    {
      "all": [
        {"field":"email_domain","op":"in","in":["hexaware.com","example.com"]},
        {"field":"is_active","op":"eq","value":true}
      ]
    }
    """
    if not eligibility_rules:
        return EligibilityResult(True, None)
    try:
        rules = json.loads(eligibility_rules)
        if not isinstance(rules, dict):
            return EligibilityResult(True, None)
        ok = _eval_rules(user, rules)
        return EligibilityResult(ok, None if ok else "Not eligible for this certification drive")
    except Exception:  # noqa: BLE001
        # If rules are malformed, fail open for hackathon/dev
        return EligibilityResult(True, None)

