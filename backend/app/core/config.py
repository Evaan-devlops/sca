from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    onetrust_base_url: str = "https://uat-de.onetrust.com"
    onetrust_login_url: str = "https://uat-de.onetrust.com/auth/login"
    onetrust_email: str = ""
    playwright_headless: bool = False
    playwright_user_data_dir: str = ".playwright/onetrust-profile"
    playwright_timeout_ms: int = 90000
    scan_timeout_ms: int = 300000
    debug: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
