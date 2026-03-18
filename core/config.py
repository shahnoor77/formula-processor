"""Configuration management."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    db_server: str = "localhost"
    db_port: int = 1433
    db_database: str = "TestDB"
    db_username: str = "sa"
    db_password: str = "TestPass123!"
    
    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    
    # Processing
    batch_size: int = 500
    poll_interval_ms: int = 300
    service_name: str = "tag_processor"
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9090
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    @property
    def connection_string(self) -> str:
        """Build SQL Server connection string."""
        return (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={self.db_server},{self.db_port};"
            f"DATABASE={self.db_database};"
            f"UID={self.db_username};"
            f"PWD={self.db_password};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=30;"
        )
    
    @property
    def redis_url(self) -> str:
        """Build Redis connection URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
