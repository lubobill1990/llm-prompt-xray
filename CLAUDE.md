# llm-prompt-xray

AI 编程助手流量分析工具链 — 捕获、记录、分析 LLM API 调用。

## 项目结构

Yarn workspaces monorepo，包含三个应用：

- `apps/proxy` — HTTP 代理服务器（Node.js + Hono）
- `apps/sniffer` — HTTPS 流量嗅探器（Python + mitmproxy）
- `apps/log-viewer` — 日志查看器 Web UI（Next.js + React）

## Skills

### deploy-xray

一键部署 Sniffer + Log Viewer 的完整指南。当用户请求部署、配置、启动项目时使用。

文件：`.claude/skills/deploy-xray/SKILL.md`
