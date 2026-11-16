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
