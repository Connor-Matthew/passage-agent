# Web 搜索功能开发计划

## 目标

为文章创作流程增加一个可选的 Web 搜索能力：用户在创建文章时可以开启“联网搜索”，后端基于选题搜索最新资料，并将搜索结果注入标题、大纲、正文生成流程，提升文章时效性、事实性和可验证性。

## 当前结论

推荐采用 **AI 生成搜索查询 + Tavily 搜索 + 创建任务时搜索一次 + 数据库存储搜索上下文 + Prompt 注入复用** 的方案。

原因：

1. 项目环境变量里已经出现 `TAVILY_API_KEY`、`TAVILY_ENABLED`、`TAVILY_MAX_RESULTS`，说明之前已经预留过 Tavily 方向。
2. 当前文章生成是分阶段流程：创建任务、确认标题、确认大纲、生成正文之间会从数据库恢复状态，所以搜索结果必须持久化。
3. 搜索属于外部依赖，不能影响核心创作链路；搜索失败时应降级为普通创作。
4. 创建时先由 AI 把用户选题转换成事实型搜索 query，再搜索一次；这比机械搜索标题更准确，也比每个阶段重复搜索更省成本。

## 不做什么

本次不做以下内容：

- 不做多搜索引擎聚合。
- 不做用户自定义搜索关键词。
- 不做搜索结果人工编辑页面。
- 不做搜索结果缓存复用系统。
- 不改现有配图搜索、Pexels、Bing 表情包、Iconify 等逻辑。
- 不把搜索失败视为文章创建失败。

## 推荐交互

前端在文章创建页新增一个开关：

- 文案：`启用联网搜索（使用最新资料）`
- 默认：关闭
- 开启后：创建任务请求中携带 `enableWebSearch: true`

建议不做 VIP 限制，先全量开放验证价值。若后续 Tavily 成本明显上升，再增加额度或会员限制。

## 数据流

```text
用户开启联网搜索
  -> frontend /article/create 提交 enableWebSearch
  -> backend 创建 article 任务并保存 enableWebSearch
  -> phase1 前 AI 生成 searchQueries
  -> 使用 searchQueries 调用 Tavily
  -> 合并、去重、截断搜索结果
  -> 保存 webSearchContext 到 article 表
  -> 标题生成使用 webSearchContext
  -> 用户确认标题
  -> 大纲生成从 DB 读取并复用 webSearchContext
  -> 用户确认大纲
  -> 正文生成从 DB 读取并复用 webSearchContext
  -> 最终正文末尾生成参考资料
```

## 后端设计

### 1. 配置

修改 `python-backend/app/config.py`，增加 Tavily 配置：

- `tavily_api_key`
- `tavily_enabled`
- `tavily_max_results`
- `tavily_timeout`
- 可选：`tavily_search_url`

同步更新 `.env.example`。

### 2. 搜索关键词设计

不直接使用文章标题或爆款标题搜索。

原因：标题是面向传播的表达，往往包含悬念、情绪词和夸张修辞；搜索 query 应该面向事实、数据、案例和权威观点。如果机械搜索标题，结果容易变成同类营销文章，而不是可用于生成内容的可靠资料。

推荐新增一个轻量的 **Search Query Planner**。

它需要独立提示词，但第一版不建议做成主编排器里的正式 Agent，而是作为 `ArticleAgentService.prepare_web_search_context()` 内部的轻量 LLM 子步骤：

- 不进入 `ArticleAgentOrchestrator` 主流程。
- 不需要 SSE 流式展示。
- 不需要新增前端阶段。
- 可以通过 agent log 记录为 `search_query_planner`，方便排查生成了哪些 query。
- 后续如果搜索策略变复杂，再升级为 `app/agent/agents/search_query_planner.py` 这样的正式 Agent。

输入：

- `topic`
- `style`
- 未来可选：`userDescription`

输出：3-5 个搜索 query。

query 类型建议覆盖：

- `background`：背景、趋势、定义。
- `data`：数据、报告、统计。
- `case`：案例、公司实践、真实事件。
- `viewpoint`：专家观点、争议或不同立场。

提示词目标：

