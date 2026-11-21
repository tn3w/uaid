import json
import random
from ipaddress import ip_address
from itertools import pairwise
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
        assert all(gram in uaid.data["rules"][position][0][0] for position in indexed)


def test_browsers_are_not_bots():
    assert not [agent for agent in BROWSERS if uaid.match(agent)]
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
    assert uaid.match("Mozilla/5.0 (X11; Linux) lightning/1.0b1") is None
    assert uaid.match("Mozilla/5.0 (X11; Linux) Firefox/3.0 FirePHP/0.4") is None


@pytest.mark.parametrize("agent", [None, "", " ", "Mozilla/5.0", "\x00\xff"])
def test_missing_or_bare_user_agents_are_bots(agent):
    assert uaid.is_bot(agent)
    assert "tags" not in uaid.identify(agent)


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


GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
SHARED_SUFFIXES = {
    ".amazonaws.com",
    ".googleusercontent.com",
    ".cloudapp.azure.com",
    ".cloudapp.net",
    ".linodeusercontent.com",
    ".your-server.de",
}


def googlebot_address():
    return str(ip_address(uaid.bounds[".googlebot.com"][0]))


@pytest.mark.parametrize(
    ("agent", "version"),
    [
        (GOOGLEBOT, "2.1"),
        ("curl/8.4.0", "8.4.0"),
        ("Mozilla/5.0 (compatible; lightspeed)", None),
    ],
)
def test_identify_extracts_version(agent, version):
    assert uaid.identify(agent).get("version") == version


def links(agent):
    return uaid.identify(agent)["links"]


def test_links_finds_urls_and_emails():
    assert links(GOOGLEBOT) == ["http://www.google.com/bot.html"]
    assert links("foo/1.0 (bot@example.com; @handle)") == ["bot@example.com"]
    assert links(None) == []


@pytest.mark.parametrize(
    ("agent", "name", "version"),
    [
        (
            "Mozilla/5.0 (compatible; FooBot/1.2; +https://foo.example/bot)",
            "FooBot",
            "1.2",
        ),
        ("acme-fetcher/3.1 (ops@acme.example)", "acme-fetcher", "3.1"),
        ("zzq/1.0", "zzq", "1.0"),
        ("Mozilla/5.0", None, None),
    ],
)
def test_identify_guesses_unknown_bots(agent, name, version):
    found = uaid.identify(agent)
    assert (found.get("name"), found.get("version")) == (name, version)
    assert "tags" not in found


def test_identify_flags_bots_like_is_bot():
    for agent in BROWSERS[:2000] + INSTANCES[:2000]:
        assert uaid.identify(agent)["bot"] == uaid.is_bot(agent), agent


GOLD = json.loads((ROOT / "gold.json").read_text())
ACCURACY = {
    "bot": 0.97,
    "browser": 0.85,
    "browser_version": 0.87,
    "engine": 0.92,
    "os": 0.93,
    "os_version": 0.91,
    "device": 0.91,
    "brand": 0.89,
    "model": 0.84,
}


@pytest.mark.parametrize(("field", "minimum"), ACCURACY.items())
def test_gold_set_accuracy(field, minimum):
    found = [uaid.identify(row["ua"]).get(field) for row in GOLD]
    right = sum(value == row[field] for value, row in zip(found, GOLD, strict=True))
    assert right / len(GOLD) >= minimum


