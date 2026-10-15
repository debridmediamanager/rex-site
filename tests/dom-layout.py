"""Measure the rendered site through an existing Chrome CDP profile.

Runs against any served copy of public/, the live site included. Install the driver with:
  uv run --with websocket-client python tests/dom-layout.py --base-url http://zen:PORT
No browser is launched and only this script's own tab is closed.
"""
import argparse
import base64
import itertools
import json
from pathlib import Path
import time
import urllib.request
from urllib.parse import urlsplit
import websocket


class Page:
    def __init__(self, endpoint):
        self.endpoint = endpoint.rstrip('/')
        req = urllib.request.Request(self.endpoint + '/json/new?about:blank', method='PUT')
        info = json.load(urllib.request.urlopen(req))
        self.id = info['id']
        self.ws = websocket.create_connection(info['webSocketDebuggerUrl'], suppress_origin=True, timeout=45)
        self.ids = itertools.count(1)
        self.call('Page.enable')
        self.call('Network.enable')
        self.call('Network.setCacheDisabled', {'cacheDisabled': True})
        self.call('Network.setBypassServiceWorker', {'bypass': True})
        self.call('Emulation.setFocusEmulationEnabled', {'enabled': True})

    def call(self, method, params=None):
        call_id = next(self.ids)
        self.ws.send(json.dumps({'id': call_id, 'method': method, 'params': params or {}}))
        while True:
            event = json.loads(self.ws.recv())
            if event.get('id') == call_id:
                if 'error' in event:
                    raise RuntimeError(event['error'])
                return event.get('result', {})

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
        if 'exceptionDetails' in result:
            raise RuntimeError(result['exceptionDetails'])
        return result.get('result', {}).get('value')

    def navigate(self, url):
        self.evaluate('window.__layoutNavigationPending = true')
        result = self.call('Page.navigate', {'url': url})
        if result.get('errorText'):
            raise RuntimeError(result['errorText'] + ': ' + url)
        for _ in range(300):
            time.sleep(.1)
            if self.evaluate("document.readyState === 'complete' && !window.__layoutNavigationPending"):
                break
        else:
            raise RuntimeError('Page did not finish loading: ' + url)
        self.evaluate('document.fonts.ready.then(() => true)')
        time.sleep(.3)
        actual = urlsplit(self.evaluate('location.href'))
        expected = urlsplit(url)
        if actual.netloc != expected.netloc or actual.path.removesuffix('.html') != expected.path.removesuffix('.html'):
            raise RuntimeError('Unexpected navigation: ' + actual.geturl())

    def close(self):
        self.ws.close()
        urllib.request.urlopen(self.endpoint + '/json/close/' + self.id).read()


MEASURE = r"""(() => {
  const width = document.documentElement.clientWidth;
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const identify = el => ({tag: el.tagName, text: el.textContent.trim().slice(0, 65), class: typeof el.className === 'string' ? el.className : ''});
  const inScroller = el => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { if (['auto', 'scroll'].includes(getComputedStyle(p).overflowX)) return true; } return false; };
  const elements = [...document.querySelectorAll('main, main *, header, header *, footer, footer *')].filter(visible);
  const overflow = elements.filter(el => !inScroller(el)).filter(el => {const r = el.getBoundingClientRect();return r.left < -1 || r.right > width + 1;}).map(identify);
  const smallText = [...document.querySelectorAll('p, li')].filter(visible).filter(el => !el.matches('.eyebrow, .sec-label')).filter(el => parseFloat(getComputedStyle(el).fontSize) < 14).map(identify);
  const controls = [...document.querySelectorAll('button, summary, nav a, a.btn, a.funding-link')].filter(visible);
  const smallControls = controls.filter(el => { const r = el.getBoundingClientRect();return r.height < 43.5; }).map(identify);
  const navigation = [...document.querySelectorAll('header nav a')].filter(visible);
  const brokenImages = [...document.images].filter(visible).filter(el => el.complete && !el.naturalWidth).map(el => el.src);
  const badScrollers = [...document.querySelectorAll('.tscroll, pre')].filter(visible).filter(el => el.scrollWidth > el.clientWidth + 1 && el.tabIndex < 0).map(identify);
  const heading = document.querySelector('h1');
  return {width, scrollWidth: document.documentElement.scrollWidth, overflow, smallText, smallControls, navigation: navigation.length, brokenImages, badScrollers, heading: heading?.textContent.trim() ?? null, main: !!document.querySelector('main')};
})()"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--cdp', default='http://127.0.0.1:9222')
    parser.add_argument('--report', default='/tmp/dom-layout-report.json')
    parser.add_argument('--screenshots')
    parser.add_argument('--sweep', action='store_true', help='Measure every 40px from 320 through 2560')
    args = parser.parse_args()
    routes = ['/']
    widths = [320, 360, 375, 390, 414, 430, 600, 768, 820, 1024, 1280, 1366, 1440, 1536, 1920, 2560]
    if args.sweep:
        widths = sorted(set(widths) | set(range(320, 2561, 40)))
    page = Page(args.cdp)
    records = []
    try:
        agent = page.evaluate('navigator.userAgent')
        for route in routes:
            page.navigate(args.base_url.rstrip('/') + route)
            # full-page captures need every lazy image loaded, not only the ones in the first viewport
            page.evaluate("Promise.all([...document.images].map(i => { i.loading = 'eager'; return i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; }); })).then(() => true)")
            for width, height in [(w, 900) for w in widths] + [(844, 390)]:
                page.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
                time.sleep(.06)
                record = page.evaluate(MEASURE)
                record.update(route=route, viewport=width, height=height)
                record['passed'] = all([
                    record['scrollWidth'] <= record['width'] + 1,
                    not record['overflow'], not record['smallText'], not record['smallControls'],
                    record['navigation'] > 0, not record['brokenImages'], not record['badScrollers'],
                    record['main'], bool(record['heading']),
                ])
                records.append(record)
                if args.screenshots and width in [320, 390, 768, 1024, 1440, 1920] and height == 900:
                    target = Path(args.screenshots)
                    target.mkdir(parents=True, exist_ok=True)
                    slug = route.strip('/').replace('/', '-').replace('?', '-') or 'home'
                    shot = page.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': True,
                        'clip': {'x': 0, 'y': 0, 'width': width, 'height': page.evaluate('document.documentElement.scrollHeight'), 'scale': 1}})
                    (target / f'{slug}-{width}.png').write_bytes(base64.b64decode(shot['data']))
            # Native disclosure controls must be reachable, open, and remain within the viewport.
            page.call('Emulation.setDeviceMetricsOverride', {'width': 320, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            if page.evaluate("!!document.querySelector('summary')"):
                page.evaluate("document.querySelector('summary').focus()")
                page.call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Enter', 'code': 'Enter', 'text': '\r', 'windowsVirtualKeyCode': 13})
                page.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13})
                opened = page.evaluate("document.querySelector('details').open")
                expanded = page.evaluate(MEASURE)
                expanded.update(route=route, viewport=320, state='expanded disclosure', passed=opened and not expanded['overflow'] and not expanded['smallControls'])
                records.append(expanded)
            failed = sum(not r['passed'] for r in records if r['route'] == route)
            print(f'{route}: {failed} failed viewport checks', flush=True)
    finally:
        page.close()
    Path(args.report).write_text(json.dumps({'browser': agent, 'baseUrl': args.base_url, 'measurements': records}, indent=2))
    failed = [r for r in records if not r['passed']]
    print(f'{len(records) - len(failed)}/{len(records)} viewport checks passed. Report: {args.report}')
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