- 把用户选题转成事实型搜索 query。
- 避免生成爆款标题式、情绪化、悬念式搜索词。
- 优先生成容易搜到权威资料、报告、案例和数据的表达。
- 科技、商业、国际趋势类选题优先使用英文 query。
- 直接返回 JSON，不输出解释。

示例输出：

```json
{
  "queries": [
    {
      "type": "background",
      "query": "AI workplace automation trends 2026"
    },
    {
      "type": "data",
      "query": "generative AI productivity workplace report 2025"
    },
    {
      "type": "case",
      "query": "companies using generative AI employee workflow case study"
    }
  ]
}
```

第一版建议只在创建任务后、phase1 前生成一次 query。用户确认标题时填写的 `userDescription` 暂不触发二次搜索，避免流程复杂化。后续如果发现用户补充描述经常改变文章方向，再增加补搜机制。

### 3. 新增搜索服务

新增 `python-backend/app/services/tavily_search_service.py`。

职责：

- 判断 Tavily 是否启用。
- 接收 AI 生成的多个搜索 query。
- 使用 `httpx` 调用 Tavily Search API。
- 每个 query 拉取少量结果，合并后按 URL 去重。
- 返回结构化结果：`title`、`url`、`content`、`queryType`、`query`。
- 限制最终结果数量和 snippet 长度，避免 Prompt 过长。
- 捕获异常并返回空结果，不向上抛出导致文章失败。

### 4. Schema 扩展

修改 `python-backend/app/schemas/article.py`：

- `ArticleCreateRequest` 增加 `enable_web_search`，前端字段为 `enableWebSearch`。
- `ArticleState` 增加：
  - `enable_web_search`
  - `web_search_context`
- 如需文章详情展示来源，可在 `ArticleVO` 增加：
  - `enableWebSearch`
  - `webSearchContext`

建议详情页暂时不展示完整搜索上下文，只在最终正文中体现参考资料。

### 5. 数据库字段

修改 `python-backend/app/models/article.py`，为 `Article` 增加：

- `enableWebSearch`：是否启用联网搜索，默认 0。
- `webSearchContext`：搜索 query 和搜索结果 JSON 文本。

新增迁移文件：

- `sql/add_web_search_fields.sql`

同时考虑更新 `sql/create_table.sql`，保证新环境初始化时字段完整。

### 6. 路由和服务传参

修改：

- `python-backend/app/routers/article.py`
- `python-backend/app/services/article_service.py`
- `python-backend/app/services/article_async_service.py`

需要完成：

- `/article/create` 接收 `enableWebSearch`。
- 创建任务时保存该字段。
- phase1 启动时带上该字段。
- phase2 / phase3 从数据库恢复 `enableWebSearch` 和 `webSearchContext`。

### 7. 搜索时机

在 phase1 生成标题前执行搜索：

1. 如果 `enableWebSearch=false`，跳过。
2. 如果 Tavily 未配置或关闭，跳过。
3. 先调用 LLM 生成 3-5 个搜索 query。
4. 如果 query 生成失败，降级为使用 `topic` 作为唯一 query。
5. 使用 query 列表调用 Tavily。
6. 合并、去重、截断搜索结果。
7. 保存 query 和结果到 DB。
8. 如果搜索失败，记录日志并继续普通生成。

### 8. Prompt 注入

修改 `python-backend/app/constants/prompt.py`，新增 Web 搜索资料段落模板。

建议规则：

- 搜索资料仅作为事实参考。
- 不要编造来源。
- 使用资料中的时间、数据、事件、观点时要保持准确。
- 正文末尾增加「参考资料」，列出使用到的来源标题和 URL。
- 如果搜索资料为空，不要提及参考资料。

修改 `python-backend/app/services/article_agent_service.py`：

- Search Query Planner 生成搜索 query。
- 标题生成追加搜索上下文。
- 大纲生成追加搜索上下文。
- 正文生成追加搜索上下文。
- Agent 日志中记录是否启用搜索、生成的 query、搜索结果数量。

## 前端设计

修改 `frontend/src/pages/article/ArticleCreatePage.vue`：

- 增加 `enableWebSearch = ref(false)`。
- 在选题/风格区域附近增加开关或复选框。
- 创建文章时把 `enableWebSearch` 传给 `createArticle`。
- 重置创作时恢复为 `false`。
- 可在实时日志中提示：`已启用联网搜索，将参考最新资料生成文章`。

