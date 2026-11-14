import json
from pathlib import Path

import uaid

ROOT = Path(__file__).parent
CRAWLERS = json.loads((ROOT.parent / "crawlers.json").read_text())
BROWSERS = (ROOT / "browsers.txt").read_text().splitlines()
INSTANCES = [agent for crawler in CRAWLERS for agent in crawler["instances"]]
TAGS = set(
    "search-engine ai-crawler ai-fetcher social-preview seo monitoring feed-reader "
    "archiver advertising scanner http-library browser-automation academic".split()
)


def matches(crawler, user_agent):
    lowered = "^" + user_agent.lower()
    rules = [[rule] if isinstance(rule, str) else rule for rule in crawler["match"]]
    return any(all(part in lowered for part in rule) for rule in rules)


def test_entries_are_valid():
    invalid = [
        crawler["match"]
        for crawler in CRAWLERS
        if not crawler["match"]
        or not crawler["description"]
        or not TAGS.issuperset(crawler["tags"])
        or json.dumps(crawler["match"]) != json.dumps(crawler["match"]).lower()
    ]
    assert not invalid


def test_entries_are_unique():
    rules = [json.dumps(crawler["match"]) for crawler in CRAWLERS]
    assert len(rules) == len(set(rules))


def test_instances_match_their_entry():
    unmatched = [
        agent
        for crawler in CRAWLERS
        for agent in crawler["instances"]
        if not matches(crawler, agent)
    ]
    assert not unmatched


def test_browsers_are_not_identified():
    assert not [agent for agent in BROWSERS if uaid.identify(agent)]


def test_identify():
    googlebot = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    assert "search-engine" in uaid.identify(googlebot)["tags"]
    assert uaid.is_bot("curl/8.4.0")


def test_heuristic_quality():
    recall = sum(map(uaid.looks_like_bot, INSTANCES)) / len(INSTANCES)
    false_positives = sum(map(uaid.looks_like_bot, BROWSERS)) / len(BROWSERS)
    assert recall >= 0.9
    assert false_positives <= 0.002
