# 职学导航：目标能力诊断与个性化培训资源生成系统

面向计算机类职业学习者的多 Agent 能力诊断、资料审查与个性化培训资源生成平台。

系统服务于已经明确目标岗位、但需要判断自身能力是否达标的学习者。用户提交学习描述、简历、项目材料和课程记录后，系统提取能力证据，对照岗位能力模型识别差距，再基于领域知识库生成学习路径与培训资源，并对生成内容进行来源校验。

> **本次交付重点：七 Agent 串行协同 + 精确上下文管理。**
> 项目不是把一段超长历史文本反复交给多个模型，而是为每个 Agent 建立独立的输入白名单、输出契约、上下文长度上限、证据来源链和可追踪快照。每一步只能读取上一步批准的结构化产物，未经校验的内容不得进入资源生成和前端展示。详细实现见 `backend/adapters/context_manager.py`，详细阶段契约见 `backend/workflow/serial-workflow.json` 和 `backend/prompts/`。

## 核心闭环

```text
选择目标岗位
  -> 第 1 轮资料描述与证据提取
  -> 资料审查 Agent 针对关键缺口追问
  -> 第 2 轮补充（或明确选择按当前资料进入诊断）
  -> 多 Agent 能力诊断
  -> 真实结果校准
  -> 生成学习路径与培训资源
  -> 知识库来源校验与审核纠偏
  -> 学习、收藏、完成记录与复测
```

当前内置四个数字技术岗位方向：

- 前端开发工程师
- 后端开发工程师
- 运维工程师
- 产品经理

## 已实现功能

### 用户与资料

- 用户注册、登录、JWT 身份认证和密码修改
- 诊断结果采用服务端 `active_assessment_id` 作为唯一当前记录：新诊断完成后自动切换到最新结果；用户选择历史诊断后，能力诊断与资料库共同切换并跨刷新保留
- PDF、Word、文本、代码和常见图片资料上传
- 用户资料解析、列表、下载和删除
- 自由文本学习经历补充
- 默认至少两轮资料审查：第一轮后自动提出一项关键问题；第二轮补充或“暂不补充”后才允许进入正式诊断
- `Session` 与 `SessionMessage` 持久化每轮学习者输入、Agent 追问和结构化摘要；刷新页面会从服务端恢复会话，而不是要求用户重新填写

### 诊断与 Agent

- 资料审查 Agent 的多轮对话准入：不新增第八个 Agent；第一轮固定追问，第二轮根据证据充分性放行或继续追问，用户可明确选择按当前资料进入诊断
- 七个 Agent 串行协作：学情解析、知识库检索、能力诊断、结果校验、真实结果准确率校准、资源生成、学习路径规划
- 16 维能力向量、能力矩阵、知识缺口和岗位匹配结果
- 基于客观题、实操结果或专家标注的真实结果校准
- 诊断页提供一键“自动证据校准”：后端直接读取该诊断已保存的多轮文本与能力证据，自动完成逐能力项连续误差复核，无需学习者填写 16 项表单
- 当前 Agent、阶段说明、百分比和最近事件实时展示
- Agent 执行轨迹与知识库检索来源查询

### 知识库与资源

- Qdrant 本地向量库与 BGE-M3 语义检索
- 讲义、练习、实操任务等个性化资源生成
- `source_chunk_id`、`source_text` 与生成资源绑定
- 生成内容与知识库原文分级比对：`passed` 直接发布，`partial` 标记待复核但允许展示，`blocked` 拦截
- 资源搜索、筛选、详情、收藏与取消收藏
- 开始学习、完成学习和真实学习进度记录

## 系统架构

| 层级 | 技术与职责 |
|---|---|
| 前端 | Vue 3、TypeScript、Vite、Pinia、Element Plus、ECharts |
| API | FastAPI 提供认证、资料、诊断、Agent、资源与学习记录接口 |
| 业务数据 | SQLAlchemy + SQLite；部署时可迁移至 PostgreSQL/MySQL |
| 向量检索 | Qdrant 本地存储岗位知识片段 |
| Embedding | BGE-M3 将查询与知识片段编码为向量 |
| Agent 编排 | Python 串行运行时、独立 Prompt、结构化 JSON 输出 |
| 大模型 | DeepSeek 或任意 OpenAI 兼容 API |
| 防幻觉 | 检索原文绑定、规则拦截和外部大模型二次校验 |

