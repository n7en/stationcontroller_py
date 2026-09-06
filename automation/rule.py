# Backward-compatibility shim - Rule is now Automation, RuleTier is AutomationTier.
from .automation import Automation as Rule, AutomationTier as RuleTier, AutomationMode  # noqa: F401
