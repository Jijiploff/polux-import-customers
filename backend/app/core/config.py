"""Configuración centralizada por variables de entorno."""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    APP_NAME: str = "Polux Import · Customers API"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_VERSION: str = "0.3.0"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    DB_HOST: str = "localhost"
    DB_PORT: int = 1433
    DB_NAME: str = "PoluxImportDB"
    DB_USER: str = "sa"
    DB_PASSWORD: str = "YourStrong!Passw0rd"
    DB_DRIVER: str = "ODBC Driver 18 for SQL Server"
    DB_TRUST_CERT: bool = True

    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    JWT_SECRET_KEY: str = "dev-only-change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Scheduler (motor de reglas)
    SCHEDULER_ENABLED: bool = False
    SCHEDULER_INTERVAL_SECONDS: int = 300
    SCHEDULER_RUN_ON_STARTUP: bool = False

        # ---- Agente IA ----
    LLM_PROVIDER: str = "mock"           # mock | openai
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TIMEOUT_SECONDS: int = 20
    LLM_MAX_TOKENS: int = 400

        # ---- WhatsApp Business Cloud API ----
    WHATSAPP_ENABLED: bool = False
    WHATSAPP_DRY_RUN: bool = True
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "polux-verify-token"
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_GRAPH_VERSION: str = "v22.0"
    WHATSAPP_API_TIMEOUT_SECONDS: int = 15
    WHATSAPP_MAX_RETRIES: int = 5
    WHATSAPP_BACKOFF_BASE_SECONDS: int = 30

    # ---- Correo de respaldo ----
    EMAIL_ENABLED: bool = False
    EMAIL_PROVIDER: str = "mock"  # mock | resend | smtp
    EMAIL_API_KEY: str = ""
    EMAIL_FROM: str = "no-reply@poluximport.pe"
    EMAIL_FROM_NAME: str = "Polux Import"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True

    # ---- Outbox worker ----
    OUTBOX_ENABLED: bool = True
    OUTBOX_INTERVAL_SECONDS: int = 60
    OUTBOX_BATCH_SIZE: int = 50

        # ---- Agente: control de calidad y comportamiento ----
    AGENT_MIN_CONFIDENCE: float = 0.55
    AGENT_RECENT_HUMAN_RESPONSE_MINUTES: int = 10
    AGENT_CONTEXT_MESSAGES: int = 5
    AGENT_MAX_RESPONSE_SECONDS: int = 12

    @property
    def database_url(self) -> str:
        driver = self.DB_DRIVER.replace(" ", "+")
        trust = "yes" if self.DB_TRUST_CERT else "no"
        return (
            f"mssql+pyodbc://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?driver={driver}&TrustServerCertificate={trust}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()