## Agent 工作流

```text
1. 自由文本学情解析 Agent
2. 岗位知识库检索 Agent
3. 岗位能力诊断 Agent
4. 诊断结果校验 Agent
5. 真实结果校准 Agent
6. 个性化资源生成 Agent
7. 个性化学习路径 Agent
```

七个 Agent 的代码入口、提示词和阶段接口如下：

> **数量口径说明：本系统固定为 7 个业务 Agent。** 路径规划 Agent 内部可以生成 8 个学习步骤，这 8 个步骤是学习任务节点，不是新增 Agent；资源生成后的知识库来源校验属于审核纠偏护栏，也不单独计数。

| 顺序 | Agent | Python 实现 | Prompt | 主要输出 |
|---|---|---|---|---|
| 1 | 自由文本学情解析 Agent | `InputParsingAgent.run()` | `prompts/01_parse_input.md` | 技能证据、正向技能、否定技能、未知技能 |
| 2 | 岗位知识库检索 Agent | `RAGEvidenceAgent.run()` | `prompts/02_retrieve_knowledge.md` | `source_chunk_id`、原文、检索分数 |
| 3 | 岗位能力诊断 Agent | `CapabilityScoringAgent.run()` | `prompts/03_diagnose_capability.md` | 16 维能力向量、能力缺口、置信度 |
| 4 | 诊断结果校验 Agent | `CalibrationAgent.run()` | `prompts/04_calibrate_result.md` | 字段、数值、证据链校验结果 |
| 5 | 真实结果校准 Agent | `GroundTruthCalibrationAgent.run()` | `prompts/05_calibrate_against_ground_truth.md` | 准确率、MAE、校准记录 |
| 6 | 个性化资源生成 Agent | `ResourceAgent.run()` | `prompts/05_generate_resource.md` | 讲义、练习或案例资源 |
| 7 | 个性化学习路径 Agent | `PathAgent.run()` | `prompts/06_plan_path.md` | 分阶段学习路径 |

这里的“七个接口”指七个 Agent 的内部 Python `run()` 阶段接口；对前端公开的是统一的业务 HTTP 接口。`POST /api/assessment/{id}/submit` 负责按顺序调度七个 Agent，`/calibrate`、`/progress` 和 `/agents` 分别负责真实结果校准、实时进度和轨迹查询，不把七个内部阶段强行拆成七个互不兼容的 HTTP 服务。

资源生成后的知识库来源校验属于防幻觉护栏，不另计为第八个 Agent：它由 `review_resources()` 和 `guardrail.py` 执行，负责检查 `source_chunk_id`、原文绑定、来源泄漏和生成内容一致性。审核采用分级 Gate，而不是所有非完全匹配内容一票否决：来源充分且结论一致的资源标记为 `passed`；有来源、核心内容一致但仍需人工确认的资源标记为 `partial`，可以在资料库展示并明确提示复核状态；只有缺少来源、与原文冲突、泄露原始切片或包含无法追溯的关键断言时才标记为 `blocked` 并禁止发布。外部审核模型不可用时会使用可复现的词项重合与来源绑定规则降级，不会把所有资源直接拦截；知识库完全没有可靠来源时，资源仍不得冒充正式可信内容。

### 精确上下文管理

多 Agent 不是把所有历史文本直接拼接给下一个模型，而是使用 `backend/adapters/context_manager.py` 建立有边界的上下文账本。每个阶段具有：

- `trace_id`、`stage`、`sequence`、`schema_version` 和 `prompt_version`，保证一次运行可追踪、可复现；
- 输入白名单，只接收本阶段需要的字段，禁止跨阶段读取用户原始资料、无关历史消息或其他 Agent 的内部推理；
- 文本、列表和知识片段数量上限，知识片段只保留 `source_chunk_id`、标题、分数和截断原文，避免上下文无限膨胀；
- 输出快照、`evidence_id`、`source_chunk_id` 和校准状态，形成阶段级证据链；
- 失败时保留失败阶段和输入摘要，允许重试或人工复核，不使用未经审核的中间结果。

