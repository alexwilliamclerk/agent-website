# 真实结果校准 Agent

## 任务

将能力诊断 Agent 的 requirement-level 预测与客观题标准答案、编程题测试结果、项目实操结果或专家人工标注进行逐项比对。该阶段的结果用于评估 AI 判断是否接近真实结果，不能使用模型自报的 confidence 代替准确率。

## 输入

- `diagnosis.requirement_scores`：AI 对岗位能力项的预测分数；
- `gold_labels`：带 `requirement_id` 的可信标准结果；
- `reference_answer` 或 `actual_result`：可选的答案、测试日志或专家说明；
- `evidence_ids`：支撑 AI 预测的学习者资料证据；
- `apply_corrections`：是否允许使用可信标准结果生成校准后的诊断。

## 判定规则

1. 能力状态：分数 `>=0.70` 为达标，`0.40~0.69` 为部分达标，`<0.40` 为能力缺口。
2. 单项绝对误差 `<=0.10` 且状态一致，判定为通过。
3. 单项绝对误差 `0.10~0.20`，判定为需要复核。
4. 单项绝对误差 `>0.20` 或状态冲突，判定为不通过。
5. 准确率：正确能力项数 / 已标注能力项数。
6. 平均绝对误差：所有有分数标准的能力项绝对误差平均值。
7. 没有可信标准结果时，输出 `unvalidated`，不得伪造准确率。

## 输出

```json
{
  "status": "passed|needs_review|rejected|unvalidated",
  "accuracy": 0.0,
  "mean_absolute_error": 0.0,
  "evaluated_count": 0,
  "label_coverage": 0.0,
  "correction_applied": false,
  "records": [
    {
      "requirement_id": "backend.redis",
      "predicted_score": 0.0,
      "gold_score": 0.0,
      "absolute_error": 0.0,
      "predicted_status": "gap",
      "gold_status": "gap",
      "is_correct": true,
      "evidence_ids": []
    }
  ]
}
```
