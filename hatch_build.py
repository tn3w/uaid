import json
from collections import Counter, defaultdict
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

FIELDS = ("description", "tags", "url", "rdns", "ranges")
TARGET = "src/uaid/rules.json"


def trigrams(text):
    return {text[start : start + 3] for start in range(len(text) - 2)}


def build_rules(crawlers):
    for index, crawler in enumerate(crawlers):
        for rule in crawler["match"]:
            parts = [rule] if isinstance(rule, str) else sorted(rule, key=len)[::-1]
            yield [parts[0], parts[1:], index]


def rule_length(rule):
    return len(rule[0]) + sum(map(len, rule[1]))


def build_index(rules):
    counts = Counter(gram for first, _, _ in rules for gram in trigrams(first))
    index = defaultdict(list)
    for position, (first, _, _) in enumerate(rules):
        index[min(sorted(trigrams(first)), key=counts.__getitem__)].append(position)
    return index


def build_info(crawler):
    return {key: crawler[key] for key in FIELDS if key in crawler}


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        crawlers = json.loads(Path(self.root, "crawlers.json").read_text())
        rules = sorted(build_rules(crawlers), key=rule_length, reverse=True)
        data = {
            "index": build_index(rules),
            "rules": rules,
            "crawlers": list(map(build_info, crawlers)),
        }
        Path(self.root, TARGET).write_text(json.dumps(data, separators=(",", ":")))
        build_data["artifacts"].append(TARGET)
