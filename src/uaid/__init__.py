import json
from bisect import bisect_right
from ipaddress import ip_address
from itertools import accumulate
from pathlib import Path

data = json.loads(Path(__file__).with_name("rules.json").read_text())
bounds = {key: [*accumulate(deltas)] for key, deltas in data["networks"].items()}
keywords = (
    "bot crawl spider http .com url @ check site headless preview scan scrap fetch "
    "monitor index feed inspect resolver google- -google ptst"
).split()
not_models = tuple("mobile tablet harmonyos linux windows android opera xbox rv:".split())
separators = str.maketrans("();,+", "     ")
token_characters = set("abcdefghijklmnopqrstuvwxyz0123456789-_.")
rule_edges = "^/ ;()"


def trigrams(text: str) -> set[str]:
    return {text[start : start + 3] for start in range(len(text) - 2)}


def candidates(grams: set[str], index: dict[str, list[int]]) -> list[int]:
    return sorted(position for gram in grams & index.keys() for position in index[gram])


def match(user_agent: str) -> tuple[str, dict] | None:
    lowered = "^" + user_agent.lower()
    return first_rule(lowered, trigrams(lowered))


def first_rule(lowered: str, grams: set[str]) -> tuple[str, dict] | None:
    for position in candidates(grams, data["index"]):
        parts, index = data["rules"][position]
        if parts[0] in lowered and all(part in lowered for part in parts[1:]):
            info = {key: value[:] for key, value in data["crawlers"][index].items()}
            return parts[0].strip(rule_edges), info


def guess(words: list[str]) -> str:
    names = [word for word in words if "://" not in word and "@" not in word]
    named = [word for word in names if any(key in word.lower() for key in keywords)]
    plain = [word for word in names[:1] if not word.lower().startswith("mozilla/")]
    return (named + plain + [""])[0].partition("/")[0]


def clean(version: str) -> str | None:
    version = version.partition(" ")[0].replace("_", ".")
    return version if version[:1].isdigit() else None


def product(user_agent: str, text: str, pattern: str) -> dict:
    found = user_agent.lower().find(pattern.lower())
    start = max(text.rfind(" ", 0, found), text.rfind("/", 0, found)) + 1
    end = found + len(pattern)
    word = text[end:].partition(" ")[0]
    rest, _, version = word.partition("/")
    return {"name": user_agent[start:end] + rest, "version": clean(version)}


def is_model(name: str) -> bool:
    locale = len(name) == 5 and name[2] == "-"
    return len(name) > 2 and not locale and not name.lower().startswith(not_models)


def android_model(user_agent: str, lowered: str) -> str | None:
    tail = user_agent[lowered.find("android") :]
    end = tail.find(" Build/")
    segments = tail[: end if end != -1 else tail.find(")")].split(";")[1:]
    for segment in segments:
        name = segment.strip()
        if is_model(name):
            return name


def describe(user_agent: str, text: str, lowered: str, grams: set[str]) -> dict:
    words = text.split()
    result = {
        "bot": False,
        "links": [word for word in words if "://" in word or "@" in word[1:-1]],
        "languages": [word for word in words if len(word) == 5 and word[2] == "-"],
    }
    for position in candidates(grams, data["browser_index"]):
        field, token, name, *fixed = data["browsers"][position]
        if field in result or token not in lowered:
            continue
        end = lowered.find(token) + len(token)
        result[field] = name
        result[f"{field}_version"] = fixed[0] if fixed else clean(text[end:])
    if "android" in lowered and "model" not in result:
        result["model"] = android_model(user_agent, lowered)
    return result


def looks_like_bot(user_agent: str | None) -> bool:
    lowered = (user_agent or "").lower()
    return "(" not in lowered or any(word in lowered for word in keywords)


def is_bot(user_agent: str | None) -> bool:
    return looks_like_bot(user_agent) or match(user_agent or "") is not None


def identify(user_agent: str | None) -> dict:
    user_agent = user_agent or ""
    text, lowered = user_agent.translate(separators), user_agent.lower()
    grams = trigrams("^" + lowered)
    result = describe(user_agent, text, lowered, grams)
    rule = first_rule("^" + lowered, grams)
    if rule or looks_like_bot(user_agent):
        pattern, info = rule or (guess(text.split()), {})
        result["bot"] = True
        if pattern:
            result |= product(user_agent, text, pattern)
        result |= info
    return {key: value for key, value in result.items() if value is not None}


def networks(ip: str, keys: list[str] | None = None) -> list[str]:
    address = ip_address(ip)
    number = int(getattr(address, "ipv4_mapped", None) or address)
    keys = bounds if keys is None else keys
    return [key for key in keys if bisect_right(bounds.get(key, ()), number) % 2]


def verify(user_agent: str | None, ip: str) -> bool:
    crawler = identify(user_agent)
    keys = crawler.get("rdns", []) + crawler.get("ranges", [])
    return bool(networks(ip, keys))


def agents(*tags: str) -> list[str]:
    wanted = set(tags)
    tokens = {parts[0].strip(rule_edges): index for parts, index in data["rules"]}
    return sorted(
        token
        for token, index in tokens.items()
        if set(token) <= token_characters
        and wanted & set(data["crawlers"][index]["tags"])
    )


def robots_txt(*tags: str) -> str:
    lines = [f"User-agent: {agent}" for agent in agents(*tags)]
    return "\n".join([*lines, "Disallow: /", ""]) if lines else ""
