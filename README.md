# uaid

Identify crawlers and bots by user agent. Plain substring matching, no regex, no dependencies.

```
pip install uaid
```

```python
import uaid

uaid.is_bot("curl/8.4.0")  # True

googlebot = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
uaid.identify(googlebot)
# {'name': 'Googlebot', 'version': '2.1', 'links': ['http://www.google.com/bot.html'],
#  'description': ..., 'tags': ['search-engine'], 'url': ..., 'rdns': [...], 'ranges': [...]}
uaid.identify("Mozilla/5.0 (compatible; FooBot/1.2; +https://foo.example/bot)")
# {'name': 'FooBot', 'version': '1.2', 'links': ['https://foo.example/bot']}

uaid.verify(googlebot, "66.249.66.1")  # True, no network request
uaid.networks("66.249.66.1")  # ['.googlebot.com', 'https://developers.google.com/...']
uaid.robots_txt("ai-crawler")  # 'User-agent: agentdatabot\n...\nDisallow: /\n'
```

- `is_bot` checks ~4500 known crawlers plus a keyword heuristic for unknown bots
  (~92% recall, ~0.1% false positives on 30k real browser user agents).
  A missing user agent (`None` or `""`) counts as a bot.
- `identify` returns `None` for browsers and a dict for every bot: its name, version and
  embedded URLs and email addresses (`links`). Known crawlers add their database entry,
  where `rdns` lists forward-confirmed reverse DNS suffixes and `ranges` the URLs of IP
  lists the operator publishes. Unknown bots are named after the word that looks like one.
- `verify` checks that an IP belongs to the crawler its user agent claims, offline against
  the bundled networks of its `rdns` suffixes and `ranges` URLs (IPv4, IPv6, v4-mapped).
  `networks` lists which known crawler networks contain an IP.
- `agents` and `robots_txt` list the robots.txt tokens of crawlers with any of the tags.
- ~0.3 µs per `is_bot` call on obvious bots, ~11 µs per `identify` or `verify` call,
  ~30 ms import time.

## Data

`crawlers.json` is the source database. Each `match` rule is tested against the lowercased
user agent: a string must be contained, a leading `^` anchors it to the start, a nested
list requires all parts. The wheel ships a compact, pre-indexed version generated at build
time, including the networks from the latest `crawler-ips.json` as delta-encoded spans.

## Robots.txt stats

A daily workflow reads the robots.txt of the top 25,000 [Tranco](https://tranco-list.eu)
sites and publishes two files to the [`robots` release](https://github.com/tn3w/uaid/releases/tag/robots):

- `robots-today.json`: fetch status counts, per user agent how many sites block it fully,
  partially or allow it (and set a crawl delay), Content-Signal counts, and per site the
  blocked and partially blocked agents.
- `robots-history.json`: per date and user agent, the share of sites that restrict it.

## Crawler IPs

The same workflow publishes `crawler-ips.json` to the `robots` release: the IPv4 networks
behind every `rdns` suffix and the parsed networks of every `ranges` URL.

```json
{"date": "2026-11-20", "rdns": {".googlebot.com": ["66.249.64.0/27", ...]},
 "ranges": {"https://openai.com/gptbot.json": ["132.196.86.0/24", ...]}}
```

`rdns` networks come from every IPv4 PTR record in the
[iplore rDNS database](https://github.com/tn3w/iplore). Records ending in a suffix are
grouped per /24, and a group is kept only if a sampled address forward-confirms (its name
resolves back to it), which drops spoofed PTR records. Each build bundles this file, so
`uaid.verify` gives the result of a full-circle DNS check without any lookup; it is as
fresh as the release it was built from.

## Crawler info

`crawler-info.json` in the same release adds context per crawler and per `rdns` domain:

- `domains`: for each registered domain behind an `rdns` suffix, the HTTP status of its
  `robots.txt` and `security.txt`, MX records, SPF record, and RDAP registration date,
  registrar and registrant (when the registry publishes them).
- `crawlers`, keyed by the first `match` rule: `url_status` of the crawler's info page,
  `observed` traffic from [tn3w/opendata](https://github.com/tn3w/opendata) (addresses,
  requests, addresses that fetched robots.txt, verified addresses, first and last seen),
  and `robots`, today's robots.txt stats for its token with the share of sites restricting it.
