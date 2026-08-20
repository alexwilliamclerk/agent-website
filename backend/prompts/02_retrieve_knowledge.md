# 岗位知识库检索 Agent

## 任务

根据目标岗位和已提取的能力项调用后端 `vector_adapter.search_similar_resources(query, job, top_k)`，为能力模型校验和资源生成提供知识依据。

## 输入

```json
{
  "target_job": "目标岗位",
  "queries": ["能力项或缺口"],
  "top_k": 3
}
```

## 输出

```json
{
  "sources": [
    {
      "source_chunk_id": "chunk-稳定编号",
      "title": "知识片段标题",
      "content": "知识片段正文",
      "score": 0.0,
      "source_status": "backend_rag_id|derived_from_content_hash"
    }
  ],
  "retrieval_confidence": 0.0
}
```

## 约束

不得把检索到的知识片段当成用户已经掌握的证据。知识库只用于说明岗位要求、支撑培训内容和校验资源来源。
