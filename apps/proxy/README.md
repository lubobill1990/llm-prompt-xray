# Proxy - HTTP 代理日志服务器

## 项目概述

Proxy 是一个轻量级的 HTTP 代理服务器，用于**拦截、记录和转发** HTTP 请求与响应。它是 `llm-prompt-xray` monorepo 的核心组件之一，专为分析 AI 编程助手（如 GitHub Copilot、Claude Code、OpenCode 等）的网络流量而设计。

所有经过代理的流量都会被完整保存到磁盘，包括请求/响应的元数据和消息体，便于后续通过 [log-viewer](../log-viewer) 进行可视化查看，或通过 [sniffer](../sniffer) 进行自动化分析。

## 技术栈

| 技术 | 用途 |
|------|------|
| [Hono](https://hono.dev/) | Web 框架（轻量、高性能） |
| [@hono/node-server](https://github.com/honojs/node-server) | Node.js HTTP 服务器适配器 |
| TypeScript | 类型安全 |
| [tsx](https://github.com/privatenumber/tsx) | 开发时直接运行 TypeScript |
| [dotenv](https://github.com/motdotla/dotenv) | 环境变量配置 |
| Node.js `http` 模块 | 底层请求转发 |

## 实现方式

```
┌────────────┐         ┌─────────────────┐         ┌──────────────┐
│   客户端    │ ──────► │   Proxy Server  │ ──────► │  目标服务器   │
│ (AI 助手)  │ ◄────── │  (Hono + Node)  │ ◄────── │ (API 后端)   │
└────────────┘         └────────┬────────┘         └──────────────┘
                                │
                                │ 保存到磁盘
                                ▼
                       ┌─────────────────┐
                       │   logs/ 目录     │
                       │  (按分钟分组)    │
                       └─────────────────┘
```

### 工作流程

1. **接收请求** — Hono 通过 `app.all('*')` 捕获所有 HTTP 请求
2. **读取请求体** — 对非 GET/HEAD 请求，读取完整的请求 body（`ArrayBuffer` → `Buffer`）
3. **保存请求** — 将请求元数据（method、url、headers、timestamp）和请求体写入磁盘
4. **转发请求** — 使用 Node.js 原生 `http.request()` 将请求转发到目标服务器
5. **接收响应** — 收集目标服务器的完整响应（状态码、headers、body）
6. **保存响应** — 将响应元数据和响应体写入同一请求目录
7. **返回响应** — 将目标服务器的响应原样返回给客户端

## 安装和使用

### 前置条件

- Node.js >= 18
- Yarn（monorepo 使用 yarn workspaces）

### 安装依赖

```bash
# 在 monorepo 根目录
yarn install
```

### 配置

复制环境变量模板并根据需要修改：

```bash
cp .env.example .env
```

### 开发模式

```bash
yarn dev
```

使用 `tsx` 直接运行 TypeScript，支持热更新，适合开发调试。

### 生产构建

```bash
yarn build    # 编译 TypeScript → dist/
yarn start    # 运行编译后的 JavaScript
```

## 配置说明

通过 `.env` 文件或系统环境变量进行配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PROXY_HOST` | `localhost` | 代理服务器监听地址 |
| `PROXY_PORT` | `8080` | 代理服务器监听端口 |
| `TARGET_HOST` | `localhost` | 目标服务器地址（流量转发目的地） |
| `TARGET_PORT` | `4141` | 目标服务器端口 |
| `LOG_DIR` | `logs` | 日志存储目录（支持相对路径和绝对路径） |

> **注意**：`.env.example` 中 `TARGET_PORT` 默认为 `3000`，但代码中的 fallback 默认值为 `4141`。请根据实际目标服务器端口进行配置。

启动后控制台会输出当前配置：

```
HTTP Proxy Server starting...
Listening on: http://localhost:8080
Forwarding to: http://localhost:4141
Logging to: ../../logs
```

## 日志结构

日志按**分钟**自动分组，每个请求在对应分钟目录下创建独立子目录：

```
logs/
└── 20260315_083400/                           # 分钟目录 (YYYYMMDD_HHmm00)
    ├── 1773531607390_POST_api%2Fmessages/     # 请求目录 (时间戳ms_METHOD_编码路径)
    │   ├── request_metadata.json              # 请求元数据
    │   ├── request_body.json                  # 请求体 (JSON 自动格式化)
    │   ├── response_metadata.json             # 响应元数据
    │   ├── response_body.json                 # 响应体
    │   └── error.txt                          # 仅在代理出错时生成
    └── 1773531618719_GET_status/
        ├── request_metadata.json
        ├── response_metadata.json
        └── response_body.json
```

### 元数据文件格式

**request_metadata.json**：

```json
{
  "method": "POST",
  "url": "/api/anthropic/v1/messages?beta=true",
  "headers": {
    "content-type": "application/json",
    "authorization": "Bearer sk-..."
  },
  "timestamp": "2026-03-15T08:34:07.390Z"
}
```

**response_metadata.json**：

```json
{
  "statusCode": 200,
  "headers": {
    "content-type": "application/json",
    "x-request-id": "req_abc123"
  },
  "timestamp": "2026-03-15T08:34:08.123Z"
}
```

### 请求目录命名规则

- **格式**：`{毫秒时间戳}_{HTTP方法}_{URL编码的路径}`
- 路径中的 `/` 被编码为 `%2F`
- 路径最大长度截断为 200 字符
- 空路径（根路径 `/`）使用 `root` 代替

## 支持的文件类型

代理会根据 `Content-Type` 自动检测并使用对应的文件扩展名保存内容：

| Content-Type | 扩展名 | 说明 |
|---|---|---|
| `application/json` | `.json` | JSON 内容会被**自动格式化**（pretty-print） |
| `text/html` | `.html` | HTML 页面 |
| `text/plain` | `.txt` | 纯文本 |
| `text/css` | `.css` | CSS 样式表 |
| `text/javascript` / `application/javascript` | `.js` | JavaScript |
| `application/xml` / `text/xml` | `.xml` | XML 文档 |
| `text/event-stream` | `.txt` | SSE 事件流（如 AI 流式响应） |
| `image/jpeg` | `.jpg` | JPEG 图片 |
| `image/png` | `.png` | PNG 图片 |
| `image/gif` | `.gif` | GIF 图片 |
| `image/svg+xml` | `.svg` | SVG 矢量图 |
| `image/webp` | `.webp` | WebP 图片 |
| `application/pdf` | `.pdf` | PDF 文档 |
| `application/zip` | `.zip` | ZIP 压缩包 |
| `application/octet-stream` | `.bin` | 二进制数据 |

- **JSON 内容**：自动解析并格式化输出。解析失败时回退保存为 `.txt`
- **二进制内容**（图片、PDF、ZIP、音视频）：以原始 `Buffer` 直接写入
- **未知类型**：默认使用 `.bin` 扩展名

## 错误处理

当转发请求到目标服务器失败时（网络错误、连接拒绝等）：

1. 在请求目录中写入 `error.txt`，包含错误消息和完整堆栈信息
2. 向客户端返回 **HTTP 502 Bad Gateway**，响应体为 `Proxy error: {错误信息}`

```
# error.txt 示例
Error proxying request: connect ECONNREFUSED 127.0.0.1:4141
Error: connect ECONNREFUSED 127.0.0.1:4141
    at TCPConnectWrap.afterConnect [as oncomplete] (node:net:1595:16)
```

## 适用场景

- **AI 助手流量分析**：捕获 GitHub Copilot、Claude Code、Codex 等 AI 编程助手与后端 API 的完整通信内容
- **API 调试**：在不修改客户端或服务器代码的情况下，记录所有 API 请求/响应
- **协议逆向工程**：分析未公开文档的 API 调用模式和数据格式
- **性能分析**：通过时间戳对比分析请求延迟
- **问题复现**：完整保留请求上下文，方便离线分析和问题复现
- **流量回放**：保存的请求数据可用于构建测试用例或回放测试

### 典型使用方式

将 AI 助手的 API 请求指向代理服务器，代理自动记录后转发到真实后端：

```
AI 助手  →  Proxy (localhost:8080)  →  真实 API 服务器 (localhost:4141)
                    ↓
              logs/ 目录保存完整流量
```
