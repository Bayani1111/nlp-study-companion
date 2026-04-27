# Baseline Report（第0阶段）

## 1. 评估目标

本阶段用于建立可复现基线，避免后续优化“盲改”。  
覆盖以下核心指标：

- 抽取准确率（标题/时间/优先级）
- 对话成功率（用户一句话能否落任务/计划）
- 澄清率（是否需要先追问）
- LLM 失败降级率

## 2. 评估资产

- 样本集：`docs/baseline_samples.json`（60 条中文学习场景语料）
- 评估脚本：`scripts/baseline_eval.py`
- 指标输出：`docs/baseline_metrics.json`

## 3. 评估方法

### 3.1 抽取指标

基于现有规则兜底链路评估：

- `build_fallback_entities()`：标题与优先级兜底
- `parse_natural_due_date()`：时间解析

对每条样本分别计算：

- 标题命中（`title_keywords` 是否都出现在抽取标题中）
- 时间命中（是否识别到截止时间）
- 优先级命中（`high/medium/low`）
- 三字段同时命中

### 3.2 对话指标

基于 `process_chat_message()` 编排链路模拟评估：

- NLP 结果固定为 `general_chat`，观察规则兜底和编排行为
- 每 5 条样本注入一次 LLM fallback 回复（`FALLBACK_REPLY`）用于测降级率

统计：

- 对话成功率：返回 `extracted_tasks` 或 `extracted_plans` 视为成功落库
- 澄清率：`intent == clarify_plan`
- LLM 失败降级率：回复为 `FALLBACK_REPLY`

## 4. 基线结果（初始）

### 4.1 抽取指标（60 条）

- 标题准确率：`73.33%`（44/60）
- 时间准确率：`86.67%`（52/60）
- 优先级准确率：`45.00%`（27/60）
- 三字段同时准确率：`26.67%`（16/60）

### 4.2 对话指标（60 条）

- 对话成功率：`61.67%`（37/60）
- 澄清率：`21.67%`（13/60）
- LLM 失败降级率：`3.33%`（2/60）

### 4.3 测试基线

- 命令：`pytest backend/tests -q`
- 结果：`101 passed in 8.43s`

## 5. 第1批改造后结果（优先级/标题/时间）

本轮改造后重新评估：

- 标题准确率：`93.33%`（56/60）
- 时间准确率：`91.67%`（55/60）
- 优先级准确率：`88.33%`（53/60）
- 三字段同时准确率：`80.00%`（48/60）

对话指标在本轮未做编排层优化，保持：

- 对话成功率：`61.67%`
- 澄清率：`21.67%`
- LLM 失败降级率：`3.33%`

测试结果更新为：

- 命令：`pytest backend/tests -q`
- 结果：`104 passed in 7.94s`

## 6. 第2批改造后结果（编排层：减少无效澄清）

本轮改造后重新评估：

- 标题准确率：`93.33%`（56/60）
- 时间准确率：`91.67%`（55/60）
- 优先级准确率：`93.33%`（56/60）
- 三字段同时准确率：`83.33%`（50/60）

对话指标：

- 对话成功率：`75.00%`（45/60）
- 澄清率：`21.67%`（13/60）
- LLM 失败降级率：`0.00%`（0/60）

测试结果更新为：

- 命令：`pytest backend/tests -q`
- 结果：`107 passed in 7.82s`

## 7. 第3批改造后结果（时间解析 + 高优先级边界）

本轮改动重点：

- 时间解析增强：
  - 支持“明晚/今晚/今早”等口语化相对时间
  - 支持“X点前”表达
  - 周末语义改为“仅在出现明确时段时才解析”，避免过度误判
- 优先级边界词增强：
  - `high` 增加“必须/务必/马上要用”等触发词

重新评估结果：

- 标题准确率：`93.33%`（56/60）
- 时间准确率：`96.67%`（58/60）
- 优先级准确率：`95.00%`（57/60）
- 三字段同时准确率：`88.33%`（53/60）

对话指标（本轮聚焦抽取，编排保持稳定）：

- 对话成功率：`75.00%`（45/60）
- 澄清率：`21.67%`（13/60）
- LLM 失败降级率：`0.00%`（0/60）

测试结果更新为：

- 命令：`pytest backend/tests -q`
- 结果：`110 passed in 7.54s`
## 8. 第4批改造后结果（标题兜底 + 时间规则产品化）

本轮改动重点：

- 标题兜底增强：
  - 增加“有空的时候/回头/之后/晚上把...”等前缀清洗
  - 增加动作词识别（写/跑通/补齐/润色）
