from base64 import urlsafe_b64decode
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HEARTH_", extra="ignore")
    mode: Literal["production", "development", "test"] = "production"
    database_url: SecretStr = SecretStr("")
    migration_database_url: SecretStr = SecretStr("")
    fixture_identity: bool = False
    admin_origin: str = "https://localhost:8443"
    user_origin: str = "https://localhost:8444"
    identity_origin: str = "https://localhost:8445"
    trusted_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    oidc_realm: str = "hearth"
    admin_client_secret: SecretStr = SecretStr("")
    user_client_secret: SecretStr = SecretStr("")
    session_encryption_key: SecretStr = SecretStr("")
    audience: Literal["admin", "user"] = "admin"
    farm_id: UUID | None = None
    identity_internal_origin: str = "http://keycloak:8085"
    # Only the development appliance may map a host-loopback URL to QEMU's
    # same-machine gateway. Never accept transport aliases from browser input.
    development_provider_aliases: dict[str, str] = Field(default_factory=dict)
    memory_vault_path: str | None = None
    # Reasoning models spend the completion budget on both reasoning and answers.
    chat_max_output_tokens: int = Field(default=16384, ge=256, le=65536)
    chat_timeout_seconds: int = Field(default=900, ge=30, le=3600)

    @property
    def origin(self):
        return self.admin_origin if self.audience == "admin" else self.user_origin

    @property
    def issuer(self):
        return f"{self.identity_origin}/realms/{self.oidc_realm}"

    @property
    def oidc_internal(self):
        return f"{self.identity_internal_origin}/realms/{self.oidc_realm}/protocol/openid-connect"

    @property
    def client_id(self):
        return f"hearth-{self.audience}"

    @property
    def client_secret(self):
        return (self.admin_client_secret if self.audience == "admin" else self.user_client_secret).get_secret_value()

    @model_validator(mode="after")
    def fail_closed(self):
        if self.mode == "production":
            if self.development_provider_aliases:
                raise ValueError("provider transport aliases are development-only")
            if self.fixture_identity:
                raise ValueError("fixture identity cannot start in production")
            if not self.database_url.get_secret_value():
                raise ValueError("production requires a configured PostgreSQL database")
            if not all(origin.startswith("https://") for origin in (self.admin_origin, self.user_origin, self.identity_origin)):
                raise ValueError("production requires HTTPS origins")
            try:
                encoded = self.session_encryption_key.get_secret_value()
                if len(urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))) != 32:
                    raise ValueError("incorrect key length")
            except Exception as exc:
                raise ValueError("production requires a 256-bit session encryption key") from exc
        if self.fixture_identity and self.mode != "test":
            raise ValueError("fixture identity is available only in explicit test mode")
        if len({self.admin_origin, self.user_origin, self.identity_origin}) != 3:
            raise ValueError("admin, user and identity origins must be distinct")
        for origin in (self.admin_origin, self.user_origin, self.identity_origin):
            parsed = urlsplit(origin)
            if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
                raise ValueError("application origins must contain only scheme, host and optional port")
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ValueError("invalid origin port")
        if self.database_url.get_secret_value() and not self.database_url.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("hearth requires PostgreSQL through psycopg")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
