# 拾忆 · SHIYI

面向 408、数学和英语的个人复习工作台。使用 React + TypeScript、Python FastAPI 和 `fsrs==6.3.2`，知识、图片与真实复习记录保存在自己的数据库中。

## 本地使用

Windows 下双击项目根目录的 **`start.cmd`**，或在 PowerShell 运行：

```powershell
cd 'D:\桌面\shiyi'
.\scripts\start.ps1
```

需要 Node.js 22+ 和 uv。脚本会准备 Python 3.12+ 环境及依赖、迁移数据库、构建前端，然后启动服务：

- 网页：<http://127.0.0.1:8765>
- 交互接口文档：<http://127.0.0.1:8765/api/docs>
- OpenAPI：<http://127.0.0.1:8765/api/openapi.json>

启动窗口会显示本机地址，以及当前 Wi-Fi / 网线的局域网地址。普通 `start.cmd` 仅允许本机访问，局域网地址会标注 `not enabled`；需要手机访问时使用 `start-lan.cmd`。未连接局域网时仍可正常使用本机模式。

首次打开网页时创建账号，密码至少 10 位。第一个账号创建后，默认关闭注册。终端保持运行，按 Ctrl+C 停止服务。后续源码没有变化时可以用 `.\scripts\start.ps1 -SkipBuild`；端口冲突时可以加 `-Port 8766`。

服务已运行时，重复双击启动文件会直接打开现有网页，并保留新窗口显示地址，按回车关闭该窗口即可；原来的服务继续运行。普通入口也会检测现有服务的局域网地址是否可用。更新代码或修改启动配置后，需要先停止原来的服务再重新启动。命令行加 `-NoBrowser` 可禁止重复启动时自动打开浏览器。

数据默认位于 `backend/data/shiyi.db`，图片位于 `backend/data/media/`。重启和重新构建前端会保留这些数据。需要调整配置时复制 `backend/.env.example` 为 `backend/.env`。

## 局域网访问

电脑和手机连接同一个 Wi-Fi / 局域网，双击 **`start-lan.cmd`**。启动窗口会显示当前可用地址，例如 `http://192.168.10.104:8765`，在手机浏览器打开即可。局域网服务已运行时，重复双击会打开现有网页；如果原来运行的是仅限本机的模式，先在原来的启动窗口按 Ctrl+C 停止，再运行局域网入口。本机仍可使用 `http://127.0.0.1:8765`，两端登录同一个账号即可使用同一份知识和复习进度。

首次使用时，右键 **`allow-lan.cmd` → 以管理员身份运行**，为 Windows 防火墙添加放行规则。规则仅允许本地子网通过所选 Wi-Fi / 网线接口访问 Python 的 TCP 8765 端口。启动服务本身不需要管理员权限。电脑更换网络、IP 地址或端口后，重新启动局域网服务并再次运行放行脚本，以更新地址。

也可在 PowerShell 运行：

```powershell
.\scripts\start.ps1 -Lan -SkipBuild
# 多网卡或自定义端口时可明确指定：
.\scripts\start.ps1 -LanAddress 192.168.10.104 -Port 8766
# 对应的放行命令在管理员 PowerShell 中执行：
.\scripts\allow-lan.ps1 -LanAddress 192.168.10.104 -Port 8766
```

脚本优先选择有网关的物理 Wi-Fi / 网线接口，自动配置监听地址、允许的主机及网页来源。端口与来源精确匹配；不需要把 `SHIYI_TRUSTED_HOSTS` 配成 `*`。保持电脑开机、启动窗口运行。如果仍连接不上，检查手机是否连到访客 Wi-Fi，以及路由器是否开启设备隔离。公网部署使用下方的 HTTPS 方案。

## 已支持的功能