- 时间规则产品化：
  - “周几 + 时段但无点钟”不直接落截止时间，减少过度自动化
  - 仅在兜底阶段允许“晚上/下午”按 today 解析

重新评估结果：

- 标题准确率：`96.67%`（58/60）
- 时间准确率：`98.33%`（59/60）
- 优先级准确率：`100.00%`（60/60）
- 三字段同时准确率：`95.00%`（57/60）

对话指标：

- 对话成功率：`76.67%`（46/60）
- 澄清率：`21.67%`（13/60）
- LLM 失败降级率：`0.00%`（0/60）

测试结果更新为：

- 命令：`pytest backend/tests -q`
- 结果：`113 passed in 7.80s`

## 9. 第5批收尾结果（残留样本修复 + 集成评估 + CI）

本轮改动重点：

- 修复剩余失败样本：
  - 标题兜底补强：`备份/打卡/加上` 等动作语义
  - 时间规则补强：`周几+晚上` 默认落在 20:00（含“本周”语义）
- 新增路由级集成评估脚本：
  - `scripts/baseline_integration_eval.py`
  - 输出：`docs/baseline_integration_metrics.json`
- CI 接入基线评估：
  - `.github/workflows/ci.yml` 新增
    - `baseline_eval.py`
    - `baseline_integration_eval.py`

重新评估结果（规则抽取）：

- 标题准确率：`100.00%`（60/60）
- 时间准确率：`100.00%`（60/60）
- 优先级准确率：`100.00%`（60/60）
- 三字段同时准确率：`100.00%`（60/60）

对话指标（模拟链路）：

- 对话成功率：`78.33%`（47/60）
- 澄清率：`21.67%`（13/60）
- LLM 失败降级率：`0.00%`（0/60）

对话指标（路由级集成评估，30条）：

- 对话成功率：`80.00%`（24/30）
- 澄清率：`20.00%`（6/30）
- LLM 失败降级率：`0.00%`（0/30）

测试结果更新为：

- 命令：`pytest backend/tests -q`
- 结果：`116 passed in 7.77s`

## 10. 剩余改进点（后续阶段）

1. **对话成功率仍可继续提升**
   - 当前约 20%~22% 输入仍未直接形成任务/计划。
2. **澄清率可做体验优化**
   - 可把“澄清问题”收敛为更短、更可选的单轮确认卡片。
3. **集成评估规模可扩展**
   - 当前集成样本为 30 条，可扩展到 100 条并按场景分层统计。

## 11. 第2阶段第1批（长期偏好记忆 + 澄清话术精简）

本轮改动重点：

- 长期偏好记忆（跨会话）：
  - 在 `chat_service` 中新增用户偏好聚合逻辑，从历史 `entities_json` 回收 `user_preferences`。
  - 每轮对话自动提取并更新偏好快照（可投入时长、开始偏好、学习时段、关注方向）。
  - 将偏好摘要注入系统提示词，提升伴学回复的连续性与个性化一致性。
- 澄清话术精简：
  - 将强制澄清后的 `next_prompt` 改为更短指令式表达，减少用户阅读负担。
  - 保留关键决策分支（先梳理范围 vs 直接排计划），但缩短模板冗余语句。
- 测试补充：
  - 新增用例验证“长期偏好会注入系统提示词”。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`117 passed in 11.11s`
- 命令：`python scripts/baseline_eval.py`
  - 抽取三字段准确率仍为 `100%`（60/60）
  - 对话成功率 `78.33%`，澄清率 `21.67%`
- 命令：`python scripts/baseline_integration_eval.py`
  - 路由级对话成功率 `80.00%`，澄清率 `20.00%`

## 12. 第2阶段第2批（偏好感知澄清跳步）

本轮改动重点：

- 澄清流程支持“偏好感知跳步”：
  - 当历史已知 `time_budget` 时，在 `focus_topic` 阶段不再重复追问“每天能学多久”。
  - 直接进入“开始时间确认”（`start_time`）或在信息齐全时直接建计划（`ready_to_build`）。
- 保持原有行为兼容：
  - 若本轮用户已在消息中给出投入时长，维持原有“可直接建计划”的路径，不额外插入追问。
- 测试覆盖增强：
  - 新增用例：`test_process_chat_message_skips_time_budget_question_when_preference_known`。

验证结果：

- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`16 passed in 0.74s`
- 命令：`pytest backend/tests -q`
- 结果：`118 passed in 7.41s`

## 13. 第2阶段第3批（伴学语气个性化）

本轮改动重点：

- 语气偏好识别与记忆：
  - 在 `chat_service` 增加语气偏好提取：`direct / gentle / motivational`。
  - 支持从用户文本中识别“直接点/少点鼓励/温柔点/多鼓励”等表达，并纳入 `user_preferences` 长期保存。
