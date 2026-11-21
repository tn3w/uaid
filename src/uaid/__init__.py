import json
from bisect import bisect_right
from importlib.resources import files
from ipaddress import ip_address
from itertools import accumulate

data = json.loads(files(__package__).joinpath("rules.json").read_text())
bounds = {key: [*accumulate(deltas)] for key, deltas in data["networks"].items()}
keywords = (
    "bot crawl spider http .com url @ check site headless preview scan scrap fetch "
    "monitor index feed inspect resolver google- -google ptst"
).split()
separators = str.maketrans("();,+", "     ")
token_characters = set("abcdefghijklmnopqrstuvwxyz0123456789-_.")
rule_edges = "^/ ;()"


def candidates(lowered: str) -> list[int]:
    grams = {lowered[start : start + 3] for start in range(len(lowered) - 2)}
    index = data["index"]
    return sorted(position for gram in grams & index.keys() for position in index[gram])


def match(user_agent: str) -> tuple[str, dict] | None:
    lowered = "^" + user_agent.lower()
    for position in candidates(lowered):
        parts, index = data["rules"][position]
        if all(part in lowered for part in parts):
            info = {key: value[:] for key, value in data["crawlers"][index].items()}
            return parts[0].strip(rule_edges), info


def guess(words: list[str]) -> str:
    names = [word for word in words if "://" not in word and "@" not in word]
    named = [word for word in names if any(key in word.lower() for key in keywords)]
    plain = [word for word in names[:1] if not word.lower().startswith("mozilla/")]
    return (named + plain + [""])[0].partition("/")[0]


def product(user_agent: str, pattern: str) -> dict:
    if not pattern:
        return {"name": None, "version": None}
    text = user_agent.translate(separators)
    found = user_agent.lower().find(pattern.lower())
    start = max(text.rfind(" ", 0, found), text.rfind("/", 0, found)) + 1
    end = found + len(pattern)
    rest, _, version = text[end:].partition(" ")[0].partition("/")
    version = version if version[:1].isdigit() else None
    return {"name": user_agent[start:end] + rest, "version": version}


def looks_like_bot(user_agent: str | None) -> bool:
    lowered = (user_agent or "").lower()
    return "(" not in lowered or any(word in lowered for word in keywords)


def is_bot(user_agent: str | None) -> bool:
    return looks_like_bot(user_agent) or match(user_agent or "") is not None


def identify(user_agent: str | None) -> dict | None:
    user_agent = user_agent or ""
    rule = match(user_agent)
    if not rule and not looks_like_bot(user_agent):
        return None
    words = user_agent.translate(separators).split()
    links = [word for word in words if "://" in word or "@" in word[1:-1]]
    pattern, info = rule or (guess(words), {})
    return product(user_agent, pattern) | {"links": links} | info


def networks(ip: str, keys: list[str] | None = None) -> list[str]:
    address = ip_address(ip)
    number = int(getattr(address, "ipv4_mapped", None) or address)
    keys = bounds if keys is None else keys
    return [key for key in keys if bisect_right(bounds.get(key, ()), number) % 2]


def verify(user_agent: str | None, ip: str) -> bool:
    crawler = identify(user_agent) or {}
    return bool(networks(ip, crawler.get("rdns", []) + crawler.get("ranges", [])))


def agents(*tags: str) -> list[str]:
    wanted, crawlers = set(tags), data["crawlers"]
    tokens = {parts[0].strip(rule_edges): index for parts, index in data["rules"]}
    return sorted(
        token
        for token, index in tokens.items()
        if set(token) <= token_characters and wanted & set(crawlers[index]["tags"])
    )


def robots_txt(*tags: str) -> str:
    lines = [f"User-agent: {agent}" for agent in agents(*tags)]
    return "\n".join([*lines, "Disallow: /", ""]) if lines else ""