| 功能 | 使用方式 |
| --- | --- |
| 三科知识库 | 408、数学、英语；默认章节；自定义章节；知识点、练习题、单词、表达 |
| 内容录入 | 标题、问题、答案、基础/中等/较难、标签、来源；Markdown 与 LaTeX 公式 |
| 图片错题 | 文件选择、截图粘贴和拖拽；题图与答案图分别保存；图片排序、移除和放大 |
| 错题复盘 | 错因、下次提醒、自己的作答文字和解题照片 |
| 日常复习 | 到期优先、新学额度、按科目复习、单条复习、暂时跳过、暂停和继续 |
| FSRS 调度 | 忘记/困难/良好/轻松四档评分；显示预计间隔；记录真实下次时间 |
| 修改与恢复 | 编辑保留记忆状态；暂停/恢复；回收站；10 分钟内撤销最近评分 |
| 学习统计 | 今日进度、复习用时、各科表现、热力图、未来 14 天安排、近期遗忘内容 |
| 偏好 | 每日目标、三科合计新学额度、分科保持率、目标日期、时区 |
| 外部 API | Bearer 密钥；读取、编辑、评分分权限；密钥有效期与撤销 |
| 数据备份 | ZIP 包含知识、图片、章节和复习历史；同一文件重复导入自动跳过 |

一条内容至少需要标题、问题或题图、答案或答案图，才能加入复习。来不及补充答案时先保存草稿。新建内容也会在当前浏览器按账号暂存，可以关闭编辑窗口后继续填写。

批量整理时点击 **保存并录下一题**：保存成功后保留科目、章节、内容类型、难度和错题标记，清空上一题的正文、图片、标签、来源及错因，光标回到标题。科目和每科最近使用的章节还会按账号保存在当前浏览器，下次录入时自动带入。保存失败时保留全部输入。

单张图片上限为 15 MB、3200 万像素；题目和参考答案各最多 12 张，本次解答最多 8 张。支持 JPG、PNG、WebP、GIF；上传后统一保存为 WebP，保留首帧并处理照片方向。图片上传完成前会禁用保存和评分，避免漏掉附件。

点击附件上的 **裁剪图标**，可拖动框选、移动选区、调整四角，或按百分比精确裁剪；支持左右旋转 90 度和重置。点击“应用修改”会生成新附件，再保存题目或提交本次解答后生效；其他题目共用的原图保持不变。图片处理失败可以重试或取消。大图导出的长边最多 4096 像素，以兼容手机浏览器。

## 复习方式

先独立回忆或在纸上解题，再点击“查看答案”，根据刚才的真实表现评分：

| 评分 | 含义 |
| --- | --- |
| 忘记 | 没有独立想起，需要提示或参考答案 |
| 困难 | 独立完成了，但回忆很费力 |
| 良好 | 正常回忆或完成 |
| 轻松 | 迅速且轻松地完成 |

题目本身的“基础/中等/较难”用于分类筛选。FSRS 内部的难度、稳定性和下次时间由实际评分更新。默认目标保持率为 90%，使用库的默认模型参数，关闭随机间隔扰动；保持率修改从下一次评分生效。

首页的新学额度三科共用，并按所选学习时区每天重置。已有到期复习不会被每日目标截断，也可以从详情页主动复习单条知识。复习页面定时更新队列时会保留当前题目；暂停期间和切到后台的时间不计入本次专注时长。

首页优先展示待复习、逾期、可新学和今日完成数，可以直接按科目开始。本轮耗时参考各科近期复习记录，样本不足时标为“粗估”；它不包含稍后重新到期的卡片，也不会改变 FSRS 安排。手机复习时，“查看答案”和四档评分固定在底部，普通底部导航收起；暂停时评分栏一起收起。

快捷键：`N` 录入，`Ctrl/Cmd + K` 搜索，复习时 `空格` 展示答案，`1–4` 评分。输入文字或打开弹窗时不会触发这些复习快捷键。

