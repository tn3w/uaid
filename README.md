# uaid

Identify crawlers and bots by user agent. Plain substring matching, no regex, no dependencies.

```
pip install uaid
```

```python
import uaid

uaid.is_bot("curl/8.4.0")  # True

uaid.identify("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
# {'description': 'Google search indexing bot', 'tags': ['search-engine'], 'url': ..., 'rdns': [...]}
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
