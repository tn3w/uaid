import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from html import escape
from ipaddress import ip_network
from pathlib import Path
from urllib.parse import quote, urlsplit

import uaid

SITE = "https://uaid.tn3w.dev"
ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).with_name("static")
EDGES = "^/ ;()"
SHOWN_NETWORKS = 400
TAGS = {
    "search-engine": ("Search engine crawlers", "index pages for web search results"),
    "ai-crawler": ("AI crawlers", "collect pages to train AI models or build AI indexes"),
    "ai-fetcher": ("AI fetchers", "fetch pages on demand for AI assistants and agents"),
    "seo": ("SEO crawlers", "audit backlinks, rankings and on-page SEO"),
    "monitoring": ("Monitoring bots", "check uptime, performance and page changes"),
    "http-library": ("HTTP libraries", "are HTTP clients and command-line tools"),
    "scanner": ("Security scanners", "probe sites for vulnerabilities and open services"),
    "feed-reader": ("Feed readers", "poll RSS and Atom feeds"),
    "social-preview": ("Social preview bots", "build link previews for chats and posts"),
    "advertising": ("Advertising bots", "check pages for ad placement and ad quality"),
    "academic": ("Academic crawlers", "collect data for research projects"),
    "archiver": (
        "Web archivers",
        "preserve pages for archives such as the Wayback Machine",
    ),
    "browser-automation": (
        "Browser automation",
        "drive headless or remote-controlled browsers",
    ),
}
FIELDS = {
    "browser": "Browser",
    "engine": "Engine",
    "os": "Operating system",
    "device": "Device",
    "brand": "Brand",
    "model": "Model",
    "cpu": "CPU",
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unnamed"


def parts(rule: str | list[str]) -> list[str]:
    return [rule] if isinstance(rule, str) else rule


def display_name(token: str, instances: list[str]) -> str:
    names = [
        instance[found : found + len(token)].strip(EDGES)
        for instance in instances
        if (found := instance.lower().find(token)) != -1
    ]
    capitalized = [name for name in names if not name.islower()]
    return (capitalized + names + [token])[0]


def hostname(url: str) -> str | None:
    host = urlsplit(url).hostname if "://" in url else None
    return host.removeprefix("www.") if host else None


def crawler_domain(crawler: dict) -> str | None:
    urls = [crawler.get("url", "")]
    urls += [
        url
        for instance in crawler["instances"]
        for url in uaid.identify(instance).get("urls", [])
    ]
    hosts = [hostname(url) for url in urls if hostname(url)]
    suffixes = [suffix.strip(".") for suffix in crawler.get("rdns", [])]
    return (hosts + suffixes + [None])[0]


def load_crawlers(path: Path) -> list[dict]:
    crawlers, seen = [], Counter()
    for crawler in json.loads(path.read_text()):
        token = parts(crawler["match"][0])[0].strip(EDGES)
        slug = slugify(token)
        seen[slug] += 1
        if seen[slug] > 1:
            slug = f"{slug}-{seen[slug]}"
        crawler |= {
            "slug": slug,
            "token": token,
            "key": " + ".join(parts(crawler["match"][0])),
            "name": display_name(token, crawler["instances"]),
        }
        crawlers.append(crawler)
    return crawlers


def script_json(value) -> str:
    escapes = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026"}
    return re.sub("[<>&]", lambda found: escapes[found.group()], json.dumps(value))


def text(value) -> str:
    return escape(str(value))


def number(value: float) -> str:
    return f"{value:,}" if isinstance(value, int) else f"{value:,.1f}"


def percent(value: float) -> str:
    return f"{value * 100:.1f}%" if value < 0.1 else f"{value * 100:.0f}%"


def link(href: str, label: str, external: bool = False) -> str:
    rel = ' rel="nofollow noopener"' if external else ""
    return f'<a href="{text(href)}"{rel}>{text(label)}</a>'


def favicon(domain: str | None, size: int = 32) -> str:
    if not domain:
        return '<span class="icon blank" aria-hidden="true"></span>'
    source = f"https://icons.duckduckgo.com/ip3/{quote(domain)}.ico"
    return (
        f'<img class="icon" src="{source}" width="{size}" height="{size}" alt="" '
        f'loading="lazy" referrerpolicy="no-referrer">'
    )


def table(headers: list[str], rows: list[list[str]], classes: str = "") -> str:
    head = "".join(f"<th>{header}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return (
        f'<div class="scroll"><table class="{classes}"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def facts(pairs: list[tuple[str, str]]) -> str:
    items = "".join(
        f"<dt>{label}</dt><dd>{value}</dd>" for label, value in pairs if value
    )
    return f'<dl class="facts">{items}</dl>'


def tiles(pairs: list[tuple[str, str]]) -> str:
    items = "".join(
        f'<div class="tile"><span>{label}</span><strong>{value}</strong></div>'
        for label, value in pairs
    )
    return f'<div class="tiles">{items}</div>'


def code(content: str) -> str:
    return f"<pre><code>{text(content)}</code></pre>"


def svg(width: int, height: int, label: str, inner: str) -> str:
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{text(label)}">{inner}</svg>'
    )


def strip(label: str, rectangles: str) -> str:
    return (
        f'<svg class="strip" viewBox="0 0 100 4" preserveAspectRatio="none" role="img" '
        f'aria-label="{text(label)}">{rectangles}</svg>'
    )


def bar_chart(label: str, rows: list[tuple], format_value=number) -> str:
    if not rows:
        return ""
    top = max(row[1] for row in rows) or 1
    items = []
    for name, value, *href in rows:
        title = link(href[0], name) if href and href[0] else text(name)
        width = max(value / top * 100, 0.6)
        bar = strip(
            f"{name}: {format_value(value)}", f'<rect width="{width:.2f}" height="4"/>'
        )
        items.append(f"<li><span>{title}</span><b>{format_value(value)}</b>{bar}</li>")
    return f'<ul class="bars" aria-label="{text(label)}">{"".join(items)}</ul>'


def split_bar(label: str, segments: list[tuple[str, int]]) -> str:
    total = sum(value for _, value in segments) or 1
    offset, rectangles, legend = 0.0, [], []
    for index, (name, value) in enumerate(segments, start=1):
        width = value / total * 100
        if width > 0:
            rectangles.append(
                f'<rect class="s{index}" x="{offset:.2f}" '
                f'width="{max(width - 0.5, 0.3):.2f}" '
                f'height="4"><title>{text(name)}: {number(value)}</title></rect>'
            )
        legend.append(
            f'<span class="key"><i class="swatch s{index}"></i>{text(name)} '
            f"<b>{number(value)}</b> {percent(value / total)}</span>"
        )
        offset += width
    return strip(label, "".join(rectangles)) + f'<p class="legend">{"".join(legend)}</p>'


def line_chart(label: str, dates: list[str], series: list[tuple[str, list]]) -> str:
    values = [value for _, points in series for value in points if value is not None]
    if not values:
        return ""
    width, height, left, bottom = 640, 220, 48, 26
    steps = (0.001, 0.002, 0.005, 0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25)
    top = next((step * 4 for step in steps if step * 4 >= max(values) * 1.05), 1.0)
    x_step = (width - left - 12) / max(len(dates) - 1, 1)

    def position(index: int, value: float) -> tuple[float, float]:
        return left + index * x_step, (height - bottom) * (1 - value / top) + 4

    grid = []
    for step in range(5):
        value = top * step / 4
        y = position(0, value)[1]
        grid.append(
            f'<line class="grid" x1="{left}" x2="{width}" y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text class="axis" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">'
            f"{percent(value)}</text>"
        )
    for index in sorted({0, len(dates) // 2, len(dates) - 1}):
        anchor = "start" if index == 0 else "end" if index == len(dates) - 1 else "middle"
        grid.append(
            f'<text class="axis" x="{position(index, 0)[0]:.1f}" y="{height - 6}" '
            f'text-anchor="{anchor}">{text(dates[index])}</text>'
        )
    lines, legend = [], []
    for slot, (name, points) in enumerate(series, start=1):
        coordinates = [
            position(index, value)
            for index, value in enumerate(points)
            if value is not None
        ]
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in coordinates)
        last_x, last_y = coordinates[-1]
        latest = next(value for value in reversed(points) if value is not None)
        lines.append(
            f'<g class="s{slot}">'
            f"<title>{text(name)}: {percent(latest)} on {dates[-1]}</title>"
            f'<polyline class="line" points="{path}"/>'
            f'<circle class="dot" cx="{last_x:.1f}" cy="{last_y:.1f}" r="4"/></g>'
        )
        if len(series) > 1:
            legend.append(
                f'<span class="key"><i class="swatch s{slot}"></i>{text(name)} '
                f"{percent(latest)}</span>"
            )
    chart = svg(width, height, label, "".join(grid + lines))
    return chart + (f'<p class="legend">{"".join(legend)}</p>' if legend else "")


def layout(
    path: str, title: str, description: str, body: str, crumbs=(), script=""
) -> str:
    trail = [("Home", "/"), *crumbs]
    schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": name, "item": SITE + href}
            for index, (name, href) in enumerate(trail, start=1)
        ],
    }
    breadcrumbs = " › ".join(link(href, name) for name, href in trail) if crumbs else ""
    scripts = f'<script src="/{script}" defer></script>' if script else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{text(title)}</title>
