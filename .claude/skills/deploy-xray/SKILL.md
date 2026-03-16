---
name: deploy-xray
description: >
  Deploy the llm-prompt-xray toolkit — set up Sniffer (HTTPS traffic capture) and
  Log Viewer (web analysis UI) so they work together out of the box.
  Use this skill whenever the user asks to deploy, set up, install, configure,
  or start the llm-prompt-xray project, or any combination of Sniffer + Log Viewer.
  Also trigger when the user mentions "capture AI traffic", "analyze Copilot prompts",
  "set up the proxy logger", or "one-click deploy".
---

# Deploy llm-prompt-xray

One-click deployment of the **Sniffer** (HTTPS traffic capture) and **Log Viewer** (web analysis UI),
automatically wired together so captured traffic is immediately viewable in the browser.

## Overview

This skill guides you through deploying two components that work as a pipeline:

```
AI Coding Assistant  →  Sniffer (mitmproxy)  →  logs on disk  →  Log Viewer (Next.js)
```

The user picks which AI assistant(s) to capture, and the skill handles:
1. Installing all dependencies
2. Generating correct `.env` configs so Log Viewer reads Sniffer's output directories
3. Starting both services
4. Verifying they're working

## Prerequisites Detection

Before starting, check the user's environment. Run these checks and report any issues:

```
1. Python >= 3.12    → python --version  (or python3 --version)
2. uv installed      → uv --version
3. Node.js >= 18     → node --version
4. Yarn              → yarn --version
5. mitmproxy CA cert → check if ~/.mitmproxy/mitmproxy-ca-cert.pem exists
```

If `uv` is missing, suggest: `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`

If the mitmproxy CA cert doesn't exist, warn the user that HTTPS capture requires installing the
mitmproxy CA certificate. On first run mitmproxy auto-generates it; the user will need to trust it
in their OS/browser. Link: https://docs.mitmproxy.org/stable/concepts-certificates/

## Deployment Steps

### Step 1: Install Dependencies

From the project root directory:

```bash
# Node.js dependencies (proxy + log-viewer)
yarn install

# Python dependencies (sniffer)
cd apps/sniffer
uv sync
cd ../..
```

### Step 2: Choose Capture Target

Ask the user which AI assistant(s) they want to capture. Map to sniffer configs:

| AI Assistant | Config File | Port | Notes |
|-------------|-------------|------|-------|
| All traffic | `config.all.yaml` | 8888 | Excludes noisy domains (Teams telemetry etc.) |
| GitHub Copilot | `config.copilot.yaml` | 8893 | VS Code Copilot domains |
| Claude Code | `config.claude-code.yaml` | 8894 | Captures `llmapi.weavejam.com` |
| OpenCode | `config.opencode.yaml` | 8891 | Uses GitHub Copilot API |
| OpenAI Codex CLI | `config.codex.yaml` | 8892 | `api.openai.com` |

If the user isn't sure, recommend `config.all.yaml` — it captures everything and they can filter later.

### Step 3: Configure Log Viewer to Read Sniffer Output

The critical integration step: configure Log Viewer's `LOG_DIRS` env variable to point at
the Sniffer's output directories.

The mapping from sniffer config → capture directory:

| Config | `capture_dir` in YAML | Resulting LOG_DIRS path |
|--------|----------------------|------------------------|
| `config.all.yaml` | `./logs/all/captured` | `../sniffer/logs/all/captured` |
| `config.copilot.yaml` | `./logs/copilot/captured` | `../sniffer/logs/copilot/captured` |
| `config.claude-code.yaml` | `./logs/claude-code/captured` | `../sniffer/logs/claude-code/captured` |
| `config.opencode.yaml` | `./logs/opencode/captured` | `../sniffer/logs/opencode/captured` |
| `config.codex.yaml` | `./logs/codex/captured` | `../sniffer/logs/codex/captured` |

Paths in LOG_DIRS are relative to `apps/log-viewer/`.

**Generate the `.env` file for Log Viewer:**

