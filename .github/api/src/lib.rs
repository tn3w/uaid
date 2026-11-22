use std::cmp::Reverse;
use std::collections::HashMap;
use std::iter::once;
use std::net::{AddrParseError, IpAddr};
use std::sync::LazyLock;

use aho_corasick::AhoCorasick;
use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

pub const MAX_LENGTH: usize = 4096;
pub const EDGES: &[char] = &['^', '/', ' ', ';', '(', ')'];
const KEYWORDS: [&str; 22] = [
    "bot", "crawl", "spider", "http", ".com", "url", "@", "check", "site", "headless",
    "preview", "scan", "scrap", "fetch", "monitor", "index", "feed", "inspect",
    "resolver", "google-", "-google", "ptst",
];
const NOT_MODELS: [&str; 9] = [
    "mobile",
    "tablet",
    "harmonyos",
    "linux",
    "windows",
    "android",
    "opera",
    "xbox",
    "rv:",
];
const SEPARATORS: [char; 5] = ['(', ')', ';', ',', '+'];

#[derive(Deserialize)]
pub struct Crawler {
    #[serde(rename = "match")]
    pub rules: Vec<Rule>,
    pub instances: Vec<String>,
    #[serde(flatten)]
    pub info: Info,
}

#[derive(Deserialize, Serialize)]
pub struct Info {
    pub description: String,
    pub tags: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub rdns: Vec<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub ranges: Vec<String>,
}

#[derive(Deserialize)]
#[serde(untagged)]
pub enum Rule {
    One(String),
    All(Vec<String>),
}

impl Rule {
    pub fn parts(&self) -> &[String] {
        match self {
            Rule::One(part) => std::slice::from_ref(part),
            Rule::All(parts) => parts,
        }
    }

    pub fn longest(&self) -> &str {
        let parts = self.parts();
        parts.iter().fold(&parts[0], |longest, part| {
            if part.len() > longest.len() {
                part
            } else {
                longest
            }
        })
    }

    fn length(&self) -> usize {
        self.parts().iter().map(String::len).sum()
    }
}

#[derive(Deserialize)]
#[serde(untagged)]
enum Token {
    Versioned(String, String),
    Fixed(String, String, Option<String>),
}

impl Token {
    fn token(&self) -> &str {
        let (Token::Versioned(token, _) | Token::Fixed(token, ..)) = self;
        token
    }

    fn name(&self) -> &str {
        let (Token::Versioned(_, name) | Token::Fixed(_, name, _)) = self;
        name
    }

    fn version(&self, after: &str) -> Option<String> {
        match self {
            Token::Versioned(..) => clean(after),
            Token::Fixed(.., version) => version.clone(),
        }
    }
}

struct Rules {
    list: Vec<(&'static Rule, usize)>,
    finder: AhoCorasick,
    positions: Vec<Vec<usize>>,
}

#[derive(Deserialize)]
struct CrawlerIps {
    rdns: IndexMap<String, Vec<String>>,
    ranges: IndexMap<String, Vec<String>>,
}

static CRAWLERS: LazyLock<Vec<Crawler>> =
    LazyLock::new(|| parse(include_str!("../../../crawlers.json")));
static BROWSERS: LazyLock<IndexMap<String, Vec<Token>>> =
    LazyLock::new(|| parse(include_str!("../../../browsers.json")));
static RULES: LazyLock<Rules> = LazyLock::new(build_rules);
static NETWORKS: LazyLock<Vec<(String, Vec<u128>)>> = LazyLock::new(|| {
    let ips: CrawlerIps = parse(include_str!("../../../crawler-ips.json"));
    ips.rdns
        .into_iter()
        .chain(ips.ranges)
        .filter(|(_, cidrs)| !cidrs.is_empty())
        .map(|(key, cidrs)| (key, bounds(&cidrs)))
        .collect()
});

fn parse<T: serde::de::DeserializeOwned>(json: &str) -> T {
    serde_json::from_str(json).expect("bundled data is valid")
}

fn build_rules() -> Rules {
    let mut list: Vec<(&Rule, usize)> = CRAWLERS
        .iter()
        .enumerate()
        .flat_map(|(index, crawler)| crawler.rules.iter().map(move |rule| (rule, index)))
        .collect();
    list.sort_by_key(|(rule, _)| Reverse(rule.length()));

    let mut patterns: IndexMap<&str, Vec<usize>> = IndexMap::new();
    for (position, (rule, _)) in list.iter().enumerate() {
        patterns.entry(rule.longest()).or_default().push(position);
    }
    let finder = AhoCorasick::new(patterns.keys()).expect("rule patterns");
    let positions = patterns.into_values().collect();
    Rules {
        list,
        finder,
        positions,
    }
}

pub fn crawlers() -> &'static [Crawler] {
    &CRAWLERS
}