<meta name="description" content="{text(description)}">
<link rel="canonical" href="{SITE}{path}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/style.css">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#09090b">
<meta property="og:type" content="website">
<meta property="og:site_name" content="uaid">
<meta property="og:title" content="{text(title)}">
<meta property="og:description" content="{text(description)}">
<meta property="og:url" content="{SITE}{path}">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">{script_json(schema)}</script>
{scripts}
</head>
<body>
<header class="top"><nav>
<a class="brand" href="/">uaid</a>
<a href="/">Analyzer</a>
<a href="/crawlers/">Crawlers</a>
<a href="/browsers/">Browsers</a>
<a href="/robots/">robots.txt</a>
</nav></header>
<main>
{f'<p class="crumbs">{breadcrumbs}</p>' if breadcrumbs else ""}
{body}
</main>
<footer>
<a href="https://github.com/tn3w/uaid">uaid</a> · open data · icons by DuckDuckGo ·
<a href="https://www.tn3w.dev/">tn3w</a>
</footer>
</body>
</html>
"""


class Builder:
    def __init__(self, repo: Path, data: Path):
        def read(path: Path):
            return json.loads(path.read_text())

        self.crawlers = load_crawlers(repo / "crawlers.json")
        self.by_slug = {crawler["slug"]: crawler for crawler in self.crawlers}
        self.by_token = {}
        for crawler in self.crawlers:
            self.by_token.setdefault(crawler["token"], crawler)
        self.ips = read(repo / "crawler-ips.json")
        self.info = read(data / "crawler-info.json")
        self.robots = read(data / "robots-today.json")
        self.history = read(data / "robots-history.json")
        self.browsers = read(repo / "browsers.json")
        self.samples = [
            line.strip()
            for name in ("browsers.txt", "modern_browsers.txt")
            for line in (repo / "tests" / name).read_text().splitlines()
            if line.strip()
        ]
        self.date = self.ips["date"]
        self.pages: list[str] = []

    def write(self, out: Path, path: str, html: str, index: bool = True) -> None:
        target = out / path.strip("/")
        target = target / "index.html" if path.endswith("/") else target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html)
        if index:
            self.pages.append(path)

    def crawler_stats(self, crawler: dict) -> dict:
        return self.info["crawlers"].get(crawler["key"], {})

    def share(self, crawler: dict) -> float:
        return self.crawler_stats(crawler).get("robots", {}).get("share", 0)

    def networks(self, crawler: dict) -> list[tuple[str, str, list[str]]]:
        found = [
            ("rdns", key, self.ips["rdns"].get(key, []))
            for key in crawler.get("rdns", [])
        ]
        found += [
            ("ranges", key, self.ips["ranges"].get(key, []))
            for key in crawler.get("ranges", [])
        ]
        return found

    def domain_info(self, crawler: dict) -> dict[str, dict]:
        names = [suffix.strip(".") for suffix in crawler.get("rdns", [])]
        names += [crawler["domain"]] if crawler["domain"] else []
        found = {}
        for name in names:
            labels = name.split(".")
            for size in (2, 3):
                candidate = ".".join(labels[-size:])
                if candidate in self.info["domains"]:
                    found[candidate] = self.info["domains"][candidate]
        return found

    def build(self, out: Path) -> None:
        shutil.rmtree(out, ignore_errors=True)
        shutil.copytree(STATIC, out)
        for crawler in self.crawlers:
            crawler["domain"] = crawler_domain(crawler)
        self.write(out, "/", self.home())
        self.write(out, "/crawlers/", self.crawler_index())
        for crawler in self.crawlers:
            self.write(out, f"/crawlers/{crawler['slug']}/", self.crawler_page(crawler))
        for tag in TAGS:
            self.write(out, f"/tags/{tag}/", self.tag_page(tag))
        self.write(out, "/robots/", self.robots_page())
        families = {field: self.families(field) for field in ("browser", "os")}
        self.write(out, "/browsers/", self.browser_index(families))
        for field, groups in families.items():
            for name, group in groups.items():
                path = f"/{'browsers' if field == 'browser' else 'os'}/{slugify(name)}/"
                self.write(out, path, self.family_page(field, name, group))
        self.write(out, "/404.html", self.not_found(), index=False)
        self.write(
            out,
            "/robots.txt",
            f"User-agent: *\nDisallow: /api\nDisallow: /?\nSitemap: {SITE}/sitemap.xml\n",
            index=False,
        )
        urls = "".join(
            f"<url><loc>{SITE}{path}</loc><lastmod>{self.date}</lastmod></url>"
            for path in self.pages
        )
        self.write(
            out,
            "/sitemap.xml",
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{urls}</urlset>\n",
            index=False,
        )

    def crawler_list(self, crawlers: list[dict]) -> str:
        items = "".join(
            f'<li><a href="/crawlers/{crawler["slug"]}/">{favicon(crawler["domain"], 20)}'
            f"<b>{text(crawler['name'])}</b></a> "
            f"<span>{text(crawler['description'])}</span></li>"
            for crawler in crawlers
        )
        return f'<ul class="crawlers">{items}</ul>'

    def crawler_chips(self, crawlers: list[dict]) -> str:
        items = "".join(
            f'<a href="/crawlers/{crawler["slug"]}/">{favicon(crawler["domain"], 16)}'
            f"{text(crawler['name'])}</a>"
            for crawler in crawlers
        )
        return f'<p class="chips">{items}</p>'

    def most_blocked(self, count: int) -> list[dict]:
        return sorted(self.crawlers, key=self.share, reverse=True)[:count]

    def home(self) -> str:
        verifiable = [crawler for crawler in self.crawlers if self.networks(crawler)]
        networks = sum(
            len(cidrs) for crawler in verifiable for *_, cidrs in self.networks(crawler)
        )
        tag_links = "".join(
            f'<li><a href="/tags/{tag}/">{text(title)}'
            f"<span>{number(self.tag_count(tag))}</span></a></li>"
            for tag, (title, _) in TAGS.items()
        )
        body = f"""
