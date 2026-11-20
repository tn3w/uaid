# uaid

Identify crawlers and bots by user agent. Plain substring matching, no regex, no dependencies.

```
pip install uaid
```

```python
import uaid

uaid.is_bot("curl/8.4.0")  # True

uaid.identify("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
# {'name': 'Googlebot', 'description': 'Google search indexing bot', 'tags': ['search-engine'], 'url': ..., 'rdns': [...]}
```

- `is_bot` checks ~4500 known crawlers plus a keyword heuristic for unknown bots
  (~92% recall, ~0.1% false positives on 30k real browser user agents).
  A missing user agent (`None` or `""`) counts as a bot.
- `identify` returns the most specific known crawler, or `None`.
- `rdns` lists forward-confirmed reverse DNS suffixes for verifying a crawler's IP.
- `ranges` lists URLs of IP range lists the operator publishes for the crawler.
- ~15 µs per call through a trigram index, ~20 ms import time.

## Data

`crawlers.json` is the source database. Each `match` rule is tested against the lowercased
user agent: a string must be contained, a leading `^` anchors it to the start, a nested
list requires all parts. The wheel ships a compact, pre-indexed version generated at build
time.

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
resolves back to it), which drops spoofed PTR records. A crawler's addresses are the union
of its `rdns` suffixes and `ranges` URLs:

```python
crawler = uaid.identify(user_agent)
ips = crawler_ips["rdns"] | crawler_ips["ranges"]
keys = crawler.get("rdns", []) + crawler.get("ranges", [])
networks = {network for key in keys for network in ips.get(key, [])}
```

## Crawler info

`crawler-info.json` in the same release adds context per crawler and per `rdns` domain:

- `domains`: for each registered domain behind an `rdns` suffix, the HTTP status of its
  `robots.txt` and `security.txt`, MX records, SPF record, and RDAP registration date,
  registrar and registrant (when the registry publishes them).
- `crawlers`, keyed by the first `match` rule: `url_status` of the crawler's info page,
  `observed` traffic from [tn3w/opendata](https://github.com/tn3w/opendata) (addresses,
  requests, addresses that fetched robots.txt, verified addresses, first and last seen),
  and `robots`, today's robots.txt stats for its token with the share of sites restricting it.
