import json
import sys

from . import identify, robots_txt, verify


def describe(line: str, lookup: bool) -> dict:
    ip, tab, user_agent = line.partition("\t")
    if not tab:
        return identify(line)
    try:
        verified = verify(user_agent, ip, lookup)
    except ValueError:
        verified = False
    return identify(user_agent) | {"ip": ip, "verified": verified}


def main(arguments: list[str]) -> None:
    if arguments[:1] == ["robots"]:
        print(robots_txt(*arguments[1:]), end="")
        return
    lookup = "--lookup" in arguments
    for line in sys.stdin:
        print(json.dumps(describe(line.rstrip("\r\n"), lookup)))


main(sys.argv[1:])