上下文传递规则为“阶段产物白名单传递”：解析 Agent 只输出能力证据，检索 Agent 只输出知识来源，诊断 Agent 只输出能力判断，校验与真实结果校准 Agent 负责拦截错误，资源和路径 Agent 只能读取已批准的缺口与来源。完整上下文账本会写入 Agent 轨迹，供前端协同看板和测试文档核验。

#### 多轮对话上下文与自动追问

资料审查不再以“一段文字立刻诊断”的方式运行。它是 **Agent 1（自由文本学情解析 Agent）开始前的对话准入策略**，不增加新的业务 Agent，因此系统仍固定为 7 个 Agent。

```text
第 1 轮学习者描述
  -> review_dialogue.py 提取已知技能、实践证据、待补强项
  -> 固定选择一个最关键的证据缺口追问
第 2 轮学习者补充 / 明确“暂不补充”
  -> 写入 SessionMessage 和 review_state
  -> 满足条件后，提交接口从数据库重建上下文
  -> Agent 1 至 Agent 7 串行执行
```

- **自动获取上下文**：后端按 `session_id` 读取 `SessionMessage` 中的学习者原文、`review_state.summary` 和最近对话。前端只保存一个会话 ID 用于刷新后恢复，不能把浏览器拼接的聊天记录当作正式诊断依据。
- **精确上下文范围**：追问模型只能收到岗位名称、岗位技能、结构化摘要、最近 6 条消息和当前输入；正式诊断会纳入全部学习者轮次，并把固定字符预算均匀分配到各轮，同时附带 1 份不超过 1600 字的已确认摘要。它不会读取无关历史、其他 Agent 的内部推理或整库原文。
- **默认最少两轮**：第 1 轮即使内容完整也必须提问；第 2 轮后才可放行。用户点击“暂不补充”会作为第二轮明确记录，系统保留未补足证据并进入诊断，不虚构达标结论。
- **后端强制**：`POST /api/assessment/{id}/submit` 必须携带已完成的 `session_id`，否则返回 `409`；旧 `review-input` 仅作兼容预检，不能绕过两轮门槛。
- **可追溯性**：每次追问都会写入 `review_conversation` 上下文账本，包括 `trace_id`、输入白名单、结构化输出和缺口清单，供审查和测试记录核验。

置信度与准确率是两个不同指标：

- 置信度描述系统对单次诊断依据充分程度的估计。
- 准确率必须使用客观题、实操结果或专家标注作为真实值计算。
- 没有真实标注时，校准状态为 `unvalidated`，不会用置信度代替准确率。

诊断页的 `POST /api/assessment/{id}/auto-calibrate` 是面向学习者的一键自动证据复核：按钮点击后无需继续输入，系统只评价本轮明确提及的能力证据。能力连续分数采用 `±10 分` 自动复核容差带，之后按 `自动证据校准得分 = 45% × [1-max(0, MAE-0.10)] + 40% × 诊断置信度 + 15% × 显式证据覆盖率` 计算；旧版二元正确率保存在 `binary_item_accuracy` 中供审计。该指标会标记 `mode=automatic_evidence_review` 与 `is_ground_truth=false`，用于检查诊断和现有证据是否一致，不冒充比赛测试集上的真实准确率。比赛验收使用 `POST /api/assessment/{id}/calibrate`，以客观题、实操测试或专家标注为可信真值计算准确率与 MAE，真实准确率通过线仍保持为 90%。

历史诊断若因旧版审核门禁过严而没有可见资源，资料库会自动调用 `POST /api/assessment/{id}/repair-learning-package`。该接口只重建路径、知识库检索、学习正文和审核结果，保留原诊断分数、置信度及校准记录；旧学习包会在同一事务中替换，重建失败时回滚并保留原内容。

详细规则参见 [GROUND_TRUTH_CALIBRATION.md](GROUND_TRUTH_CALIBRATION.md)。

## 实时 Agent 进度

诊断执行期间，后端维护有界进度事件序列，前端约每 0.9 秒读取一次：

```http
GET /api/assessment/{assessment_id}/progress
```

响应示例：

```json
{
  "stage": "resource",
  "agent": "资源生成 Agent",
  "label": "正在生成学习资源 (3/8)",
  "percent": 68,
  "status": "running",
  "updated_at": "2026-08-17T05:00:00Z",
  "events": []
}
```

