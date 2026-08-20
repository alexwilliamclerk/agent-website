from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # JWT配置
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24小时

    # 队友接口配置（暂不使用）
    AGENT_API_URL: str = "http://localhost:8001"
    GRAPH_API_URL: str = "http://localhost:8002"
    VECTOR_API_URL: str = "http://localhost:8003"

    class Config:
        env_file = ".env"


settings = Settings()
