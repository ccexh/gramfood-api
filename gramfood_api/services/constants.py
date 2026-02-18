from enum import StrEnum, unique


@unique
class Platform(StrEnum):
    """The user device platform."""

    DEFAULT = "default"
    KIOSK = "kiosk"
