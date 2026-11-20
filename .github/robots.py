import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

HEADERS = {"User-Agent": "uaid-robots/1.0 (+https://github.com/tn3w/uaid)"}
LINE = re.compile(r"\s*([\w-]+)\s*:\s*(.*?)\s*$", re.ASCII)
HISTORY = Path("robots-history.json")


def download(domain):
    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}/robots.txt"
        request = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return "ok", response.read().decode(errors="replace")
        except urllib.error.HTTPError as error:
            return ("unavailable" if error.code >= 500 else "missing"), ""
        except Exception:
            continue
    return "unreachable", ""


def parse(text):
    rules, signals, sitemap = {}, [], False
    group, in_rules = [], False
    for line in text.split("\n"):
        match = LINE.match(line.split("#")[0])
        if not match:
            continue
        field, value = match[1].lower(), match[2]
        sitemap |= field == "sitemap"
        if field == "content-signal":
            signals += [part.strip() for part in value.lower().split(",")]
        if field == "user-agent" and value:
            group = [] if in_rules else group
            in_rules = False
            group.append(value.lower())
            rules.setdefault(value.lower(), {"allow": [], "disallow": []})
        if not group or field not in ("allow", "disallow", "crawl-delay"):
            continue
        in_rules = True
        for agent in group:
            if field == "crawl-delay":
                rules[agent]["delay"] = True
            elif value:
                rules[agent][field].append(value)
    return rules, signals, sitemap


def state(rules):
    if not rules["disallow"]:
        return "allowed"
    root = any(path in ("/", "/*") for path in rules["disallow"])
    return "blocked" if root and not rules["allow"] else "partial"


def restricted(stats):
    return stats["blocked"] + stats["partial"]


def analyze(domains, results):
    today = {"date": date.today().isoformat(), "sites": len(domains)}
    today |= {"status": Counter(), "analyzed": 0, "sitemaps": 0}
    agents, signals, sites = {}, Counter(), {}
    for domain, (status, text) in zip(domains, results, strict=True):
        today["status"][status] += 1
        rules, site_signals, sitemap = parse(text)
        if not rules:
            continue
        today["analyzed"] += 1
        today["sitemaps"] += sitemap
        signals.update(set(site_signals))
        site = {}
        for agent, agent_rules in rules.items():
            result = state(agent_rules)
            empty = {"blocked": 0, "partial": 0, "allowed": 0, "delay": 0}
            stats = agents.setdefault(agent, empty)
            stats[result] += 1
            stats["delay"] += "delay" in agent_rules
            if result != "allowed":
                site.setdefault(result, []).append(agent)
        if site_signals:
            site["signals"] = site_signals
        if site:
            sites[domain] = site
    ranked = dict(sorted(agents.items(), key=lambda item: -restricted(item[1])))
    return today | {"signals": signals, "agents": ranked, "domains": sites}


def update_history(today):
    empty = {"dates": [], "agents": {}}
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else empty
    if today["date"] not in history["dates"]:
        history["dates"].append(today["date"])
    column = history["dates"].index(today["date"])
    for agent, stats in today["agents"].items():
        if not restricted(stats):
            continue
        row = history["agents"].setdefault(agent, [])
        row += [None] * (column + 1 - len(row))
        row[column] = round(restricted(stats) / today["analyzed"], 6)
    return history


def write(path, data):
    Path(path).write_text(json.dumps(data, separators=(",", ":")))


def main():
    lines = sys.stdin.read().splitlines()[:25_000]
    domains = [domain for line in lines if (domain := line.partition(",")[2].strip())]
    with ThreadPoolExecutor(128) as pool:
        today = analyze(domains, list(pool.map(download, domains)))
    write("robots-today.json", today)
    write(HISTORY, update_history(today))
    print(f"{today['analyzed']} of {today['sites']} sites analyzed", today["status"])


if __name__ == "__main__":
    main()
