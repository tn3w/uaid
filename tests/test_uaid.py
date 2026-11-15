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


FIELDS = ("description", "tags", "url", "rdns")


def info(crawler):
    return {key: crawler[key] for key in FIELDS if key in crawler}


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


def test_rules_belong_to_one_entry():
    rules = [json.dumps(rule) for crawler in CRAWLERS for rule in crawler["match"]]
    assert len(rules) == len(set(rules))


def test_instances_identify_as_their_entry():
    misidentified = [
        agent
        for crawler in CRAWLERS
        for agent in crawler["instances"]
        if uaid.identify(agent) != info(crawler)
    ]
    assert not misidentified


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
        ("Lightpanda/1.0 ShapBot/0.1.0", "parallel"),
        ("Mozilla/5.0 HeadlessChrome/120.0.0.0 Safari/537.36 Puppeteer", "puppeteer"),
        ("Mozilla/5.0 (compatible; Go-http-client/1.1; +centurybot9@x.com)", "century"),
        ("AppEngine-Google; (appid: s~virustotalcloud)", "virustotal"),
        ("WPScan v3.8.22 (https://wpscan.com/wordpress-security-scanner)", "wpscan"),
        ("Chrome/61.0 Safari/537.36 PingdomPageSpeed/1.0 (pingbot/2.0)", "pingdom"),
        ("munin/http_loadtime", "munin"),
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
