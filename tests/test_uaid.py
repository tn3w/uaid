import json
import random
from pathlib import Path

import pytest

import uaid

ROOT = Path(__file__).parent
CRAWLERS = json.loads((ROOT.parent / "crawlers.json").read_text())
INSTANCES = [agent for crawler in CRAWLERS for agent in crawler["instances"]]
FIELDS = ("description", "tags", "url", "rdns", "ranges")
TAGS = set(
    "search-engine ai-crawler ai-fetcher social-preview seo monitoring feed-reader "
    "archiver advertising scanner http-library browser-automation academic".split()
)


def read_lines(name):
    return (ROOT / name).read_text().splitlines()


def info(crawler):
    return {key: crawler[key] for key in FIELDS if key in crawler}


BROWSERS = read_lines("browsers.txt")


def test_entries_are_valid():
    rules = [json.dumps(rule) for crawler in CRAWLERS for rule in crawler["match"]]
    assert len(rules) == len(set(rules))
    assert all(rule == rule.lower() for rule in rules)
    assert all(crawler["match"] and crawler["description"] for crawler in CRAWLERS)
    assert all(TAGS.issuperset(crawler["tags"]) for crawler in CRAWLERS)


def test_instances_identify_as_their_entry_with_a_name():
    for crawler in CRAWLERS:
        for agent in crawler["instances"]:
            found = uaid.identify(agent)
            assert info(found) == info(crawler), agent
            assert found["name"], agent


def test_every_rule_is_indexed_by_its_own_trigram():
    positions = sorted(sum(uaid.data["index"].values(), []))
    assert positions == list(range(len(uaid.data["rules"])))
    for gram, indexed in uaid.data["index"].items():
        assert all(gram in uaid.data["rules"][position][0] for position in indexed)


def test_browsers_are_not_bots():
    assert not [agent for agent in BROWSERS if uaid.identify(agent)]
    assert not [
        agent for agent in read_lines("modern_browsers.txt") if uaid.is_bot(agent)
    ]


def test_modern_bots_are_bots():
    assert all(map(uaid.is_bot, read_lines("modern_bots.txt")))


@pytest.mark.parametrize(
    ("agent", "name", "description"),
    [
        ("Mozilla/5.0 (compatible; Googlebot/2.1)", "Googlebot", "google"),
        ("MOZILLA/5.0 (COMPATIBLE; GOOGLEBOT/2.1)", "GOOGLEBOT", "google"),
        ("curl/8.4.0", "curl", "command-line"),
        ("pycurl/7.45.3", "pycurl", "python curl"),
        (
            "Mozilla/5.0 (compatible; adidxbot/2.0; +http://bing.com/bingbot)",
            "adidxbot",
            "advertis",
        ),
        ("Mozilla/5.0 (compatible; bingbot/2.0)", "bingbot", "bing"),
        (
            "Mozilla/5.0 (compatible; BlogTraffic/1.4 Feed-Fetcher)",
            "Feed-Fetcher",
            "blogtraffic",
        ),
        ("Lightpanda/1.0 ShapBot/0.1.0", "Lightpanda", "parallel"),
        (
            "HeadlessChrome/120.0.0.0 Safari/537.36 Puppeteer",
            "HeadlessChrome",
            "puppeteer",
        ),
        (
            "(compatible; Go-http-client/1.1; +centurybot9@x.com)",
            "Go-http-client",
            "century",
        ),
        (
            "AppEngine-Google; (appid: s~virustotalcloud)",
            "AppEngine-Google",
            "virustotal",
        ),
        ("WPScan v3.8.22 (https://wpscan.com)", "WPScan", "wpscan"),
        (
            "Safari/537.36 PingdomPageSpeed/1.0 (pingbot/2.0)",
            "PingdomPageSpeed",
            "pingdom",
        ),
        ("munin/http_loadtime", "munin", "munin"),
        ("libwww-perl/6.0 LWP::Simple/6.0", "LWP::Simple", "lwp::simple"),
        ("Symfony BrowserKit", "BrowserKit", "symfony"),
        ("Mozilla/5.0 (compatible; lightspeed)", "lightspeed", "lightspeed"),
    ],
)
def test_identify_most_specific_crawler(agent, name, description):
    found = uaid.identify(agent)
    assert found["name"] == name
    assert description in found["description"].lower()


def test_anchored_rules_only_match_at_start():
    assert uaid.identify("Mozilla/5.0 (X11; Linux) lightning/1.0b1") is None
    assert uaid.identify("Mozilla/5.0 (X11; Linux) Firefox/3.0 FirePHP/0.4") is None


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
