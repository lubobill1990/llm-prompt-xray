# Sniffer — HTTPS 流量嗅探器

基于 [mitmproxy](https://mitmproxy.org/) 的 HTTPS 流量捕获工具。通过中间人代理（MITM）拦截系统网络流量，自动设置 Windows 系统代理，将请求/响应完整保存到磁盘。主要用于分析 AI 编程助手（GitHub Copilot、Claude Code、OpenCode、Codex CLI 等）的 API 调用。

## 目录

- [Sniffer — HTTPS 流量嗅探器](#sniffer--https-流量嗅探器)
  - [目录](#目录)
  - [技术栈](#技术栈)
  - [架构概述](#架构概述)
  - [安装](#安装)
  - [使用方法](#使用方法)
    - [启动嗅探器](#启动嗅探器)
    - [使用预设配置](#使用预设配置)
    - [过滤已捕获的日志](#过滤已捕获的日志)
  - [配置文件说明](#配置文件说明)
    - [嗅探器配置 (run.py)](#嗅探器配置-runpy)
    - [过滤器配置 (filter\_logs.py)](#过滤器配置-filter_logspy)
  - [预设配置一览](#预设配置一览)
    - [嗅探器预设](#嗅探器预设)
    - [过滤器预设](#过滤器预设)
  - [日志格式](#日志格式)
    - [捕获日志 (Capture Log)](#捕获日志-capture-log)
    - [访问日志 (Access Log)](#访问日志-access-log)
  - [Windows 系统代理管理](#windows-系统代理管理)
    - [自动代理设置](#自动代理设置)
    - [上游代理链式转发](#上游代理链式转发)
    - [崩溃恢复](#崩溃恢复)
  - [适用场景](#适用场景)
  - [CLI 参数参考](#cli-参数参考)
    - [run.py](#runpy)
    - [filter\_logs.py](#filter_logspy)

---

## 技术栈

| 组件 | 版本 / 说明 |
|------|-------------|
| Python | >= 3.12 |
| [mitmproxy](https://mitmproxy.org/) | >= 12.2.1 — HTTPS 流量拦截核心 |
| [PyYAML](https://pyyaml.org/) | >= 6.0.3 — 配置文件解析 |
| [uv](https://docs.astral.sh/uv/) | 推荐的 Python 包管理器 |
| Windows Registry (winreg) | 系统代理自动设置/恢复 |

---

## 架构概述

```
┌────────────────────────────────────────────────────────────────┐
│                      应用程序 (浏览器/IDE)                       │
│                     HTTP_PROXY=127.0.0.1:port                  │
└─────────────────────────┬──────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Sniffer (mitmproxy DumpMaster)              │
│                                                                 │
│  ┌─────────────┐  ┌────────────────┐  ┌──────────────────────┐ │
│  │ 域名过滤    │  │ 路径模式排除   │  │ 排除域名             │ │
│  │ (include)   │  │ (regex)        │  │ (exclude)            │ │
│  └──────┬──────┘  └───────┬────────┘  └──────────┬───────────┘ │
│         │                 │                      │              │
│         └─────────┬───────┘──────────────────────┘              │
│                   ▼                                             │
│  ┌──────────────────────────────────────────┐                   │
│  │ Access Log (nginx 格式, 所有请求)        │                   │
│  │ Capture Log (匹配的请求完整保存)         │                   │
│  └──────────────────────────────────────────┘                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │ (如有上游代理则链式转发)
                          ▼
                    ┌──────────────┐
                    │  目标服务器   │
                    └──────────────┘
```

**核心模块：**

| 文件 | 说明 |
|------|------|
| `run.py` | 主入口。启动 mitmproxy、设置系统代理、捕获流量、写日志 |
| `filter_logs.py` | 事后过滤工具。按时间范围、域名、方法、路径、请求头过滤已捕获日志 |
| `copilot_capture.py` | 旧版独立 mitmproxy addon（简化版捕获，仅供参考） |
| `config*.yaml` | 嗅探器预设配置 |
| `filter.*.yaml` | 日志过滤器预设配置 |

---

## 安装

```bash
# 使用 uv (推荐)
uv sync

# 或使用 pip
pip install -e .
```

> **注意**：mitmproxy 首次启动时会在 `~/.mitmproxy/` 下生成 CA 证书。需要将 `mitmproxy-ca-cert.pem` 安装为系统/浏览器信任的根证书，才能正确拦截 HTTPS 流量。详见 [mitmproxy 证书文档](https://docs.mitmproxy.org/stable/concepts-certificates/)。

---

## 使用方法

### 启动嗅探器

```bash
# 使用默认配置 (config.yaml — GitHub Copilot 域名)
uv run run.py

# 使用指定配置文件
uv run run.py -c config.all.yaml

# 覆盖端口号 (CLI 参数优先于配置文件)
uv run run.py -c config.all.yaml --port 9999

# 不自动设置系统代理 (手动模式)
uv run run.py --no-proxy
```

启动后输出示例：

```
============================================================
  HTTP(S) Traffic Sniffer
============================================================
  Config:      C:\src\llm-prompt-xray\apps\sniffer\config.all.yaml
  Proxy:       http://127.0.0.1:8888
  Capture dir: C:\src\llm-prompt-xray\apps\sniffer\logs\all\captured
  Access log:  C:\src\llm-prompt-xray\apps\sniffer\logs\all\access
  Filter:      (all traffic)
  Exclude:     teams.events.data.microsoft.com, monitor.azure.com, sharepoint.com
               ... and 4 more
  Sys proxy:   enabled
  State file:  C:\src\llm-prompt-xray\apps\sniffer\.proxy_state.json
============================================================
  Press Ctrl+C to stop
```

按 `Ctrl+C` 停止，系统代理会自动恢复。

### 使用预设配置

```bash
# 捕获所有流量（排除噪音域名）
uv run run.py -c config.all.yaml

# 仅捕获 GitHub Copilot
uv run run.py -c config.copilot.yaml

# 仅捕获 Claude Code
uv run run.py -c config.claude-code.yaml

# 仅捕获 OpenCode
uv run run.py -c config.opencode.yaml

# 仅捕获 OpenAI Codex CLI
uv run run.py -c config.codex.yaml
```

### 过滤已捕获的日志

使用 `filter_logs.py` 对已捕获的日志进行二次过滤：

```bash
# 通过 YAML 配置文件
uv run filter_logs.py -c filter.all2githubcopilot.yaml

# 通过命令行参数
uv run filter_logs.py \
    --input ./logs/all/captured \
    --output ./logs/filtered/captured \
    --domains api.github.com copilot-proxy.githubusercontent.com \
    --from 2026-03-14T10:00 \
    --to 2026-03-14T18:00

# 同时过滤 access log
uv run filter_logs.py \
    --input ./logs/all/captured \
    --output ./logs/filtered/captured \
    --access-input ./logs/all/access \
    --access-output ./logs/filtered/access \
    --domains api.openai.com \
    --methods POST \
    --path-patterns "/chat/completions"
```

---

## 配置文件说明

### 嗅探器配置 (run.py)

YAML 格式，所有字段均可选（有默认值）：

```yaml
# 代理监听端口 (默认: 8888)
port: 8888

# 是否自动设置 Windows 系统代理 (默认: true)
# 启动时设置，退出时恢复原始配置
auto_proxy: true

# ─── 日志目录 ───────────────────────────────────────

# 完整请求/响应捕获目录 (默认: ./captured_logs)
# 每个请求生成独立子目录，包含 metadata + body 文件
capture_dir: ./captured_logs

# nginx 风格访问日志目录 (默认: ./access_logs)
# 每天一个文件，记录所有经过代理的请求（一行一条）
access_log_dir: ./access_logs

# ─── 域名过滤 ───────────────────────────────────────

# 仅捕获匹配这些域名的流量 (子串匹配)
# 留空 = 捕获所有流量
# 支持 "copilot" 快捷预设，自动展开为所有已知 Copilot 域名
filter_domains:
  - api.github.com
  - copilot-proxy.githubusercontent.com
  # 或使用预设:
  # - copilot

# 排除这些域名的流量（即使匹配 filter_domains 也不捕获）
# 仅影响捕获日志，access log 仍会记录
exclude_domains:
  - teams.events.data.microsoft.com
  - monitor.azure.com

# 排除匹配这些正则的路径
exclude_path_patterns:
  - ^/OneCollector/
  - ^/v1/engines/gpt-41-copilot/completions
```

**默认值：**

| 字段 | 默认值 |
|------|--------|
| `port` | `8888` |
| `auto_proxy` | `true` |
| `capture_dir` | `./captured_logs` |
| `access_log_dir` | `./access_logs` |
| `filter_domains` | `[]`（全部捕获） |
| `exclude_domains` | `[]` |
| `exclude_path_patterns` | `[]` |

**`copilot` 预设展开域名：**

```
api.github.com
copilot-proxy.githubusercontent.com
api.individual.githubcopilot.com
api.business.githubcopilot.com
api.enterprise.githubcopilot.com
default.exp-tas.com
copilot-telemetry.githubusercontent.com
githubcopilot.com
```

### 过滤器配置 (filter_logs.py)

```yaml
# 输入/输出目录
input_dir: ./logs/all/captured
output_dir: ./logs/filtered/captured
access_input_dir: ./logs/all/access        # 可选
access_output_dir: ./logs/filtered/access   # 可选

# 时间范围 (可选, 支持格式: YYYY-MM-DDTHH:MM, YYYY-MM-DD HH:MM:SS, YYYY-MM-DD)
from: "2026-03-14T10:00"
to: "2026-03-14T18:00"

# 结构化请求过滤器
# - 数组元素之间为 OR 关系（匹配任一即通过）
# - 同一元素内的字段为 AND 关系（必须全部匹配）
# - headers_patterns 数组元素之间为 OR 关系
# - headers_patterns 单个元素内的键值对为 AND 关系
request_filters:
  - domains: ["api.github.com", "copilot-proxy.githubusercontent.com"]
    methods: ["POST"]
    path_patterns: ["/chat/completions"]
    headers_patterns:
      - Content-Type: "application/json"
        vscode-sessionid: ".*"
```

**过滤器逻辑：**

```
request_filters:          # OR — 匹配任意一个 filter 即保留
  - domains: [...]        # AND ┐
    methods: [...]        # AND ├─ 同一 filter 内所有条件必须同时满足
    path_patterns: [...]  # AND │
    headers_patterns:     # AND ┘
      - header1: "regex"  # OR ┐ headers_patterns 数组元素之间为 OR
        header2: "regex"  #    │ 同一元素内为 AND
      - header3: "regex"  # OR ┘
```

---

## 预设配置一览

### 嗅探器预设

| 配置文件 | 端口 | 用途 | 域名过滤 |
|----------|------|------|----------|
| `config.yaml` | 8888 | GitHub Copilot 标准捕获 | Copilot 相关域名 |
| `config.all.yaml` | 8888 | 全流量捕获 | 无过滤，排除噪音域名 |
| `config.copilot.yaml` | 8893 | GitHub Copilot 专用 | Copilot 域名 |
| `config.claude-code.yaml` | 8894 | Claude Code | `llmapi.weavejam.com` |
| `config.opencode.yaml` | 8891 | OpenCode (GitHub Copilot API) | Copilot API 域名 |
| `config.codex.yaml` | 8892 | OpenAI Codex CLI | `api.openai.com` |

### 过滤器预设

| 配置文件 | 用途 |
|----------|------|
| `filter.all2githubcopilot.yaml` | 从全流量日志中提取 GitHub Copilot 请求 |
| `filter.all2opencode.yaml` | 从全流量日志中提取 OpenCode 请求 |

---

## 日志格式

### 捕获日志 (Capture Log)

与 monorepo 中 proxy 应用使用相同的目录结构，每个请求保存为独立子目录：

```
capture_dir/
└── 20260314_154700/                          # 分钟级目录 (YYYYMMDD_HHMMSS)
    ├── 1710425220123_POST_api%2Fv1%2Fchat/    # 请求目录 ({timestamp_ms}_{METHOD}_{url_path})
    │   ├── request_metadata.json              # 请求元数据
    │   ├── request_body.json                  # 请求体 (JSON 格式化)
    │   ├── response_metadata.json             # 响应元数据
    │   └── response_body.json                 # 响应体
    └── 1710425221456_GET_api%2Fmodels/
        ├── request_metadata.json
        ├── response_metadata.json
        └── response_body.json
```

**request_metadata.json 示例：**

```json
{
  "method": "POST",
  "url": "https://api.github.com/copilot_internal/v2/token",
  "host": "api.github.com",
  "path": "/copilot_internal/v2/token",
  "headers": {
    "Host": "api.github.com",
    "Authorization": "token ghu_...",
    "Content-Type": "application/json"
  },
  "timestamp": "2026-03-14T15:47:32.123456"
}
```

**response_metadata.json 示例：**

```json
{
  "statusCode": 200,
  "headers": {
    "Content-Type": "application/json",
    "X-Request-Id": "abcd-1234"
  },
  "timestamp": "2026-03-14T15:47:32.456789"
}
```

**请求体/响应体保存格式**（根据 Content-Type 自动判断）：

| Content-Type | 文件名 | 格式 |
|-------------|--------|------|
| `*/json` | `*_body.json` | JSON pretty-printed (缩进 2 空格) |
| `text/*`, `*/javascript`, `*/event-stream` | `*_body.txt` | 原始文本 |
| 其他 / 二进制 | `*_body.bin` | 原始二进制 |

### 访问日志 (Access Log)

nginx combined 风格，每天自动轮转，**记录所有经过代理的请求**（不受域名过滤影响）：

```
access_log_dir/
├── access_20260314.log
└── access_20260315.log
```

日志格式：

```
[$time] $remote_addr "$method $url $protocol" $status $body_bytes ${duration}ms "$user_agent"
```

示例：

```
[14/Mar/2026:15:47:32 +0000] 127.0.0.1 "POST https://api.github.com/copilot_internal/v2/token HTTP/2.0" 200 1234 45ms "vscode/1.95.0"
```

---

## Windows 系统代理管理

### 自动代理设置

启动时（`auto_proxy: true`）：

1. 读取当前 Windows 系统代理设置（通过注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings`）
2. 如果已存在系统代理，检测并配置为上游代理（链式转发）
3. 将自身设置为系统代理 (`127.0.0.1:{port}`)
4. 保存原始代理设置到 `.proxy_state.json`（用于崩溃恢复）

退出时：

1. 恢复原始代理设置
2. 删除 `.proxy_state.json`

### 上游代理链式转发

如果启动时检测到已有系统代理（非嗅探器自身），自动配置为上游代理：

```
应用程序 → Sniffer (127.0.0.1:8888) → 已有代理 (upstream) → 目标服务器
```

mitmproxy 会以 `upstream:http://{existing_proxy}/` 模式运行。

### 崩溃恢复

如果嗅探器异常终止（崩溃、强杀进程等），系统代理可能残留指向已关闭的嗅探器端口。下次启动时会自动检测并恢复：

1. 读取 `.proxy_state.json` 中保存的原始设置
2. 检查当前系统代理是否仍指向 `127.0.0.1:*`
3. 如果是，自动恢复原始代理设置

**信号处理**：注册了 `SIGINT`、`SIGTERM`、`SIGBREAK`（Windows 专用）处理函数，确保在多种终止场景下都能正确恢复代理。

---

## 适用场景

- **分析 AI 编程助手 API 调用**：捕获 GitHub Copilot、Claude Code、OpenCode、Codex CLI 等工具的完整请求/响应，分析 prompt 构造、模型参数、上下文内容
- **对比不同 AI 助手**：使用 `config.all.yaml` 全量捕获，再用 `filter_logs.py` 按工具分类提取
- **调试 API 问题**：查看完整的请求头、请求体、响应状态码和响应体
- **流量审计**：通过 access log 了解某个时间段内的请求概况
- **性能分析**：access log 中记录了每个请求的耗时（毫秒）
- **配合 Log Viewer 使用**：捕获日志格式与 monorepo 中的 `log-viewer` 应用兼容，可在 Web UI 中可视化浏览

---

## CLI 参数参考

### run.py

```
usage: run.py [-h] [-c CONFIG] [--port PORT] [--no-proxy]

HTTP(S) traffic sniffer powered by mitmproxy

options:
  -h, --help            显示帮助信息
  -c, --config CONFIG   YAML 配置文件路径 (默认: config.yaml)
  --port PORT           覆盖代理端口
  --no-proxy            不设置系统代理（手动模式）
```

### filter_logs.py

```
usage: filter_logs.py [-h] [-c CONFIG] [--input INPUT] [--output OUTPUT]
                      [--access-input ACCESS_INPUT] [--access-output ACCESS_OUTPUT]
                      [--domains DOMAINS [DOMAINS ...]] [--from FROM_TIME] [--to TO]
                      [--methods METHODS [METHODS ...]]
                      [--path-patterns PATH_PATTERNS [PATH_PATTERNS ...]]

Filter captured HTTP(S) logs by time range and domains

options:
  -h, --help            显示帮助信息
  -c, --config CONFIG   YAML 配置文件路径
  --input INPUT         输入目录（已捕获日志）
  --output OUTPUT       输出目录（过滤结果）
  --access-input        访问日志输入目录
  --access-output       访问日志输出目录
  --domains             按域名过滤（子串匹配，多个用空格分开）
  --from                开始时间 (如 2026-03-14T10:00)
  --to                  结束时间 (如 2026-03-14T18:00)
  --methods             按 HTTP 方法过滤 (如 POST GET)
  --path-patterns       按路径正则过滤 (如 "/chat/completions")
```