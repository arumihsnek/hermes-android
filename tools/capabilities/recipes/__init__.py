"""Recipes — capability recipe data model, registry, and validation."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Optional


class MaturityState(str, enum.Enum):
    """Recipe maturity lifecycle states."""
    DISCOVERED = "discovered"
    CANDIDATE = "candidate"
    DOGFOOD = "dogfood"
    STABLE = "stable"
    SUSPECT = "suspect"
    QUARANTINED = "quarantined"
    DEPRECATED = "deprecated"


# Default maturity filter: only stable and dogfood recipes are resolved
_DEFAULT_MATURITIES = {MaturityState.STABLE, MaturityState.DOGFOOD}


@dataclass
class Recipe:
    """A capability recipe — defines how to execute a capability on a specific app."""
    id: str
    capability: str
    maturity: MaturityState
    package: str = ""
    version: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    verifier: dict[str, Any] = field(default_factory=dict)
    fingerprint: dict[str, Any] = field(default_factory=dict)
    invalidation_conditions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def load_recipe_from_dict(data: dict[str, Any]) -> Recipe:
    """Load a recipe from a dictionary, validating required fields."""
    if "id" not in data:
        raise ValueError("Recipe must have an 'id' field")
    if "capability" not in data:
        raise ValueError("Recipe must have a 'capability' field")

    maturity_str = data.get("maturity", "discovered")
    try:
        maturity = MaturityState(maturity_str)
    except ValueError:
        valid = [s.value for s in MaturityState]
        raise ValueError(f"Invalid maturity '{maturity_str}'. Must be one of: {valid}")

    return Recipe(
        id=data["id"],
        capability=data["capability"],
        maturity=maturity,
        package=data.get("package", ""),
        version=data.get("version", ""),
        steps=data.get("steps", []),
        verifier=data.get("verifier", {}),
        fingerprint=data.get("fingerprint", {}),
        invalidation_conditions=data.get("invalidation_conditions", []),
        metadata=data.get("metadata", {}),
    )


def validate_recipe(data: dict[str, Any]) -> list[str]:
    """Validate a recipe dictionary, returning list of error messages."""
    errors = []
    if "id" not in data:
        errors.append("Missing required field: id")
    if "capability" not in data:
        errors.append("Missing required field: capability")
    maturity = data.get("maturity", "")
    if maturity and maturity not in [s.value for s in MaturityState]:
        errors.append(f"Invalid maturity: {maturity}")
    return errors


class RecipeRegistry:
    """Registry for loading, storing, and querying recipes."""

    def __init__(self):
        self._recipes: dict[str, Recipe] = {}

    def register(self, recipe: Recipe) -> None:
        self._recipes[recipe.id] = recipe

    def find_by_capability(
        self,
        capability: str,
        package: Optional[str] = None,
        min_maturity: Optional[MaturityState] = None,
    ) -> list[Recipe]:
        """Find recipes matching capability, optionally filtered by package and maturity."""
        results = []
        for recipe in self._recipes.values():
            if recipe.capability != capability:
                continue
            if package and recipe.package and recipe.package != package:
                continue
            # Filter by maturity
            if recipe.maturity not in _DEFAULT_MATURITIES:
                continue
            results.append(recipe)
        return results

    def get(self, recipe_id: str) -> Optional[Recipe]:
        return self._recipes.get(recipe_id)

    def all(self) -> list[Recipe]:
        return list(self._recipes.values())

    def count(self) -> int:
        return len(self._recipes)
