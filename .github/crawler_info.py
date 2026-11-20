import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import dns.exception
import dns.resolver

HEADERS = {"User-Agent": "uaid-crawler-info/1.0 (+https://github.com/tn3w/uaid)"}
BOOTSTRAP = "https://data.iana.org/rdap/dns.json"
SECOND_LEVELS = {"ac", "co", "com", "net", "org"}

CRAWLERS = json.loads(Path("crawlers.json").read_text())


def parts(rule):
    return [rule] if isinstance(rule, str) else rule


def key(crawler):
    return " + ".join(parts(crawler["match"][0]))


RULES = sorted(
    ((parts(rule), key(crawler)) for crawler in CRAWLERS for rule in crawler["match"]),
    key=lambda rule: -sum(map(len, rule[0])),
)


def identify(agent):
    lowered = "^" + agent.lower()
    return next((name for rule, name in RULES if all(p in lowered for p in rule)), None)


def request(url, timeout=10):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=HEADERS), timeout=timeout
    )


def status(url):
    try:
        with request(url) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception:
        return None


def fetch_json(url):
    try:
        with request(url, timeout=20) as response:
            return json.load(response)
    except Exception:
        return {}


def registered_domain(suffix):
    labels = suffix.strip(".").split(".")
    is_second_level = len(labels[-1]) == 2 and labels[-2] in SECOND_LEVELS
    return ".".join(labels[-3:] if is_second_level else labels[-2:])


def entity_name(data, role):
    for entity in data.get("entities", []):
        if role not in entity.get("roles", []):
            continue
        fields = entity.get("vcardArray", [None, []])[1]
        names = [field[3] for field in fields if field[0] in ("org", "fn")]
        return names[0] if names else None


def rdap(domain, servers):
    server = servers.get(domain.rsplit(".", 1)[-1])
    data = fetch_json(f"{server}domain/{domain}") if server else {}
    events = {
        event["eventAction"]: event["eventDate"][:10] for event in data.get("events", [])
    }
    return {
        "registered": events.get("registration"),
        "registrar": entity_name(data, "registrar"),
        "registrant": entity_name(data, "registrant"),
    }


def records(domain, kind):
    try:
        return [
            answer.to_text() for answer in dns.resolver.resolve(domain, kind, lifetime=5)
        ]
    except dns.exception.DNSException:
        return []


def domain_info(domain, servers):
    texts = [text.strip('"') for text in records(domain, "TXT")]
    return {
        "robots_txt": status(f"https://{domain}/robots.txt"),
        "security_txt": status(f"https://{domain}/.well-known/security.txt"),
        "mx": sorted(records(domain, "MX")),
        "spf": next((text for text in texts if text.startswith("v=spf1")), None),
        **rdap(domain, servers),
    }


def collect_domains():
    bootstrap = fetch_json(BOOTSTRAP).get("services", [])
    servers = {tld: urls[-1] for tlds, urls in bootstrap for tld in tlds}
    suffixes = {suffix for crawler in CRAWLERS for suffix in crawler.get("rdns", [])}
    domains = sorted({registered_domain(suffix) for suffix in suffixes})
    with ThreadPoolExecutor(32) as pool:
        infos = pool.map(lambda domain: domain_info(domain, servers), domains)
        return dict(zip(domains, infos, strict=True))


def check_urls():
    urls = sorted({crawler["url"] for crawler in CRAWLERS if "url" in crawler})
    with ThreadPoolExecutor(64) as pool:
        statuses = dict(zip(urls, pool.map(status, urls), strict=True))
    return {
        key(crawler): statuses[crawler["url"]] for crawler in CRAWLERS if "url" in crawler
    }


def day(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()


def observe(entries):
    observed = defaultdict(
        lambda: {"ips": 0, "requests": 0, "robots_txt": 0, "verified": 0}
    )
    for entry in entries.values():
        for name in {identify(agent) for agent in entry["user_agents"]} - {None}:
            stats = observed[name]
            stats["ips"] += 1
            stats["requests"] += entry["requests"]
            stats["robots_txt"] += entry["robots_txt"]
            stats["verified"] += entry.get("verified") is True
            first, last = day(entry["first_seen"]), day(entry["last_seen"])
            stats["first_seen"] = min(stats.get("first_seen", first), first)
            stats["last_seen"] = max(stats.get("last_seen", last), last)
    return observed


def blocking(robots):
    tokens = {}
    for crawler in CRAWLERS:
        for rule in crawler["match"]:
            if isinstance(rule, str):
                tokens.setdefault(rule.strip("^/ ;()"), key(crawler))
    shares = {}
    for agent, stats in robots["agents"].items():
        if agent in tokens:
            restricted = stats["blocked"] + stats["partial"]
            shares[tokens[agent]] = stats | {
                "share": round(restricted / robots["analyzed"], 6)
            }
    return shares


def main():
    observed = observe(json.loads(Path(sys.argv[1]).read_text()))
    robots = blocking(json.loads(Path(sys.argv[2]).read_text()))
    urls = check_urls()
    crawlers = {}
    for crawler in CRAWLERS:
        name = key(crawler)
        info = {"url_status": urls.get(name), "observed": observed.get(name)}
        info["robots"] = robots.get(name)
        crawlers[name] = {
            field: value for field, value in info.items() if value is not None
        }
    output = {
        "date": date.today().isoformat(),
        "domains": collect_domains(),
        "crawlers": {name: info for name, info in crawlers.items() if info},
    }
    Path("crawler-info.json").write_text(json.dumps(output, separators=(",", ":")))
    print(f"{len(output['domains'])} domains, {len(output['crawlers'])} crawlers")


if __name__ == "__main__":
    main()
