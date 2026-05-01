from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    APP_NAME: str = "Maverick Certification Hub"
    ENVIRONMENT: str = "dev"
    API_BASE_URL: str = "http://127.0.0.1:8080"
    FRONTEND_BASE_URL: str = "http://127.0.0.1:3000"

    # Security
    # I run the cmd in terminal for jwt - python -c "import secrets; print(secrets.token_hex(32))"
    JWT_SECRET: str = "7c2cc3691f3a204eec2909b69871f2a6a2463f1702b338aeac0d0799ede386f2"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # DB
    DATABASE_URL: str = "sqlite:///./backend.db"

    # Admin bootstrap
    BOOTSTRAP_ADMIN_EMAIL: str = "varshithagovindaswamy@gmail.com"
    BOOTSTRAP_ADMIN_PASSWORD: str = "Admin@12345"

    # SendGrid
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM: str = "no-reply@maverick.local"

    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_CONTAINER: str = "certifications"

    # Azure OpenAI
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-4o-mini"
    AI_ENABLED: bool = False

    # Scheduler
    REMINDER_JOB_INTERVAL_MINUTES: int = 60
    OVERDUE_AFTER_DAYS: int = 14


settings = Settings()