<section class="hero">
<h1>User agent analyzer</h1>
<p class="lede">Browser, OS, device or bot behind any user agent, and whether an IP
really belongs to the crawler it claims.</p>
<form id="analyze" class="analyze" action="/" method="get">
<textarea id="ua" name="ua" rows="3" spellcheck="false" autocomplete="off"
aria-label="User agent" placeholder="Paste a user agent"></textarea>
<div class="row">
<input id="ip" name="ip" spellcheck="false" autocomplete="off"
aria-label="IP address, optional" placeholder="IP address (optional)">
<button type="submit">Analyze</button>
<button type="button" id="mine" class="quiet">Mine</button>
</div>
</form>
<div id="result" aria-live="polite"><noscript><p class="note">The analyzer needs
JavaScript; the <a href="/api">JSON API</a> and every other page work without it.</p>
</noscript></div>
</section>
{
            tiles(
                [
                    ("crawlers", number(len(self.crawlers))),
                    ("verifiable by IP", number(len(verifiable))),
                    ("crawler networks", number(networks)),
                    ("robots.txt files", number(self.robots["analyzed"])),
                ]
            )
        }
<h2>Most blocked</h2>
{
            bar_chart(
                "Most restricted crawlers in robots.txt",
                [
                    (
                        crawler["name"],
                        self.share(crawler),
                        f"/crawlers/{crawler['slug']}/",
                    )
                    for crawler in self.most_blocked(10)
                ],
                percent,
            )
        }
