# uaid

Identify bots, crawlers and browsers by user agent: name, version, engine, OS, device,
brand and model, plus offline verification of crawler IPs. Plain substring matching, no
regex, no dependencies, no network requests.

```
pip install uaid
```

## Bot or not

```python
import uaid

uaid.is_bot("curl/8.4.0")  # True
uaid.is_bot("Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/120.0.0.0")  # False
uaid.is_bot(None)  # True, so is ""
```

One call per request, no network, no regex, no waiting.

```
 (⌐■_■)   papers, please.
 <)   )>  ~ googlebot? checking 66.249.66.1 ... verified.
  /   \
```

## What is it

```python
uaid.identify(
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.6099.230 Mobile Safari/537.36"
)
# {'bot': False, 'browser': 'Chrome', 'browser_version': '120.0.6099.230',
#  'engine': 'Blink', 'engine_version': '120.0.6099.230', 'os': 'Android',
#  'os_version': '14', 'device': 'mobile', 'brand': 'Samsung', 'model': 'SM-S918B'}

uaid.identify(
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.2210.91"
)
# {'bot': False, 'browser': 'Edge', 'browser_version': '120.0.2210.91',
#  'engine': 'Blink', 'engine_version': '120.0.0.0', 'os': 'Windows', 'os_version': '10',
#  'device': 'desktop', 'cpu': 'amd64'}

uaid.identify(
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
)
# {'bot': False, 'browser': 'Safari', 'browser_version': '17.1', 'engine': 'WebKit',
#  'engine_version': '605.1.15', 'os': 'iOS', 'os_version': '17.1', 'device': 'mobile',
#  'brand': 'Apple', 'model': 'iPhone'}
```

A known crawler gets its database entry on top:

```python
uaid.identify(
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.6099.199 Mobile Safari/537.36 "
    "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
# {'bot': True,
#  'urls': ['http://www.google.com/bot.html'],
#  'browser': 'Chrome', 'browser_version': '120.0.6099.199',
#  'engine': 'Blink', 'engine_version': '120.0.6099.199',
#  'os': 'Android', 'os_version': '6.0.1',
#  'device': 'mobile', 'brand': 'Google', 'model': 'Nexus 5X',
#  'signals': ['database', 'bot', 'http', '.com'],
#  'name': 'Googlebot', 'version': '2.1',
#  'description': "Google's main web crawling bot for search indexing",
#  'tags': ['search-engine'],
#  'url': 'http://www.google.com/bot.html',
#  'rdns': ['.1e100.net', '.googlebot.com', '.google.com'],
#  'ranges': ['https://developers.google.com/static/crawling/ipranges/common-crawlers.json']}
```

An unknown bot is still named, and its contacts are pulled out:

```python
uaid.identify("FooBot/1.2 (de-DE; +https://foo.example/bot; ops@foo.example)")
# {'bot': True, 'urls': ['https://foo.example/bot'], 'emails': ['ops@foo.example'],
#  'languages': ['de-DE'], 'signals': ['bot', 'http', '@'], 'name': 'FooBot',
#  'version': '1.2'}

uaid.identify("curl/8.4.0")
# {'bot': True, 'signals': ['database', 'no-comment', 'url'], 'name': 'curl',
#  'version': '8.4.0', 'description': 'cURL command-line tool for HTTP requests',
#  'tags': ['http-library'], 'url': 'https://curl.se/'}

uaid.identify(None)
# {'bot': True, 'signals': ['no-comment']}
```

| key | values |
| --- | --- |
| `bot` | always present, same answer as `is_bot` |
| `browser`, `browser_version` | `Chrome`, `Safari`, `Firefox`, `Edge`, `Samsung Internet`, `Chrome WebView`, `Facebook`, ... |
| `engine`, `engine_version` | `Blink`, `WebKit`, `Gecko`, `Trident`, `EdgeHTML`, `Presto` |
| `os`, `os_version` | `Android` `14`, `iOS` `17.1`, `macOS` `10.15.7`, `Windows` `10`, `Linux`, `Chrome OS`, ... |
| `device` | `desktop`, `mobile`, `tablet`, `tv`, `console`, `wearable` |
| `brand`, `model` | `Samsung` `SM-S918B`, `Apple` `iPhone`, `Google` `Pixel 8`, ... |
| `cpu` | `amd64`, `arm64`, `arm`, `ia32`, `ppc` |
| `urls`, `emails`, `languages` | found in the user agent |
| `signals` | bots only: why it is one, `database`, `no-comment` (no parentheses) or matched keywords |
| `name`, `version` | bots only: the crawler or tool |
| `description`, `tags`, `url` | known crawlers: from the database, `tags` such as `search-engine`, `ai-crawler`, `seo`, `monitoring`, `http-library` |
| `rdns`, `ranges` | known crawlers: forward-confirmed reverse DNS suffixes and published IP list URLs |

Keys without a value are left out. On a gold set of 644 user agents labeled by Claude
Haiku, mostly rare ones, the browser is right 86% of the time, the OS 94% and the device
92%.

## Is it really that crawler

```python
googlebot = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

uaid.verify(googlebot, "66.249.66.1")  # True, a Google address
uaid.verify(googlebot, "::ffff:66.249.66.1")  # True, v4-mapped
uaid.verify(googlebot, "2001:4860:4801:10::1")  # True, IPv6
uaid.verify(googlebot, "203.0.113.7")  # False, someone pretending
uaid.verify("curl/8.4.0", "66.249.66.1")  # False, curl publishes no addresses

# also asks DNS when the bundled data has no match
uaid.verify(googlebot, "203.0.113.7", lookup=True)
```

Without `lookup`, no request leaves the machine: the networks behind every `rdns` suffix and
`ranges` URL ship with the package. `lookup=True` adds a live check for addresses newer than
the data: the reverse DNS name must end in one of the crawler's suffixes and resolve back to
the same address.

```python
uaid.networks("66.249.66.1")
# ['.googlebot.com', 'https://developers.google.com/static/crawling/ipranges/common-crawlers.json']
uaid.networks("203.0.113.7")  # []
```

## robots.txt

```python
uaid.agents("ai-crawler")  # ['agentdatabot', 'agenttimes', 'ai2bot', 'aisearchbot', ...]
print(uaid.robots_txt("ai-crawler", "seo", path="/private/"))
```

```
User-agent: agentdatabot
User-agent: agenttimes
...
Disallow: /private/
```

## Command line

```
$ printf 'curl/8.4.0\n66.249.66.1\tGooglebot/2.1\n203.0.113.7\tGooglebot/2.1\n' | python -m uaid
{"bot": true, "signals": ["database", "no-comment", "url"], "name": "curl", ...}
{"bot": true, ..., "name": "Googlebot", "version": "2.1", ..., "ip": "66.249.66.1", "verified": true}
{"bot": true, ..., "name": "Googlebot", "version": "2.1", ..., "ip": "203.0.113.7", "verified": false}
```

One user agent per line, or `IP<TAB>user agent` to verify the address too. `--lookup` enables
the DNS check.

```
awk -F'"' '{print $6}' access.log | python -m uaid
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

## Performance

| call | time |
| --- | --- |
| `is_bot` on an obvious bot | ~0.3 µs |
| `identify` or `verify`, repeated user agent | ~1 µs |
| `identify`, new bot | ~15 µs |
| `identify`, new browser | ~28 µs |
| `import uaid` | ~19 ms |

Rules are found through trigram indexes, results of the last 4096 user agents are cached
and user agents are cut at 4096 characters.

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
