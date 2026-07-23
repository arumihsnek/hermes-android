"""
Capability system error types — stable, serializable failure classifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import FailureClass, ResultStatus


@dataclass(frozen=True)
class CapabilityError:
    """Structured, serializable error from capability execution."""
    failure_class: FailureClass
    message: str
    step: Optional[int] = None
    tool: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "failure_class": self.failure_class.value,
            "message": self.message,
        }
        if self.step is not None:
            d["step"] = self.step
        if self.tool is not None:
            d["tool"] = self.tool
        return d


class AuthorizationRefused(Exception):
    """Raised when policy gate blocks an action."""
    def __init__(self, failure_class: FailureClass, message: str):
        self.failure_class = failure_class
        self.message = message
        super().__init__(message)


class PolicyViolation(Exception):
    """Raised when an action violates safety policy."""
    def __init__(self, classification: str, message: str):
        self.classification = classification
        self.message = message
        super().__init__(message)


class FlowValidationError(Exception):
    """Raised when a flow schema is invalid."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Flow validation failed: {'; '.join(errors)}")


class RecipeNotFoundError(Exception):
    """Raised when no compatible recipe exists."""
    def __init__(self, capability: str, device_digest: str):
        self.capability = capability
        self.device_digest = device_digest
        super().__init__(f"No compatible recipe for {capability} on device {device_digest}")


class RecipeQuarantined(Exception):
    """Raised when a recipe is quarantined or deprecated."""
    def __init__(self, recipe_id: str, maturity: str):
        self.recipe_id = recipe_id
        self.maturity = maturity
        super().__init__(f"Recipe {recipe_id} is {maturity}")
