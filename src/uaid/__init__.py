import json
from importlib.resources import files

data = json.loads(files(__package__).joinpath("rules.json").read_text())
keywords = (
    "bot crawl spider http .com url @ check site headless preview scan scrap fetch "
    "monitor index feed inspect resolver google- -google ptst"
).split()


def identify(user_agent: str) -> dict | None:
    lowered = "^" + user_agent.lower()
    for first, rest, index in data["rules"]:
        if first in lowered and all(part in lowered for part in rest):
            return data["crawlers"][index]


def looks_like_bot(user_agent: str) -> bool:
    lowered = user_agent.lower()
    return "(" not in lowered or any(word in lowered for word in keywords)


def is_bot(user_agent: str) -> bool:
    return looks_like_bot(user_agent) or identify(user_agent) is not None
