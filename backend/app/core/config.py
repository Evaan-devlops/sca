from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    onetrust_base_url: str = Field(
        default="https://uat-de.onetrust.com",
        validation_alias="ONETRUST_BASE_URL",
    )
    onetrust_login_url: str = Field(
        default="https://uat-de.onetrust.com/auth/login",
        validation_alias="ONETRUST_LOGIN_URL",
    )
    onetrust_email: str = Field(
        default="",
        validation_alias="ONETRUST_EMAIL",
    )
    playwright_headless: bool = Field(
        default=False,
        validation_alias="PLAYWRIGHT_HEADLESS",
    )
    playwright_user_data_dir: str = Field(
        default=".playwright/onetrust-profile",
        validation_alias="PLAYWRIGHT_USER_DATA_DIR",
    )
    playwright_timeout_ms: int = Field(
        default=90000,
        validation_alias="PLAYWRIGHT_TIMEOUT_MS",
    )
    onetrust_scan_timeout_ms: int = Field(
        default=300000,
        validation_alias="ONETRUST_SCAN_TIMEOUT_MS",
    )
    onetrust_website_table_timeout_ms: int = Field(
        default=120000,
        validation_alias="ONETRUST_WEBSITE_TABLE_TIMEOUT_MS",
    )
    debug: bool = Field(
        default=False,
        validation_alias="ONETRUST_DEBUG",
    )
    onetrust_manual_login_timeout_ms: int = Field(
        default=600000,
        validation_alias="ONETRUST_MANUAL_LOGIN_TIMEOUT_MS",
    )
    onetrust_iam_username: str = Field(
        default="",
        validation_alias="ONETRUST_IAM_USERNAME",
    )


settings = Settings()
