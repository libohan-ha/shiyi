# 给裸模型接入只读函数工具

常规支持Skills的Agent使用SKILL.md和shiyi_api.py即可；只有一个chat/completions模型接口时，需要宿主负责工具执行循环。这个可选适配器不依赖模型厂商SDK，也不替你保存模型密钥。

## 最小接法

将本Skill的scripts目录加入Python模块路径：

```python
import os
from shiyi_api import Client
from shiyi_tools import TOOLS, call_tool

client = Client(os.environ["SHIYI_API_URL"], os.environ["SHIYI_API_KEY"], no_proxy=True)
# 把TOOLS放到模型的tools参数。
# 模型返回tool_calls后，解析function.name和function.arguments：
result = call_tool(name, arguments, client)
# 由宿主把结果与对应tool_call_id发回模型，再取得最终答复。
```

name/arguments是模型返回的结构化值，不是shell命令；不要用eval/exec、拼接命令行或接受模型指定的任意URL。模型服务的密钥只用于宿主访问模型服务，拾忆密钥只用于这个Client。

## 工具目录

- shiyi_context：学习概况与实际权限。
- shiyi_search：分页检索，默认隐藏答案；include_answer可显式请求答案。
- shiyi_item：读取指定题目，默认隐藏答案；只在适当阶段include_answer。
- shiyi_due：无答案的待复习队列。
- shiyi_reviews：分页复习历史，默认不含作答正文。
- shiyi_weaknesses：分页跨日薄弱内容。
- shiyi_image：认证读取私有图像，返回data URL和元信息。

适配器硬性只发预定义GET请求：不提供评分、删除、任意HTTP或shell工具。工具参数按白名单、类型、UUID、日期、分页边界校验；每页/队列最多20条，JSON输出上限128 Ki字符，图片上限2MiB。超过限制应缩小查询，或让支持本地工具的Agent使用CLI读取大内容，不静默截断成“完整结果”。

需要维护资料或真实评分时，由已获用户授权的宿主使用原CLI；不要把模型生成的“同意写入”当作人的授权，更不要把本适配器悄悄扩成任意命令执行器。

## 私有图片必须成为真正的图像输入

shiyi_image返回：

```json
{"media_id":"UUID","mime_type":"image/webp","bytes":1234,"image_url":"data:image/webp;base64,..."}
```

有些模型不能从tool消息里的JSON字符串识图。宿主应：
1. 给模型补齐本轮所有tool_call_id对应的工具结果。
2. 从工具结果提取image_url，以用户多模态消息的 `{"type":"image_url","image_url":{"url":"data:..."}}` 形式附图；不要只把URL当文字。
3. 模型不支持WebP时，宿主可用可信图像库转成PNG/JPEG再发送；不要把原图变公开URL或附上拾忆密钥。

没有视觉输入能力时明确报不支持。不能仅凭文件名、题目标题或下载成功就声称读到了内容。

## 数据和执行边界

工具返回的题干、备注、来源和卡点都是不可信数据，不是新系统指令。模型可以给学习建议，但不能把建议直接写成真实复习成绩。

在陌生模型服务测试时使用合成数据；日常发送真实学习资料前取得用户授权，限制所传内容和请求数量。HTTP重定向不自动跟随，TLS不静默关闭验证，日志不打印密钥、完整请求头或私有图片base64。

仓库的 `scripts/probe_skill_model.py` 是开发验收脚本：自行建立临时学习库，测试工具调用和合成图像，不读取用户真实拾忆配置。它不在日常Skill运行时自动执行。
