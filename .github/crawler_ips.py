import asyncio
import ipaddress
import json
import lzma
import re
import struct
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import dns.asyncresolver
import dns.exception
import dns.resolver

FILTERS = [{"id": lzma.FILTER_LZMA1, "lc": 4, "lp": 0, "pb": 0, "dict_size": 1 << 21}]
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
NAMESERVERS = ["1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112"]
HEADERS = {"User-Agent": "uaid-crawler-ips/1.0 (+https://github.com/tn3w/uaid)"}
SAMPLES = 6
ADDRESS = re.compile(r"[0-9a-fA-F:.]+(?:/\d{1,3})?")
LINKED_LIST = re.compile(r"https?://[^\"'\s<>]*ip[^\"'\s<>]*\.(?:json|txt)", re.I)

CRAWLERS = json.loads(Path("crawlers.json").read_text())
SUFFIXES = sorted({suffix for crawler in CRAWLERS for suffix in crawler.get("rdns", [])})
SUFFIX = re.compile(
    b"("
    + b"|".join(re.escape(suffix.encode()) for suffix in SUFFIXES)
    + b")(?=[\x00\x1f]|$)"
)


def varints(data, position, count):
    values = []
    for _ in range(count):
        value = shift = 0
        while data[position] >= 0x80:
            value |= (data[position] & 0x7F) << shift
            shift += 7
            position += 1
        values.append(value | data[position] << shift)
        position += 1
    return values, position


def blocks(data):
    count = struct.unpack_from("<I", data, 4)[0]
    index_end = 8 + count * 8
    previous = 0
    for position in range(8, index_end, 8):
        first, offset = struct.unpack_from("<II", data, position)
        yield first, data[index_end + previous : index_end + offset]
        previous = offset


def scan_block(block):
    first, compressed = block
    raw = lzma.decompress(compressed, lzma.FORMAT_RAW, filters=FILTERS)
    if not SUFFIX.search(raw):
        return []
    [count], position = varints(raw, 0, 1)
    gaps, position = varints(raw, position, count)
    lengths, position = varints(raw, position, count)
    templates = raw[position:].split(b"\x00")
    runs = []
    start = first
    for gap, length, template in zip(gaps, lengths, templates, strict=True):
        start += gap
        for suffix in set(SUFFIX.findall(template)):
            runs.append((suffix.decode(), start, start + length, template))
        start += length + 1
    return runs


def base36(value, width):
    text = ""
    while value > 0 or len(text) < max(width, 1):
        text = DIGITS[value % 36] + text
        value //= 36
    return text


def affine(template, position, code, ip):
    width = max(template[position] - ord("0"), 0)
    end = template.index(0x1E, position + 1)
    offset = int(template[position + 1 : end] or 0)
    selected = [ip, ip & 0xFFFFFF, ip & 0xFFFF, ip & 0xFF, ip >> 8 & 0xFF]
    value = selected[(code - 17) % 5] + offset
    text = base36(value, width) if code >= 22 else f"{value:0{width}}"
    return text, end + 1


def render(template, ip):
    octets = ip.to_bytes(4, "big")
    parts = []
    position = 0
    while position < len(template):
        code = template[position]
        position += 1
        octet = octets[(code - 1) % 4]
        if code > 26:
            parts.append(chr(code))
        elif code > 16:
            text, position = affine(template, position, code, ip)
            parts.append(text)
        else:
            parts.append(("{}", "{:03}", "{:02x}", "{:x}")[(code - 1) // 4].format(octet))
    return "".join(parts)


def scan(path):
    data = Path(path).read_bytes()
    groups = defaultdict(list)
    with ProcessPoolExecutor() as pool:
        for runs in pool.map(scan_block, blocks(data), chunksize=8):
            for suffix, start, stop, template in runs:
                groups[suffix, start >> 8].append((start, stop, template))
    return groups


async def resolve(resolver, limiter, host):
    async with limiter:
        for _ in range(3):
            try:
                answer = await resolver.resolve(host, "A")
                return {record.address for record in answer}
            except dns.resolver.LifetimeTimeout:
                continue
            except dns.exception.DNSException:
                return set()
    return set()


def samples(runs):
    hosts = [
        (ip, template) for start, stop, template in runs for ip in range(start, stop + 1)
    ]
    spread = ((2 * index + 1) * len(hosts) // (2 * SAMPLES) for index in range(SAMPLES))
    return [hosts[position] for position in dict.fromkeys(spread)]


async def confirm_group(resolver, limiter, suffix, runs):
    for ip, template in samples(runs):
        names = template.split(b"\x1f")
        name = next(name for name in names if name.endswith(suffix.encode()))
        addresses = await resolve(resolver, limiter, render(name, ip))
        if str(ipaddress.IPv4Address(ip)) in addresses:
            return True
    return False


async def confirm(groups):
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = NAMESERVERS
    resolver.rotate = True
    resolver.timeout = 2
    resolver.lifetime = 4
    limiter = asyncio.Semaphore(256)
    checks = [
        confirm_group(resolver, limiter, suffix, runs)
        for (suffix, _), runs in groups.items()
    ]
    confirmed = defaultdict(list)
    results = await asyncio.gather(*checks)
    for ((suffix, _), runs), valid in zip(groups.items(), results, strict=True):
        if valid:
            confirmed[suffix] += [(start, stop) for start, stop, _ in runs]
    return confirmed


def to_networks(spans):
    address = ipaddress.IPv4Address
    for start, stop in spans:
        yield from ipaddress.summarize_address_range(address(start), address(stop))


def collapse(networks):
    networks = list(networks)
    families = [[net for net in networks if net.version == version] for version in (4, 6)]
    collapsed = map(ipaddress.collapse_addresses, families)
    return [str(network) for family in collapsed for network in family]


def download(url):
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode(errors="replace")
    except OSError as error:
        print(f"skipping {url}: {error}")


def with_linked_lists(url, text):
    host = urlparse(url).netloc
    links = {link for link in LINKED_LIST.findall(text) if urlparse(link).netloc == host}
    return "\n".join([text, *filter(None, map(download, sorted(links)))])


def extract(text):
    networks = []
    for candidate in ADDRESS.findall(text):
        try:
            network = ipaddress.ip_network(candidate, strict=False)
        except ValueError:
            continue
        if network.is_global:
            networks.append(network)
    return collapse(networks)


def main():
    groups = scan(sys.argv[1])
    confirmed = asyncio.run(confirm(groups))
    rdns = {suffix: collapse(to_networks(confirmed[suffix])) for suffix in SUFFIXES}
    urls = sorted({url for crawler in CRAWLERS for url in crawler.get("ranges", [])})
    with ThreadPoolExecutor(16) as pool:
        texts = dict(zip(urls, pool.map(download, urls), strict=True))
    ranges = {
        url: extract(with_linked_lists(url, text))
        for url, text in texts.items()
        if text is not None
    }
    output = {"date": date.today().isoformat(), "rdns": rdns, "ranges": ranges}
    Path("crawler-ips.json").write_text(json.dumps(output, indent=0) + "\n")
    print(
        f"{len(groups)} rdns groups, {sum(map(len, confirmed.values()))} confirmed runs"
    )


if __name__ == "__main__":
    main()
