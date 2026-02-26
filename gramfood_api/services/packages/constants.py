from enum import StrEnum, unique


@unique
class MealType(StrEnum):
    """The meal type for a package subscription."""

    LUNCH = "lunch"
    DINNER = "dinner"
    BOTH = "both"
