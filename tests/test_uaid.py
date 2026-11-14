import json
import random
from pathlib import Path

import pytest

import uaid

ROOT = Path(__file__).parent


def read_lines(name):
    return (ROOT / name).read_text().splitlines()


CRAWLERS = json.loads((ROOT.parent / "crawlers.json").read_text())
BROWSERS = read_lines("browsers.txt")
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


@pytest.mark.parametrize("agent", read_lines("modern_browsers.txt"))
def test_modern_browsers_are_not_bots(agent):
    assert not uaid.is_bot(agent)


@pytest.mark.parametrize("agent", read_lines("modern_bots.txt"))
def test_modern_bots_are_bots(agent):
    assert uaid.is_bot(agent)


@pytest.mark.parametrize(
    ("agent", "description"),
    [
        ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://google.com/bot)", "google"),
        ("MOZILLA/5.0 (COMPATIBLE; GOOGLEBOT/2.1)", "google"),
        ("curl/8.4.0", "command-line"),
        ("pycurl/7.45.3", "python curl"),
        ("Mozilla/5.0 (compatible; adidxbot/2.0; +http://bing.com/bingbot)", "advertis"),
        ("Mozilla/5.0 (compatible; bingbot/2.0; +http://bing.com/bingbot)", "bing"),
        ("Mozilla/5.0 (compatible; BlogTraffic/1.4 Feed-Fetcher)", "blogtraffic"),
    ],
)
def test_identify_most_specific_crawler(agent, description):
    assert description in uaid.identify(agent)["description"].lower()


def test_anchored_rules_only_match_at_start():
    assert uaid.identify("Mozilla/5.0 (X11; Linux) lightning/1.0b1") is None
    assert uaid.identify("Mozilla/5.0 (X11; Linux) Firefox/3.0 FirePHP/0.4") is None


def test_identify_matches_full_scan():
    def full_scan(agent):
        lowered = "^" + agent.lower()
        for first, rest, index in uaid.data["rules"]:
            if first in lowered and all(part in lowered for part in rest):
                return uaid.data["crawlers"][index]

    agents = BROWSERS + INSTANCES + read_lines("modern_bots.txt")
    assert not [agent for agent in agents if uaid.identify(agent) != full_scan(agent)]


@pytest.mark.parametrize("agent", [None, "", " ", "Mozilla/5.0", "\x00\xff"])
def test_missing_or_bare_user_agents_are_bots(agent):
    assert uaid.is_bot(agent)
    assert uaid.identify(agent) is None


def test_identify_returns_independent_copies():
    uaid.identify("curl/8.4.0")["tags"].append("changed")
    assert "changed" not in uaid.identify("curl/8.4.0")["tags"]


def test_random_input_never_fails():
    generator = random.Random(0)
    for _ in range(2000):
        length = generator.randint(0, 500)
        uaid.is_bot("".join(map(chr, generator.choices(range(0x2FFFF), k=length))))


def test_heuristic_quality():
    recall = sum(map(uaid.looks_like_bot, INSTANCES)) / len(INSTANCES)
    false_positives = sum(map(uaid.looks_like_bot, BROWSERS)) / len(BROWSERS)
    assert recall >= 0.9
    assert false_positives <= 0.002
