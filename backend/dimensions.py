"""
16维度能力模型 — 维度定义 + 岗位权重配比

给前端用的核心数据：
  DIMENSIONS      → 16个维度的名称/分类/描述
  JOB_WEIGHTS     → 4个岗位各自的维度权重（high / mid / low）
  label_vector()  → 把裸数值数组转成前端可直接渲染的带标签结构
"""

from typing import Literal

# ─── 维度定义 ───────────────────────────────────────────

WeightLevel = Literal["high", "mid", "low"]

DIMENSIONS = [
    {"index": 1,  "name": "编程基础",       "category": "通用基础", "desc": "变量、控制流、函数、面向对象等基础编程能力"},
    {"index": 2,  "name": "数据结构与算法",  "category": "通用基础", "desc": "数组、链表、树、图、排序、搜索等"},
    {"index": 3,  "name": "计算机网络",      "category": "通用基础", "desc": "TCP/IP、HTTP、DNS、网络拓扑等"},
    {"index": 4,  "name": "操作系统",        "category": "通用基础", "desc": "进程线程、内存管理、文件系统、Linux基础等"},
    {"index": 5,  "name": "前端技术",        "category": "专业方向", "desc": "HTML/CSS/JS、Vue/React、响应式、浏览器原理"},
    {"index": 6,  "name": "后端技术",        "category": "专业方向", "desc": "API设计、中间件、并发处理、框架（FastAPI/Spring等）"},
    {"index": 7,  "name": "数据库",          "category": "专业方向", "desc": "SQL/NoSQL、索引优化、事务、ER建模"},
    {"index": 8,  "name": "系统设计",        "category": "专业方向", "desc": "架构模式、微服务、高可用、容量规划"},
    {"index": 9,  "name": "运维部署",        "category": "专业方向", "desc": "CI/CD、容器化、监控告警、云服务"},
    {"index": 10, "name": "测试与质量",      "category": "专业方向", "desc": "单元测试、集成测试、自动化测试、代码审查"},
    {"index": 11, "name": "产品分析",        "category": "专业方向", "desc": "需求分析、用户研究、竞品分析、数据驱动决策"},
    {"index": 12, "name": "项目管理",        "category": "专业方向", "desc": "敏捷开发、进度管控、风险管理、跨团队协调"},
    {"index": 13, "name": "沟通表达",        "category": "综合素质", "desc": "文档写作、技术演讲、需求沟通、团队协作"},
    {"index": 14, "name": "逻辑思维",        "category": "综合素质", "desc": "抽象推理、问题拆解、批判性思维、模式识别"},
    {"index": 15, "name": "学习能力",        "category": "综合素质", "desc": "新技术上手速度、知识迁移、自我驱动学习"},
    {"index": 16, "name": "安全规范",        "category": "综合素质", "desc": "OWASP、加密认证、权限控制、安全编码"},
]

# ─── 岗位权重配比 ───────────────────────────────────────

# 每个岗位的维度权重映射: 高→核心能力  中→支撑能力  低→了解即可
# 前端 / 后端 / 运维 / 产品经理
JOB_WEIGHTS: dict[str, dict[str, WeightLevel]] = {
    "前端开发工程师": {
        "编程基础": "high", "数据结构与算法": "mid", "计算机网络": "mid", "操作系统": "low",
        "前端技术": "high", "后端技术": "mid", "数据库": "mid", "系统设计": "mid",
        "运维部署": "low", "测试与质量": "mid", "产品分析": "mid", "项目管理": "low",
        "沟通表达": "mid", "逻辑思维": "mid", "学习能力": "mid", "安全规范": "low",
    },
    "后端开发工程师": {
        "编程基础": "high", "数据结构与算法": "high", "计算机网络": "mid", "操作系统": "mid",
        "前端技术": "low", "后端技术": "high", "数据库": "high", "系统设计": "high",
        "运维部署": "mid", "测试与质量": "mid", "产品分析": "low", "项目管理": "low",
        "沟通表达": "low", "逻辑思维": "mid", "学习能力": "mid", "安全规范": "mid",
    },
    "运维工程师": {
        "编程基础": "mid", "数据结构与算法": "low", "计算机网络": "high", "操作系统": "high",
        "前端技术": "low", "后端技术": "mid", "数据库": "mid", "系统设计": "mid",
        "运维部署": "high", "测试与质量": "mid", "产品分析": "low", "项目管理": "low",
        "沟通表达": "low", "逻辑思维": "mid", "学习能力": "mid", "安全规范": "high",
    },
    "产品经理": {
        "编程基础": "low", "数据结构与算法": "low", "计算机网络": "low", "操作系统": "low",
        "前端技术": "mid", "后端技术": "low", "数据库": "low", "系统设计": "low",
        "运维部署": "low", "测试与质量": "low", "产品分析": "high", "项目管理": "high",
        "沟通表达": "high", "逻辑思维": "high", "学习能力": "mid", "安全规范": "low",
    },
}

# ─── 工具函数 ───────────────────────────────────────────