<p class="note">Share of the top {number(self.robots["sites"])} sites restricting it in
robots.txt. <a href="/robots/">Full report</a></p>
<h2>Categories</h2>
<ul class="tags">{tag_links}</ul>
<p class="note"><a href="/crawlers/">All {number(len(self.crawlers))} crawlers</a> ·
<a href="/browsers/">Browsers</a></p>
<h2>robots.txt generator</h2>
<form id="robots" class="robots" action="/api/robots" method="get">
<fieldset>{
            "".join(
                f'<label><input type="checkbox" name="tag" value="{tag}"> '
                f"{text(title)}</label>"
                for tag, (title, _) in TAGS.items()
            )
        }</fieldset>
<div class="row">
<input id="path" name="path" value="/" aria-label="Disallowed path">
<button type="submit">Generate</button>
</div>
</form>
<pre id="robots-output" hidden></pre>
<h2>API</h2>
{
            code(
                f"curl '{SITE}/api?ua=Googlebot/2.1&ip=66.249.66.1'{chr(10)}"
                f"curl '{SITE}/api/robots?tag=ai-crawler&path=/'"
            )
        }
<p class="note">JSON, CORS, no key; without <code>ua</code> or <code>ip</code> your own
request is used. Offline in Python: <code>pip install uaid</code>
(<a href="https://github.com/tn3w/uaid">GitHub</a>).</p>
<h2>What is a user agent?</h2>
<p class="note">The <code>User-Agent</code> header names the software behind a request.
Anyone can send any value, so a request claiming to be Googlebot is only Googlebot if its
IP address belongs to Google. uaid checks that offline against the forward-confirmed
reverse DNS networks and published IP lists of {number(len(verifiable))} crawlers.</p>"""
        return layout(
            "/",
            "User Agent Analyzer & Crawler Database – uaid",
            "Parse any user agent string: browser, OS, device and bot. Verify crawler "
            f"IP addresses and browse {number(len(self.crawlers))} bots with robots.txt "
            "stats.",
            body,
            script="app.js",
        )

    def tag_count(self, tag: str) -> int:
        return sum(tag in crawler["tags"] for crawler in self.crawlers)

    def crawler_index(self) -> str:
        groups = defaultdict(list)
        for crawler in sorted(self.crawlers, key=lambda crawler: crawler["name"].lower()):
            initial = crawler["name"][:1].upper()
            groups[initial if initial.isalpha() else "#"].append(crawler)
        letters = " ".join(f'<a href="#{letter}">{letter}</a>' for letter in groups)
        years = Counter(crawler.get("addition_date", "")[:4] for crawler in self.crawlers)
        sections = "".join(
            f'<h2 id="{letter}">{letter}</h2>{self.crawler_list(crawlers)}'
            for letter, crawlers in groups.items()
        )
        body = f"""
<h1>Crawler and bot user agent list</h1>
<p class="lede">{number(len(self.crawlers))} web crawlers, bots, HTTP libraries and
scanners, each with example user agent strings, IP verification data and robots.txt
statistics.</p>
<h2>By category</h2>
{
            bar_chart(
                "Crawlers per category",
                [
                    (title, self.tag_count(tag), f"/tags/{tag}/")
                    for tag, (title, _) in TAGS.items()
                ],
            )
        }
<h2>Added to the database per year</h2>
{
            bar_chart(
                "Crawlers added per year",
                [(year, count) for year, count in sorted(years.items()) if year],
            )
        }
