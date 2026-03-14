"""
Filter captured HTTP(S) logs by time range and domains.

Reads from a captured log directory (e.g. logs/all/captured) and copies
matching requests to an output directory, preserving the same structure.

Usage:
    python filter_logs.py -c filter.yaml
    python filter_logs.py --input ./logs/all/captured --output ./logs/filtered \
                          --domains api.openai.com --from 2026-03-14T10:00 --to 2026-03-14T18:00
    python filter_logs.py --input ./logs/all/captured --output ./logs/filtered \
                          --domains api.openai.com --from 2026-03-14T10:00 --to 2026-03-14T18:00 \
                          --access-input ./logs/all/access --access-output ./logs/filtered/access

Config YAML example (filter.yaml):
    input_dir: ./logs/all/captured
    output_dir: ./logs/filtered/captured
    access_input_dir: ./logs/all/access
    access_output_dir: ./logs/filtered/access
    from: "2026-03-14T10:00"
    to: "2026-03-14T18:00"
    filter_domains:
      - api.openai.com
      - openai.com
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml


def parse_timestamp_from_dirname(dirname: str) -> int | None:
    """
    Extract millisecond timestamp from request directory name.
    Format: {timestamp_ms}_{METHOD}_{path}
    """
    match = re.match(r"^(\d+)_", dirname)
    if match:
        return int(match.group(1))
    return None


def parse_minute_dir(dirname: str) -> datetime | None:
    """
    Parse minute directory name like 20260314_154700 -> datetime.
    """
    try:
        return datetime.strptime(dirname, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def load_metadata(req_dir: Path) -> dict | None:
    meta_file = req_dir / "request_metadata.json"
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def matches_domain(meta: dict, domains: list[str]) -> bool:
    if not domains:
        return True
    host = meta.get("host", "")
    url = meta.get("url", "")
    return any(d in host or d in url for d in domains)


def matches_method(meta: dict, methods: list[str]) -> bool:
    if not methods:
        return True
    return meta.get("method", "").upper() in [m.upper() for m in methods]


def matches_path(meta: dict, path_patterns: list[str]) -> bool:
    if not path_patterns:
        return True
    req_path = meta.get("path", "")
    return any(re.search(p, req_path) for p in path_patterns)


def matches_time(ts_ms: int, from_dt: datetime | None, to_dt: datetime | None) -> bool:
    if from_dt and ts_ms < from_dt.timestamp() * 1000:
        return False
    if to_dt and ts_ms > to_dt.timestamp() * 1000:
        return False
    return True


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {s}")


def filter_access_logs(
    access_input: Path,
    access_output: Path,
    domains: list[str],
    from_dt: datetime | None,
    to_dt: datetime | None,
    methods: list[str] | None = None,
    path_patterns: list[str] | None = None,
):
    """Filter access log files by domain and time range."""
    if not access_input.exists():
        print(f"  ⚠  Access input dir not found: {access_input}")
        return 0

    access_output.mkdir(parents=True, exist_ok=True)
    total = 0

    for log_file in sorted(access_input.glob("access_*.log")):
        # Check date range from filename (access_YYYYMMDD.log)
        match = re.search(r"access_(\d{8})\.log$", log_file.name)
        if match:
            file_date = datetime.strptime(match.group(1), "%Y%m%d")
            if from_dt and file_date.date() < from_dt.date():
                continue
            if to_dt and file_date.date() > to_dt.date():
                continue

        out_file = access_output / log_file.name
        count = 0
        with open(log_file, "r", encoding="utf-8") as fin, \
             open(out_file, "w", encoding="utf-8") as fout:
            for line in fin:
                # Parse timestamp from log line: [14/Mar/2026:15:47:32 ]
                ts_match = re.search(r'\[(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2})', line)
                if ts_match:
                    try:
                        line_dt = datetime.strptime(ts_match.group(1), "%d/%b/%Y:%H:%M:%S")
                        if from_dt and line_dt < from_dt:
                            continue
                        if to_dt and line_dt > to_dt:
                            continue
                    except ValueError:
                        pass

                # Domain filter
                if domains:
                    if not any(d in line for d in domains):
                        continue

                # Method filter on access log line
                if methods:
                    if not any(f'"{m.upper()} ' in line for m in methods):
                        continue

                # Path filter on access log line
                if path_patterns:
                    if not any(re.search(p, line) for p in path_patterns):
                        continue

                fout.write(line)
                count += 1

        if count == 0:
            out_file.unlink(missing_ok=True)
        else:
            total += count

    return total


def filter_captured_logs(
    input_dir: Path,
    output_dir: Path,
    domains: list[str],
    from_dt: datetime | None,
    to_dt: datetime | None,
    methods: list[str] | None = None,
    path_patterns: list[str] | None = None,
) -> tuple[int, int]:
    """Filter captured log directories. Returns (matched, total)."""
    if not input_dir.exists():
        print(f"  ⚠  Input dir not found: {input_dir}")
        return 0, 0

    output_dir.mkdir(parents=True, exist_ok=True)
    matched = 0
    total = 0

    # Iterate minute directories (20260314_154700)
    for minute_dir in sorted(input_dir.iterdir()):
        if not minute_dir.is_dir():
            continue
        minute_dt = parse_minute_dir(minute_dir.name)
        if minute_dt:
            # Quick skip: if the entire minute is outside the range
            if from_dt and minute_dt < from_dt.replace(second=0) and \
               (not to_dt or minute_dt < to_dt.replace(second=0)):
                # Could still have requests in range if minute_dt + 60s > from_dt
                pass  # don't skip, check individual requests

        # Iterate request directories
        for req_dir in sorted(minute_dir.iterdir()):
            if not req_dir.is_dir():
                continue
            total += 1

            # Time filter
            ts_ms = parse_timestamp_from_dirname(req_dir.name)
            if ts_ms is not None and not matches_time(ts_ms, from_dt, to_dt):
                continue

            # Domain filter
            meta = load_metadata(req_dir)
            if meta and not matches_domain(meta, domains):
                continue

            # Method filter
            if meta and methods and not matches_method(meta, methods):
                continue

            # Path pattern filter
            if meta and path_patterns and not matches_path(meta, path_patterns):
                continue

            # Copy to output
            out_minute = output_dir / minute_dir.name
            out_req = out_minute / req_dir.name
            if out_req.exists():
                shutil.rmtree(out_req)
            shutil.copytree(req_dir, out_req)
            matched += 1

    return matched, total


def parse_args():
    p = argparse.ArgumentParser(
        description="Filter captured HTTP(S) logs by time range and domains"
    )
    p.add_argument(
        "-c", "--config", type=str, default=None,
        help="Path to YAML config file",
    )
    p.add_argument(
        "--input", type=str, default=None,
        help="Input captured log directory",
    )
    p.add_argument(
        "--output", type=str, default=None,
        help="Output directory for filtered logs",
    )
    p.add_argument(
        "--access-input", type=str, default=None,
        help="Input access log directory",
    )
    p.add_argument(
        "--access-output", type=str, default=None,
        help="Output directory for filtered access logs",
    )
    p.add_argument(
        "--domains", nargs="+", default=None,
        help="Filter by domains (substring match)",
    )
    p.add_argument(
        "--from", dest="from_time", type=str, default=None,
        help="Start time (e.g. 2026-03-14T10:00)",
    )
    p.add_argument(
        "--to", type=str, default=None,
        help="End time (e.g. 2026-03-14T18:00)",
    )
    p.add_argument(
        "--methods", nargs="+", default=None,
        help="Filter by HTTP methods (e.g. POST GET)",
    )
    p.add_argument(
        "--path-patterns", nargs="+", default=None,
        help="Filter by path regex patterns (e.g. '/chat/completions')",
    )
    return p.parse_args()


def main():
    args = parse_args()

    # Load YAML config if provided
    cfg = {}
    if args.config:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = Path(__file__).parent / config_path
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        else:
            print(f"  ⚠  Config not found: {config_path}")
            sys.exit(1)

    # CLI args override YAML config
    base = Path(__file__).parent

    input_dir = Path(args.input) if args.input else (Path(cfg["input_dir"]) if "input_dir" in cfg else None)
    output_dir = Path(args.output) if args.output else (Path(cfg["output_dir"]) if "output_dir" in cfg else None)
    access_input = Path(args.access_input) if args.access_input else (Path(cfg["access_input_dir"]) if "access_input_dir" in cfg else None)
    access_output = Path(args.access_output) if args.access_output else (Path(cfg["access_output_dir"]) if "access_output_dir" in cfg else None)

    if not input_dir or not output_dir:
        print("Error: --input and --output (or input_dir/output_dir in config) are required.")
        sys.exit(1)

    # Resolve relative paths against script directory
    if not input_dir.is_absolute():
        input_dir = base / input_dir
    if not output_dir.is_absolute():
        output_dir = base / output_dir
    if access_input and not access_input.is_absolute():
        access_input = base / access_input
    if access_output and not access_output.is_absolute():
        access_output = base / access_output

    domains = args.domains or cfg.get("filter_domains", []) or []
    methods = args.methods or cfg.get("filter_methods", []) or []
    path_patterns = args.path_patterns or cfg.get("filter_path_patterns", []) or []
    from_dt = parse_dt(args.from_time or cfg.get("from"))
    to_dt = parse_dt(args.to or cfg.get("to"))

    # Print info
    print("=" * 60)
    print("  Log Filter")
    print("=" * 60)
    print(f"  Input:       {input_dir}")
    print(f"  Output:      {output_dir}")
    if access_input:
        print(f"  Access in:   {access_input}")
    if access_output:
        print(f"  Access out:  {access_output}")
    if from_dt:
        print(f"  From:        {from_dt.isoformat()}")
    if to_dt:
        print(f"  To:          {to_dt.isoformat()}")
    if domains:
        print(f"  Domains:     {', '.join(domains[:5])}")
        if len(domains) > 5:
            print(f"               ... and {len(domains) - 5} more")
    else:
        print("  Domains:     (all)")
    if methods:
        print(f"  Methods:     {', '.join(methods)}")
    if path_patterns:
        print(f"  Paths:       {', '.join(path_patterns)}")
    print("=" * 60)

    # Filter captured logs
    matched, total = filter_captured_logs(input_dir, output_dir, domains, from_dt, to_dt, methods, path_patterns)
    print(f"\n  Captured: {matched}/{total} requests matched")

    # Filter access logs
    if access_input and access_output:
        access_count = filter_access_logs(access_input, access_output, domains, from_dt, to_dt, methods, path_patterns)
        print(f"  Access:   {access_count} log lines matched")

    print(f"\n  Output written to: {output_dir}")
    if access_output:
        print(f"  Access log output: {access_output}")


if __name__ == "__main__":
    main()