fn truncate(user_agent: &str) -> &str {
    user_agent
        .char_indices()
        .nth(MAX_LENGTH)
        .map_or(user_agent, |(index, _)| &user_agent[..index])
}

fn first_rule(lowered: &str) -> Option<(&'static str, &'static Crawler)> {
    let mut found: Vec<usize> = RULES
        .finder
        .find_overlapping_iter(lowered)
        .flat_map(|hit| &RULES.positions[hit.pattern()])
        .copied()
        .collect();
    found.sort_unstable();
    let matches = |rule: &Rule| {
        rule.parts()
            .iter()
            .all(|part| lowered.contains(part.as_str()))
    };
    let (rule, crawler) = found
        .into_iter()
        .map(|position| RULES.list[position])
        .find(|(rule, _)| matches(rule))?;
    Some((rule.longest().trim_matches(EDGES), &CRAWLERS[crawler]))
}

pub fn find(user_agent: &str) -> Option<(&'static str, &'static Crawler)> {
    first_rule(&format!("^{}", truncate(user_agent).to_ascii_lowercase()))
}

fn before(word: &str, separator: char) -> &str {
    word.split(separator).next().unwrap_or(word)
}

fn clean(version: &str) -> Option<String> {
    let version = before(version, ' ').replace('_', ".");
    version
        .starts_with(|character: char| character.is_ascii_digit())
        .then_some(version)
}

fn is_locale(word: &str) -> bool {
    word.chars().count() == 5 && word.chars().nth(2) == Some('-')
}

fn inner(word: &str) -> &str {
    let mut characters = word.chars();
    characters.next();
    characters.next_back();
    characters.as_str()
}

fn has_keyword(word: &str) -> bool {
    let lowered = word.to_lowercase();
    KEYWORDS.iter().any(|keyword| lowered.contains(keyword))
}

fn guess(text: &str) -> &str {
    let names: Vec<&str> = text
        .split_whitespace()
        .filter(|word| !word.contains("://") && !word.contains('@'))
        .collect();
    let named = names.iter().find(|word| has_keyword(word));
    let plain = names
        .first()
        .filter(|word| !word.to_lowercase().starts_with("mozilla/"));
    named.or(plain).map_or("", |word| before(word, '/'))
}

fn product(result: &mut Map<String, Value>, user_agent: &str, text: &str, pattern: &str) {
    let lowered = user_agent.to_ascii_lowercase();
    let Some(found) = lowered.find(&pattern.to_ascii_lowercase()) else {
        return;
    };
    let start = text[..found].rfind([' ', '/']).map_or(0, |index| index + 1);
    let end = found + pattern.len();
    let word = before(&text[end..], ' ');
    let (rest, version) = word.split_once('/').unwrap_or((word, ""));
    result.insert(
        "name".into(),
        format!("{}{rest}", &user_agent[start..end]).into(),
    );
    result.insert("version".into(), clean(version).into());
}

fn is_model(name: &str) -> bool {
    let lowered = name.to_lowercase();
    name.chars().count() > 2
        && !is_locale(name)
        && !NOT_MODELS.iter().any(|prefix| lowered.starts_with(prefix))
}

fn android_model<'a>(user_agent: &'a str, lowered: &str) -> Option<&'a str> {
    let tail = &user_agent[lowered.find("android")?..];
    let last = tail.char_indices().last().map_or(0, |(index, _)| index);
    let end = tail
        .find(" Build/")
        .or_else(|| tail.find(')'))
        .unwrap_or(last);
    tail[..end]
        .split(';')
        .skip(1)
        .map(str::trim)
        .find(|name| is_model(name))
}