<p class="letters">{letters}</p>
{sections}"""
        return layout(
            "/crawlers/",
            f"List of {number(len(self.crawlers))} Crawler & Bot User Agents – uaid",
            "Every known web crawler, bot and HTTP client user agent A–Z: search "
            "engines, AI "
            "crawlers, SEO tools, monitoring and scanners with IPs and robots.txt data.",
            body,
            [("Crawlers", "/crawlers/")],
        )

    def tag_page(self, tag: str) -> str:
        title, purpose = TAGS[tag]
        crawlers = sorted(
            (crawler for crawler in self.crawlers if tag in crawler["tags"]),
            key=lambda crawler: (-self.share(crawler), crawler["name"].lower()),
        )
        top = [crawler for crawler in crawlers if self.share(crawler)][:15]
        others = "".join(
            f'<a href="/tags/{other}/">{text(TAGS[other][0])}</a> '
            for other in TAGS
            if other != tag
        )
        tokens = uaid.agents(tag)
        robots = code(uaid.robots_txt(tag))
        if len(tokens) > 40:
            listed = "\n".join(f"User-agent: {token}" for token in tokens[:40])
            robots = code(f"{listed}\n...\nDisallow: /") + (
                f'<p><a href="/api/robots?tag={tag}" rel="nofollow">'
                "Download the full file</a></p>"
            )
        body = f"""
<h1>{text(title)}</h1>
<p class="lede">{number(len(crawlers))} known bots that {text(purpose)}, with their user
agents, IP verification data and how often websites block them.</p>
{
            "<h2>Most restricted in robots.txt</h2>"
            + bar_chart(
                f"Most restricted {title}",
                [
                    (
                        crawler["name"],
                        self.share(crawler),
                        f"/crawlers/{crawler['slug']}/",
                    )
                    for crawler in top
                ],
                percent,
            )
            if top
            else ""
        }
<h2>Block all {text(title.lower())}</h2>
<p>robots.txt with all {number(len(tokens))} tokens:</p>
{robots}
<h2>All {text(title.lower())}</h2>
{self.crawler_list(crawlers)}
<p class="tags-inline">Other categories: {others}</p>"""
        return layout(
            f"/tags/{tag}/",
            f"{title}: {number(len(crawlers))} User Agents & Bots – uaid",
            f"List of {number(len(crawlers))} {title.lower()} that {purpose}: user agent "
            "strings, IP ranges and robots.txt block rates.",
            body,
            [("Crawlers", "/crawlers/"), (title, f"/tags/{tag}/")],
        )

    def instance_list(self, crawler: dict) -> str:
        if not crawler["instances"]:
            return (
                f"<p>No sample recorded yet. uaid matches any user agent containing "
                f"<code>{text(crawler['token'])}</code>.</p>"
            )
        items = []
        for instance in crawler["instances"]:
            parsed = uaid.identify(instance)
            details = [
                " ".join(
                    filter(None, [parsed.get(field), parsed.get(f"{field}_version")])
                )
                for field in ("name", "browser", "os", "device")
            ]
            items.append(
                f"<li><code>{text(instance)}</code>"
                f"<small>{text(' · '.join(filter(None, details)))} "
                f'<a href="/?ua={quote(instance)}" rel="nofollow">analyze</a>'
                "</small></li>"
            )
        return f'<ul class="uas">{"".join(items)}</ul>'

    def verify_section(self, crawler: dict) -> str:
        name, found = text(crawler["name"]), self.networks(crawler)
        sample = crawler["instances"][0] if crawler["instances"] else crawler["token"]
        if not found:
            return f"""
<h2>Is it really {name}?</h2>
<p>{name} publishes no IP list or reverse DNS name, so any client can send its user
agent and the request cannot be verified by address. Treat it like any other visitor:
rate limits and robots.txt apply.</p>"""
        rows = []
        for kind, key, cidrs in found:
            addresses = sum(
                ip_network(cidr).num_addresses for cidr in cidrs if ":" not in cidr
            )
            source = (
                f"<code>*{text(key)}</code>"
                if kind == "rdns"
                else link(key, hostname(key) or key, external=True)
            )
            shown = "\n".join(cidrs[:SHOWN_NETWORKS])
            more = len(cidrs) - SHOWN_NETWORKS
            listing = (
                f"<details><summary>{number(len(cidrs))} networks · "
                f"{number(addresses)} IPv4"
                f"</summary><pre>{text(shown)}"
                f"{f'{chr(10)}… {number(more)} more' if more > 0 else ''}</pre></details>"
                if cidrs
                else "<small>no confirmed networks yet</small>"
            )
            rows.append(f"<li>{source}{listing}</li>")
        suffixes = crawler.get("rdns", [])
        manual = ""
        if suffixes:
            steps = code(
                "host 192.0.2.1\n"
                f"# 1.2.0.192.in-addr.arpa domain name pointer crawl-1{suffixes[0]}.\n"
                f"host crawl-1{suffixes[0]}\n"
                "# must resolve back to 192.0.2.1"
            )
            manual = f"<details><summary>Check by hand</summary>{steps}</details>"
        return f"""
