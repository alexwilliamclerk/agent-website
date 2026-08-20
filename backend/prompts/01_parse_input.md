# 自由文本学情解析 Agent

## 任务

从一段用户自由文本中提取目标岗位相关的技能陈述、实践动作、明确否定和可回溯原文片段。

## 输入

```json
{
  "user_id": "string",
  "target_job": "前端开发工程师|后端开发工程师|运维工程师|产品经理",
  "user_input": "用户的一段自由文本",
  "career_skills": ["岗位能力项"]
}
```

## 输出

```json
{
  "evidence_records": [
    {
      "evidence_id": "evidence_xxx",
      "requirement_id": "稳定能力编号",
      "material_id": "user_input",
      "evidence_type": "self_report|practice|explicit_negative",
      "excerpt": "必须来自用户原文",
      "confidence": 0.0
    }
  ],
  "matched_skills": ["已明确提及技能"],
  "negative_skills": ["明确不会的技能"],
  "unknown_skills": ["未提及技能"]
}
```

## 约束

“会 Java，不会 Redis”只能产生 Java 的正向证据和 Redis 的明确负向证据，不能把 Spring Boot、MySQL、Docker 批量判为不会。
