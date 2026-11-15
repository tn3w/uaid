import { existsSync, readFileSync, writeFileSync } from "node:fs";

const headers = { "User-Agent": "uaid-robots/1.0 (+https://github.com/tn3w/uaid)" };
const date = new Date().toISOString().slice(0, 10);
const domains = readFileSync(0, "utf8")
  .split("\n")
  .slice(0, 25_000)
  .map((line) => line.split(",")[1]?.trim())
  .filter(Boolean);

async function download(domain) {
  for (const scheme of ["https", "http"]) {
    try {
      const url = `${scheme}://${domain}/robots.txt`;
      const response = await fetch(url, { headers, signal: AbortSignal.timeout(5000) });
      if (response.status >= 500) return { status: "unavailable" };
      if (!response.ok) return { status: "missing" };
      return { status: "ok", text: await response.text() };
    } catch {}
  }
  return { status: "unreachable" };
}

function parse(text) {
  const robots = { rules: {}, signals: [], sitemap: false };
  let group = [];
  let inRules = false;
  for (const line of text.split("\n")) {
    const [, key, value] = line.split("#")[0].match(/^\s*([\w-]+)\s*:\s*(.*?)\s*$/) ?? [];
    const field = key?.toLowerCase();
    if (field === "sitemap") robots.sitemap = true;
    if (field === "content-signal") robots.signals.push(...value.toLowerCase().split(","));
    if (field === "user-agent" && value) {
      if (inRules) group = [];
      inRules = false;
      group.push(value.toLowerCase());
      robots.rules[value.toLowerCase()] ??= { allow: [], disallow: [] };
    }
    if (!group.length || !["allow", "disallow", "crawl-delay"].includes(field)) continue;
    inRules = true;
    for (const agent of group) {
      if (field === "crawl-delay") robots.rules[agent].delay = true;
      else if (value) robots.rules[agent][field].push(value);
    }
  }
  return robots;
}

const state = ({ allow, disallow }) => {
  if (!disallow.length) return "allowed";
  const root = disallow.some((path) => path === "/" || path === "/*");
  return root && !allow.length ? "blocked" : "partial";
};

const today = { date, sites: domains.length, status: {}, analyzed: 0, sitemaps: 0 };
const agents = {};
const signals = {};
const sites = {};
const count = (target, key) => (target[key] = (target[key] ?? 0) + 1);

function record(domain, { status, text = "" }) {
  count(today.status, status);
  const robots = parse(text);
  if (!Object.keys(robots.rules).length) return;
  today.analyzed++;
  today.sitemaps += robots.sitemap;
  for (const signal of new Set(robots.signals.map((part) => part.trim()))) {
    count(signals, signal);
  }
  const site = {};
  for (const [agent, rules] of Object.entries(robots.rules)) {
    const result = state(rules);
    const stats = (agents[agent] ??= { blocked: 0, partial: 0, allowed: 0, delay: 0 });
    stats[result]++;
    stats.delay += Boolean(rules.delay);
    if (result !== "allowed") (site[result] ??= []).push(agent);
  }
  if (robots.signals.length) site.signals = robots.signals.map((part) => part.trim());
  if (Object.keys(site).length) sites[domain] = site;
}

const queue = [...domains];
await Promise.all(
  Array.from({ length: 128 }, async () => {
    for (let domain; (domain = queue.shift()); ) record(domain, await download(domain));
  }),
);

const restricted = ({ blocked, partial }) => blocked + partial;
const ranked = Object.entries(agents).sort(([, a], [, b]) => restricted(b) - restricted(a));
const share = (stats) => Number((restricted(stats) / today.analyzed).toFixed(6));

const history = existsSync("robots-history.json")
  ? JSON.parse(readFileSync("robots-history.json", "utf8"))
  : { dates: [], agents: {} };
let column = history.dates.indexOf(date);
if (column < 0) column = history.dates.push(date) - 1;
for (const [agent, stats] of ranked) {
  if (!restricted(stats)) continue;
  const row = (history.agents[agent] ??= []);
  while (row.length < column) row.push(null);
  row[column] = share(stats);
}

const output = { ...today, signals, agents: Object.fromEntries(ranked), domains: sites };
writeFileSync("robots-today.json", JSON.stringify(output));
writeFileSync("robots-history.json", JSON.stringify(history));
console.log(`${today.analyzed} of ${today.sites} sites analyzed`, today.status);
