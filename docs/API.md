# 拾忆 API 使用说明

基础地址为 `http://127.0.0.1:8765/api/v1`；部署后将主机替换为自己的域名。所有时间均以带 UTC 时区的 ISO 8601 字符串返回；统计日期按账号偏好中的时区计算。

## 鉴权与权限

网页登录后，在“偏好与连接 → API 连接”创建密钥。外部工具使用 `Authorization: Bearer sy_...`。Swagger 文档 `/api/docs` 的 Authorize 中直接填写密钥，不必额外输入 `Bearer`。

| 权限 | 接口 |
| --- | --- |
| `read` | 知识和章节查询、图片读取、到期队列、评分预览、复习历史、统计 |
| `write` | 创建/修改/删除/恢复知识、管理章节、上传图片 |
| `review` | 提交评分、撤销评分 |

通常为需要完整工作流的工具同时授予 `read`、`write`、`review`。账号、偏好、密码、密钥管理和 ZIP 导入导出需要网页登录会话，不能通过 API 密钥管理。

以下 curl 示例采用 Bash 语法，先在本机配置环境变量。Windows 可使用 PowerShell 的 `Invoke-RestMethod`，或安装了 Bash 的终端。

```bash
export SHIYI_API_URL='http://127.0.0.1:8765/api/v1'
export SHIYI_API_KEY='sy_替换为自己的密钥'
```

## 知识 CRUD

```bash
# 新建内容
curl -fS "$SHIYI_API_URL/items" \
  -H "Authorization: Bearer $SHIYI_API_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"title":"导数的定义","subject":"math","kind":"concept","question":"写出导数定义并说明存在条件。","answer":"差商的极限存在且有限；左右极限一致。","difficulty":"medium","tags":["高等数学","导数"],"external_id":"my-notes:math:001"}'

# 检索、筛选与分页
curl -fS -G "$SHIYI_API_URL/items" \
  -H "Authorization: Bearer $SHIYI_API_KEY" \
  --data-urlencode 'q=导数' --data-urlencode 'subject=math' \
  --data-urlencode 'page=1' --data-urlencode 'page_size=24'

# 单条读取；将 ITEM_ID 替换为创建响应的 id
curl -fS "$SHIYI_API_URL/items/ITEM_ID" \
  -H "Authorization: Bearer $SHIYI_API_KEY"

# 部分更新；expected_version 来自读取响应的 version
curl -fS -X PATCH "$SHIYI_API_URL/items/ITEM_ID" \
  -H "Authorization: Bearer $SHIYI_API_KEY" -H 'Content-Type: application/json' \
  --data '{"difficulty":"hard","expected_version":1}'

# 删除为移入回收站，成功返回 204
curl -fS -X DELETE "$SHIYI_API_URL/items/ITEM_ID" \
  -H "Authorization: Bearer $SHIYI_API_KEY"

# 恢复原来的状态与学习进度
curl -fS -X POST "$SHIYI_API_URL/items/ITEM_ID/restore" \
  -H "Authorization: Bearer $SHIYI_API_KEY"
```

创建响应包含 `id`、`version` 和 `schedule`。PATCH 只更改提交的字段，编辑不会重置 FSRS 状态。`external_id` 在每个账号内唯一，回收站中的记录也保留该标识；用于与笔记 ID 对应，可通过 `GET /items?external_id=...` 查询。回收站需要同时传 `status=deleted`。

创建和更新字段：

| 字段 | 值或说明 |
| --- | --- |
| `title` | 必填，1–240 字符 |
| `subject` | 必填：`408`、`math`、`english` |
| `kind` | `concept`、`problem`、`vocabulary`、`expression` |
| `question` / `answer` | Markdown 文本，每个字段最多 60000 字符 |
| `question_media` / `answer_media` | 已上传图片 ID 的有序数组，每个最多 12 张 |
| `difficulty` | `basic`、`medium`、`hard`，用于分类筛选 |
| `chapter_id` | 本账号、同科目章节的 ID，或 `null` |
| `tags` | 最多 20 个标签，每个不超过 40 字符 |
| `source` | 来源文本或链接，最多 500 字符 |
| `is_mistake` | 是否进入错题本 |
| `mistake_reason` / `takeaway` | 错因与复盘提醒，各最多 10000 字符 |
| `status` | `active`、`draft`、`suspended` |
| `external_id` | 外部系统标识，最多 200 字符，或 `null` |
| `expected_version` | 编辑时传当前 `version`，防止旧内容覆盖新修改 |

非草稿至少需要“问题文字或题图”和“答案文字或答案图”。暂时没有答案可用 `status=draft`；暂停复习用 `status=suspended`。

