from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_server: str = "localhost"
    db_port: int = 1433
    db_database: str = "CorxNew"
    db_username: str = "sa"
    db_password: str = ""

    batch_size: int = 200
    poll_interval_ms: int = 1000
    service_name: str = "formula_processor"
    num_workers: int = 4

    db_pool_size: int = 5
    db_max_overflow: int = 10

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    table_source: str = "MQTT_OPC_UA_Data"
    table_variables: str = "Variables"
    table_executions: str = "Executions"
    table_failed_executions: str = "FailedExecutions"
    table_processing_state: str = "ProcessingState"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def connection_string(self) -> str:
        return (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={self.db_server},{self.db_port};"
            f"DATABASE={self.db_database};"
            f"UID={self.db_username};"
            f"PWD={self.db_password};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=30;"
        )


settings = Settings()