阶段包括 `material`、`retrieval`、`diagnosis`、`calibration`、`path`、`resource`、`review` 和 `complete`。失败时进度不会被清空，而是返回 `failed`，便于前端终止动画并提示重试。

> 当前进度事件保存在后端进程内，适用于本地演示和单 Worker 部署。采用多 Worker 或多服务器部署时，应将进度状态迁移到 Redis，并按 `assessment_id` 设置过期时间，避免负载均衡后读取到不同进程的数据。

## 登录与权限

- 后端业务接口通过 Bearer Token 校验当前用户。
- 用户只能读取和修改自己的评估、资料、资源收藏及学习记录。
- 首页与登录页允许公开访问。
- 资料审查、能力诊断、资料库、资源详情和个人中心默认需要登录。
- `GET /api/auth/me` 同时返回最新诊断和当前选中诊断；`PUT /api/auth/active-assessment` 用于选择历史记录。能力诊断页、资料库和学习路径均以当前选中诊断为同一数据作用域，禁止混用其他诊断的资源。
- 新诊断只有在能力分析、资源生成和审核纠偏全部提交成功后，才会成为当前记录。用户刷新能力诊断或资料库时会重新读取服务端状态，因此能立即切换到刚完成的新结果；没有新诊断或历史选择时，原结果保持不变。
- 七 Agent 正式流程按单个数据库事务发布：路径、资源或审核任一步失败都会回滚诊断结果，避免出现“诊断有分数、资料库却为空”的半成品状态。重复提交同一会话保持幂等，不会重复生成资源；失败时会释放已完成的两轮审查会话，用户可以直接重试正式诊断。
- `VITE_PUBLIC_PREVIEW=true` 只用于本地开发视觉验收；源码同时要求 `import.meta.env.DEV`，生产构建会强制关闭公开预览。
- 正式运行和生产构建始终启用登录认证，资料审查、能力诊断、资料库和资源详情不会因环境变量误配而公开。

生产环境必须设置新的 JWT 密钥：

```env
JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_EXPIRE_MINUTES=1440
CORS_ORIGINS=https://your-frontend.example.com
```

本地开发允许 `localhost` 和 `127.0.0.1` 的任意端口；对外部署必须通过 `CORS_ORIGINS` 明确填写前端域名，业务接口不接受未登录访问。

## 环境要求

- Python 3.10+
- Node.js 18+
- 约 3 GB 可用磁盘空间用于依赖和 BGE-M3
- DeepSeek 或其他 OpenAI 兼容 API Key（可选，但建议配置）

## 安装

### 后端

```bash
cd backend
python -m venv .venv
```

Windows：

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux/macOS：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

`FlagEmbedding` 会安装 PyTorch，下载时间和体积较大。网络受限时可使用可信镜像源。

### 前端

```bash
cd frontend
npm install
```

## LLM 配置

编辑 `backend/llm_config.json`：

```json
{
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-v4-flash",
  "api_key": "sk-your-api-key",
  "temperature": 0.7,
  "trust_env": false
}
```

该客户端兼容 OpenAI API 协议。切换模型服务时，需要同步验证模型名称、JSON 输出稳定性、上下文长度和计费策略。

不要把真实 API Key 提交到 Git。部署时建议通过密钥管理服务或环境挂载配置文件。

## 知识库准备

完整检索需要以下两部分：

1. `backend/qdrant_storage/`：Qdrant 本地集合，保存岗位知识向量与原始片段元数据。
2. `backend/bge-m3/`：BGE-M3 模型目录，约 2.2 GB，不随 Git 仓库分发。

从 Hugging Face 下载模型：

```bash
huggingface-cli download BAAI/bge-m3 --local-dir backend/bge-m3
```

国内网络可临时设置：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

缺少模型时后端仍可启动，但向量检索和资源来源质量会下降。不得把“接口可运行”当作“知识库已完整接入”。

## 启动

### 1. 启动后端

```bash
cd backend
python main.py
```

- API 地址：`http://localhost:8000`
- Swagger：`http://localhost:8000/docs`

### 2. 启动前端

```bash
cd frontend
npm run dev
```

