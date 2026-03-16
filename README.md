# AI Coding Assistant Traffic Analyzer

捕获、记录、分析 AI 编程助手（GitHub Copilot、Claude Code、OpenCode、Codex CLI 等）与 LLM API 之间的完整网络通信。

## 这是什么？

在使用 AI 编程助手时，你是否好奇它们发送了什么 prompt？用了哪些 tools？消耗了多少 tokens？每次请求耗时多久？

本项目提供了一套**端到端的 AI 编程助手流量分析工具链**：

1. **捕获流量** — 通过 HTTP 代理或 HTTPS 嗅探拦截 AI 助手的 API 调用
2. **保存到磁盘** — 完整记录请求/响应的 headers、body、时间戳
3. **可视化分析** — 在 Web UI 中浏览、搜索、深度解析 LLM 对话内容

```
┌──────────────────┐     ┌───────────────┐     ┌──────────────────┐
│   AI 编程助手     │────►│  Proxy/Sniffer │────►│   LLM API 后端   │
│  (Copilot, Claude│◄────│  拦截并记录流量  │◄────│ (OpenAI, Claude) │
│   Code, etc.)    │     └───────┬───────┘     └──────────────────┘
└──────────────────┘             │
                                 │ 保存
                                 ▼
                        ┌─────────────────┐
                        │   logs/ 目录     │
                        │  (结构化存储)    │
                        └────────┬────────┘
                                 │
                                 │ 读取
                                 ▼
                        ┌─────────────────┐
                        │   Log Viewer    │
                        │  (Web UI 分析)   │
                        └─────────────────┘
```

## 效果展示

### 请求列表 — 浏览所有 API 调用

- 按时间范围、HTTP 方法、关键词筛选
- 颜色编码的 HTTP 方法和状态码
- 收藏重要请求并添加自定义标题

### LLM 对话解析 — 深度查看 AI 对话

- 自动解析 Claude / OpenAI 的请求与响应格式
- 还原 SSE 流式响应为完整对话
- 提取 system prompt、用户消息、助手回复、工具调用
- 展示 tool_use / tool_result 详情

### 多源切换 — 同时分析多个 AI 助手

- 支持配置多个日志目录（Copilot、Claude Code、OpenCode 等）
- 一键切换不同捕获源

## 快速开始

### 前置条件

- Node.js >= 18
- Yarn 1.x
- Python >= 3.12 + [uv](https://docs.astral.sh/uv/)（仅 sniffer 需要）

### 1. 安装依赖

```bash
# 安装 Node.js 项目依赖（proxy + log-viewer）
yarn install

# 安装 Python 项目依赖（sniffer）
cd apps/sniffer
uv sync
cd ../..
```

### 2. 选择捕获方式

根据你的需求选择合适的流量捕获方式：

| 方式 | 适用场景 | 协议 | 说明 |
|------|---------|------|------|
| **Proxy**（HTTP 代理） | 目标应用支持配置代理地址 | HTTP | 轻量，无需证书 |
| **Sniffer**（HTTPS 嗅探） | 需要拦截加密流量 | HTTPS | 自动设置系统代理，需安装 mitmproxy CA 证书 |

#### 方式 A：使用 Proxy

```bash
# 配置
cd apps/proxy
cp .env.example .env
# 编辑 .env，设置 TARGET_HOST/TARGET_PORT 为 AI 助手的 API 后端

# 启动
cd ../..
yarn dev:proxy
```

将 AI 助手配置为使用 `http://localhost:8080` 作为代理。

#### 方式 B：使用 Sniffer

```bash
cd apps/sniffer

# 使用预设配置（例如：捕获所有流量）
uv run python run.py -c config.all.yaml

# 或指定 AI 助手
uv run python run.py -c config.copilot.yaml    # GitHub Copilot
uv run python run.py -c config.claude-code.yaml # Claude Code
uv run python run.py -c config.opencode.yaml    # OpenCode
uv run python run.py -c config.codex.yaml       # OpenAI Codex CLI
```

Sniffer 会自动设置 Windows 系统代理，退出时自动恢复。

### 3. 启动 Log Viewer

```bash
# 配置日志源
cd apps/log-viewer
cp .env.example .env
# 编辑 .env 中的 LOG_DIRS，指向你的捕获目录

# 启动
cd ../..
yarn dev:viewer
```

打开 http://localhost:3001 查看捕获的流量。

### 一键启动（Proxy + Log Viewer）

```bash
yarn dev
```

同时启动 Proxy（:8080）和 Log Viewer（:3001）。

## 项目结构

```
nodeproxy/
├── apps/
│   ├── proxy/           # HTTP 代理服务器（Node.js + Hono）
│   ├── sniffer/         # HTTPS 流量嗅探器（Python + mitmproxy）
│   └── log-viewer/      # 日志查看器 Web UI（Next.js + React）
├── logs/                # 共享日志目录
│   └── YYYYMMDD_HHMMSS/ # 按分钟分组
│       └── {ts}_{METHOD}_{path}/
│           ├── request_metadata.json
│           ├── request_body.*
│           ├── response_metadata.json
│           └── response_body.*
├── scripts/             # 工具脚本
│   └── migrate-log-dirs.mjs
├── systemd/             # Linux systemd 服务配置
└── package.json         # Yarn workspaces 配置
```

### 组件说明

| 组件 | 说明 | 技术栈 | 文档 |
|------|------|--------|------|
| [proxy](apps/proxy) | HTTP 代理，拦截并记录明文 HTTP 流量 | Node.js, Hono, TypeScript | [README](apps/proxy/README.md) |
| [sniffer](apps/sniffer) | HTTPS 嗅探器，通过 MITM 拦截加密流量 | Python 3.12+, mitmproxy | [README](apps/sniffer/README.md) |
| [log-viewer](apps/log-viewer) | Web 日志查看器，可视化分析 LLM API 调用 | Next.js 16+, React 19, Tailwind | [README](apps/log-viewer/README.md) |

## 日志格式

Proxy 和 Sniffer 使用**相同的日志格式**，Log Viewer 可以无差别地读取两者的输出：

```
logs/
├── 20260315_143000/                              # 分钟目录
│   ├── 1773531607390_POST_api%2Fv1%2Fmessages/   # 请求目录
│   │   ├── request_metadata.json                 # 请求元数据
│   │   ├── request_body.json                     # 请求体（JSON 自动格式化）
│   │   ├── response_metadata.json                # 响应元数据
│   │   └── response_body.txt                     # 响应体（SSE 流文本）
│   └── 1773531618719_POST_chat%2Fcompletions/
│       ├── request_metadata.json
│       ├── request_body.json
│       ├── response_metadata.json
│       └── response_body.json
└── 20260315_143100/
    └── ...
```

## 适用场景

- **调试 AI 编程助手** — 查看 Copilot/Claude Code 到底发了什么 prompt
- **分析 Token 消耗** — 了解每次请求使用了多少 tokens
- **对比不同 AI 助手** — 同时捕获多个助手的流量进行对比
- **研究 System Prompt** — 查看 AI 助手的完整 system prompt 内容
- **性能分析** — 分析 API 响应延迟和 SSE 流传输时间
- **开发调试** — 调试任何 HTTP/HTTPS API 调用

## 生产部署

对于 Linux 生产环境，可使用 systemd 服务部署，详见 [systemd/README.md](systemd/README.md)。

```bash
yarn build
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now proxy.service log-viewer.service
```

## License

MIT