@pytest.mark.parametrize(
    ("agent", "expected"),
    [
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.2210.91",
            {
                "browser": "Edge",
                "browser_version": "120.0.2210.91",
                "engine": "Blink",
                "os": "Windows",
                "os_version": "10",
                "device": "desktop",
                "cpu": "amd64",
            },
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
            {
                "browser": "Safari",
                "browser_version": "17.1",
                "os": "iOS",
                "os_version": "17.1",
                "device": "mobile",
                "brand": "Apple",
                "model": "iPhone",
            },
        ),
        (
            "Mozilla/5.0 (Linux; Android 14; SM-S918B Build/UP1A.231005.007; wv) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.230 "
            "Mobile Safari/537.36",
            {
                "browser": "Chrome WebView",
                "os": "Android",
                "os_version": "14",
                "device": "mobile",
                "brand": "Samsung",
                "model": "SM-S918B",
            },
        ),
        (
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 "
            "Firefox/121.0",
            {
                "browser": "Firefox",
                "browser_version": "121.0",
                "engine": "Gecko",
                "engine_version": "121.0",
                "os": "Linux",
                "device": "desktop",
                "cpu": "amd64",
            },
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; de-DE) AppleWebKit/605.1.15",
            {
                "os": "macOS",
                "os_version": "10.15.7",
                "languages": ["de-DE"],
                "bot": False,
            },
        ),
    ],
)
def test_identify_describes_browsers(agent, expected):
    found = uaid.identify(agent)
    assert {key: found.get(key) for key in expected} == expected


def test_verify_confirms_crawler_networks():
    address = googlebot_address()
    assert ".googlebot.com" in uaid.networks(address)
    assert uaid.verify(GOOGLEBOT, address)
    assert uaid.verify(GOOGLEBOT, f"::ffff:{address}")
    assert not uaid.verify("Mozilla/5.0 (compatible; bingbot/2.0)", address)
    assert not uaid.verify(None, address)


@pytest.mark.parametrize("address", ["127.0.0.1", "8.8.8.8", "::1", "2001:db8::1"])
def test_verify_rejects_foreign_addresses(address):
    assert uaid.networks(address) == []
    assert not uaid.verify(GOOGLEBOT, address)


def test_verify_rejects_invalid_addresses():
    with pytest.raises(ValueError):
        uaid.verify(GOOGLEBOT, "not an ip")


def test_ip_sources_are_well_formed():
    for crawler in CRAWLERS:
        suffixes, urls = crawler.get("rdns", []), crawler.get("ranges", [])
        assert all(suffix.startswith(".") for suffix in suffixes)
        assert all(suffix == suffix.lower() for suffix in suffixes)
        assert not SHARED_SUFFIXES & set(suffixes), crawler["match"]
        assert all(url.startswith("https://") for url in urls)
        assert len(set(suffixes + urls)) == len(suffixes + urls)


def test_bundled_networks_are_sorted_disjoint_spans():
    assert {".googlebot.com", ".search.msn.com"} <= uaid.bounds.keys()
    for key, bounds in uaid.bounds.items():
        assert bounds and len(bounds) % 2 == 0
        assert all(left < right for left, right in pairwise(bounds)), key


def test_network_spans_include_start_and_exclude_end():
    keys = [".googlebot.com"]
    start, end = uaid.bounds[keys[0]][:2]
    assert uaid.networks(str(ip_address(start)), keys) == keys
    assert uaid.networks(str(ip_address(end - 1)), keys) == keys
    assert uaid.networks(str(ip_address(end)), keys) == []
    assert uaid.networks(str(ip_address(start - 1)), keys) == []
    assert uaid.networks(str(ip_address(start)), ["unknown"]) == []


def test_links_strip_plus_and_keep_order():
    agent = "Bot/1.0 (+https://example.com/bot; mailto bot@example.com) +http://x.io"
    assert links(agent) == [
        "https://example.com/bot",
        "bot@example.com",
        "http://x.io",
    ]


def test_robots_txt_lists_tagged_agents():
    agents = uaid.agents("ai-crawler")
    assert {"gptbot", "ccbot", "claudebot"} <= set(agents)
    assert "googlebot" not in agents
    assert agents == sorted(set(agents))
    assert all(set(agent) <= uaid.token_characters for agent in agents)
    lines = uaid.robots_txt("ai-crawler").splitlines()
    assert lines == [f"User-agent: {agent}" for agent in agents] + ["Disallow: /"]
    assert uaid.robots_txt("unknown-tag") == ""


def test_agents_unite_tags():
    combined = set(uaid.agents("ai-crawler", "seo"))
    assert combined == set(uaid.agents("ai-crawler")) | set(uaid.agents("seo"))
    assert "ahrefsbot" in combined
