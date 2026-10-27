"""Collect public playlists, decode bounded samples, publish M3U + a machine-readable audit.

Python 3.10+, FFmpeg. No clock-age gate and no TLS bypass. Does not scan IP ranges.
"""
import argparse
import concurrent.futures
import datetime
import json
import pathlib
import re
import subprocess
import urllib.parse
import urllib.request

SOURCES = [
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.m3u",
    "https://raw.githubusercontent.com/ngo5/IPTV/main/m3u/ipv4.m3u",
]
NOTICE_LABELS = {"更新时间", "支持作者", "赞助作者", "打赏", "订阅说明", "更新说明"}


def web_url(url):
    try:
        value = urllib.parse.urlsplit(url)
        return value.scheme in ("http", "https") and bool(value.hostname) and value.username is None
    except ValueError:
        return False


def parse(text, source):
    """M3U / name,url TXT; keep only the headers supported by the Android app."""
    rows, name, group, headers = [], "", "", {}
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if line.startswith("#EXTINF:"):
            title = re.search(r',(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', line)
            name = line[title.end():].strip() if title else ""
            match = re.search(r'group-title="([^"]*)"', line)
            group = match[1] if match else ""
            headers = {}
        elif line.startswith("#EXTVLCOPT:"):
            key, _, value = line.partition(":")[2].partition("=")
            key = {"http-referrer": "Referer", "http-user-agent": "User-Agent"}.get(key.lower())
            if key:
                headers[key] = value
        elif line and not line.startswith("#"):
            if line.endswith(",#genre#"):
                group = line.split(",", 1)[0]
                continue
            if not name and not web_url(line) and "," in line:
                name, line = line.split(",", 1)
            for route in re.split(r"#(?=https?://)", line):
                url, _, options = route.partition("|")
                url = urllib.parse.urljoin(source, url)
                route_headers = dict(headers)
                for key, value in urllib.parse.parse_qsl(options):
                    canonical = {"referer": "Referer", "referrer": "Referer", "user-agent": "User-Agent"}.get(key.lower())
                    if canonical:
                        route_headers[canonical] = value
                if name.strip() and web_url(url) and group.strip() not in NOTICE_LABELS and name.strip() not in NOTICE_LABELS and not re.fullmatch(r"\d{4}-\d\d-\d\d.*", name.strip()):
                    if all("\r" not in value and "\n" not in value for value in route_headers.values()):
                        rows.append(dict(name=name.strip(), group=group, url=url, headers=route_headers, source=source))
            name, headers = "", {}
    return rows


def download(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "BraviaLive-Collector/0.5"}), timeout=20) as response:
        data = response.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("playlist exceeds 4 MiB")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("gb18030")
        if text.lstrip().startswith("<"):
            raise ValueError("HTML/XML response is not a channel playlist")
        return parse(text, url)


def probe(row, ffmpeg):
    # Check the entry URL using the system certificate store before starting the decoder.
    # FFmpeg HLS demuxers do not consistently accept the protocol-only tls_verify option.
    try:
        with urllib.request.urlopen(urllib.request.Request(row["url"], headers=row["headers"]), timeout=6) as response:
            response.read(1024)
    except Exception as error:
        return dict(row, ok=False, error=type(error).__name__)
    command = [ffmpeg, "-hide_banner", "-nostdin", "-rw_timeout", "6000000"]
    if row["headers"]:
        command += ["-headers", "".join(f"{key}: {value}\r\n" for key, value in row["headers"].items())]
    command += ["-i", row["url"], "-map", "0:v:0", "-an", "-t", "6", "-vf", "fps=1", "-f", "null", "-"]
    try:
        run = subprocess.run(command, capture_output=True, timeout=25)
        log = run.stderr.decode("utf-8", "replace")
        video = re.search(r"Video:.*?\b(\d{3,5})x(\d{3,5})\b", log)
        frames = [int(n) for n in re.findall(r"frame=\s*(\d+)", log)]
        width, height = (int(video[1]), int(video[2])) if video else (0, 0)
        return dict(row, ok=run.returncode == 0 and max(frames, default=0) >= 3 and height >= 720,
                    width=width, height=height, decodedSamples=max(frames, default=0))
    except subprocess.TimeoutExpired:
        return dict(row, ok=False, error="decode_timeout")


def m3u(rows):
    output = ["#EXTM3U"]
    for row in rows:
        # Publisher text may contain quotes; do not allow it to inject playlist directives.
        name = row["name"].replace("\r", " ").replace("\n", " ")
        group = row["group"].replace('"', "'").replace("\r", " ").replace("\n", " ")
        output.append(f'#EXTINF:-1 group-title="{group}",{name}')
        for key, value in row["headers"].items():
            option = {"Referer": "http-referrer", "User-Agent": "http-user-agent"}[key]
            output.append(f"#EXTVLCOPT:{option}={value}")
        output.append(row["url"])
    return "\n".join(output) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", help="repeatable public playlist URL; defaults to the two reviewed directories")
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("public/live"))
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows, errors = [], []
    for source in args.source or SOURCES:
        try:
            rows.extend(download(source))
        except Exception as error:
            errors.append(dict(source=source, error=type(error).__name__))
    unique = { (row["url"], tuple(sorted(row["headers"].items()))): row for row in rows }
    candidates = list(unique.values())
    # Round-robin stations before testing multiple backups of the same station.
    groups = {}
    for row in candidates:
        groups.setdefault(row["name"], []).append(row)
    ordered = [group[i] for i in range(max(map(len, groups.values()), default=0)) for group in groups.values() if i < len(group)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        results = list(pool.map(lambda row: probe(row, args.ffmpeg), ordered[:max(1, args.limit)]))
    verified = [row for row in results if row["ok"]]
    # A failed run must not replace the previously published working list with an empty file.
    if verified:
        temp = args.output / "channels.m3u.tmp"
        temp.write_text(m3u(verified), encoding="utf-8")
        temp.replace(args.output / "channels.m3u")
    report = dict(checkedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  candidates=len(candidates), checked=len(results), decoded=len(verified), sourceErrors=errors, results=results)
    (args.output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"candidates={len(candidates)} checked={len(results)} decoded={len(verified)} sourceErrors={len(errors)}")
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
