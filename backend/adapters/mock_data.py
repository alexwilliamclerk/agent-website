# Mock数据 - 队友接口未就绪时使用
# 注意：ability_vector 这里是裸数组（模拟队友原始返回），
# agent_adapter.diagnose() 会通过 label_vector() 给数组加上维度名称和岗位权重

MOCK_DIAGNOSIS = {
    "overall_mastery": 0.72,
    "ability_vector": [0.8, 0.6, 0.9, 0.7, 0.5, 0.8, 0.6, 0.9, 0.7, 0.8, 0.6, 0.5, 0.9, 0.7, 0.8, 0.6],
    "ability_matrix": [
        {"ability": "HTML/CSS", "target": "精通", "evidence": "做过电商网站和博客系统", "status": "已达标"},
        {"ability": "JavaScript", "target": "精通", "evidence": "熟悉JS基础语法", "status": "部分达标"},
        {"ability": "Vue框架", "target": "熟练", "evidence": "有项目经验", "status": "已达标"},
        {"ability": "算法与数据结构", "target": "掌握", "evidence": "学过计算机网络和数据结构", "status": "证据不足"},
    ],
    "knowledge_gaps": ["贪心算法", "动态规划"],
    "confidence": 0.85,
}

MOCK_RESOURCE = {
    "content_type": "讲义",
    "title": "贪心算法入门指南",
    "body": "贪心算法是一种在每一步选择中都采取在当前状态下最好或最优的选择，从而希望导致结果是最好或最优的算法。",
    "difficulty": 3,
    "gap_id": "gap_001",
    "source_chunk_id": "chunk_algo_001",
}

# 按资源类型提供不同 Mock，让前端能区分讲义和练习
MOCK_RESOURCE_BY_TYPE = {
    "讲义": {
        "content_type": "讲义",
        "title": "贪心算法入门指南",
        "body": "贪心算法是一种在每一步选择中都采取在当前状态下最好或最优的选择，从而希望导致结果是最好或最优的算法。",
        "difficulty": 3,
        "gap_id": "gap_001",
        "source_chunk_id": "chunk_algo_001",
    },
    "练习": {
        "content_type": "练习",
        "title": "贪心算法练习题",
        "body": "1. 给定一组区间，用贪心算法找出最大不相交子集。\n2. 用贪心策略解决活动安排问题。\n3. 证明贪心选择性质在找零钱问题中的正确性。",
        "difficulty": 4,
        "gap_id": "gap_001",
        "source_chunk_id": "chunk_algo_002",
    },
    "案例": {
        "content_type": "案例",
        "title": "贪心算法工程实战",
        "body": "在路由协议OSPF中，Dijkstra算法（贪心策略）用于计算最短路径树。每轮选择距离最小的未访问节点。",
        "difficulty": 3,
        "gap_id": "gap_002",
        "source_chunk_id": "chunk_algo_003",
    },
    "视频脚本": {
        "content_type": "视频脚本",
        "title": "贪心算法可视化讲解",
        "body": "[开场] 贪心算法，就是每一步都做当下最好的选择。\n[示例] 假设你在找零钱，每次拿最大面额的硬币...",
        "difficulty": 2,
        "gap_id": "gap_001",
        "source_chunk_id": "chunk_algo_004",
    },
}

MOCK_PATH = [
    {"step": 1, "knowledge_point": "贪心算法", "resource_type": "讲义", "estimated_time": 30, "prerequisite": "基础算法"},
    {"step": 2, "knowledge_point": "动态规划", "resource_type": "练习", "estimated_time": 45, "prerequisite": "贪心算法"},
]

MOCK_KNOWLEDGE_RELATIONS = {
    "concept": "贪心算法",
    "prerequisites": ["基础算法", "排序算法"],
    "next_concepts": ["动态规划", "图算法"],
    "related_skills": ["问题分解", "最优子结构"],
}

MOCK_JOB_SKILLS = {
    "job": "前端开发工程师",
    "core_skills": ["HTML", "CSS", "JavaScript", "React", "Vue"],
    "skill_dependencies": [
        {"from": "HTML", "to": "CSS"},
        {"from": "JavaScript", "to": "React"},
    ],
}

MOCK_REVIEW_RESULT = {
    "review_result": "passed",
    "risk_level": "low",
    "issues": [],
    "suggestion": "可以进入正式推荐",
    "checked_source": True,
    "checked_gap": True,
    "checked_hallucination": True,
}

MOCK_SIMILAR_CASES = [
    {
        "case_id": "case_001",
        "similarity": 0.92,
        "user_profile": {"target_job": "前端开发", "study_months": 6},
        "learning_outcome": "成功入职",
    }
]
