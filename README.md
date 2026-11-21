# uaid

Identify bots, crawlers and browsers by user agent: name, version, engine, OS, device,
brand and model, plus offline verification of crawler IPs. Plain substring matching, no
regex, no dependencies, no network requests.

```
pip install uaid
```

```python
import uaid

uaid.is_bot("curl/8.4.0")  # True

uaid.identify(
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36"
)
# {'bot': False, 'links': [], 'languages': [], 'browser': 'Chrome',
#  'browser_version': '120.0.6099.230', 'engine': 'Blink', 'engine_version': '120.0.6099.230',
#  'os': 'Android', 'os_version': '14', 'device': 'mobile', 'brand': 'Samsung',
#  'model': 'SM-S918B'}

googlebot = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
uaid.identify(googlebot)
# {'bot': True, 'links': ['http://www.google.com/bot.html'], 'languages': [],
#  'name': 'Googlebot', 'version': '2.1', 'description': ..., 'tags': ['search-engine'],
#  'url': ..., 'rdns': [...], 'ranges': [...]}

uaid.verify(googlebot, "66.249.66.1")  # True, no network request
uaid.networks("66.249.66.1")  # ['.googlebot.com', 'https://developers.google.com/...']
uaid.robots_txt("ai-crawler")  # 'User-agent: agentdatabot\n...\nDisallow: /\n'
```

- `is_bot` checks ~4500 known crawlers plus a keyword heuristic for unknown bots
  (~92% recall, ~0.1% false positives on 30k real browser user agents).
  A missing user agent (`None` or `""`) counts as a bot.
- `identify` describes any user agent. Keys without a value are left out:
  - `bot`, `links` (embedded URLs and email addresses) and `languages` (`en-US`).
  - `browser`, `engine`, `os` with their `_version`, and `device` (desktop, mobile,
    tablet, tv, console, wearable), `brand`, `model` and `cpu`.
  - For bots `name` and `version`. Known crawlers add their database entry, where `rdns`
    lists forward-confirmed reverse DNS suffixes and `ranges` the URLs of IP lists the
    operator publishes. Unknown bots are named after the word that looks like one.
- `verify` checks that an IP belongs to the crawler its user agent claims, offline against
  the bundled networks of its `rdns` suffixes and `ranges` URLs (IPv4, IPv6, v4-mapped).
  `networks` lists which known crawler networks contain an IP.
- `agents` and `robots_txt` list the robots.txt tokens of crawlers with any of the tags.
- ~0.3 µs per `is_bot` call on obvious bots, ~15 µs per `identify` or `verify` call on
  bots and ~28 µs on browsers through trigram indexes, ~19 ms import time.

## Data

`crawlers.json` is the source database. Each `match` rule is tested against the lowercased
user agent: a string must be contained, a leading `^` anchors it to the start, a nested
list requires all parts. `browsers.json` lists per field ordered `[token, name]` rules; the
first token contained in the lowercased user agent wins, and its version is read right
after the token unless the rule fixes it as a third value. `crawler-ips.json` holds the
networks behind every `rdns` suffix and `ranges` URL. The wheel ships all three as one
compact, pre-indexed `rules.json` generated at build time, without network access.

`tests/gold.json` is a gold set of user agents labeled by Claude Haiku that the tests hold
`identify` to, field by field.

A daily workflow refreshes `crawler-ips.json` in the repository and publishes it, along
with more data, to the [`robots` release](https://github.com/tn3w/uaid/releases/tag/robots):

- `crawler-ips.json`: `rdns` networks come from every IPv4 PTR record in the
  [iplore rDNS database](https://github.com/tn3w/iplore). Records ending in a suffix are
  grouped per /24, and a group is kept only if a sampled address forward-confirms (its name
  resolves back to it), which drops spoofed PTR records. `ranges` networks are parsed from
  each URL, following IP lists linked from the page. So `uaid.verify` gives the result of a
  full-circle DNS check without any lookup, as fresh as the build.

  ```json
  {"date": "2026-11-21", "rdns": {".googlebot.com": ["66.249.64.0/27", ...]},
   "ranges": {"https://openai.com/gptbot.json": ["132.196.86.0/24", ...]}}
  ```

- `robots-today.json`: robots.txt of the top 25,000 [Tranco](https://tranco-list.eu) sites,
  with fetch status counts, per user agent how many sites block it fully, partially or
  allow it (and set a crawl delay), Content-Signal counts, and per site the blocked and
  partially blocked agents. `robots-history.json` has per date and user agent the share of
  sites that restrict it.
- `crawler-info.json`: per registered domain behind an `rdns` suffix the HTTP status of its
  `robots.txt` and `security.txt`, MX and SPF records, and RDAP registration date,
  registrar and registrant (when published). Per crawler, keyed by the first `match` rule,
  the `url_status` of its info page, `observed` traffic from
  [tn3w/opendata](https://github.com/tn3w/opendata) (addresses, requests, addresses that
  fetched robots.txt, verified addresses, first and last seen) and its robots.txt stats.