fn words_where(words: &[&str], keep: impl Fn(&str) -> bool) -> Value {
    json!(words.iter().filter(|word| keep(word)).collect::<Vec<_>>())
}

fn describe(user_agent: &str, text: &str, lowered: &str) -> Map<String, Value> {
    let words: Vec<&str> = text.split_whitespace().collect();
    let email = |word: &str| inner(word).contains('@') && !word.contains("://");
    let mut result = Map::new();
    result.insert("bot".into(), false.into());
    result.insert(
        "urls".into(),
        words_where(&words, |word| word.contains("://")),
    );
    result.insert("emails".into(), words_where(&words, email));
    result.insert("languages".into(), words_where(&words, is_locale));

    for (field, tokens) in BROWSERS.iter() {
        let found = tokens.iter().find_map(|token| {
            let start = lowered.find(token.token())?;
            Some((token, start + token.token().len()))
        });
        if let Some((token, end)) = found {
            result.insert(field.clone(), token.name().into());
            result.insert(
                format!("{field}_version"),
                token.version(&text[end..]).into(),
            );
        }
    }
    if lowered.contains("android") && !result.contains_key("model") {
        result.insert("model".into(), android_model(user_agent, lowered).into());
    }
    result
}

fn signals(lowered: &str) -> Vec<&'static str> {
    let found = KEYWORDS
        .into_iter()
        .filter(|keyword| lowered.contains(keyword));
    if lowered.contains('(') {
        found.collect()
    } else {
        once("no-comment").chain(found).collect()
    }
}

fn is_empty(value: &Value) -> bool {
    value.is_null() || value.as_array().is_some_and(Vec::is_empty)
}

pub fn identify(user_agent: &str) -> Map<String, Value> {
    let user_agent = truncate(user_agent);
    let text = user_agent.replace(SEPARATORS, " ");
    let lowered = user_agent.to_ascii_lowercase();
    let mut result = describe(user_agent, &text, &lowered);
    let rule = first_rule(&format!("^{lowered}"));
    let reasons = signals(&lowered);

    let mut pattern = rule.map_or("", |(pattern, _)| pattern);
    if rule.is_some() || !reasons.is_empty() {
        if pattern.is_empty() {
            pattern = guess(&text);
        }
        let database = rule.map(|_| "database");
        let signals: Vec<&str> = database.into_iter().chain(reasons).collect();
        result.insert("bot".into(), true.into());
        result.insert("signals".into(), signals.into());
    }
    if !pattern.is_empty() {
        product(&mut result, user_agent, &text, pattern);
    }

    result.retain(|_, value| !is_empty(value));
    if let Some((_, crawler)) = rule
        && let Value::Object(info) = json!(crawler.info)
    {
        result.extend(info);
    }
    result
}

fn number(address: IpAddr) -> u128 {
    match address {
        IpAddr::V4(address) => u32::from(address).into(),
        IpAddr::V6(address) => address.into(),
    }
}

fn span(cidr: &str) -> (u128, u128) {
    let (address, prefix) = cidr.split_once('/').unwrap_or((cidr, ""));
    let address: IpAddr = address.parse().expect("bundled network is valid");
    let bits = if address.is_ipv4() { 32 } else { 128 };
    let size = bits - prefix.parse().unwrap_or(bits);
    let host = if size == 0 {
        0
    } else {
        u128::MAX >> (128 - size)
    };
    let start = number(address);
    (start, (start | host).saturating_add(1))
}

fn bounds(cidrs: &[String]) -> Vec<u128> {
    let mut spans: Vec<(u128, u128)> = cidrs.iter().map(|cidr| span(cidr)).collect();
    spans.sort_unstable();
    let mut bounds: Vec<u128> = Vec::new();
    for (start, end) in spans {
        match bounds.last_mut() {
            Some(last) if start <= *last => *last = (*last).max(end),
            _ => bounds.extend([start, end]),
        }
    }
    bounds
}

fn normalize(ip: &str) -> Result<IpAddr, AddrParseError> {
    let address: IpAddr = ip.parse()?;
    Ok(match address {
        IpAddr::V6(v6) => v6.to_ipv4_mapped().map_or(address, IpAddr::V4),
        IpAddr::V4(_) => address,
    })
}

