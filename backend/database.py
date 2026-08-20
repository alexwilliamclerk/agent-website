from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 使用SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./capability_diagnosis.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
