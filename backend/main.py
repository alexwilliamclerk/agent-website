"""
面向计算机类职业学习者的目标能力诊断与个性化学习资源生成系统 - 后端入口
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from database import engine, Base, SessionLocal
from routers import auth, assessment, session, resource, path, jobs, record, material
from models.calibration import CalibrationRecord  # noqa: F401 - ensure table metadata is loaded
from models.material import UserMaterial  # noqa: F401 - ensure table metadata is loaded
from models.resource_bookmark import ResourceBookmark  # noqa: F401 - ensure table metadata is loaded
from models.session import SessionMessage  # noqa: F401 - ensure table metadata is loaded

# 自动创建数据库表
Base.metadata.create_all(bind=engine)


# ─── SQLite 迁移：老库补齐新增列（create_all 不会给已有表加列）───
def _ensure_columns(table: str, columns: dict[str, str]) -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        existing = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))]
        for col, dtype in columns.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}"))


_ensure_columns("assessments", {
    "gap_validation": "TEXT",
    "requirement_scores": "TEXT",
    "calibration_status": "VARCHAR(30)",
    "calibration_summary": "TEXT",
    "material_ids": "TEXT",
    "agent_trace": "TEXT",
})
_ensure_columns("resources", {
    "source_chunk_id": "VARCHAR(100)",
    "source_text": "TEXT",
    "source_title": "VARCHAR(255)",
    "source_score": "DECIMAL(6, 4)",
    "review_status": "VARCHAR(20)",
    "review_reason": "TEXT",
    "generation_method": "VARCHAR(20)",
    "is_legacy": "INTEGER DEFAULT 0",
    "assessment_id": "VARCHAR(36)",
})
_ensure_columns("learning_paths", {"assessment_id": "VARCHAR(36)"})
_ensure_columns("sessions", {
    "turn_count": "INTEGER DEFAULT 0",
    "minimum_turns": "INTEGER DEFAULT 2",
    "ready_for_diagnosis": "INTEGER DEFAULT 0",
    "review_state": "TEXT",
    "assessment_id": "VARCHAR(36)",
})

# ─── 种子数据：4个职业 ──────────────────────────────────

SEED_JOBS = [
    {
        "job_title": "前端开发工程师",
        "description": "负责Web前端界面的开发与维护，将UI设计转化为可交互的网页应用",
        "required_skills": ["HTML", "CSS", "JavaScript", "Vue", "React", "TypeScript", "浏览器原理", "响应式设计", "Webpack/Vite", "前端性能优化"],
    },
    {
        "job_title": "后端开发工程师",
        "description": "负责服务端架构设计与业务逻辑开发，为前端提供稳定高效的API服务",
        "required_skills": ["Python", "Java", "Spring Boot", "FastAPI", "MySQL", "Redis", "Linux", "系统设计", "并发编程", "API设计"],
    },
    {
        "job_title": "运维工程师",
        "description": "负责服务器、网络、中间件的部署与维护，保障线上服务的稳定运行",
        "required_skills": ["Linux", "Docker", "Kubernetes", "Nginx", "Shell脚本", "监控告警", "网络协议", "CI/CD", "日志管理", "故障排查"],
    },
    {
        "job_title": "产品经理",
        "description": "负责产品规划、需求分析与项目推进，连接用户需求与开发实现",
        "required_skills": ["需求分析", "用户研究", "产品设计", "数据分析", "项目推进", "竞品分析", "文档撰写", "沟通协调", "原型设计", "业务理解"],
    },
]


def seed_jobs():
    """如果 jobs 表为空，写入4个初始职业"""
    from models.job import Job

    db = SessionLocal()
    try:
        if db.query(Job).count() == 0:
            for j in SEED_JOBS:
                db.add(Job(**j))
            db.commit()
            print(f"[seed] 已写入 {len(SEED_JOBS)} 个职业到 jobs 表")
        else:
            print(f"[seed] jobs 表已有数据，跳过")
    finally:
        db.close()


seed_jobs()

# ─── 应用实例 ───────────────────────────────────────────

app = FastAPI(
    title="能力诊断与学习资源生成系统",
    description="面向计算机类职业学习者的目标能力诊断与个性化学习资源生成系统API",
    version="1.0.0",
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局验证错误处理
@app.exception_handler(ValidationError)
async def validation_exception_handler(request, exc):
    import traceback
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": f"数据校验失败: {exc}"})

# 注册路由
app.include_router(auth.router, prefix="/api/auth", tags=["用户认证"])
app.include_router(assessment.router, prefix="/api/assessment", tags=["能力评估"])
app.include_router(session.router, prefix="/api/session", tags=["学习会话"])
app.include_router(resource.router, prefix="/api/resource", tags=["学习资源"])
app.include_router(path.router, prefix="/api/path", tags=["学习路径"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["职业列表"])
app.include_router(record.router, prefix="/api/record", tags=["学习记录"])
app.include_router(material.router, prefix="/api/material", tags=["学习资料"])


@app.get("/")
def root():
    return {"message": "能力诊断与学习资源生成系统API"}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
