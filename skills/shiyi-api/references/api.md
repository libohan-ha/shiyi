# 拾忆 API 与 Skills v2 参考

业务路径相对 `/api/v1`；健康检查相对服务根地址。默认端口8765。所有私有请求使用 `Authorization: Bearer API_KEY`，CLI自动设置；密钥不得出现在URL、JSON正文或命令行参数中。交互文档为 `/api/docs`，OpenAPI为 `/api/openapi.json`。Agent查询能力版本由 `context.agent_api_version` 标识，不仅看健康接口的应用版本号。

## 权限和命令

| HTTP路径 | 权限 | CLI |
| --- | --- | --- |
| GET `/api/health`（根地址） | 无 | `health` |
| GET `/agent/context` | read | `context` |
| GET `/agent/reviews` | read | `reviews` |
| GET `/agent/weaknesses` | read | `weaknesses` |
| GET `/items` | read | `list` |
| POST `/items` | write | `create --file FILE` |
| GET `/items/{id}` | read | `get ID` |
| PATCH `/items/{id}` | write | `update ID --file FILE` |
| DELETE `/items/{id}` | write | `delete ID` |
| POST `/items/{id}/restore` | write | `restore ID` |
| GET、POST `/chapters` | read、write | `chapters`、`chapter-create --file FILE` |
| PATCH、DELETE `/chapters/{id}` | write | `chapter-update ID --file FILE`、`chapter-delete ID` |
| POST `/media` | write | `upload FILE` |
| GET `/media/{id}` | read | `download ID --out FILE` |
| GET `/reviews/due` | read | `due` |
| GET `/items/{id}/preview` | read | `preview ID` |
| POST `/items/{id}/reviews` | review | `review-submit --file ATTEMPT` |
| GET `/items/{id}/reviews` | read | `history ID` |
| POST `/reviews/{id}/undo` | review | `undo ID` |
| GET `/stats` | read | `stats` |

`doctor` 仅GET健康与context，不试写来探权限。context不存在（404）时回退chapters读检查并返回 `agent_support:false`；新概况/历史/薄弱点命令仍需要升级后端。401、403、连接错误不能当作旧版本。

学习偏好可只读；修改偏好、账号、密码、API Key管理、ZIP备份仍需要网页登录。新接口不能突破当前账号或密钥权限。

## 学习概况

`context` 返回：
- `agent_api_version: 1`。
- `permissions`：当前密钥/会话实际拥有的read/write/review子集，不是所有可能权限。
- `profile.display_name` 与 `profile.preferences`：白名单学习设置，如时区、目标日期、分科保持率、新学额度和每日目标。
- `study_date`：学习时区的今天，ISO日期；`server_time`：带时区的服务器时间。
- `summary.today/totals/subjects/learning/forecast`：原统计的数量、成功率、分科表现、样本数、估算标记、未来安排。learning只含摘要，不带题目列表。

context不返回题干、参考答案、作答正文、密码、会话或密钥列表。要查具体内容，用后续分页命令。

## 跨题复习历史

```bash
python scripts/shiyi_api.py reviews --subject math --date-from 2026-09-01 --date-to 2026-09-07 --page-size 20
python scripts/shiyi_api.py reviews --independent-completed false --has-blocker true
```

| CLI参数 | API参数与说明 |
| --- | --- |
| `--subject` | subject=408/math/english |
| `--item-id` | item_id=真实条目UUID |
| `--rating` | rating=again/hard/good/easy |
| `--independent-completed true/false` | independent_completed；false不包含历史null |
| `--has-blocker true/false` | has_blocker；按是否有卡点文字过滤 |
| `--date-from` / `--date-to` | date_from/date_to；学习时区日期，含首尾，默认近30日，跨度最多366日 |
| `--include-undone` | 包含撤销记录，默认排除 |
| `--include-deleted` | 包含已删除条目的历史，默认排除 |
| `--include-answers` | 返回answer_text/answer_media，默认不返回 |
| `--page` / `--page-size` | 1起；每页1..100，CLI默认20 |

返回 `{items,total,page,page_size,has_more,date_from,date_to,timezone,server_time}`。每行包含评分记录以及 `item` 元信息（当前id/title/subject/kind/status/source_item_id）。按reviewed_at、id倒序。题名等元信息反映当前条目，不是过去题干的版本快照。未来时间记录不算已发生。

## 完整薄弱点分页

```bash
python scripts/shiyi_api.py weaknesses --subject 408 --days 30 --page 1 --page-size 20
```

days为1..365，默认30；分页规则同上。返回 `{items,total,page,page_size,has_more,days,timezone,server_time}`。条目含id/title/subject/kind/status/source_item_id/schedule/blocker/reviewed_at/elapsed_days，不含题干和参考答案。