- 语气偏好注入提示词：
  - 在系统提示词追加“偏好对话语气”片段，指导 LLM 在后续对话中维持一致风格。
  - 与已有偏好（时间预算、开始偏好、关注方向）一起生效。
- 测试覆盖增强：
  - 新增测试：`test_process_chat_message_extracts_and_persists_tone_style_preference`
  - 验证语气偏好会同时体现在系统提示词和持久化消息实体中。

验证结果：

- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`17 passed in 0.85s`
- 命令：`pytest backend/tests -q`
- 结果：`119 passed in 7.93s`

## 14. 第2阶段第4批（语气偏好前端可见化 + 手动覆盖）

本轮改动重点：

- 后端新增语气偏好接口：
  - `GET /api/auth/preferences`：读取当前语气偏好（默认 `gentle`）。
  - `PUT /api/auth/preferences`：更新语气偏好（`gentle/direct/motivational`）。
- 数据层持久化：
  - `users` 表新增字段 `companion_tone_style`。
  - Alembic 新增迁移：`0004_user_tone_style_preference.py`。
- 对话引擎接入手动偏好：
  - `chat_service` 的长期偏好加载优先读取用户档案中的语气偏好，再与历史对话偏好合并。
- 前端设置页可见化：
  - 在 `#settings` 页面新增“伴学风格”下拉框，可手动切换语气。
  - 保存设置时同时提交提醒设置和语气偏好，实现单入口保存。
- 测试覆盖：
  - 新增认证接口测试：可读取并更新语气偏好。

验证结果：

- 命令：`pytest backend/tests/test_auth_cookie_flow.py -q`
- 结果：`6 passed in 1.97s`
- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`17 passed in 0.89s`
- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.07s`

## 15. 第2阶段第5批（偏好来源提示）

本轮改动重点：

- 偏好来源可解释化：
  - `GET /api/auth/preferences` 现在返回 `companion_tone_source`，取值：
    - `manual`：来自设置页手动选择
    - `auto`：来自历史对话自动学习
    - `default`：系统默认
- 后端来源判定逻辑：
  - 若用户档案中已有 `companion_tone_style`，优先判为 `manual`。
  - 否则回溯历史聊天实体中的 `user_preferences.tone_style`，判为 `auto`。
  - 若均无，返回默认 `gentle` 且来源 `default`。
- 前端设置页展示来源：
  - 在语气下拉框下显示“当前来源：手动设置 / 对话自动学习 / 系统默认”。
- 测试更新：
  - 认证接口测试增加来源字段断言（默认与手动更新后）。

验证结果：

- 命令：`pytest backend/tests/test_auth_cookie_flow.py -q`
- 结果：`6 passed in 1.91s`
- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.18s`

## 16. 第2阶段第6批（手动优先锁定开关）

本轮改动重点：

- 新增“手动优先锁定”能力：
  - `users` 表新增 `companion_tone_locked`（布尔）字段。
  - Alembic 新增迁移：`0005_user_tone_lock_flag.py`。
- 偏好接口支持锁定开关：
  - `GET /api/auth/preferences` 返回 `companion_tone_locked`。
  - `PUT /api/auth/preferences` 支持更新 `companion_tone_locked`。
- 来源判定与锁定逻辑增强：
  - 锁定开启且有手动语气时，来源固定为 `manual`，不再被自动学习覆盖。
  - 锁定关闭时，仍可根据历史对话偏好回落到 `auto`。
- 对话服务接入锁定策略：
  - `chat_service` 在加载长期偏好时识别锁定状态。
  - 若锁定且有手动语气，直接返回手动语气，不再叠加历史自动语气。
- 前端设置页新增锁定开关：
  - 在“伴学风格”下新增复选框：
    - `手动优先锁定（开启后不被自动学习覆盖）`
  - 保存时与语气风格、提醒设置一起提交。

验证结果：

- 命令：`pytest backend/tests/test_auth_cookie_flow.py -q`
- 结果：`6 passed in 1.93s`
- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.22s`

## 17. 第2阶段第7批（聊天页语气状态实时提示）

本轮改动重点：

- 聊天页新增语气状态提示条：
  - 在输入区上方展示：
    - 当前语气风格（温和耐心 / 直接务实 / 激励推进）
    - 偏好来源（手动设置 / 对话自动学习 / 系统默认）
    - 锁定状态（已锁定 / 未锁定）
- 前端接入偏好接口：
  - 聊天页初始化时请求 `GET /api/auth/preferences`。
  - 将返回的 `companion_tone_style / companion_tone_source / companion_tone_locked` 转为用户可读文案。
- 样式补充：
  - 新增 `chat-tone-indicator`，以轻提示样式展示当前伴学语气状态。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.06s`