For the chosen config(s), produce `apps/log-viewer/.env`:

```env
PORT=3001
LOG_DIRS=[{"name":"<display-name>","path":"../sniffer/logs/<subdir>/captured"}]
```

Example for "all traffic":

```env
PORT=3001
LOG_DIRS=[{"name":"all","path":"../sniffer/logs/all/captured"}]
```

Example for multiple targets:

```env
PORT=3001
LOG_DIRS=[{"name":"all","path":"../sniffer/logs/all/captured"},{"name":"copilot","path":"../sniffer/logs/copilot/captured"},{"name":"claude-code","path":"../sniffer/logs/claude-code/captured"}]
```

If the user also wants to include the HTTP proxy's logs, add:

```json
{"name":"proxy","path":"../../logs"}
```

### Step 4: Start Services

Start both services. The Sniffer must start first (it creates the log directories on first capture).

**Terminal 1 — Sniffer:**

```bash
cd apps/sniffer
uv run python run.py -c <chosen-config>.yaml
```

On Windows, the Sniffer automatically sets the system proxy. The user will see output like:

```
============================================================
  HTTP(S) Traffic Sniffer
============================================================
  Proxy:       http://127.0.0.1:8888
  Capture dir: .../logs/all/captured
  Sys proxy:   enabled
============================================================
  Press Ctrl+C to stop
```

**Terminal 2 — Log Viewer:**

```bash
# From project root
yarn dev:viewer
```

Opens at http://localhost:3001.

The Sniffer MUST keep running in its own terminal. Use background terminal for the sniffer
and a separate terminal for the log viewer, so both run concurrently.

### Step 5: Verify Integration

After both are running:

1. The user should trigger some AI assistant activity (e.g., open VS Code with Copilot, or run Claude Code)
2. Check Sniffer terminal — should show intercepted requests:
   `[#1] POST https://api.github.com/... -> 200`
3. Open http://localhost:3001 in a browser
4. Requests should appear in the Log Viewer list
5. Click a request to see full details — for LLM calls, the LLM call detail view will show parsed conversations

If Log Viewer shows "no logs", common causes:
- Sniffer hasn't captured anything yet (no AI assistant activity)
- LOG_DIRS path mismatch — double-check the `.env` paths
- The selected log directory in the dropdown doesn't match where Sniffer is writing

## Platform Notes

### Windows
- Sniffer auto-manages the system proxy via Windows Registry
- If the sniffer crashes, the proxy may be left set — restart sniffer to auto-recover
- Use `Ctrl+C` to cleanly stop the sniffer and restore the proxy

### Linux / macOS
- `auto_proxy: true` only works on Windows. On other platforms, use `--no-proxy` and manually
  configure the proxy:
  ```bash
  export HTTPS_PROXY=http://127.0.0.1:8888
  export HTTP_PROXY=http://127.0.0.1:8888
  ```
- Or configure the specific application to use the proxy

### mitmproxy Certificate
- First run creates `~/.mitmproxy/mitmproxy-ca-cert.pem`
- Must be trusted by the OS or browser for HTTPS interception
- Without the cert, HTTPS requests will fail with certificate errors
- Docs: https://docs.mitmproxy.org/stable/concepts-certificates/

## Production Deployment (Linux/systemd)

For persistent deployment, use the systemd service files in `systemd/`:

```bash
# Build
yarn build

# Install services
sudo cp systemd/log-viewer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now log-viewer.service
```

The sniffer is typically run interactively (since it manages system proxy), not as a daemon.

## Quick Reference

| Component | Directory | Start Command | Default URL |
|-----------|-----------|---------------|-------------|
| Sniffer | `apps/sniffer` | `uv run python run.py -c config.all.yaml` | proxy at `:8888` |
| Log Viewer | `apps/log-viewer` | `yarn dev:viewer` | http://localhost:3001 |
| Both (no sniffer) | root | `yarn dev` | proxy `:8080`, viewer `:3001` |
