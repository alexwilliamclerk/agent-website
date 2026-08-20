# 真实结果校准与前端准确率展示说明

## 1. 这次增加了什么

本版本在原有“结构校正 Agent”和“资源防幻觉校验”之外，增加了“真实结果校准 Agent”。它解决的是一个独立问题：**AI 的置信度不能代表 AI 的准确率**。

- 置信度：模型对自己判断的把握程度，只能作为辅助信号。
- 准确率：将 AI 对每个能力要求的预测，与客观题、实操结果、专家标注或可信参考答案逐项比较后计算。
- 防幻觉：检查生成资源是否能被检索到的知识库来源支持，与能力诊断准确率不是同一指标。

没有真实标注时，校准状态为 `unvalidated`，准确率和平均绝对误差显示为 `null`，前端显示“未校验”，不会用置信度替代准确率。

## 2. 串行位置

当前测评流程为：

```text
用户输入
  -> 输入资料审查 Agent
  -> 学情解析 Agent
  -> 知识库检索 Agent
  -> 能力诊断 Agent
  -> 结构校正 Agent
  -> 真实结果校准 Agent（本次新增）
  -> 能力缺口验证
  -> 资源生成 Agent
  -> 资源防幻觉校验
  -> 学习路径生成 Agent
```

真实结果校准 Agent 只负责评价和可选纠正，不负责自行创造“标准答案”。因此，比赛测试时必须为测试样本准备可信的 `gold_labels`；没有标注只能说明“尚未验证”，不能宣称达到 90% 准确率。

## 3. 计算规则

每个能力要求都有稳定的 `requirement_id`，例如 `backend.redis`。系统把 AI 结果整理为：

```json
{
  "requirement_id": "backend.redis",
  "requirement_name": "Redis",
  "dimension": "后端技术",
  "score": 0.72,
  "status": "partial",
  "evidence_ids": ["ev-001"]
}
```

真实标注示例：

```json
{
  "requirement_id": "backend.redis",
  "gold_score": 0.65,
  "source_type": "unit_test",
  "reference_answer": "能够完成缓存读写，并能说明缓存失效处理方式。",
  "trusted": true
}
```

逐项计算：

```text
absolute_error_i = |predicted_score_i - gold_score_i|
score_correct_i = 1（absolute_error_i <= 0.10），否则为 0
status_correct_i = 1（预测状态 = 真实状态），否则为 0
```

汇总计算：

```text
判定准确率 = score_correct 项数 / 有效标注项数
状态准确率 = status_correct 项数 / 有效标注项数
平均绝对误差 MAE = Σ absolute_error_i / 有效标注项数
标注覆盖率 = 有效标注项数 / AI 输出能力项数
```

默认验收阈值：判定准确率 `>= 0.90` 且 MAE `<= 0.10` 为 `passed`；判定准确率 `>= 0.75` 且 MAE `<= 0.20` 为 `needs_review`；否则为 `rejected`。阈值是评估规则，不是把结果强行抬高到目标值。

当 `apply_corrections=true` 且标注 `trusted=true` 时，系统才允许用真实标注修正该能力项分数，并重新计算能力向量、综合掌握度和能力缺口。未验证或不可信标注只记录，不改变诊断结果。

## 4. 后端接口

### 4.1 提交测评时同时校准

```http
POST /api/assessment/{assessment_id}/submit
Content-Type: application/json
```

```json
{
  "user_input": "我会使用 Redis 开发并完成缓存项目，能够实现缓存读写和问题排查。",
  "gold_labels": [
    {
      "requirement_id": "backend.redis",
      "gold_score": 0.65,
      "source_type": "practical_task",
      "reference_answer": "完成缓存读写、过期策略和异常排查。",
      "trusted": true
    }
  ],
  "apply_corrections": false
}
```

### 4.2 对已经完成的测评补录真实结果

```http
POST /api/assessment/{assessment_id}/calibrate
Content-Type: application/json
```

请求体为：

```json
{
  "gold_labels": [
    {
      "requirement_id": "backend.redis",
      "gold_score": 0.65,
      "source_type": "expert",
      "reference_answer": "专家依据实操结果给出的能力等级。",
      "trusted": true
    }
  ],
  "apply_corrections": true
}
```

返回结果中的关键字段：

```json
{
  "calibration": {
    "status": "passed",
    "evaluated_count": 1,
    "accuracy": 1.0,
    "status_accuracy": 1.0,
    "mean_absolute_error": 0.07,
    "correction_applied": true
  },
  "diagnosis_updated": true
}
```

### 4.3 查询校准详情

```http
GET /api/assessment/{assessment_id}/calibration
```

该接口返回汇总指标和逐能力项记录，便于前端、评委演示页和测试文档取数。

## 5. 数据保存

`assessments` 表保存一次测评的汇总结果：

- `requirement_scores`：AI 对各能力要求的原始或校正后分数；
- `calibration_status`：`unvalidated / passed / needs_review / rejected`；
- `calibration_summary`：准确率、状态准确率、MAE、覆盖率和校正状态。

`calibration_records` 表保存逐项证据：

- `assessment_id`、`requirement_id`：定位测评和能力要求；
- `predicted_score`、`gold_score`、`absolute_error`：计算误差；
- `predicted_status`、`gold_status`、`is_correct`：计算状态判定准确率；
- `source_type`、`trusted`、`reference_answer`：说明真实结果来源；
- `evidence_ids`、`details`、`calibration_version`：保留可追溯信息和版本。

## 6. 前端展示规则

诊断结果页的“准确率校准”卡片固定展示：

1. 已比对能力项：有效真实标注项数；
2. 判定准确率：分数误差不超过 0.10 的能力项比例；
3. 状态准确率：`qualified / partial / gap / unknown` 判定一致比例；
4. 平均绝对误差：AI 分数与真实分数的平均差异。

未提交真实标注时，三项指标显示 `—`，并提示“当前只有 AI 诊断结果，尚未接入客观题、实操或专家标注”。点击“录入真实结果”后，可为每个能力项录入 0 到 1 的真实分数，并选择是否用可信标注修正诊断。

前端文案必须明确：**置信度是模型自评，准确率来自真实结果对照，二者不能互换。**

## 7. 比赛测试数据建议

每个职业方向至少准备三类画像：基础薄弱型、概念掌握但实践不足型、项目与实操证据充分型。每个样本至少保留：

- 用户输入原文；
- AI 预测的 `requirement_scores`；
- 客观题或实操任务结果；
- 专家标注或标准答案；
- 校准汇总与逐项记录；
- 是否应用校正；
- 人工复核备注。

最终测试文档中应使用所有样本的逐项记录计算总体准确率，而不是挑选单个高分样本。推荐报告：样本数、有效能力项数、判定准确率、状态准确率、MAE、标注覆盖率和人工复核通过率。

## 8. 与防幻觉的边界

真实结果校准用于回答“能力判断是否接近真实情况”；防幻觉校验用于回答“生成内容是否有知识库依据”。生成资源仍然必须保留 `source_chunk_id`，并通过知识库原文校验。准确率校准不能替代 RAG 来源校验，RAG 来源校验也不能替代真实结果校准。