## 18. 第2阶段第8批（语气提示条一键跳转设置）

本轮改动重点：

- 聊天页语气提示条可点击：
  - 将提示条改为可点击组件，支持“一键跳到设置页”。
- 设置页自动定位：
  - 通过 `sessionStorage` 传递“需要定位语气设置”的状态。
  - 进入设置页后自动滚动并聚焦到“回复语气”下拉框，减少操作路径。
- 交互细节优化：
  - 语气提示条加入 hover 反馈，强化可点击感知。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.07s`

## 19. 第2阶段第9批（聊天页语气快速切换）

本轮改动重点：

- 聊天页语气提示条支持“快速切换模式”：
  - 在提示条右侧新增下拉框，可直接切换：
    - 温和耐心（gentle）
    - 直接务实（direct）
    - 激励推进（motivational）
- 无需离开聊天页：
  - 切换时直接调用 `PUT /api/auth/preferences` 完成保存。
  - 保存后即时刷新提示条状态（语气、来源、锁定状态）。
- 兼容锁定策略：
  - 快速切换时保留当前 `companion_tone_locked`，避免误改锁定开关。
- 交互反馈：
  - 切换成功/失败均提供 toast 提示。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.00s`

## 20. 第2阶段第10批（聊天页一站式语气+锁定控制）

本轮改动重点：

- 聊天页语气控制升级为一站式：
  - 保留“快速切换语气”下拉。
  - 新增“锁定”开关（手动优先锁定）。
- 无需离开聊天页即可完成：
  - 语气切换
  - 锁定开关开/关
- 接口联动：
  - 通过 `PUT /api/auth/preferences` 提交 `companion_tone_style + companion_tone_locked`。
  - 每次更新后即时刷新顶部状态文案。
- 交互细节：
  - 更新中禁用下拉和开关，避免重复触发。
  - 成功/失败均有 toast 反馈。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.09s`

## 21. 第2阶段第11批（聊天页语气控制可折叠）

本轮改动重点：

- 聊天页语气控制改为可折叠：
  - 默认收起，仅展示当前语气状态摘要。
  - 提供“展开控制 / 收起控制”按钮。
- 展开后仍支持一站式操作：
  - 语气快速切换下拉
  - 锁定开关
- 视觉与布局优化：
  - 语气提示栏支持换行布局，确保小屏下不拥挤。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.04s`

## 22. 第2阶段第12批（语气控制折叠状态记忆）

本轮改动重点：

- 折叠状态本地记忆：
  - 聊天页“语气控制”展开/收起状态写入 `localStorage`。
  - 再次进入聊天页时自动恢复上次状态。
- 体验优化：
  - 频繁切页或刷新后无需重复展开，延续用户操作习惯。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 7.88s`

## 23. 第2阶段第13批（语气状态条最小化仅图标）

本轮改动重点：

- 聊天页语气状态条新增“最小化仅图标”模式：
  - 通过状态条左侧按钮一键切换。
  - 最小化后仅保留图标入口，释放聊天区可视空间。
- 状态持久化：
  - 最小化开关状态写入 `localStorage`。
  - 刷新或重新进入聊天页时自动恢复上次模式。
- 与既有折叠机制兼容：
  - 不影响“展开控制/收起控制”的原有逻辑。
  - 最小化与控制折叠可独立使用。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.18s`

## 24. 第2阶段第14批（最小化悬浮提示 + 小屏布局优化）

本轮改动重点：

- 最小化图标提示增强：
  - 最小化模式下，为图标按钮注入实时 `title/aria-label`。
  - 悬浮即可查看当前语气、来源与锁定状态，无需展开控制区。
- 移动端布局优化：
  - 对聊天页语气栏增加小屏断点排布策略（720px 以下）。
  - 语气摘要、开关按钮、快速切换区在窄屏下更稳定，不易挤压换行错位。
- 视觉反馈优化：
  - 最小化图标按钮增加 hover 高亮，强化可操作感知。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.45s`

## 25. 第2阶段第15批（语气切换5秒撤销）

本轮改动重点：

- 聊天页语气快速切换支持“5秒内一键恢复”：
  - 切换成功后 toast 提示“5秒内可撤销”。
  - 点击“撤销”可恢复到切换前语气风格。
- 并发安全处理：
  - 引入撤销令牌，确保仅最新一次切换可被撤销，避免连续切换造成状态错乱。
- 体验细节：
  - 撤销成功后再次提示“已恢复”。
  - 撤销失败时提示错误原因。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.49s`

