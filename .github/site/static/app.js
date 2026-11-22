const fields = [
  ['Browser', 'browser', 'browser_version'], ['Engine', 'engine', 'engine_version'],
  ['OS', 'os', 'os_version'], ['Device', 'device'], ['Brand', 'brand', 'model'],
  ['CPU', 'cpu'], ['Category', 'tags'], ['Signals', 'signals'],
  ['Languages', 'languages'], ['Emails', 'emails'],
];

const element = (tag, content, attributes = {}) => {
  const node = Object.assign(document.createElement(tag), attributes);
  node.append(...[content].flat().filter((item) => item != null && item !== ''));
  return node;
};

const joined = (result, keys) => keys.map((key) => [result[key]].flat().join(', '))
  .filter(Boolean).join(' ');

function domainOf(result) {
  try {
    return new URL(result.url || result.urls?.[0]).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

function header(result) {
  const domain = result.bot ? domainOf(result) : null;
  const icon = domain ? element('img', null, {
    className: 'icon', width: 32, height: 32, alt: '', referrerPolicy: 'no-referrer',
    src: `https://icons.duckduckgo.com/ip3/${encodeURIComponent(domain)}.ico`,
  }) : null;
  const title = result.bot
    ? joined(result, ['name', 'version']) || 'Unknown bot'
    : joined(result, ['browser', 'browser_version']) || 'Unknown browser';
  const subtitle = result.bot ? result.description
    : [joined(result, ['os', 'os_version']), result.device].filter(Boolean).join(' · ');
  return element('header', [icon, element('div', [
    element('strong', title), element('small', subtitle),
  ]), element('span', result.bot ? 'bot' : 'browser', { className: 'kind' })]);
}

const check = (content, state = '') =>
  element('p', content, { className: `check ${state}` });

function ipCheck(result) {
  if (!result.ip) return null;
  if (result.error) return check(`${result.ip}: ${result.error}`, 'bad');
  if ('verified' in result) {
    return result.verified
      ? check(`${result.ip} is a verified ${result.name} address`, 'good')
      : check(`${result.ip} is not a ${result.name} address: spoofed user agent`, 'bad');
  }
  const owners = result.owners || [];
  if (!owners.length) return check(`${result.ip} is in no known crawler network`);
  const shown = owners.slice(0, 3).flatMap((owner, index) =>
    [index ? ', ' : '', element('a', owner.name, { href: owner.page })]);
  const more = owners.length > 3 ? ` +${owners.length - 3}` : '';
  return check([`${result.ip} belongs to `, ...shown, more]);
}

function cell([label, ...keys], result) {
  const value = joined(result, keys);
  return value ? element('div', [element('dt', label), element('dd', value)]) : null;
}

function render(result) {
  const cells = fields.map((field) => cell(field, result));
  const links = [
    result.page && element('a', 'Crawler page →', { href: result.page }),
    element('details', [
      element('summary', 'JSON'), element('pre', JSON.stringify(result, null, 2)),
    ]),
  ];
  document.getElementById('result').replaceChildren(element('div', [
    header(result), ipCheck(result), element('dl', cells, { className: 'fields' }),
    element('footer', links),
  ], { className: 'card' }));
}

async function analyze(userAgent, ip) {
  const query = new URLSearchParams({ ua: userAgent });
  if (ip) query.set('ip', ip);
  const response = await fetch(`/api?${query}`);
  render(await response.json());
}

function submitAnalyze(event) {
  event.preventDefault();
  const userAgent = document.getElementById('ua').value.trim() || navigator.userAgent;
  const ip = document.getElementById('ip').value.trim();
  const query = new URLSearchParams({ ua: userAgent });
  if (ip) query.set('ip', ip);
  history.replaceState(null, '', `/?${query}`);
  analyze(userAgent, ip);
}

async function submitRobots(event) {
  event.preventDefault();
  const query = new URLSearchParams(new FormData(event.target));
  const response = await fetch(`/api/robots?${query}`);
  const output = document.getElementById('robots-output');
  output.textContent = await response.text();
  output.hidden = false;
}

function useMine() {
  document.getElementById('ua').value = navigator.userAgent;
  document.getElementById('ip').value = '';
  history.replaceState(null, '', '/');
  analyze(navigator.userAgent, '');
}

function start() {
  const query = new URLSearchParams(location.search);
  const userAgent = query.get('ua') || navigator.userAgent;
  document.getElementById('ua').value = userAgent;
  document.getElementById('ip').value = query.get('ip') || '';
  document.getElementById('analyze').addEventListener('submit', submitAnalyze);
  document.getElementById('robots').addEventListener('submit', submitRobots);
  document.getElementById('mine').addEventListener('click', useMine);
  analyze(userAgent, query.get('ip') || '');
}

start();
