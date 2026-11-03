"""Configuration management with environment validation and secret protection."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = Field(default="development")
    APP_NAME: str = Field(default="Connects")
    LOG_LEVEL: str = Field(default="INFO")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://connects_app:connects_dev_password@localhost:5432/connects_dev"
    )
    DIRECT_DATABASE_URL: str | None = Field(default=None)

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Vault / Credential Encryption (AES-256-GCM)
    # Master keys must be 32 bytes base64-encoded strings
    VAULT_MASTER_KEY_V1: SecretStr = Field(
        default=SecretStr(
            "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
        )  # 32-byte default for dev/tests
    )
    VAULT_MASTER_KEY_V2: SecretStr | None = Field(default=None)
    VAULT_ACTIVE_KEY_VERSION: str = Field(default="v1")

    # Authentication & JWT
    JWT_SECRET_KEY: SecretStr = Field(
        default=SecretStr("insecure_development_jwt_secret_change_in_production_32b")
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)

    # GitHub App Integration (Read-Only Repository Intelligence)
    GITHUB_APP_ID: str | None = Field(default=None)
    GITHUB_APP_NAME: str | None = Field(default=None)  # e.g. "connects-app"
    GITHUB_APP_PRIVATE_KEY: SecretStr | None = Field(default=None)  # PEM RSA private key
    GITHUB_APP_CLIENT_ID: str | None = Field(default=None)
    GITHUB_APP_CLIENT_SECRET: SecretStr | None = Field(default=None)
    GITHUB_APP_WEBHOOK_SECRET: SecretStr | None = Field(default=None)

    def is_github_configured(self) -> bool:
        """Returns True if the required GitHub App credentials are configured."""
        return bool(self.GITHUB_APP_ID and self.GITHUB_APP_PRIVATE_KEY)

    def get_github_private_key_pem(self) -> str | None:
        """Returns normalized PEM format RSA private key string."""
        if not self.GITHUB_APP_PRIVATE_KEY:
            return None
        val = self.GITHUB_APP_PRIVATE_KEY.get_secret_value().strip()
        # Handle literal \n newlines in env strings
        if "\\n" in val:
            val = val.replace("\\n", "\n")
        return val

    def get_vault_keys(self) -> dict[str, bytes]:
        """Returns decoded 32-byte master keys mapped by key version."""
        import base64

        keys: dict[str, bytes] = {}
        if self.VAULT_MASTER_KEY_V1:
            raw = base64.b64decode(self.VAULT_MASTER_KEY_V1.get_secret_value())
            if len(raw) != 32:
                raise ValueError("VAULT_MASTER_KEY_V1 must be exactly 32 bytes (256 bits)")
            keys["v1"] = raw

        if self.VAULT_MASTER_KEY_V2:
            raw = base64.b64decode(self.VAULT_MASTER_KEY_V2.get_secret_value())
            if len(raw) != 32:
                raise ValueError("VAULT_MASTER_KEY_V2 must be exactly 32 bytes (256 bits)")
            keys["v2"] = raw

        return keys


settings = Settings()
