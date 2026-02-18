import logging
import tomllib
from pathlib import Path
from contextlib import suppress
from typing import ClassVar, Literal, Any, overload
from configparser import ConfigParser, SectionProxy

from . import types

logger = logging.getLogger(__name__)
config_path = Path(__file__).parent.with_name("config.toml")


class ConfigManager:
    """The Configuration manager."""

    __instance: ClassVar[ConfigManager | None] = None

    def __new__(cls) -> ConfigManager:
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)

        return cls.__instance

    def __init__(self) -> None:
        if hasattr(self, "_config"):
            return

        self._config: types.Config = {}
        self.load()

    @overload
    def __getitem__(self, key: Literal["main"]) -> types._ConfigMain: ...
    @overload
    def __getitem__(self, key: Literal["log"]) -> types._ConfigLog: ...
    @overload
    def __getitem__(self, key: Literal["database"]) -> types._ConfigDatabase: ...
    @overload
    def __getitem__(self, key: Literal["api"]) -> types._ConfigApi: ...
    @overload
    def __getitem__(
        self, key: Literal["authentication"]
    ) -> types._ConfigAuthentication: ...
    @overload
    def __getitem__(self, key: Literal["sms"]) -> types._ConfigSms: ...
    def __getitem__(self, key: str) -> Any:
        return self._config[key]

    def __contains__(self, key: str) -> bool:
        return key in self._config

    def _read_env(self) -> SectionProxy | None:
        if (env_path := config_path.with_name(".env")).exists():
            # Simple hack to avoid parsing the file manually
            parser = ConfigParser()
            parser.read_string(f"[env]\n{env_path.read_text()}")

            return parser["env"]

    def _validate(self) -> None:
        """Validates and normalizes the configuration values.

        Raises:
            `SystemExit`: If validation fails with invalid values.
        """
        secrets_dir = Path("/run/secrets")
        with suppress(FileNotFoundError):
            if sms_api_key := (secrets_dir / "sms_api_key").read_text():
                self._config["sms"]["api_key"] = sms_api_key

        if env := self._read_env():
            if domain := env["API_DOMAIN"]:
                self._config["api"]["domain"] = domain

    def load(self) -> None:
        """Loads the configuration file.

        On recall, it reloads the configuration.
        """
        self._config.clear()
        self._config |= tomllib.loads(config_path.read_text())
        self._validate()

        if not (temp_path := Path(self._config["main"]["temp_path"])).exists():
            temp_path.mkdir(mode=0o750, parents=True, exist_ok=True)


config = ConfigManager()
