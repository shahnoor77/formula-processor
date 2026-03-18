"""Pre-defined formula registry."""
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class FormulaDefinition:
    """Pre-defined formula definition."""
    id: str
    name: str
    description: str
    expression: str
    required_tags: int  # Number of tags required


# Pre-defined formula registry
FORMULA_REGISTRY: Dict[str, FormulaDefinition] = {
    "sum": FormulaDefinition(
        id="sum",
        name="Sum",
        description="Calculate sum of selected tags",
        expression="sum(tags)",
        required_tags=2
    ),
    "average": FormulaDefinition(
        id="average",
        name="Average",
        description="Calculate average of selected tags",
        expression="sum(tags) / len(tags)",
        required_tags=2
    ),
    "difference": FormulaDefinition(
        id="difference",
        name="Difference",
        description="Calculate difference between two tags (Tag1 - Tag2)",
        expression="tags[0] - tags[1]",
        required_tags=2
    ),
    "multiply": FormulaDefinition(
        id="multiply",
        name="Multiply",
        description="Multiply selected tags",
        expression="tags[0] * tags[1]",
        required_tags=2
    ),
    "divide": FormulaDefinition(
        id="divide",
        name="Divide",
        description="Divide first tag by second (Tag1 / Tag2)",
        expression="tags[0] / tags[1] if tags[1] != 0 else 0",
        required_tags=2
    ),
    "max": FormulaDefinition(
        id="max",
        name="Maximum",
        description="Find maximum value among selected tags",
        expression="max(tags)",
        required_tags=2
    ),
    "min": FormulaDefinition(
        id="min",
        name="Minimum",
        description="Find minimum value among selected tags",
        expression="min(tags)",
        required_tags=2
    ),
    "percentage": FormulaDefinition(
        id="percentage",
        name="Percentage",
        description="Calculate percentage (Tag1 / Tag2 * 100)",
        expression="(tags[0] / tags[1] * 100) if tags[1] != 0 else 0",
        required_tags=2
    ),
    "power": FormulaDefinition(
        id="power",
        name="Power",
        description="Raise first tag to power of second (Tag1 ^ Tag2)",
        expression="tags[0] ** tags[1]",
        required_tags=2
    ),
    "weighted_avg": FormulaDefinition(
        id="weighted_avg",
        name="Weighted Average",
        description="Weighted average: (Tag1 * 0.7 + Tag2 * 0.3)",
        expression="tags[0] * 0.7 + tags[1] * 0.3",
        required_tags=2
    )
}


def get_all_formulas() -> List[FormulaDefinition]:
    """Get all available formulas."""
    return list(FORMULA_REGISTRY.values())


def get_formula(formula_id: str) -> FormulaDefinition:
    """Get formula by ID."""
    if formula_id not in FORMULA_REGISTRY:
        raise ValueError(f"Formula '{formula_id}' not found")
    return FORMULA_REGISTRY[formula_id]