<h2>Verify an IP address</h2>
<p>Anyone can copy a user agent. A request is from {name} only if its address is in one
of these networks.</p>
<ul class="networks">{"".join(rows)}</ul>
<form class="inline" action="/" method="get">
<input type="hidden" name="ua" value="{text(sample)}">
<input name="ip" placeholder="IP address" aria-label="IP address" required>
<button type="submit">Verify</button>
</form>
{manual}"""

    def robots_section(self, crawler: dict) -> str:
        name = text(crawler["name"])
        stats = self.crawler_stats(crawler).get("robots")
        token = crawler["token"]
        snippet = code(f"User-agent: {token}\nDisallow: /")
        if not stats:
            return f"""
<h2>Block {name}</h2>
{snippet}
<p>None of the top {number(self.robots["sites"])} websites name it in robots.txt.</p>"""
        history = self.history["agents"].get(token)
        chart = (
            line_chart(
                f"Share of top sites restricting {crawler['name']} over time",
                self.history["dates"],
                [(crawler["name"], history)],
            )
            if history
            else ""
        )
        named = stats["blocked"] + stats["partial"] + stats["allowed"]
        return f"""
<h2>Blocked by {percent(stats["share"])} of top sites</h2>
<p>robots.txt of the top {number(self.robots["sites"])} websites (Tranco,
{self.robots["date"]}). {number(stats["delay"])} set a crawl delay.</p>
{
            split_bar(
                f"robots.txt rules for {crawler['name']}",
                [
                    ("Blocked", stats["blocked"]),
                    ("Partly", stats["partial"]),
                    ("Allowed", stats["allowed"]),
                ],
            )
            if named
            else ""
        }
{chart}
<h3>Block {name}</h3>
{snippet}"""

    def observed_section(self, crawler: dict) -> str:
        seen = self.crawler_stats(crawler).get("observed")
        if not seen:
            return ""
        return f"""
<h2>Seen in the wild</h2>
{
            tiles(
                [
                    ("requests", number(seen["requests"])),
                    ("addresses", number(seen["ips"])),
                    ("verified", number(seen.get("verified", 0))),
                    ("fetched robots.txt", number(seen.get("robots_txt", 0))),
                ]
            )
        }
<p class="note">{seen["first_seen"]} to {seen["last_seen"]} on the
<a href="https://github.com/tn3w/opendata">tn3w open data</a> sensors.</p>"""

    def operator_section(self, crawler: dict) -> str:
        domains = self.domain_info(crawler)
        if not domains:
            return ""
        items = []
        for domain, info in domains.items():
            registration = ", ".join(
                filter(
                    None,
                    [
                        info.get("registrant"),
                        info.get("registrar"),
                        f"since {info['registered']}" if info.get("registered") else None,
                    ],
                )
            )
            files = " · ".join(
                f"{name} {info[key]}"
                for key, name in (
                    ("robots_txt", "robots.txt"),
                    ("security_txt", "security.txt"),
                )
                if info.get(key)
            )
            dns = "\n".join(
                [f"MX   {record}" for record in info.get("mx") or []]
                + ([f"SPF  {info['spf']}"] if info.get("spf") else [])
            )
            items.append(
                f"<li>{favicon(domain, 16)} <b>{text(domain)}</b> "
                f"<small>{text(registration)}{' · ' + files if files else ''}</small>"
                + (f"<details><summary>DNS</summary>{code(dns)}</details>" if dns else "")
                + "</li>"
            )
        return f"""
<h2>Operator</h2>
<ul class="operators">{"".join(items)}</ul>"""

    def similar(self, crawler: dict) -> list[dict]:
        tag = (crawler["tags"] or [""])[0]
        same = [
            other
            for other in self.crawlers
            if tag in other["tags"] and other is not crawler
        ]
        operator = crawler["domain"]
        siblings = [other for other in same if operator and other["domain"] == operator]
        ranked = siblings + sorted(same, key=self.share, reverse=True)
        return list({other["slug"]: other for other in ranked}.values())[:12]

    def crawler_page(self, crawler: dict) -> str:
        name, stats = text(crawler["name"]), self.crawler_stats(crawler)
        tags = " ".join(
            f'<a class="tag" href="/tags/{tag}/">{text(TAGS[tag][0])}</a>'
            for tag in crawler["tags"]
            if tag in TAGS
        )
        rules = ", ".join(
            "<code>" + " + ".join(text(part) for part in parts(rule)) + "</code>"
            for rule in crawler["match"]
        )
        depends = ", ".join(
            link(
                f"/crawlers/{self.by_token[token]['slug']}/", self.by_token[token]["name"]
            )
            if token in self.by_token
            else text(token)
            for token in crawler.get("depends_on", [])
        )
        networks = sum(len(cidrs) for *_, cidrs in self.networks(crawler))
        verdict = (
            '<span class="badge good">verifiable by IP</span>'
            if self.networks(crawler)
            else '<span class="badge">not verifiable by IP</span>'
        )
        first_tag = next((tag for tag in crawler["tags"] if tag in TAGS), None)
        crumbs = [("Crawlers", "/crawlers/")]
        crumbs += [(TAGS[first_tag][0], f"/tags/{first_tag}/")] if first_tag else []
        crumbs += [(crawler["name"], f"/crawlers/{crawler['slug']}/")]
        sample = json.dumps(
            crawler["instances"][0] if crawler["instances"] else crawler["token"]
        )
        website = crawler.get("url")
        status = stats.get("url_status")
        body = f"""
