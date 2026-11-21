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
# {'bot': False, 'browser': 'Chrome', 'browser_version': '120.0.6099.230',
#  'engine': 'Blink', 'engine_version': '120.0.6099.230', 'os': 'Android',
#  'os_version': '14', 'device': 'mobile', 'brand': 'Samsung', 'model': 'SM-S918B'}

googlebot = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
uaid.identify(googlebot)
# {'bot': True, 'urls': ['http://www.google.com/bot.html'],
#  'signals': ['database', 'bot', 'http', '.com'], 'name': 'Googlebot', 'version': '2.1',
#  'description': ..., 'tags': ['search-engine'], 'url': ..., 'rdns': [...], 'ranges': [...]}

uaid.verify(googlebot, "66.249.66.1")  # True, no network request
uaid.verify(googlebot, "66.249.79.1", lookup=True)  # live DNS if not in bundled data
uaid.networks("66.249.66.1")  # ['.googlebot.com', 'https://developers.google.com/...']
uaid.robots_txt("ai-crawler", path="/")  # 'User-agent: agentdatabot\n...\nDisallow: /\n'
```

- `is_bot` checks ~4500 known crawlers plus a keyword heuristic for unknown bots
  (~92% recall, ~0.1% false positives on 30k real browser user agents).
  A missing user agent (`None` or `""`) counts as a bot.
- `identify` describes any user agent and leaves out keys without a value:
  - `bot`, embedded `urls` and `emails`, and `languages` (`en-US`).
  - `browser`, `engine`, `os` with their `_version`, and `device` (desktop, mobile,
    tablet, tv, console, wearable), `brand`, `model` and `cpu`.
  - For bots `signals` (why it counts as one: `database`, `no-comment` or the matched
    keywords), `name` and `version`. Known crawlers add their database entry, where
    `rdns` lists forward-confirmed reverse DNS suffixes and `ranges` the URLs of IP lists
    the operator publishes. Unknown bots are named after the word that looks like one.
- `verify` checks that an IP belongs to the crawler its user agent claims, offline against
  the bundled networks of its `rdns` suffixes and `ranges` URLs (IPv4, IPv6, v4-mapped).
  With `lookup=True` it falls back to a live forward-confirmed reverse DNS check for
  addresses the bundled data does not know yet. `networks` lists which known crawler
  networks contain an IP.
- `agents` and `robots_txt` list the robots.txt tokens of crawlers with any of the tags.
- Results are cached for repeated user agents (~1 µs). Uncached, `identify` takes ~15 µs on
  bots and ~28 µs on browsers through trigram indexes, `is_bot` ~0.3 µs on obvious bots.
  Import takes ~19 ms. User agents are cut at 4096 characters.

## Command line

Reads one user agent per line, or `IP<TAB>user agent` to also verify the IP, and prints
one JSON object per line:

```
awk -F'"' '{print $6}' access.log | python -m uaid
awk '{print $1}' access.log | paste - <(awk -F'"' '{print $6}' access.log) | python -m uaid --lookup
python -m uaid robots ai-crawler seo > robots.txt
```

## Web frameworks

Reject requests whose user agent claims a verifiable crawler from an address it does not
own, for example in Flask:

```python
from flask import Flask, abort, request

import uaid

app = Flask(__name__)


@app.before_request
def block_fake_crawlers():
    crawler = uaid.identify(request.user_agent.string)
    claims = crawler.get("rdns") or crawler.get("ranges")
    if claims and not uaid.verify(request.user_agent.string, request.remote_addr):
        abort(403)
```

The same check works as ASGI middleware for FastAPI or Starlette:

```python
class FakeCrawlerBlocker:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        user_agent = headers.get(b"user-agent", b"").decode("latin-1")
        crawler = uaid.identify(user_agent)
        claims = crawler.get("rdns") or crawler.get("ranges")
        client = (scope.get("client") or ("0.0.0.0", 0))[0]
        if scope["type"] == "http" and claims and not uaid.verify(user_agent, client):
            await send({"type": "http.response.start", "status": 403, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return
        await self.app(scope, receive, send)
```

Behind a proxy, pass the client address your proxy reports instead of the socket address.

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