修改 `frontend/src/api/typings.d.ts`：

- `ArticleCreateRequest` 增加 `enableWebSearch?: boolean`。

## 是否新增 SSE 消息

本次建议先不新增强制 SSE 类型，减少改动面。

可以只在日志或后端 agent log 中记录搜索状态。若希望用户明显感知，可后续增加：

- `WEB_SEARCH_COMPLETE`
- `WEB_SEARCH_SKIPPED`
- `WEB_SEARCH_FAILED`

## 涉及文件

预计修改文件：

- `python-backend/app/config.py`
- `python-backend/app/services/tavily_search_service.py`
- `python-backend/app/schemas/article.py`
- `python-backend/app/models/article.py`
- `python-backend/app/routers/article.py`
- `python-backend/app/services/article_service.py`
- `python-backend/app/services/article_async_service.py`
- `python-backend/app/services/article_agent_service.py`
- `python-backend/app/constants/prompt.py`
- `frontend/src/pages/article/ArticleCreatePage.vue`
- `frontend/src/api/typings.d.ts`
- `.env.example`
- `sql/add_web_search_fields.sql`
- `sql/create_table.sql`

## 验证计划

### 后端验证

1. `enableWebSearch=false` 时，文章创建流程与当前一致。
2. `enableWebSearch=true` 且 Tavily 配置正确时：
   - phase1 前先生成搜索 query。
   - 使用 query 调用 Tavily 搜索。
   - `article.webSearchContext` 保存 query 和搜索结果。
   - 标题、大纲、正文 Prompt 中包含搜索资料。
   - 最终正文包含参考资料。
3. `enableWebSearch=true` 但 Tavily 未配置时：
   - 不报错。
   - 文章生成继续。
4. Tavily API 异常、超时、限流时：
   - 不报错中断创作。
   - 文章生成继续。

### 前端验证

1. 默认关闭联网搜索。
2. 开启后请求体包含 `enableWebSearch: true`。
3. 重置创作后开关恢复关闭。
4. 不影响原有风格选择和配图方式选择。

### 数据库验证

1. 旧文章默认 `enableWebSearch=0`。
2. 新文章开启搜索后保存 `enableWebSearch=1`。
3. `webSearchContext` 可被 phase2 / phase3 正确读取。

## 风险与应对

### 外部依赖失败

风险：Tavily API 不可用、超时、限流。

应对：搜索失败降级为空上下文，继续普通生成。

### Prompt 过长

风险：搜索 query 太多或搜索结果过多导致 Prompt 膨胀。

应对：限制 query 数量、每个 query 的搜索条数、最终结果总数，并截断每条 content。

### 事实污染

风险：搜索 query 设计不当或搜索结果质量不稳定，模型可能引用错误信息。

应对：Search Query Planner 要生成事实型 query，避免营销化标题词；Prompt 明确要求只使用来源中出现的事实，不编造来源。

### 成本增长

风险：所有用户启用后 Tavily 成本上升。

应对：默认关闭；后续可按会员、额度或每日次数限制。

## 回滚方案

如果上线后效果不好：

1. 将 `TAVILY_ENABLED=false`，立即关闭搜索能力。
2. 前端隐藏或禁用联网搜索开关。
3. 已新增数据库字段可保留，不影响旧流程。
4. 搜索上下文为空时所有 Prompt 逻辑应自动退化为原流程。

## 待确认问题

1. 最终文章是否必须展示「参考资料」？推荐展示。
2. 联网搜索是否所有用户可用？推荐所有用户可用，后续根据成本再限制。
3. 是否需要在创作进度中展示“联网搜索中/完成”？推荐第一版不做强 SSE，只做后端日志和最终效果。

## 建议实施顺序

1. 后端配置与 Tavily 服务。
2. 数据库字段与 schema 扩展。
3. 创建任务链路传递 `enableWebSearch`。
4. Search Query Planner 轻量 LLM 子步骤生成搜索 query。
5. phase1 使用 query 搜索并保存上下文。
6. phase2 / phase3 复用上下文。
7. Prompt 注入和参考资料规则。
8. 前端开关和类型更新。
9. 本地验证关闭、开启、query 生成失败、搜索失败降级四条路径。
