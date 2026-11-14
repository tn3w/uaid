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

- `is_bot` checks ~2900 known crawlers plus a keyword heuristic for unknown bots
  (~94% recall, ~0.1% false positives on 30k real browser user agents).
- `identify` returns the most specific known crawler, or `None`.
- `rdns` lists forward-confirmed reverse DNS suffixes for verifying a crawler's IP.

## Data

`crawlers.json` is the source database. Each `match` rule is tested against the lowercased
user agent: a string must be contained, a leading `^` anchors it to the start, a nested
list requires all parts. The wheel ships a compact, pre-sorted version generated at build
time.
