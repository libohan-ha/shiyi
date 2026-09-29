# Goal Document: 考研复习反馈与次日安排

## Go / No-Go
- **Judgment**: Go。用户已授权实现并创建 PR，合并由用户完成。
- **Reason**: 范围已明确，以现有 FSRS 和单条内容为基础做增量修改。

## Target Outcome
整题复习能记录是否独立完成和主要卡点；卡点可人工提炼为独立小任务。忘记/困难的短间隔统一留到次日，统计区分重复练习与跨日独立回忆，不设置强制复习时长。

## Goal Definition
- **Type**: product / delivery。
- **Boundary**: 评分与预览、复习反馈、关联任务录入与详情、统计、迁移和备份、说明及测试。
- **Non-goals**: 不重写 FSRS，不自动拆题，不自动把整题评分传播给关联任务，不要求清空或限时，不重做配额，不增加自动错因管控，不合并 PR。
- **Deferred work**: 考前规划、完整题库标签图谱、配额和队列排序重做。
- **Verification rule / Evidence source**: 隔离 SQLite API 测试、真实浏览器测试、迁移/备份往返测试、生产前端构建和 lint。
- **Pass criteria**: 新用例先出现预期失败，实现后全部通过；旧测试仍通过；无真实数据修改；PR 可由用户审阅。
- **Confidence note**: 测试证明行为和兼容性，不宣称已证明提分效果。
- **Judgment owner**: 自动化测试判定行为，用户决定合并和实际使用效果。

## Current State
- React + FastAPI + py-fsrs 6.3.2；已有四档评分、撤销、乐观锁、备份、统计。
- 已有学习步骤 1/10 分钟、重学 10 分钟，只有评分次数和混合成功率统计。
- 每题一个记忆状态，尚无本次独立完成/卡点与原题关联字段。
- 历史记录不得倒推为明确的独立完成结果；旧 API 调用和 v1 备份需要继续可用。

## Priority Rationale
先定义数据与行为测试，再落地次日规则和反馈，再做页面闭环与统计，最后跑迁移、备份和全量回归。

## Assumptions and Open Decisions
| Item | Status | Impact | Owner / Next step |
| --- | --- | --- | --- |
| 只调整 again/hard 的不足 24 小时间隔 | confirmed | good/easy 和已达到一天的间隔不变 | 实现共享规则 |
| “明天”采用用户学习时区的下一日 00:00 起可复习 | assumed | 不要求等到明天同一时刻；预览明确标为明天 | 文档和跨时区测试 |
| 整题是 kind=problem；网页明确选是否独立完成 | assumed | 旧 API 可省略为未知；非整题不显示整题控件 | 前后端验证 |
| 未独立完成需主要卡点，且与 again 对齐；困难表示独立完成但费力 | assumed | 不允许成功评分与未独立完成相矛盾 | 评分校验 |
| 每题每日第一次、且上次真实复习在更早学习日，才进入跨日指标 | assumed | 当日反复成功不掩盖首次失败；初学和撤销排除 | 隔离时间样例 |
| 90 分钟仅是常见习惯，不是硬性上限 | confirmed | 不增加时间预算/终止设置 | 维持现有自由复习 |

## Phases
### Phase 1: 行为测试与最小数据结构
- **Purpose / Entry**: 从干净的 origin/main 功能分支开始，锁定行为和兼容边界。
- **Rules**: 先写新测试并运行 RED；只用临时数据库；旧数据用 nullable/default 保留未知状态。
- **Todos**:
  - [x] 次日规则、反馈/关联权限、跨日统计和备份测试（API/tests；证明预期 RED）。
  - [x] 添加 review.independent_completed / blocker、item.source_item_id 迁移和兼容字段（schema/models；证明旧数据可迁移）。
- **Exit proof**: RED 失败是缺少目标行为，而非环境问题。
- **Stop condition**: 数据迁移需要删除历史或使用真实库。

### Phase 2: 次日调度与反馈闭环
- **Purpose / Entry**: 有明确失败测试后实现最小后端。
- **Rules**: 预览与提交共用规则；保持真实评分时间与 FSRS 状态；仅改下次 due；不批量改历史。
- **Todos**:
  - [x] 新卡和重学的 again/hard 短间隔改到下一学习日；撤销精确恢复（reviews；边界测试）。
  - [x] 独立完成/卡点入历史，校验矛盾反馈和内容版本（reviews/schemas；错误与重试测试）。
  - [x] 小任务关联原题、独立记忆状态、权限约束、备份 ID 重映射（library/backup；往返测试）。
