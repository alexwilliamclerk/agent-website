# 串行提示词包

这些提示词是 PK-MACDM 后端接入 DeepSeek/Qwen 时的唯一提示词源。运行顺序由 `workflow/serial-workflow.json` 固定，不能由模型自行改变。

## 拼接顺序

每个节点的最终请求按以下顺序组装：

```text
00_shared_output_rules.md
→ 当前节点 Prompt
→ 程序注入的结构化 JSON 输入
→ 当前节点输出契约
```

模型返回后必须先执行 JSON 解析、字段校验和来源 ID 校验，再写入后续节点输入。

后端模型适配器必须使用 `prompt_registry.build_serial_prompt(stage_id, state)`。
该函数只会把当前阶段在 `serial-workflow.json` 中声明的输入字段传给模型，并且
在上游字段缺失时直接抛错，不能退回到把整份用户状态拼成一个总 Prompt 的做法。

## 重要边界

当前 `agent_runtime.py` 是无外部 API 的确定性运行时，使用这些提示词的 DeepSeek 调用应由后端模型适配器完成。提示词文件不能被视为“已经接入模型”；联调时必须在日志中记录 `prompt_version`、请求耗时、重试次数和模型返回校验结果。