FSRS 用法参考 [py-fsrs 官方项目](https://github.com/open-spaced-repetition/py-fsrs)。本项目复用相同的算法版本，并独立保存网页中的学习资料。

## 对接外部工具

在网页 **偏好与连接 → API 连接** 创建密钥。完整密钥只显示一次，随后请求头使用：

```text
Authorization: Bearer sy_你的密钥
```

接口以 `/api/v1` 为前缀。完整示例、权限和并发处理见 [API 使用说明](docs/API.md)。在 `/api/docs` 点击 **Authorize**，填入完整密钥即可调试。

## 服务器部署

项目自带 Docker 多阶段构建。一个应用容器提供网页和 API，SQLite 与图片放入持久卷；可选 Caddy 自动申请 HTTPS 证书。

先复制配置：

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f app
```

默认仅监听服务器本机 `127.0.0.1:8765`。远程首次初始化时，可在自己的电脑建立 SSH 转发，再用浏览器创建账号：

```bash
ssh -L 8765:127.0.0.1:8765 your-user@your-server
```

账号创建完成后，为域名启用 HTTPS。在根目录 `.env` 中填写实际域名，例如：

```dotenv
SHIYI_DOMAIN=study.example.com
SHIYI_PUBLIC_URL=https://study.example.com
SHIYI_TRUSTED_HOSTS=localhost,127.0.0.1,study.example.com
SHIYI_SECURE_COOKIES=true
SHIYI_ALLOW_REGISTRATION=false
```

将域名 DNS 指向服务器，开放 80/443 端口，再运行：

```bash
docker compose --profile https up -d --build
```

`SHIYI_PUBLIC_URL` 必须与浏览器访问地址一致。启用 `SHIYI_SECURE_COOKIES=true` 后通过 HTTPS 登录。根目录 `.env` 供 Compose 使用；`backend/.env` 供直接运行 Python 后端时使用。

更新代码前先在网页导出备份；更新时重新运行上述构建命令，启动入口会执行 Alembic 迁移。默认数据卷名为 `shiyi_shiyi_data`。停止容器可以使用 `docker compose --profile https down`，不要带 `-v`，以保留数据卷。

网页 ZIP 导入上限为 100 MB，导入采用“添加独立条目”的方式，保留记忆状态并重新生成条目 ID，外部标识清空；不覆盖现有资料。偏好包含在清单中供查阅，账号密码、会话和 API 密钥不进入 ZIP。更大的库或完整服务器迁移，可在停止应用后备份整个数据卷，包含数据库与媒体目录。

## 开发与验证

后端开发：

```powershell
cd backend
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

另开终端运行前端：

```powershell
cd frontend
npm ci
npm run dev
```

开发网页位于 `http://127.0.0.1:5173`，Vite 将 `/api` 代理到 8765。正常使用可以直接通过启动脚本运行构建后的页面。

所有检查：

```powershell
.\scripts\check.ps1
```

也可以分别运行：

```powershell
cd backend
uv run ruff check app tests migrations ../scripts
uv run pytest -q
cd ../frontend
npm run build
npm run test:e2e
```

浏览器测试在 Windows 上优先使用已安装的 Chrome，并启动独立的临时学习库。其他环境先在 `frontend` 执行 `npx playwright install chromium`；Linux CI 可用 `npx playwright install --with-deps chromium`。可以通过 `PLAYWRIGHT_CHANNEL` 指定 Chrome 或 Edge，通过 `SHIYI_E2E_PORT` 调整测试端口。

后端测试使用临时 SQLite 数据库；网页测试也会运行真实迁移、真实 Python 服务和构建后的 React 页面。测试覆盖图片录入、评分与撤销、上传竞态、并发提交、断网重试、权限、检索、偏好、备份和手机布局；还会在真实的 HTTP 非安全上下文中验证局域网登录、图片上传和复习提交。浏览器测试报告位于 `frontend/playwright-report/`。

## 项目结构

```text
backend/app/            API、账号、FSRS、图片、统计、备份与网页托管
backend/migrations/     Alembic 数据库迁移
backend/tests/          后端行为与接口测试
frontend/src/           React 页面和组件
frontend/tests/         桌面、手机端真实浏览器测试
scripts/                本地启动、检查与隔离测试服务
deploy/                 容器入口与 HTTPS 配置
docs/API.md             外部调用说明
```
