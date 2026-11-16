import json
from copy import deepcopy
from importlib.resources import files

data = json.loads(files(__package__).joinpath("rules.json").read_text())
keywords = (
    "bot crawl spider http .com url @ check site headless preview scan scrap fetch "
    "monitor index feed inspect resolver google- -google ptst"
).split()


def candidates(lowered: str) -> list[int]:
    grams = {lowered[start : start + 3] for start in range(len(lowered) - 2)}
    index = data["index"]
    return sorted(position for gram in grams & index.keys() for position in index[gram])


def extract_name(user_agent: str, pattern: str) -> str:
    pattern = pattern.strip("^/ ;()")
    start = user_agent.lower().find(pattern)
    return user_agent[start : start + len(pattern)]


def identify(user_agent: str | None) -> dict | None:
    lowered = "^" + (user_agent or "").lower()
    for position in candidates(lowered):
        first, rest, index = data["rules"][position]
        if first in lowered and all(part in lowered for part in rest):
            crawler = deepcopy(data["crawlers"][index])
            return {"name": extract_name(user_agent, first), **crawler}


def looks_like_bot(user_agent: str | None) -> bool:
    lowered = (user_agent or "").lower()
    return "(" not in lowered or any(word in lowered for word in keywords)


def is_bot(user_agent: str | None) -> bool:
    return looks_like_bot(user_agent) or identify(user_agent) is not None
