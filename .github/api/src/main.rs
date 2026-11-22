use std::collections::HashMap;
use std::sync::LazyLock;

use axum::extract::Query;
use axum::http::{HeaderMap, HeaderValue, StatusCode, header};
use axum::middleware::map_response;
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::{Json, Router};
use serde_json::{Map, Value, json};
use uaid::EDGES;

type Parameters = Query<Vec<(String, String)>>;

#[derive(Default)]
struct Registry {
    pages: Vec<(String, String)>,
    by_pattern: HashMap<&'static str, usize>,
    by_network: HashMap<&'static str, Vec<usize>>,
}

static REGISTRY: LazyLock<Registry> = LazyLock::new(|| {
    let mut registry = Registry::default();
    let mut seen: HashMap<String, usize> = HashMap::new();
    for (index, crawler) in uaid::crawlers().iter().enumerate() {
        let token = crawler.rules[0].parts()[0].trim_matches(EDGES);
        let slug = slugify(token);
        let count = seen.entry(slug.clone()).or_default();
        *count += 1;
        let slug = if *count > 1 {
            format!("{slug}-{count}")
        } else {
            slug
        };
        let name = display_name(token, &crawler.instances);
        registry.pages.push((name, format!("/crawlers/{slug}/")));

        for rule in &crawler.rules {
            registry
                .by_pattern
                .entry(rule.longest().trim_matches(EDGES))
                .or_insert(index);
        }
        for key in crawler.info.rdns.iter().chain(&crawler.info.ranges) {
            registry.by_network.entry(key).or_default().push(index);
        }
    }
    registry
});

fn slugify(text: &str) -> String {
    let lowered = text.to_lowercase();
    let words: Vec<&str> = lowered
        .split(|character: char| {
            !character.is_ascii_lowercase() && !character.is_ascii_digit()
        })
        .filter(|word| !word.is_empty())
        .collect();
    if words.is_empty() {
        "unnamed".into()
    } else {
        words.join("-")
    }
}

fn is_lower(text: &str) -> bool {
    text.chars().any(char::is_lowercase) && !text.chars().any(char::is_uppercase)
}

fn display_name(token: &str, instances: &[String]) -> String {
    let names: Vec<&str> = instances
        .iter()
        .filter_map(|instance| {
            let found = instance.to_ascii_lowercase().find(token)?;
            Some(instance[found..found + token.len()].trim_matches(EDGES))
        })
        .collect();
    let capitalized = names.iter().find(|name| !is_lower(name));
    capitalized
        .or(names.first())
        .copied()
        .unwrap_or(token)
        .to_string()
}

fn first<'a>(query: &'a [(String, String)], name: &str) -> Option<&'a str> {
    query
        .iter()
        .find(|(key, value)| key == name && !value.is_empty())
        .map(|(_, value)| value.as_str())
}

fn header_text(headers: &HeaderMap, name: &str) -> String {
    let value = headers
        .get(name)
        .map(HeaderValue::as_bytes)
        .unwrap_or_default();
    String::from_utf8_lossy(value).into_owned()
}

fn owners(keys: &[&str]) -> Vec<Value> {
    let mut found: Vec<usize> = Vec::new();
    for index in keys
        .iter()
        .filter_map(|key| REGISTRY.by_network.get(key))
        .flatten()
    {
        if !found.contains(index) {
            found.push(*index);
        }
    }
    found
        .into_iter()
        .map(|index| {
            let (name, page) = &REGISTRY.pages[index];
            json!({"name": name, "page": page})
        })
        .collect()
}

fn describe(user_agent: &str, ip: &str) -> Map<String, Value> {
    let mut result = Map::new();
    result.insert("user_agent".into(), user_agent.into());
    result.extend(uaid::identify(user_agent));
    let found =
        uaid::find(user_agent).and_then(|(pattern, _)| REGISTRY.by_pattern.get(pattern));
    if let Some(&index) = found {
        result.insert("page".into(), REGISTRY.pages[index].1.clone().into());
    }
    if ip.is_empty() {
        return result;
    }

    result.insert("ip".into(), ip.into());
    let (Ok(keys), Ok(verified)) = (uaid::networks(ip), uaid::verify(user_agent, ip))
    else {
        result.insert("error".into(), "not an IP address".into());
        return result;
    };
    let owners = owners(&keys);
    result.insert("networks".into(), keys.into());
    result.insert("owners".into(), owners.into());
    if result.contains_key("rdns") || result.contains_key("ranges") {
        result.insert("verified".into(), verified.into());
    }
    result
}

async fn api(headers: HeaderMap, Query(query): Parameters) -> Json<Map<String, Value>> {
    let user_agent = first(&query, "ua")
        .map_or_else(|| header_text(&headers, "user-agent"), str::to_string);
    let ip = first(&query, "ip")
        .map_or_else(|| header_text(&headers, "x-client-ip"), str::to_string);
    Json(describe(&user_agent, ip.trim()))
}

async fn robots(Query(query): Parameters) -> Response {
    let tags: Vec<&str> = query
        .iter()
        .filter(|(key, _)| key == "tag")
        .map(|(_, value)| value.as_str())
        .collect();
    match uaid::robots_txt(&tags, first(&query, "path").unwrap_or("/")) {
        Err(error) => (StatusCode::BAD_REQUEST, format!("{error}\n")).into_response(),
        Ok(body) if body.is_empty() => "# no category chosen\n".into_response(),
        Ok(body) => body.into_response(),
    }
}

async fn not_found() -> (StatusCode, &'static str) {
    (StatusCode::NOT_FOUND, "not found\n")
}

async fn no_store(mut response: Response) -> Response {
    let no_store = HeaderValue::from_static("no-store");
    response
        .headers_mut()
        .insert(header::CACHE_CONTROL, no_store);
    response
}

#[tokio::main]
async fn main() {
    LazyLock::force(&REGISTRY);
    let socket = listenfd::ListenFd::from_env()
        .take_unix_listener(0)
        .expect("socket")
        .expect("systemd socket on fd 3");
    socket.set_nonblocking(true).expect("nonblocking socket");
    let listener = tokio::net::UnixListener::from_std(socket).expect("unix listener");
    let router = Router::new()
        .route("/api", get(api))
        .route("/api/robots", get(robots))
        .fallback(not_found)
        .layer(map_response(no_store));
    axum::serve(listener, router).await.expect("serve");
}