<article>
<header class="title">
{favicon(crawler["domain"], 40)}
<div><h1>{name} <span>user agent</span></h1>
<p class="lede">{text(crawler["description"])}.</p>
<p>{tags} {verdict}</p></div>
</header>
{
            tiles(
                [
                    (
                        "of top sites restrict it",
                        percent(stats["robots"]["share"]) if "robots" in stats else "–",
                    ),
                    ("user agents", number(len(crawler["instances"]))),
                    ("IP networks", number(networks) if networks else "–"),
                    (
                        "addresses seen",
                        number(stats["observed"]["ips"]) if "observed" in stats else "–",
                    ),
                ]
            )
        }
{
            facts(
                [
                    (
                        "Website",
                        (
                            link(website, hostname(website) or website, external=True)
                            + (f" <small>HTTP {status}</small>" if status else "")
                        )
                        if website
                        else "",
                    ),
                    ("robots.txt token", f"<code>{text(crawler['token'])}</code>"),
                    ("Matched by", rules),
                    ("Based on", depends),
                    (
                        "Listed since",
                        text(crawler.get("addition_date", "").replace("/", "-")),
                    ),
                ]
            )
        }
<h2>User agent strings</h2>
{self.instance_list(crawler)}
{self.verify_section(crawler)}
{self.robots_section(crawler)}
{self.observed_section(crawler)}
{self.operator_section(crawler)}
<h2>Detect in code</h2>
{
            code(
                f"import uaid{chr(10)}{chr(10)}uaid.identify({sample}){chr(10)}"
                f"uaid.verify({sample}, ip)"
            )
        }
<h2>Similar</h2>
{self.crawler_chips(self.similar(crawler))}
</article>"""
        purpose = crawler["description"].rstrip(".")
        return layout(
            f"/crawlers/{crawler['slug']}/",
            f"{crawler['name']} User Agent – Bot Info, IPs & robots.txt – uaid",
            f"{crawler['name']}: {purpose}. User agent strings, IP address verification, "
            "robots.txt block rate and how to block it.",
            body,
            crumbs,
        )

    def robots_page(self) -> str:
        agents = self.robots["agents"]
        ranked = sorted(
            ((token, stats) for token, stats in agents.items() if token != "*"),
            key=lambda item: -item[1]["blocked"],
        )
        analyzed = self.robots["analyzed"]

        def page_of(token: str) -> str | None:
            crawler = self.by_token.get(token)
            return f"/crawlers/{crawler['slug']}/" if crawler else None

        def label(token: str) -> str:
            href = page_of(token)
            return link(href, token) if href else f"<code>{text(token)}</code>"

        history = self.history["agents"]
        top = [token for token, _ in ranked if token in history][:5]
        rows = [
            [
                label(token),
                number(stats["blocked"]),
                number(stats["partial"]),
                number(stats["allowed"]),
                number(stats["delay"]),
                percent((stats["blocked"] + stats["partial"]) / analyzed),
            ]
            for token, stats in ranked[:300]
        ]
        star = agents.get("*", {})
        body = f"""
<h1>robots.txt report: which bots do websites block?</h1>
<p class="lede">Daily scan of the robots.txt files of the top {
            number(self.robots["sites"])
        }
websites in the <a href="https://tranco-list.eu">Tranco list</a>, {self.robots["date"]}.
{number(analyzed)} files could be parsed, {number(self.robots["sitemaps"])} list a
sitemap.</p>
{
            tiles(
                [
                    ("Sites checked", number(self.robots["sites"])),
                    ("robots.txt parsed", number(analyzed)),
                    ("Block everyone (*)", number(star.get("blocked", 0))),
                    ("User agents named", number(len(agents))),
                ]
            )
        }
<h2>Fetch results</h2>
{
            split_bar(
                "robots.txt fetch results",
                [
                    ("Found", self.robots["status"].get("ok", 0)),
                    ("Unreachable", self.robots["status"].get("unreachable", 0)),
                    ("Missing", self.robots["status"].get("missing", 0)),
                ],
            )
        }
<h2>Most blocked user agents</h2>
<p>Number of sites that disallow the whole site for the token.</p>
{
            bar_chart(
                "Most blocked user agents",
                [
                    (token, stats["blocked"], page_of(token))
                    for token, stats in ranked[:25]
                ],
            )
        }
<h2>Share of sites restricting the top 5 over time</h2>
{
            line_chart(
                "Share of top sites restricting the most blocked bots",
                self.history["dates"],
                [(token, history[token]) for token in top[:5]],
            )
        }
<h2>Content-Signal directives</h2>
{
            bar_chart(
                "Content-Signal values",
                sorted(
                    (
                        (signal, count)
                        for signal, count in self.robots["signals"].items()
                        if count >= 5
                    ),
                    key=lambda item: -item[1],
                ),
            )
        }