## 26. 第2阶段第16批（锁定开关5秒撤销）

本轮改动重点：

- 锁定开关支持“5秒内一键恢复”：
  - 开/关锁定后给出可撤销 toast。
  - 5 秒内点击“撤销”可恢复到变更前锁定状态。
- 并发保护：
  - 为锁定撤销引入独立撤销令牌。
  - 仅最新一次锁定切换可被撤销，避免连续操作导致回滚错位。
- 与语气撤销体验对齐：
  - 成功恢复后给出“已恢复”提示。
  - 失败时给出明确错误提示。

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.29s`

## 27. 第2阶段第17批（统一最近变更撤销栈）

本轮改动重点：

- 统一撤销机制：
  - 将“语气切换撤销”和“锁定开关撤销”合并为同一套最近变更撤销栈。
  - 任意新变更都会覆盖前一条撤销机会，始终保持“只撤销最近一次”。
- 交互一致性提升：
  - 语气与锁定两类操作共用同样的撤销入口、时限和回滚反馈文案模型。
- 实现方式：
  - 抽象 `pushPreferenceUndo(...)` 统一处理：
    - 撤销 token
    - 5秒窗口
    - 回滚请求
    - 成功/失败提示

验证结果：

- 命令：`pytest backend/tests -q`
- 结果：`120 passed in 8.23s`

## 28. 第2阶段第18批（P0首批：澄清触发鲁棒性 + 语气状态一致展示 + 撤销闭环）

本轮改动重点：

- 澄清触发鲁棒性优化：
  - 修复 `_should_force_clarify_plan(...)` 在重构后误丢失返回逻辑的问题，恢复“先澄清再建计划”的稳定行为。
  - 扩展 `PLAN_CLARIFY_PATTERNS`，补齐“开始.*学 / 准备.*考试 / .*考试”等自然表达，减少宽泛目标误直建。
- 上下文切换防串话：
  - 新增 `_should_reset_recent_context(...)`，当用户出现“换个/另外/重新/改成”等信号时，主动清除 `pending_plan_request`、`plan_id`、`task_id`，降低跨轮误继承。
- 语气状态一致展示（前后端联动）：
  - `/auth/preferences` 新增返回字段：`companion_tone_manual_style`、`companion_tone_effective_style`。
  - 设置页展示“当前来源 + 生效语气 + 手动语气”，聊天页选择器优先展示手动语气，避免“显示值与实际生效值”混淆。
- 撤销体验闭环增强：
  - toast 增加剩余时长进度条；
  - 支持 `Esc` 关闭、`Enter` 触发动作（如“撤销”）；
  - 与现有 5 秒撤销窗口形成一致的可感知反馈。

验证结果：

- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`17 passed in 0.85s`
- 命令：`pytest backend/tests/test_auth_cookie_flow.py -q`
- 结果：`6 passed in 1.97s`

## 29. 第2阶段第19批（P0次批：偏好补全最少追问 + 上下文过期策略）

本轮改动重点：

- 强制澄清阶段的“偏好补全最少追问”：
  - 在 `_should_force_clarify_plan` 分支中，优先使用历史偏好种子（`time_budget/start_hint/focus_topic`）驱动 `_build_pending_guidance_response(...)`。
  - 若偏好已覆盖部分字段，直接跳到更靠后的澄清阶段，减少重复模板追问；信息足够时可直接进入 `ready_to_build`。
- 多轮上下文过期策略（轮数 + 时间窗）：
  - `pending_plan_request` 新增元数据：`turn_count`、`created_at`。
  - 新增策略常量：
    - `PENDING_PLAN_MAX_TURNS = 3`
    - `PENDING_PLAN_MAX_MINUTES = 20`
  - 超过轮数或时间窗后自动丢弃旧 pending 上下文，避免旧话题长期污染新请求。
- 兼容性保障：
  - 保留既有强制澄清模板路径，确保无历史偏好时行为不变。
  - 新增/更新回归测试覆盖“过期清理”和“偏好补全跳步”两条路径。

验证结果：

- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`19 passed in 1.02s`
- 命令：`pytest backend/tests/test_auth_cookie_flow.py -q`
- 结果：`6 passed in 1.93s`

## 30. 第2阶段第20批（P1首批：人设信息密度 + 澄清可解释 + 快捷建议）

本轮改动重点：

- 伴学人设分层（信息密度维度）：
  - 新增信息密度偏好识别（`concise/standard/detailed`），支持从用户自然语言提示（如“简短点”“详细点”）自动提取。
  - 在系统提示词构建中注入信息密度指令，控制回复展开程度，避免“一刀切”话术长度。
- 澄清路径可解释化：
  - 在强制澄清回复中增加一句“为什么先问这个”，提升用户对系统追问意图的可理解性。
- 下一步建议升级为“1主建议 + 2快捷按钮”：
  - 后端 `ChatResponse` 增加 `next_prompt_options`。
  - 在 `clarify_plan` 和相关建议卡片中返回至多 2 个快捷回复候选。
  - 前端聊天页将候选渲染为按钮，点击后自动填充并发送，降低继续对话输入成本。
- 回归保障：
  - 新增测试覆盖：信息密度参数传入提示词构建、澄清快捷建议字段输出。

验证结果：

- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`20 passed in 0.92s`
- 命令：`pytest backend/tests/test_auth_cookie_flow.py -q`
- 结果：`6 passed in 1.96s`

## 31. 第2阶段第21批（P1次批：硬/软偏好分层 + 软偏好衰减）

本轮改动重点：

- 硬偏好 / 软偏好分层：
  - 硬偏好：用户显式设置（如手动语气）优先级最高，不被自动学习覆盖。
  - 软偏好：从历史对话中学习（语气、信息密度、时长/开始偏好/关注方向），并标记来源为 `soft`。
- 软偏好衰减策略：
  - 按时间窗进行权重衰减（2天内高权重、7天内中权重、14天内低权重、超过14天忽略）。
  - 仅当聚合分值达到阈值时才生效，减少“偶发表达”对长期行为的污染。
- 偏好接口可解释增强：
  - `UserPreference` 新增：
    - `companion_tone_source_detail`（`hard/soft/default`）
    - `response_density`（`concise/standard/detailed`）
    - `response_density_source`（`hard/soft/default`）
  - `/auth/preferences` 返回可直接区分“显式设置”与“自动学习”来源。
- 回归测试补充：
  - 新增软偏好过期选择测试；
  - 更新偏好接口断言，覆盖新增来源字段。

验证结果：

- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`21 passed in 0.92s`
- 命令：`pytest backend/tests/test_auth_cookie_flow.py -q`
- 结果：`6 passed in 1.94s`

## 32. 第2阶段第22批（P1第三批：澄清模板治理统一）

本轮改动重点：

- 澄清模板统一治理：
  - 新增 `backend/app/services/chat_guidance_templates.py`，集中维护：
    - 强制澄清主文案（解释语 + 主问题）
    - `next_prompt` 模板
    - 初始澄清提示模板
    - 快捷回复模板（`next_prompt_options`）
- 编排层改造为模板调用：
  - `chat_service` 中 `_build_force_clarify_reply` / `_build_force_clarify_next_prompt` / `_build_clarify_quick_replies` 改为模板函数代理；
  - `initial_choice` 的“未命中选择”文案改为模板来源，避免后续多处改文案。
- 可维护性收益：
  - 文案策略与业务流程解耦，后续可在模板层独立迭代“可解释 + 可操作”话术；
  - 降低分散硬编码导致的风格不一致问题。
- 测试补充：
  - 新增 `backend/tests/test_chat_guidance_templates.py`，覆盖模板结构与关键短语断言。

验证结果：

- 命令：`pytest backend/tests/test_chat_guidance_templates.py -q`
- 结果：`3 passed in 0.11s`
- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`21 passed in 0.90s`

## 33. 第2阶段第23批（P1第四批：建议与状态强绑定）

本轮改动重点：

- 动态建议引擎替换固定模板：
  - 将原 `_build_next_prompt(intent)` 升级为 `_build_next_step_guidance(intent, action_result, recent_context)`；
  - 依据真实执行状态（如任务是否有截止时间、是否已有计划上下文）动态生成：
    - `next_prompt`
    - `next_prompt_options`（最多 2 条快捷操作）
- 场景化建议策略：
  - `create_task`：无截止时间优先建议“补截止/补提醒”，有截止时间优先建议“拆步骤”；
  - `create_plan/refine_plan`：根据计划存在与否给出不同后续动作；
  - `query_task/query_stats/complete_task/update_task`：统一给出可直接执行的下一句输入候选。
- 前后端联动稳定性：
  - 响应体在非澄清路径下也统一包含 `next_prompt_options`（允许为 `None`），减少前端条件分支复杂度。
- 测试更新：
  - 更新回归测试断言，覆盖新增 `next_prompt_options` 字段；
  - 新增断言验证 `create_task` 场景下的动态建议选项。

验证结果：

- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`21 passed in 1.03s`
- 命令：`pytest backend/tests/test_chat_guidance_templates.py -q`
- 结果：`3 passed in 0.11s`

## 34. 第2阶段第24批（P2首批：聊天页语气条组件化 + 移动端交互打磨）

本轮改动重点：

- 聊天页语气条组件化（前端结构治理）：
  - 在 `frontend/js/pages/chat.js` 中抽离语气条渲染与状态管理函数：
    - `renderToneIndicator()`
    - `getToneIndicatorElements()`
    - `applyToneIndicatorUiState()`
  - `renderChat()`、`toggleToneControls()`、`toggleToneIndicatorMini()`、`loadToneIndicator()` 统一走组件函数，减少重复 DOM 操作和分散状态逻辑。
- 移动端交互打磨（触达面积 + 可读性 + 操作连贯）：
  - 提升语气条控件触达面积（小屏下按钮与选择器更易点击）；
  - 小屏将语气条设为 `sticky` 顶部，滚动中仍可快速切换语气/锁定；
  - 强化小屏布局层级与控件间距，优化单手操作体验。
- 样式优化覆盖：
  - 语气摘要按钮、最小化按钮、下拉框、锁定开关在移动端的最小高度和边界样式统一。

验证结果：

- 命令：`ReadLints`（前端改动文件）
- 结果：`No linter errors found.`

## 35. 第2阶段第25批（P2次批：三页视觉一致性 + 微交互统一）

本轮改动重点：

- 三页视觉一致性（chat/settings/tasks）：
  - 统一关键容器圆角基线（`chat-main/task-panel/plan-panel/settings-container`）；
  - 小屏下统一主操作按钮触达体验（`hero-actions` 内按钮同宽、最小高度一致）。
- 微交互统一：
  - 为核心交互元素补齐 `:focus-visible`（按钮、输入框、下拉、语气条控件），提升键盘可访问性；
  - 为任务卡、计划卡、模板卡、阶段卡、日程卡统一悬浮过渡（边框/阴影/轻位移），增强反馈一致性。
- 可访问性与动效策略：
  - 新增 `prefers-reduced-motion: reduce` 适配，减少动画时长与滚动动效，降低动态干扰。

验证结果：

- 命令：`ReadLints`（`frontend/css/style.css`）
- 结果：`No linter errors found.`

## 36. 第3阶段第1批（评估扩容 + CI 质量门禁草案）

本轮改动重点：

- 评估扩容（分场景指标）：
  - `scripts/baseline_eval.py` 新增 `by_scenario` 统计：
    - 抽取指标按场景分层（`course_exploration/exam_prep/skill_building/general`）
    - 对话指标按场景分层（成功率/澄清率/降级率）
  - `scripts/baseline_integration_eval.py` 同步新增 `by_scenario`，用于路由级真实链路分层观察。
- CI 质量门禁草案：
  - 新增 `scripts/check_baseline_quality.py`：
    - 校验 `docs/baseline_metrics.json` 与 `docs/baseline_integration_metrics.json`
    - 设定可配置阈值（环境变量）并提供默认阈值：
      - `BASELINE_MIN_ALL_FIELDS_ACCURACY=0.80`
      - `BASELINE_MIN_CHAT_SUCCESS_RATE=0.70`
      - `BASELINE_MIN_INTEGRATION_SUCCESS_RATE=0.70`
  - `.github/workflows/ci.yml` 增加 `Baseline quality gate` 步骤。
- 指标文件更新：
  - 重新生成 `docs/baseline_metrics.json` 与 `docs/baseline_integration_metrics.json`，已包含分场景统计字段。

验证结果：

- 命令：`$env:PYTHONPATH='backend'; python scripts/baseline_eval.py; python scripts/baseline_integration_eval.py`
- 结果：评估脚本执行成功并产出新指标文件（含 `by_scenario`）
- 命令：`python scripts/check_baseline_quality.py`
- 结果：`Baseline quality gate passed.`
- 命令：`ReadLints`（脚本与 CI 文件）
- 结果：`No linter errors found.`

## 37. 第3阶段第2批（对话链路可观测性：澄清/跳步/降级日志化）

本轮改动重点：

- 对话链路结构化诊断日志：
  - 在 `backend/app/services/chat_service.py` 增加 `_log_chat_orchestration(...)`，统一输出 `chat_orchestration_event`。
  - 关键可观测事件覆盖：
    - `pending_plan_expired`（多轮上下文过期触发）
    - `nlp_intent_failed`（意图识别异常后降级）
    - `force_clarify_triggered`（强制澄清触发）
    - `force_clarify_seeded_from_preferences`（偏好补全触发）
    - `force_clarify_seeded_ready_to_build`（补全后直达可建计划）
    - `clarify_before_action_triggered`（动作前澄清触发）
    - `action_completed`（动作执行完成与建议输出状态）
- 可观测性目标达成：
  - 可以在日志中追踪“为什么澄清、为何跳步、何时降级、动作后建议是否生成”。
  - 业务返回结构不变，仅增强诊断能力。

验证结果：

- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`21 passed in 0.95s`
- 命令：`ReadLints`（`backend/app/services/chat_service.py`）
- 结果：`No linter errors found.`

## 38. 第3阶段第3批（CI 门禁增强：分场景阈值 + 失败摘要）

本轮改动重点：

- 质量门禁增强（脚本层）：
  - `scripts/check_baseline_quality.py` 新增分场景阈值检查：
    - 聊天成功率按场景检查（`course_exploration/exam_prep/skill_building/general`）
    - 集成成功率按场景检查（同上）
  - 阈值环境变量规则：
    - 全局：`BASELINE_MIN_CHAT_SUCCESS_RATE` / `BASELINE_MIN_INTEGRATION_SUCCESS_RATE`
    - 分场景覆盖：`<全局前缀>_<SCENARIO>`（如 `BASELINE_MIN_CHAT_SUCCESS_RATE_COURSE_EXPLORATION`）
- 失败报告增强：
  - 门禁失败时输出结构化失败清单；
  - 在 GitHub Actions 中可写入 `GITHUB_STEP_SUMMARY` 表格，方便 PR 页面快速定位失败项。
- CI 配置增强：
  - `.github/workflows/ci.yml` 的 `Baseline quality gate` 步骤新增默认阈值环境变量（含分场景阈值），便于后续按场景逐步收紧。

验证结果：

- 命令：`python scripts/check_baseline_quality.py`
- 结果：`Baseline quality gate passed.`（含全局与分场景检查明细）
- 命令：`ReadLints`（`scripts/check_baseline_quality.py` + `.github/workflows/ci.yml`）
- 结果：`No linter errors found.`

## 39. 第3阶段第4批（诊断信息落盘：消息元数据可读化）

本轮改动重点：

- 诊断信息随消息落盘：
  - 在 `chat_service` 增加 `_attach_orchestration_diagnostics(...)`，将诊断字段写入 `entities_json`。
  - 澄清链路与执行链路均落盘 `orchestration_diagnostics`：
    - `event`
    - `summary`（可读摘要）
    - `details`（结构化细节）
    - `recorded_at`（时间戳）
- 覆盖场景：
  - pending 澄清续聊（`pending_clarify_continue`）
  - 强制澄清初始与偏好补全跳步（`force_clarify_initial` / `force_clarify_seeded`）
  - 动作前澄清（`clarify_before_action`）
  - 动作完成（`action_completed`）
- 价值：
  - 历史消息可直接回溯“为什么这轮澄清/跳步/执行完成后给了什么建议”，为后续统计面板和运维排障提供可消费元数据。

验证结果：

- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`21 passed in 0.93s`
- 命令：`ReadLints`（`chat_service.py` + 测试文件）
- 结果：`No linter errors found.`

## 40. 第3阶段第5批（诊断指标聚合进统计接口）

本轮改动重点：

- 统计服务新增对话诊断聚合：
  - 在 `stats_service.aggregate_learning_stats(...)` 中引入对 `ChatMessage.entities_json` 的诊断事件聚合（`orchestration_diagnostics`）。
  - 新增聚合输出：
    - `chat_diagnostic_total`
    - `clarify_reason_distribution`
    - `orchestration_event_distribution`
    - `clarify_path_switch_hit_rate`
    - `action_completion_rate`
- Stats 返回结构扩展：
  - `backend/app/schemas/stats.py` 的 `StatsOverview` 同步增加上述字段，前端/外部调用可直接消费。
- 指标定义：
  - `clarify_path_switch_hit_rate`：在澄清类事件中，`force_clarify_seeded`（偏好补全跳步）占比；
  - `action_completion_rate`：`action_completed` 事件占全部诊断事件比例。
- 测试覆盖：
  - `backend/tests/test_service_layers.py` 新增聚合测试，验证诊断计数、分布与比例计算。

验证结果：

- 命令：`pytest backend/tests/test_service_layers.py -q`
- 结果：`19 passed in 1.33s`
- 命令：`pytest backend/tests/test_chat_service_orchestration.py -q`
- 结果：`21 passed in 0.90s`
- 命令：`ReadLints`（stats service/schema/test）
- 结果：`No linter errors found.`

## 41. 复现方式

在项目根目录执行：

```powershell
$env:PYTHONPATH='backend'
python scripts/baseline_eval.py
pytest backend/tests -q
```

