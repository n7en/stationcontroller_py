"""
Automation definition - Trigger -> Condition -> Action.

An Automation fires when any of its triggers detects a transition.
All conditions must pass for the action to execute.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .trigger import Trigger
from .condition import Condition
from .action import Action


class AutomationTier(Enum):
    PROTECTION = "protection"       # safety, runs first
    CONFIGURATION = "configuration" # band/station setup
    ADVISORY = "advisory"           # monitoring and logging

    @property
    def order(self) -> int:
        return {"protection": 0, "configuration": 1, "advisory": 2}[self.value]


class AutomationMode(Enum):
    SINGLE = "single"       # skip if action is currently running
    RESTART = "restart"     # cancel running action and start fresh
    QUEUED = "queued"       # queue; run after current action finishes (max 10)
    PARALLEL = "parallel"   # run concurrently with any existing execution


@dataclass
class Automation:
    name: str
    tier: AutomationTier
    triggers: list[Trigger]
    action: Action
    conditions: list[Condition] = field(default_factory=list)
    description: str = ""
    enabled: bool = True
    mode: AutomationMode = AutomationMode.SINGLE
    priority: int = 0
