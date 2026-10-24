from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "shopper"
    db_user: str = "shopper"
    db_password: str = ""

    # Optional. Without it the agent falls back to keyword matching.
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
