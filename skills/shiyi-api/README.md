# 拾忆学习助手 Skills v2

## 你可以直接这样问 Agent

- “先了解我的学习情况，今天该复习什么？”
- “看看最近一周数学的卡点，哪些隔天还是不会？”
- “带我复习这道题，先别告诉我答案。”
- “看一下这道图片题，我卡在哪一步？”
- “把这个卡点整理成一个关联小任务，先存草稿。”
- “把我刚才真实的作答记录到拾忆。”

它会按需读取API，不会因为安装技能就自动把整个题库上传给模型，也不会自动把讲解或猜测写成复习成绩。

## 安装

1. 将ZIP解压，得到 `shiyi-api/`（里面直接有SKILL.md、scripts、references）。
2. 在支持Skills的Agent客户端中导入该目录或ZIP；如果替换旧版，保留自己的连接配置，不把配置复制进技能目录。
3. 宿主需有Python3.10+并能访问你的拾忆服务。只看数据用read密钥；要录入/编辑再授予write；要真实评分再授予review。
4. 拾忆网站设置里创建的 `sy_...` 密钥，与模型服务的API key不是同一种密钥。

环境变量为 `SHIYI_API_URL` 和 `SHIYI_API_KEY`；也可沿用 `~/.config/shiyi-api/config.json` 的api_url/api_key。本包不含你的地址或密钥。地址指拾忆网站，不是模型服务器；跨机器访问需要合法可达的局域网/VPN/HTTPS地址。

先运行：

```bash
python scripts/shiyi_api.py doctor
python scripts/shiyi_api.py context
```

若内网被系统代理拦截，可在子命令前加 `--no-proxy`。

## 后端版本要求

本版新概况/全局历史/完整薄弱点查询，需要后端包含 `/api/v1/agent/context`、`/agent/reviews`、`/agent/weaknesses`。doctor返回 `agent_support:false` 时，先更新并重新启动拾忆；不能只安装ZIP就获得未部署的后端接口。原有CRUD等命令保留。

整题反馈与来源关联还需要上一轮的复习机制更新。后端源码在同一项目中，部署前先备份自己的数据。本轮新增只读接口本身不需要新的数据库迁移，不会重排FSRS。

## 模型与权限

本技能不绑定某个模型；只要Agent宿主能执行Python、调用工具、读取图像，就可以使用。裸chat/completions模型需要宿主执行工具循环，可参考 `references/tools.md` 和可选 `scripts/shiyi_tools.py`。

可选函数工具适配器默认只读、固定GET白名单，没有任意shell或评分工具。完整技能通过原CLI保留授权写操作；不要把模型输出或题干里的指令当作人的授权。

私有题图由宿主认证下载并作为图像输入传给模型，不能只发送相对URL，也不能为了识图泄露拾忆密钥。首次测试陌生模型时用合成数据，不默认上传个人学习资料。

具体命令见 `references/api.md`，使用流程见 `references/workflows.md`。
