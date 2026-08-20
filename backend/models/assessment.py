import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, JSON, Numeric, Text, ForeignKey

from database import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False)
    user_input = Column(Text, nullable=True)  # 用户自由文本输入
    overall_mastery = Column(Numeric(5, 4), nullable=True)
    ability_vector = Column(JSON, nullable=True)  # 16个维度的值
    ability_matrix = Column(JSON, nullable=True)  # 能力达标矩阵 [{ability, target, evidence, status}, ...]
    knowledge_gaps = Column(JSON, nullable=True)  # 薄弱知识点
    gap_validation = Column(JSON, nullable=True)  # 缺口校验明细 [{gap, status, reason}]
    confidence = Column(Numeric(5, 4), nullable=True)
    requirement_scores = Column(JSON, nullable=True)  # requirement_id 级别预测，供真实结果校准
    calibration_status = Column(String(30), nullable=True, default="unvalidated")
    calibration_summary = Column(JSON, nullable=True)
    material_ids = Column(JSON, nullable=True)  # 本次诊断使用的资料 id 列表
    agent_trace = Column(JSON, nullable=True)  # 可视化 Agent 执行轨迹，不保存原始密钥或模型上下文
    created_at = Column(DateTime, default=datetime.utcnow)