<h2>Top 300 user agents in robots.txt</h2>
{
            table(
                [
                    "User agent",
                    "Blocked",
                    "Partly",
                    "Allowed",
                    "Crawl delay",
                    "Restricting",
                ],
                rows,
            )
        }
<p>Build your own on the <a href="/">analyzer page</a> or download a list per category:
{
            " ".join(
                f'<a href="/api/robots?tag={tag}" rel="nofollow">{text(title)}</a>'
                for tag, (title, _) in TAGS.items()
            )
        }</p>"""
        return layout(
            "/robots/",
            "robots.txt Report: Which Bots Do Top Websites Block? – uaid",
            f"Which crawlers the top {number(self.robots['sites'])} websites block in "
            "robots.txt: GPTBot, CCBot, ClaudeBot and more, updated daily.",
            body,
            [("robots.txt report", "/robots/")],
        )

    def families(self, field: str) -> dict[str, dict]:
        groups = defaultdict(lambda: {"samples": [], "fields": defaultdict(Counter)})
        for sample in self.samples:
            parsed = uaid.identify(sample)
            if parsed["bot"] or field not in parsed:
                continue
            group = groups[parsed[field]]
            group["samples"].append((parsed.get(f"{field}_version") or "", sample))
            for other in ("browser", "engine", "os", "device", "brand"):
                group["fields"][other][parsed.get(other, "Unknown")] += 1
            major = (parsed.get(f"{field}_version") or "Unknown").split(".")[0]
            group["fields"]["version"][major] += 1
        return dict(sorted(groups.items(), key=lambda item: -len(item[1]["samples"])))

    def browser_index(self, families: dict[str, dict]) -> str:
        def section(field: str, folder: str) -> str:
            return bar_chart(
                f"Sample user agents per {FIELDS[field].lower()}",
                [
                    (name, len(group["samples"]), f"/{folder}/{slugify(name)}/")
                    for name, group in list(families[field].items())[:40]
                ],
            )

        body = f"""
<h1>Browser and operating system user agents</h1>
<p class="lede">How uaid recognizes {number(len(families["browser"]))} browsers and
{number(len(families["os"]))} operating systems, with
{number(len(self.samples))} real user agent strings as examples.</p>
<h2>Browsers</h2>
{section("browser", "browsers")}
<h2>Operating systems</h2>
{section("os", "os")}"""
        return layout(
            "/browsers/",
            "Browser & OS User Agent Strings – uaid",
            "User agent strings for Chrome, Safari, Firefox, Edge, Samsung Internet and "
            "more "
            "browsers and operating systems, with versions and devices.",
            body,
            [("Browsers", "/browsers/")],
        )

    def family_page(self, field: str, name: str, group: dict) -> str:
        def version_key(item: tuple[str, str]) -> list[int]:
            return [int(piece) for piece in re.findall(r"\d+", item[0])[:4]]

        samples = sorted(set(group["samples"]), key=version_key, reverse=True)[:25]
        folder = "browsers" if field == "browser" else "os"
        tokens = [
            token for token, rule_name, *_ in self.browsers[field] if rule_name == name
        ]
        charts = "".join(
            f"<h2>{label}</h2>" + bar_chart(label, group["fields"][other].most_common(12))
            for other, label in [
                ("version", "Major versions"),
                (
                    "os" if field == "browser" else "browser",
                    "Operating systems" if field == "browser" else "Browsers",
                ),
                ("device", "Devices"),
                ("engine", "Engines"),
            ]
            if len(group["fields"][other]) > 1 or other == "version"
        )
        items = "".join(
            f"<li><code>{text(sample)}</code><small>{text(name)} {text(version)} "
            f'<a href="/?ua={quote(sample)}" rel="nofollow">analyze</a></small></li>'
            for version, sample in samples
        )
        kind = FIELDS[field].lower()
        body = f"""
<h1>{text(name)} user agent</h1>
<p class="lede">{text(name)} is a {kind} recognized by uaid in
{number(len(group["samples"]))} sample user agent strings, by the token
{", ".join(f"<code>{text(token)}</code>" for token in tokens) or "in the string"}.</p>
<h2>Latest {text(name)} user agent strings</h2>
<ul class="uas">{items}</ul>
{charts}
<p><a href="/browsers/">All browsers and operating systems</a></p>"""
        return layout(
            f"/{folder}/{slugify(name)}/",
            f"{name} User Agent Strings – Latest Versions – uaid",
            f"Latest {name} user agent strings with versions, devices and operating "
            "systems, "
            f"and how to detect {name} from the User-Agent header.",
            body,
            [("Browsers", "/browsers/"), (name, f"/{folder}/{slugify(name)}/")],
        )

    def not_found(self) -> str:
        body = """<h1>Page not found</h1>
<p>Try the <a href="/">analyzer</a> or the <a href="/crawlers/">crawler list</a>.</p>"""
        return layout("/404.html", "Not found – uaid", "Page not found.", body)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: site.py <robots-release> <out>")
    builder = Builder(ROOT, Path(sys.argv[1]))
    builder.build(Path(sys.argv[2]))
    print(f"{len(builder.pages)} pages, data from {builder.date}, built {date.today()}")


if __name__ == "__main__":
    main()