pub fn networks(ip: &str) -> Result<Vec<&'static str>, AddrParseError> {
    let number = number(normalize(ip)?);
    let inside =
        |bounds: &[u128]| bounds.partition_point(|&bound| bound <= number) % 2 == 1;
    Ok(NETWORKS
        .iter()
        .filter(|(_, bounds)| inside(bounds))
        .map(|(key, _)| key.as_str())
        .collect())
}

pub fn verify(user_agent: &str, ip: &str) -> Result<bool, AddrParseError> {
    let keys = networks(ip)?;
    Ok(find(user_agent).is_some_and(|(_, crawler)| {
        let info = &crawler.info;
        info.rdns
            .iter()
            .chain(&info.ranges)
            .any(|key| keys.contains(&key.as_str()))
    }))
}

fn is_token(token: &str) -> bool {
    token.bytes().all(|byte| {
        byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"-_.".contains(&byte)
    })
}

pub fn agents(tags: &[&str]) -> Vec<&'static str> {
    let tokens: HashMap<&str, usize> = RULES
        .list
        .iter()
        .map(|(rule, crawler)| (rule.longest().trim_matches(EDGES), *crawler))
        .collect();
    let tagged = |crawler: usize| {
        CRAWLERS[crawler]
            .info
            .tags
            .iter()
            .any(|tag| tags.contains(&tag.as_str()))
    };
    let mut found: Vec<&str> = tokens
        .into_iter()
        .filter(|(token, crawler)| is_token(token) && tagged(*crawler))
        .map(|(token, _)| token)
        .collect();
    found.sort_unstable();
    found
}

pub fn robots_txt(tags: &[&str], path: &str) -> Result<String, &'static str> {
    if path.contains(['\n', '\r']) {
        return Err("path must be a single line");
    }
    let agents = agents(tags);
    if agents.is_empty() {
        return Ok(String::new());
    }
    let lines: String = agents
        .iter()
        .map(|agent| format!("User-agent: {agent}\n"))
        .collect();
    Ok(format!("{lines}Disallow: {path}\n"))
}

#[cfg(test)]
mod tests {
    use super::*;

    const GOOGLEBOT: &str =
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)";

    #[test]
    fn identifies_crawlers_and_browsers() {
        let bot = identify(GOOGLEBOT);
        assert_eq!(bot["name"], "Googlebot");
        assert_eq!(bot["version"], "2.1");
        assert_eq!(bot["signals"], json!(["database", "bot", "http", ".com"]));
        assert!(!bot["rdns"].as_array().unwrap().is_empty());

        let firefox =
            "Mozilla/5.0 (Windows NT 10.0; rv:128.0) Gecko/20100101 Firefox/128.0";
        let browser = identify(firefox);
        assert_eq!(browser["bot"], false);
        assert_eq!(browser["browser"], "Firefox");
        assert_eq!(browser["browser_version"], "128.0");
        assert_eq!(identify("curl/8.4.0")["name"], "curl");
    }

    #[test]
    fn every_instance_finds_its_crawler() {
        for crawler in crawlers() {
            for instance in &crawler.instances {
                let (_, found) = find(instance).expect(instance);
                assert_eq!(
                    found.info.description, crawler.info.description,
                    "{instance}"
                );
            }
        }
    }

    #[test]
    fn verifies_ips() {
        assert_eq!(verify(GOOGLEBOT, "66.249.66.1"), Ok(true));
        assert_eq!(verify(GOOGLEBOT, "::ffff:66.249.66.1"), Ok(true));
        assert_eq!(verify(GOOGLEBOT, "192.0.2.1"), Ok(false));
        assert!(verify(GOOGLEBOT, "not an ip").is_err());
    }

    #[test]
    fn writes_robots_txt() {
        let robots = robots_txt(&["ai-crawler"], "/").unwrap();
        assert!(robots.contains("User-agent: gptbot\n"));
        assert!(robots.ends_with("Disallow: /\n"));
        assert_eq!(robots_txt(&[], "/"), Ok(String::new()));
        assert!(robots_txt(&["seo"], "/\n").is_err());
    }
}