- 页面地址：`http://localhost:5173`
- Vite 默认将 `/api` 代理到 `http://localhost:8000`
- 可用 `VITE_API_PROXY_TARGET` 指定其他后端地址

访问受保护页面前，需要先完成注册或登录。

## 主要 API

| 模块 | 接口 | 说明 |
|---|---|---|
| 认证 | `POST /api/auth/register` | 注册 |
| 认证 | `POST /api/auth/login` | 登录并获取 Token |
| 认证 | `GET /api/auth/me` | 当前用户 |
| 岗位 | `GET /api/jobs/list` | 岗位能力模型列表 |
| 资料 | `POST /api/material/upload` | 上传并解析资料 |
| 资料 | `POST /api/material/text` | 保存文本证据 |
| 评估 | `POST /api/assessment/create` | 创建评估 |
| 会话 | `POST /api/session/create` | 创建默认两轮的资料审查会话 |
| 会话 | `POST /api/session/{id}/review-turn` | 提交一轮资料，由资料审查 Agent 追问或放行 |
| 会话 | `GET /api/session/{id}/messages` | 恢复持久化的资料审查对话 |
| 评估 | `POST /api/assessment/{id}/submit` | 传入已完成 `session_id`，执行诊断与资源生成 |
| 评估 | `GET /api/assessment/{id}/progress` | 实时进度事件 |
| 评估 | `GET /api/assessment/{id}/agents` | Agent 轨迹与检索来源 |
| 校准 | `POST /api/assessment/{id}/calibrate` | 提交真实标注并校准 |
| 资源 | `GET /api/resource/list` | 用户资源列表 |
| 资源 | `GET /api/resource/search` | 搜索资源 |
| 收藏 | `POST /api/resource/{id}/bookmark` | 收藏资源 |
| 收藏 | `DELETE /api/resource/{id}/bookmark` | 取消收藏 |
| 学习 | `POST /api/record/resource/{id}/start` | 开始或继续学习 |
| 学习 | `PUT /api/record/{id}/complete` | 完成学习 |

## 数据与证据链

核心业务模型包括：

- `User`
- `Job`
- `UserMaterial`
- `Assessment`
- `CalibrationRecord`
- `LearningPath`
- `Resource`
- `ResourceBookmark`
- `LearningRecord`
- `Session`（学习会话）
- `SessionMessage`（资料审查的学习者 / Agent 轮次）

资源通过评估、能力缺口与知识库来源形成追溯关系：

```text
assessment_id
  -> requirement_id / gap_id
  -> source_chunk_id + source_text
  -> generated resource
  -> review_status + review_reason
```

## 项目结构

```text
PK-MACDM/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── llm_config.json
│   ├── adapters/
│   │   ├── agent_adapter.py
│   │   ├── agent_runtime.py
│   │   ├── calibration.py
│   │   ├── context_manager.py
│   │   ├── guardrail.py
│   │   ├── llm_client.py
│   │   ├── review_dialogue.py
│   │   └── vector_adapter.py
│   ├── models/
│   ├── prompts/
│   ├── routers/
│   ├── tests/
│   ├── qdrant_storage/
│   └── bge-m3/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── router/
│   │   ├── stores/
│   │   └── views/
│   └── vite.config.ts
├── GROUND_TRUTH_CALIBRATION.md
└── README.md
```

## 测试

后端：

```bash
cd backend
python -m pytest tests -q
```

前端：

```bash
cd frontend
npm run build
```

当前自动化测试覆盖校准数据持久化、资源收藏、学习进度、评估删除清理、Agent 进度事件、两轮对话准入、重复提交幂等、失败事务回滚、无效岗位拦截、零分诊断读取和跨用户资源隔离。比赛指标仍需使用独立测试集、人工标注和真实学习者样本计算，不能只引用单元测试通过率。

## 安全说明

- 不要提交真实 API Key、生产数据库、用户上传资料或 JWT 密钥。
- 防幻觉校验不能替代人工专家审核，尤其是代码安全、运维安全和职业评价结论。
- “准确率达到 90%”必须由有真实标签的独立测试集验证，不能由模型自报置信度得出。
- 对外部署前应增加 HTTPS、限流、日志脱敏、备份、上传文件校验和 Redis 共享任务状态。