def label_vector(raw_vector: list[float], target_job: str | None = None) -> list[dict]:
    """
    把裸数值数组转成前端可用的带标签结构。

    输入:  [0.8, 0.6, ...]   (16个float，按索引对应 DIMENSIONS)
    输出:  [{"index":1, "name":"编程基础", "value":0.8, "weight":"high", "category":"通用基础"}, ...]

    如果传了 target_job，会自动附加该岗位的权重字段。
    """
    if len(raw_vector) != len(DIMENSIONS):
        raise ValueError(f"ability_vector 长度应为 {len(DIMENSIONS)}，实际为 {len(raw_vector)}")

    weights = JOB_WEIGHTS.get(target_job or "", {})

    return [
        {
            "index": dim["index"],
            "name": dim["name"],
            "value": round(v, 4),
            "weight": weights.get(dim["name"], "mid"),
            "category": dim["category"],
        }
        for dim, v in zip(DIMENSIONS, raw_vector)
    ]


# ─── 知识点 → 维度映射 ─────────────────────────────────

# 每个具体知识点归属于哪个能力维度
# 队友的 AI 生成新知识点时在此补充即可
KNOWLEDGE_POINT_DIMENSIONS: dict[str, str] = {
    # 编程基础
    "变量与类型": "编程基础", "控制流": "编程基础", "函数与模块": "编程基础",
    "面向对象": "编程基础", "异常处理": "编程基础",
    # 数据结构与算法
    "数组与链表": "数据结构与算法", "栈与队列": "数据结构与算法",
    "树与图": "数据结构与算法", "哈希表": "数据结构与算法",
    "排序算法": "数据结构与算法", "搜索算法": "数据结构与算法",
    "贪心算法": "数据结构与算法", "动态规划": "数据结构与算法",
    "递归与回溯": "数据结构与算法", "字符串算法": "数据结构与算法",
    # 计算机网络
    "TCP/IP": "计算机网络", "HTTP协议": "计算机网络", "DNS": "计算机网络",
    "网络安全基础": "计算机网络", "网络拓扑": "计算机网络",
    # 操作系统
    "进程与线程": "操作系统", "内存管理": "操作系统", "文件系统": "操作系统",
    "Linux基础": "操作系统", "死锁": "操作系统",
    # 前端技术
    "HTML": "前端技术", "CSS": "前端技术", "JavaScript": "前端技术",
    "Vue": "前端技术", "React": "前端技术", "浏览器原理": "前端技术",
    "响应式设计": "前端技术", "前端性能优化": "前端技术", "TypeScript": "前端技术",
    # 后端技术
    "API设计": "后端技术", "中间件": "后端技术", "并发编程": "后端技术",
    "Spring Boot": "后端技术", "FastAPI": "后端技术", "微服务": "后端技术",
    # 数据库
    "SQL基础": "数据库", "索引优化": "数据库", "事务与锁": "数据库",
    "NoSQL": "数据库", "ER建模": "数据库", "Redis": "数据库",
    # 系统设计
    "架构模式": "系统设计", "高可用设计": "系统设计", "容量规划": "系统设计",
    "分布式系统": "系统设计",
    # 运维部署
    "Docker": "运维部署", "Kubernetes": "运维部署", "CI/CD": "运维部署",
    "Nginx": "运维部署", "监控告警": "运维部署", "云服务": "运维部署",
    # 测试与质量
    "单元测试": "测试与质量", "集成测试": "测试与质量",
    "自动化测试": "测试与质量", "代码审查": "测试与质量",
    # 产品分析
    "需求分析": "产品分析", "用户研究": "产品分析", "竞品分析": "产品分析",
    "数据分析": "产品分析",
    # 项目管理
    "敏捷开发": "项目管理", "进度管控": "项目管理", "风险管理": "项目管理",
    "跨团队协作": "项目管理",
    # 沟通表达
    "技术写作": "沟通表达", "需求沟通": "沟通表达", "技术演讲": "沟通表达",
    # 逻辑思维
    "问题拆解": "逻辑思维", "抽象推理": "逻辑思维", "模式识别": "逻辑思维",
    # 学习能力
    "知识迁移": "学习能力", "新技术学习": "学习能力",
    # 安全规范
    "OWASP": "安全规范", "认证与授权": "安全规范", "安全编码": "安全规范",
    "权限控制": "安全规范", "加密基础": "安全规范",
}


def get_weight_for_knowledge(knowledge_point: str, target_job: str | None = None) -> WeightLevel:
    """
    根据知识点名称和岗位，返回该知识点对应维度的权重等级。

    链路: 知识点 → 维度名 → 岗位权重
    返回: "high" / "mid" / "low"（查不到默认 "mid"）
    """
    dimension = KNOWLEDGE_POINT_DIMENSIONS.get(knowledge_point)
    if not dimension:
        return "mid"

    weights = JOB_WEIGHTS.get(target_job or "", {})
    return weights.get(dimension, "mid")


def get_dimension_names() -> list[str]:
    """返回16个维度名称列表，方便前端做表头"""
    return [d["name"] for d in DIMENSIONS]


def get_weight_value(level: WeightLevel) -> float:
    """权重级别 → 数值，方便计算加权总分"""
    return {"high": 0.15, "mid": 0.07, "low": 0.03}[level]