- **Exit proof**: 后端新旧测试通过。
- **Stop condition**: 需要新增自动拆题或自动同步掌握度。

### Phase 3: 页面与真实学习统计
- **Purpose / Entry**: 数据契约稳定，页面完成端到端流程。
- **Rules**: 匹配已有样式；不强制逐考点评分；不强制拆题；不加依赖。
- **Todos**:
  - [x] 浏览器先验证 RED：整题反馈、未填卡点保护、明天提示、历史提炼任务（Review/ItemDetail/Editor/tests）。
  - [x] 显示用时、不同任务数、关联薄弱任务覆盖、跨日首次表现、仍不会列表、整题独立完成列表；旧混合成功率保留明确说明（stats/Dashboard/Statistics）。
  - [x] 桌面与手机端验证；旧的整题测试补上明确选择（e2e）。
- **Exit proof**: 新浏览器测试、构建和相关回归通过。
- **Stop condition**: 新控件破坏答题输入、重试或移动端评分。

### Phase 4: 验收与 PR
- **Rules**: 不碰真实库，不合并；更新 README/API；仅提交任务相关文件。
- **Todos**:
  - [x] 全量 pytest、ruff、TypeScript/Vite、Playwright；临时库迁移升级/降级。
  - [x] 审查 diff 和兼容行为，记录实际测试结果。
  - 提交、推送功能分支、创建中文 PR，提供测试证据和合并注意事项（由本 PR 交付，合并留给用户）。
- **Exit proof**: PR 地址和可复核测试结果。
- **Stop condition**: 测试失败未解决或推送权限不足；如实报告。

## Dry-Run Findings
- 明天不能机械按服务器时区或加 24 小时，应使用学习时区下一日。
- 备份必须重映射原题引用，不能把原数据库 ID 带到新条目。
- 旧独立完成字段为空不能当成“未完成”，否则统计会伪造历史。
- 新任务有自己的 CardState，不能由原题一次评分更新所有关联任务。
- 修改题目后的旧网页不能把原题反馈写到新题，网页评分需携带内容版本。

## Final Validation
`python -m pytest`、`ruff check`、`npm run build`、`npm run test:e2e`，以及独立临时数据库的 Alembic 往返。

## First Execution Step
编写并运行次日安排的 API 测试，确认旧实现返回分钟级 due，随后实现共享规则。

## Execution Evidence
- 已完成核心 API 的首轮 RED：`test_review_mechanics.py` 15 失败、4 通过，失败为分钟级 due 未延期、新反馈/关联字段被拒绝、学习结果字段缺失；随后相关18项通过。
- 已完成旧请求重试兼容 RED：升级前 payload hash 的重复请求返回409；忽略未填写的新字段参与哈希后通过。
- 学习结果页面先运行真实 Playwright RED：找不到“今日复盘收获”区域；加入结果摘要和明细后1项通过，含390px手机布局无横向溢出检查。
- 备份/迁移 RED：批量重建表导致合成旧卡片状态从2条变0；v2字段丢失、错误来源被接受、updated_at被改写。原生增删列和两阶段恢复后，38项新增迁移/备份测试通过。
- 整题前端 RED：缺少独立完成控件和提炼入口；另一个回归用例确认编辑整题后仍沿用旧反馈。实现控件和内容版本重置后，桌面/手机22项新用例通过。
- 集成浏览器回归曾发现新摘要挤走手机首屏分科入口；将摘要移到复习入口之后，保留原测试，重新全量通过。
- **最终 GREEN（2026-09-30）**：`./backend/.venv/Scripts/python.exe -m pytest backend/tests -q -c backend/pyproject.toml` → **81 passed**；`ruff check backend/app backend/tests backend/migrations scripts` → **All checks passed**；`npm --prefix frontend run build` → 通过；`npm --prefix frontend run test:e2e` → **42 passed, 1 skipped**。跳过项是既有的手机 Ctrl+滚轮用例，桌面版本已通过。`git diff --check` 通过。
- REFACTOR：不做额外结构重写；预览与提交复用 `schedule_review`，首页和统计页复用 `LearningOutcomes`。调整后均包含在上述全量验证中。
- **限制**：测试均使用临时 SQLite，未读取/迁移真实学习数据库。PostgreSQL只核查迁移SQL，未运行真实数据库集成测试。保留原有2项依赖弃用警告和Vite大文件提示，不混入依赖升级。
- **Next Behavior**：本轮范围完成；由用户审阅合并。
