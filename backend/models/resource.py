import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Text, Integer, Numeric, ForeignKey

from database import Base


class Resource(Base):
    __tablename__ = "resources"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String(36), ForeignKey("assessments.id"), nullable=True)  # 所属诊断，NULL=旧数据未绑定
    knowledge_point = Column(String(100), nullable=False, index=True)
    content_type = Column(String(20), nullable=False)  # 讲义, 练习, 案例, 视频脚本
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    difficulty = Column(Integer, nullable=True)  # 1-5
    source_chunk_id = Column(String(100), nullable=True)  # 引自的知识库片段 id
    source_text = Column(Text, nullable=True)  # 来源原文摘录
    source_title = Column(String(255), nullable=True)  # 来源标题
    source_score = Column(Numeric(6, 4), nullable=True)  # 检索分数
    review_status = Column(String(20), nullable=True)  # passed / partial / blocked / skipped
    review_reason = Column(Text, nullable=True)  # 校验结论 / 幻觉原因
    generation_method = Column(String(20), nullable=True)  # llm / rules / none，记录由 AI 生成还是规则兜底
    is_legacy = Column(Integer, default=0)  # 1=旧数据信任（视为有依据，待以后重新判定），仅后端隔离用
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def display_status(self) -> str:
        """Only reviewed, traceable resources may enter the learner-facing library."""
        normalized_type = str(self.content_type or "").strip().lower()
        if normalized_type in {"视频脚本", "video_script", "video script", "视频"}:
            return "hide"
        # partial 表示有来源且大部分内容有依据，作为“待复核资料”可展示；
        # 无依据、审核异常或缺少来源的资源仍然必须隐藏。
        if self.review_status not in {"passed", "partial"}:
            return "hide"
        if not str(self.source_chunk_id or "").strip() or not str(self.source_text or "").strip():
            return "hide"
        if int(self.is_legacy or 0) == 1:
            return "hide"
        return "show"
