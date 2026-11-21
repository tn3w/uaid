import json
from collections import Counter, defaultdict
from ipaddress import ip_network
from itertools import pairwise
from pathlib import Path
from urllib.request import urlopen

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

FIELDS = ("description", "tags", "url", "rdns", "ranges")
TARGET = "src/uaid/rules.json"
IPS = "https://github.com/tn3w/uaid/releases/download/robots/crawler-ips.json"


def trigrams(text):
    return {text[start : start + 3] for start in range(len(text) - 2)}


def build_rules(crawlers):
    for index, crawler in enumerate(crawlers):
        for rule in crawler["match"]:
            parts = [rule] if isinstance(rule, str) else rule
            yield [sorted(parts, key=len, reverse=True), index]


def rule_length(rule):
    return sum(map(len, rule[0]))


def build_index(rules):
    counts = Counter(gram for (first, *_), _ in rules for gram in trigrams(first))
    index = defaultdict(list)
    for position, ((first, *_), _) in enumerate(rules):
        index[min(sorted(trigrams(first)), key=counts.__getitem__)].append(position)
    return index


def build_info(crawler):
    return {key: crawler[key] for key in FIELDS if key in crawler}


def span(network):
    network = ip_network(network)
    return int(network.network_address), int(network.broadcast_address) + 1


def encode(networks):
    bounds = []
    for start, end in sorted(map(span, networks)):
        if bounds and start <= bounds[-1]:
            bounds[-1] = max(bounds[-1], end)
        else:
            bounds += [start, end]
    return [bound - previous for previous, bound in pairwise([0, *bounds])]


def build_networks():
    with urlopen(IPS) as response:
        ips = json.load(response)
    keyed = ips["rdns"] | ips["ranges"]
    return {key: encode(networks) for key, networks in keyed.items() if networks}


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        crawlers = json.loads(Path(self.root, "crawlers.json").read_text())
        rules = sorted(build_rules(crawlers), key=rule_length, reverse=True)
        data = {
            "index": build_index(rules),
            "rules": rules,
            "crawlers": list(map(build_info, crawlers)),
            "networks": build_networks(),
        }
        Path(self.root, TARGET).write_text(json.dumps(data, separators=(",", ":")))
        build_data["artifacts"].append(TARGET)
