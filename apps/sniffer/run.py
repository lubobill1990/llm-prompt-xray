"""
HTTP(S) Sniffer - Captures network traffic via mitmproxy.

Usage:
    python run.py                       # Use default config.yaml
    python run.py -c my_config.yaml     # Use custom config file
    python run.py --port 9999           # Override port (CLI > config)
    python run.py --no-proxy            # Don't set system proxy

Press Ctrl+C to stop. System proxy is automatically restored on exit.
"""

import argparse
import atexit
import json
import time
import winreg
from datetime import datetime, timezone
from pathlib import Path

import yaml
from mitmproxy import http, ctx, options
from mitmproxy.tools.dump import DumpMaster

# ─── Default Copilot domains (expanded when "copilot" preset is used) ────────
COPILOT_DOMAINS = [
    "api.github.com",
    "copilot-proxy.githubusercontent.com",
    "api.individual.githubcopilot.com",
    "api.business.githubcopilot.com",
    "api.enterprise.githubcopilot.com",
    "default.exp-tas.com",
    "copilot-telemetry.githubusercontent.com",
    "githubcopilot.com",
]

# ─── Config ──────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "port": 8888,
    "auto_proxy": True,
    "capture_dir": "./captured_logs",
    "access_log_dir": "./access_logs",
    "filter_domains": [],
    "exclude_domains": [],
    "exclude_path_patterns": [],
}


def load_config(config_path: Path) -> dict:
    """Load YAML config, falling back to defaults for missing keys."""
    cfg = dict(DEFAULT_CONFIG)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        cfg.update({k: v for k, v in user_cfg.items() if v is not None})
    else:
        print(f"  ⚠  Config not found: {config_path}, using defaults")
    return cfg


def resolve_domains(raw: list[str] | None) -> list[str] | None:
    """Expand the 'copilot' preset and return domain list (None = all)."""
    if not raw:
        return None
    expanded: list[str] = []
    for d in raw:
        if d.lower() == "copilot":
            expanded.extend(COPILOT_DOMAINS)
        else:
            expanded.append(d)
    return expanded or None


# ─── Windows proxy registry ─────────────────────────────────────────────────
INET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def get_proxy_settings() -> dict:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INET_SETTINGS) as key:
            enable = winreg.QueryValueEx(key, "ProxyEnable")[0]
            try:
                server = winreg.QueryValueEx(key, "ProxyServer")[0]
            except FileNotFoundError:
                server = ""
            return {"ProxyEnable": enable, "ProxyServer": server}
    except Exception:
        return {"ProxyEnable": 0, "ProxyServer": ""}