列表返回 `{items, total, page, page_size}`，支持 `subject`、`q`、`chapter_id`、`tag`、`is_mistake`、`difficulty`、`kind`、`external_id`、`status`、`state` 和 `sort`。`status=all` 默认排除回收站；`state` 可选 `new/due/learning/review/relearning`；`sort` 可选 `updated/created/due/title`。每页上限 100。

## 上传图片

先上传，再将响应中的 `id` 放入知识的附件数组。不要手动设置 multipart 的 Content-Type，curl 会自动带上 boundary。

```bash
curl -fS "$SHIYI_API_URL/media" \
  -H "Authorization: Bearer $SHIYI_API_KEY" \
  -F 'file=@question.png'
```

返回 `id`、`url`、原文件名、尺寸和保存后的文件大小。图片读取也需要鉴权；网页使用登录 Cookie，外部程序需携带 `read` 权限密钥。图片未作为公共静态目录暴露。

图片错题可完全不填写题干文字：

```json
{
  "title": "一道需要重做的题",
  "subject": "math",
  "kind": "problem",
  "is_mistake": true,
  "question_media": ["上传题图返回的ID"],
  "answer_media": ["上传答案图返回的ID"],
  "difficulty": "hard",
  "mistake_reason": "审题时漏掉了条件"
}
```

## 复习与重试

1. `GET /reviews/due?subject=408&limit=100` 获取队列。省略 subject 为三科；上限 200 条。队列包含题目和题图，隐藏参考答案、答案图及复盘提醒。
2. 完成独立回忆后，`GET /items/{id}` 查看答案，`GET /items/{id}/preview` 查看四档预计间隔。
3. `POST /items/{id}/reviews` 记录本次表现。评分的版本号使用 **`schedule.version`**，与编辑内容使用的 **`version`** 分开。

```json
{
  "request_id": "本次尝试唯一的UUID",
  "rating": "good",
  "expected_version": 0,
  "duration_ms": 42000,
  "answer_text": "我独立完成的解答或思路",
  "answer_media": []
}
```

`rating` 为 `again/hard/good/easy`。`duration_ms` 为实际用时，范围 0–86400000；本次解答最多 30000 字符、8 张图片。需要提示或答案才能完成时记 `again`；独立完成但吃力才是 `hard`。

响应为 `{already_recorded, review}`，其中 `review.due` 为已保存的真实下次时间。如果网络超时或响应丢失，应保留原来的 `request_id` 和**完整请求体**重试。相同请求重复提交会返回既有记录，不会再次评分；同一 ID 搭配不同内容会返回 409。

不要仅为了重试生成新的请求 ID。如果因版本冲突收到 409，重新读取题目状态，再由用户判断是否开始一次新的尝试。

- `GET /items/{id}/reviews?page=1`：历史列表，每页 30 条，包含撤销标记和本次解答。
- `POST /reviews/{review_id}/undo`：撤销该题最近一次、10 分钟内的评分。原始记录保留并标记 `undone`，记忆状态恢复，版本号继续递增。

## 其他接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/chapters` | 章节列表 |
| POST | `/chapters` | 传 `{subject, name}` 创建章节 |
| PATCH | `/chapters/{id}` | 传原 subject 与新 name 重命名 |
| DELETE | `/chapters/{id}` | 删除章节，知识保留并取消章节归属 |
| GET | `/stats` | 今日统计、各科表现、热力图和未来安排 |
| GET | `/api/health` | 服务和数据库连通状态，注意此路径不在 `/api/v1` 下 |

`GET /stats` 的 `today.new_available` 是三科共用额度下实际可新学的总数，与 `/reviews/due` 一致。`today.estimated_minutes` 估算当前到期内容加本轮新学内容的时长，`today.estimate_from_history` 表示本轮涉及的科目是否都有足够用时记录。每科使用近 30 天最近 30 次有效用时的中位数，至少需要 3 次；不足时暂按 408 每条 90 秒、数学 180 秒、英语 30 秒粗估。`subjects[].overdue` 为各科逾期条数。这些字段均为展示信息，不修改复习时间。

## 错误处理

| 状态码 | 含义 |
| --- | --- |
| 401 | 未登录，或密钥无效/过期/已撤销 |
| 403 | 权限不足、注册关闭或网页请求来源不匹配 |
| 404 | 记录不存在或不属于当前账号 |
| 409 | 版本冲突、外部标识重复或不允许的状态变更 |
| 413 | 上传文件过大 |
| 422 | 字段、图片或备份内容校验失败 |
| 429 | 登录/注册尝试过于频繁 |

错误正文使用 `detail`。外部脚本应检查 HTTP 状态并处理错误，不能仅根据是否收到 JSON 判断操作成功。