口径与网站相同：每条内容每天仅取首条未撤销评分，且上次复习在更早学习日；最近一次这样的跨日首答仍为again，才在薄弱列表中。同日重学成功不会抹掉这次失败，后续跨日成功才移出。只列活跃条目，不是医学/考试意义上的掌握度诊断。初学不会但尚未跨日的卡点，请查reviews。

## 知识创建、修改与关联

| 字段 | 规则 |
| --- | --- |
| title | 必填1..240字符 |
| subject | 408/math/english |
| kind | concept/problem/vocabulary/expression |
| question、answer | Markdown/LaTeX，各最多60000字符 |
| question_media、answer_media | 已上传图片ID有序数组，各最多12张 |
| chapter_id | 同账号同科目章节或null |
| difficulty | basic/medium/hard，仅分类用途 |
| tags | 最多20个，每个不超过40字符 |
| source | 来源文字或链接，最多500字符 |
| source_item_id | 同账号同科目、kind=problem的来源原题ID或null，不能指向自己 |
| is_mistake | 是否进入错题本 |
| mistake_reason、takeaway | 条目层面的错因/提醒，各最多10000字符 |
| status | active/draft/suspended |
| external_id | 稳定外部标识，最多200字符或null；每账号唯一，包括回收站 |
| expected_version | 更新时为读取响应顶层item.version，不是schedule.version |

正式条目需要问题和答案各有文字或图片；缺答案按意图存draft。PATCH省略字段保留，数组整组替换；解除原题关联用 `source_item_id:null`。原题已有小任务时不能直接改变科目或改成非problem，先处理关联。来源关系不传播评分，子任务有独立FSRS状态。

`list`支持q/subject/chapter-id/tag/difficulty/kind/external-id/source-item-id/is-mistake/status/state/sort/page/page-size。status默认all排除deleted；state为new/due/learning/review/relearning；sort为updated/created/due/title。原list和get默认含参考答案；抽查必须加 `--question-only` 或用due。

`due --subject math --limit 20` 的limit为1..200，返回 `{items,due_count,new_count,new_available,next_due,server_time}`。到期优先、三科共享新学额度，问题不含参考答案。不要把有限items长度当作待复习总数。

章节新增/重命名文件为 `{"subject":"math","name":"微分学"}`，重命名不跨科目；删除章节保留知识。

## 私有图片

上传支持PNG/JPG/WebP/GIF，最多15MB、3200万像素；服务端校验、处理方向并转成WebP，动图仅保留首帧。将返回的真实id放入附件数组，不把URL/文件名当ID。

下载 `download MEDIA_ID --out PATH` 通过鉴权，不覆盖同名文件。成功后由宿主读图；图片工具需要真正支持视觉输入，不能只把图片URL作为纯文本发给模型。

## 真实评分与幂等性

```json
{
  "rating": "again",
  "expected_version": 0,
  "expected_item_version": 1,
  "independent_completed": false,
  "blocker": "没分清每组容量和总容量",
  "duration_ms": 0,
  "answer_text": "用户实际作答，可省略",
  "answer_media": []
}
```

该示例用于problem整题，两个版本须用该次尝试读取到的实际值，不要照抄0/1。

- expected_version是schedule.version；expected_item_version是内容version，可省略/null，建议提供以防题目被编辑。
- independent_completed只用于整题，true/false/null；历史省略/null表示未知。false需要非空blocker和again；true不能again。blocker最多2000字符，非false应为空。
- duration_ms为真实毫秒0..86400000，不知道填0；answer_text最多30000字符；answer_media最多8个已上传ID。
- hard=独立完成但费力，是成功回忆；again=未独立完成/依赖提示。刚看完答案后的复述不能冒充独立成功。
- again/hard原间隔不足24小时，服务端推到学习时区次日00:00；其他评分/至少一天的间隔不变。preview每档含due、interval_seconds、next_day，next_day=true应显示明天。

review-prepare只生成一次request_id并保存新的本地attempt文件，不联网不覆盖；review-submit读取固定服务/条目/请求体。结果不确定时原文件原样重试。409不得自动刷新版本重放旧尝试。旧attempt兼容，不能为升级客户端而重建已提交请求。

响应 `{already_recorded,review}`；review.rating为1..4，包含真实due、independent_completed、blocker。history每页30条，包含undone；undo仅限该题最近一次、10分钟内评分，保留原记录并恢复状态。

## 错误与可信度

3xx不跟随，避免转发密钥；401密钥无效；403权限不足；404不存在/地址错误/新接口未部署；409版本或状态冲突；413过大；422字段或窗口错误；429停止并遵守重试间隔；5xx或中断时写入可能已经成功，先核实、不要换ID重试。

CLI成功stdout JSON、退出0；失败stderr JSON、非0。不输出密钥或完整配置，不自动重试写入。不把被截断的一页结果冒充全部，不把模型推测当成数据库事实。