def set_proxy(enable: bool, server: str = ""):
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, INET_SETTINGS, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enable else 0)
        if server:
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, server)
    try:
        import ctypes
        internet_set_option = ctypes.windll.Wininet.InternetSetOptionW
        internet_set_option(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
        internet_set_option(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH
    except Exception:
        pass


# ─── Access log (nginx-style) ───────────────────────────────────────────────

class AccessLog:
    """
    Writes one-line-per-request logs in nginx combined-like format:
      $time $remote_addr "$method $url $protocol" $status $body_bytes $duration_ms "$user_agent"
    Rotates to a new file each day.
    """

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_date: str = ""
        self._file = None

    def _rotate(self, today: str):
        if self._file:
            self._file.close()
        log_path = self.log_dir / f"access_{today}.log"
        self._file = open(log_path, "a", encoding="utf-8", buffering=1)  # line-buffered
        self._current_date = today

    def write(self, flow: http.HTTPFlow):
        now = datetime.now()
        today = now.strftime("%Y%m%d")
        if today != self._current_date:
            self._rotate(today)

        ts = now.strftime("%d/%b/%Y:%H:%M:%S %z") or now.strftime("%d/%b/%Y:%H:%M:%S +0000")
        remote = flow.client_conn.peername[0] if flow.client_conn.peername else "-"
        method = flow.request.method
        url = flow.request.pretty_url
        protocol = flow.request.http_version
        status = flow.response.status_code if flow.response else 0
        body_bytes = len(flow.response.raw_content) if flow.response and flow.response.raw_content else 0
        duration_ms = int((flow.response.timestamp_end - flow.request.timestamp_start) * 1000) if flow.response and flow.response.timestamp_end and flow.request.timestamp_start else 0
        ua = flow.request.headers.get("user-agent", "-")

        line = f'[{ts}] {remote} "{method} {url} {protocol}" {status} {body_bytes} {duration_ms}ms "{ua}"\n'
        self._file.write(line)

    def close(self):
        if self._file:
            self._file.close()
            self._file = None


# ─── Capture log (same format as proxy/src/index.ts) ────────────────────────

def get_minute_directory(log_dir: Path) -> Path:
    now = datetime.now()
    dir_name = now.strftime("%Y%m%d_%H%M00")
    dir_path = log_dir / dir_name
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def get_request_directory(log_dir: Path, method: str, url_path: str) -> Path:
    timestamp = int(time.time() * 1000)
    safe_path = (
        url_path.lstrip("/")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
        .replace("*", "_")
        .replace("?", "_")
        .replace('"', "_")
        .replace("<", "_")
        .replace(">", "_")
        .replace("|", "_")[:100]
        or "root"
    )
    dir_name = f"{timestamp}_{method}_{safe_path}"
    minute_dir = get_minute_directory(log_dir)
    req_dir = minute_dir / dir_name
    req_dir.mkdir(parents=True, exist_ok=True)
    return req_dir


def save_body(dir_path: Path, prefix: str, content_type: str | None, data: bytes):
    if not data:
        return
    if content_type and "json" in content_type:
        try:
            parsed = json.loads(data.decode("utf-8", errors="replace"))
            (dir_path / f"{prefix}_body.json").write_text(
                json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    if content_type and ("text" in content_type or "javascript" in content_type or "event-stream" in content_type):
        (dir_path / f"{prefix}_body.txt").write_bytes(data)
    else:
        (dir_path / f"{prefix}_body.bin").write_bytes(data)


# ─── mitmproxy Addon ────────────────────────────────────────────────────────

class TrafficCapture:
    def __init__(
        self,
        capture_dir: Path,
        access_log: AccessLog,
        filter_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        exclude_path_patterns: list[str] | None = None,
    ):
        self.capture_dir = capture_dir
        self.access_log = access_log
        self.filter_domains = filter_domains
        self.exclude_domains = exclude_domains or []
        self.exclude_path_patterns = exclude_path_patterns or []
        self.count = 0

    def _match(self, host: str, path: str) -> bool:
        import re
        # Exclude check first
        if self.exclude_domains:
            if any(d in host for d in self.exclude_domains):
                return False
        if self.exclude_path_patterns:
            if any(re.search(p, path) for p in self.exclude_path_patterns):
                return False
        # Include check
        if not self.filter_domains:
            return True
        return any(d in host for d in self.filter_domains)

    def response(self, flow: http.HTTPFlow):
        host = flow.request.pretty_host
        path = flow.request.path

        # nginx-style access log — always written for ALL requests
        self.access_log.write(flow)

        if not self._match(host, path):
            return

        self.count += 1
        method = flow.request.method
        url = flow.request.pretty_url
        path = flow.request.path
        status = flow.response.status_code if flow.response else "N/A"

        ctx.log.info(f"[#{self.count}] {method} {url} -> {status}")

        # Full capture to disk
        req_dir = get_request_directory(self.capture_dir, method, path)

        req_meta = {
            "method": method,
            "url": url,
            "host": host,
            "path": path,
            "headers": dict(flow.request.headers),
            "timestamp": datetime.now().isoformat(),
        }
        (req_dir / "request_metadata.json").write_text(
            json.dumps(req_meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        save_body(
            req_dir, "request",
            flow.request.headers.get("content-type"),
            flow.request.raw_content or b"",
        )

        if flow.response:
            resp_meta = {
                "statusCode": flow.response.status_code,
                "headers": dict(flow.response.headers),
                "timestamp": datetime.now().isoformat(),
            }
            (req_dir / "response_metadata.json").write_text(
                json.dumps(resp_meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            save_body(
                req_dir, "response",
                flow.response.headers.get("content-type"),
                flow.response.raw_content or b"",
            )


# ─── Main ────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="HTTP(S) traffic sniffer powered by mitmproxy"
    )
    p.add_argument(
        "-c", "--config", type=str, default="config.yaml",
        help="Path to YAML config file (default: config.yaml)",
    )
    p.add_argument(
        "--port", type=int, default=None,
        help="Override proxy listen port",
    )
    p.add_argument(
        "--no-proxy", action="store_true",
        help="Don't set system proxy (manual mode)",
    )
    return p.parse_args()


async def run():
    args = parse_args()

    # Load config
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).parent / config_path
    cfg = load_config(config_path)

    port = args.port or cfg["port"]
    auto_proxy = cfg["auto_proxy"] and not args.no_proxy

    base = Path(__file__).parent
    capture_dir = Path(cfg["capture_dir"]) if Path(cfg["capture_dir"]).is_absolute() else base / cfg["capture_dir"]
    access_log_dir = Path(cfg["access_log_dir"]) if Path(cfg["access_log_dir"]).is_absolute() else base / cfg["access_log_dir"]
    capture_dir.mkdir(parents=True, exist_ok=True)
    access_log_dir.mkdir(parents=True, exist_ok=True)

    filter_domains = resolve_domains(cfg.get("filter_domains"))
    exclude_domains = cfg.get("exclude_domains") or []
    exclude_path_patterns = cfg.get("exclude_path_patterns") or []

    # Access log
    access_log = AccessLog(access_log_dir)

    # Save & set system proxy
    original_proxy = get_proxy_settings()
    proxy_set = False

    def restore_proxy():
        nonlocal proxy_set
        if proxy_set:
            print("\n🔄 Restoring system proxy settings...")
            set_proxy(
                bool(original_proxy["ProxyEnable"]),
                original_proxy["ProxyServer"],
            )
            proxy_set = False
            print("✅ System proxy restored.")

    atexit.register(restore_proxy)

    if auto_proxy:
        set_proxy(True, f"127.0.0.1:{port}")
        proxy_set = True

    # Print startup info
    print("=" * 60)
    print("  HTTP(S) Traffic Sniffer")
    print("=" * 60)
    print(f"  Config:      {config_path.resolve()}")
    print(f"  Proxy:       http://127.0.0.1:{port}")
    print(f"  Capture dir: {capture_dir.resolve()}")
    print(f"  Access log:  {access_log_dir.resolve()}")
    if filter_domains:
        print(f"  Filter:      {', '.join(filter_domains[:5])}")
        if len(filter_domains) > 5:
            print(f"               ... and {len(filter_domains) - 5} more")
    else:
        print("  Filter:      (all traffic)")
    if exclude_domains:
        print(f"  Exclude:     {', '.join(exclude_domains[:3])}")
        if len(exclude_domains) > 3:
            print(f"               ... and {len(exclude_domains) - 3} more")
    if exclude_path_patterns:
        print(f"  Excl paths:  {', '.join(exclude_path_patterns[:3])}")
    print(f"  Sys proxy:   {'enabled' if proxy_set else 'manual mode'}")
    print("=" * 60)
    print("  Press Ctrl+C to stop\n")

    # Start mitmproxy
    opts = options.Options(listen_port=port)
    master = DumpMaster(opts)
    master.addons.add(TrafficCapture(capture_dir, access_log, filter_domains, exclude_domains, exclude_path_patterns))

    try:
        await master.run()
    except KeyboardInterrupt:
        master.shutdown()
    finally:
        access_log.close()
        restore_proxy()


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
