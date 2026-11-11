#!/usr/bin/env python3
"""Machine translation for the DMM + zurg + rex sites. English is the only language anyone writes.

The same file is in notes, zurg-site and rex-site (i18n/translate.py). Change it in one and copy it to the others.

    translate.py md   --src .      --out build/i18n   Markdown pages (notes): one translated tree per language
    translate.py html --src public --out dist         static HTML (zurg-site, rex-site): public/ plus /<lang>/ copies

Every English piece (a Markdown section, an HTML text block, an attribute) is translated once and kept in
i18n/cache/<lang>.json under a hash of its text, so a push only pays for the pieces it changed. Without
OPENROUTER_TRANSLATE_KEY nothing is sent: cached pieces are used and the rest stay English. A piece whose
translation breaks code, links, tables or markup is retried, then left English. Exit code 3 means some
pieces stayed English; 4 means OpenRouter itself failed (key, limit, outage). Both only after every output file
has been written.
"""
import argparse, collections, concurrent.futures as cf, hashlib, html, json, os, posixpath, re, shutil, sys, time, urllib.error, urllib.request
from html.parser import HTMLParser

LANGS = {  # code: (name for the model, name in the language switcher)
    "zh": ("Simplified Chinese (zh-CN)", "中文"),
    "es": ("Spanish", "Español"),
    "ar": ("Modern Standard Arabic", "العربية"),
    "id": ("Indonesian", "Bahasa Indonesia"),
    "pt": ("Brazilian Portuguese", "Português"),
    "fr": ("French", "Français"),
    "ja": ("Japanese", "日本語"),
    "ru": ("Russian", "Русский"),
    "de": ("German", "Deutsch"),
}
ENGLISH = ("en", "English")
FAMILY = ("notes.debridmediamanager.com", "zurg.debridmediamanager.com", "rex.debridmediamanager.com")
MODEL = os.environ.get("TRANSLATE_MODEL", "anthropic/claude-haiku-5.5")
VERSION = "1"  # bump to translate everything again (prompt or rules changed)
CACHE_DIR = "i18n/cache"

RULES = """You translate the public docs and web pages of DMM + zurg + rex (Debrid Media Manager, zurg and rex are \
tools for streaming a debrid or Usenet library into Plex, Jellyfin and other players) from English into {lang}.

Reply with the translation only: no preamble, no notes, no surrounding code fence.
Keep every bit of structure exactly as it is: Markdown markers, list markers and indentation, table pipes and \
columns, blank lines, HTML tags with their attributes, Retype markers (lines starting with +++, ===, !!!, and \
{{.class}} or {{#id}} attributes), and tokens like ⟦C0⟧ (copy them unchanged, each on its own line).
Translate link text and image alt text. Never change: text inside backticks, URLs and link targets, file paths, commands, config keys, environment \
variables, version numbers, sizes and other numbers.
Keep these names in English as written: zurg, rex (always lowercase), DMM, Debrid Media Manager, gatekeeper, \
Plex, Jellyfin, Emby, Kodi, Infuse, Stremio, Real-Debrid, AllDebrid, TorBox, Premiumize, Debrid-Link, Offcloud, \
Easynews, Usenet, NZB, Sonarr, Radarr, Prowlarr, Seerr, Bazarr, Whisparr, Kometa, rclone, WebDAV, Docker, \
GitHub, Discord, Reddit, Patreon, Tailscale, Caddy.
Names of buttons, menus, fields, settings, log lines and error messages that the apps show stay in English \
exactly as written, because the apps themselves are in English. Translate the sentence around them.
Write the way a friendly, experienced user would explain it: plain, short sentences, informal where the \
language usually is for software (German du, Spanish tú, Brazilian você). Do not add or drop information."""

HTML_RULES = RULES + """

You get a JSON array of HTML fragments. Reply with a JSON array of the same length holding each fragment \
translated, in the same order. Keep every tag and attribute; translate title, alt and aria-label values."""


# ---------------------------------------------------------------- model and cache

class Translator:
    def __init__(self, lang):
        self.lang, self.name = lang, LANGS[lang][0]
        self.path = os.path.join(CACHE_DIR, f"{lang}.json")
        try:
            self.cache = json.load(open(self.path, encoding="utf-8"))
        except FileNotFoundError:
            self.cache = {}
        self.used, self.failed, self.sent, self.api_error = set(), 0, 0, None
        self.key = os.environ.get("OPENROUTER_TRANSLATE_KEY")

    def key_of(self, kind, text):
        return hashlib.sha256(f"{VERSION}\0{kind}\0{self.lang}\0{text}".encode()).hexdigest()[:20]

    def cached(self, kind, text):
        k = self.key_of(kind, text)
        if k in self.cache:
            self.used.add(k)
            return self.cache[k]

    def store(self, kind, text, out):
        k = self.key_of(kind, text)
        self.cache[k] = out
        self.used.add(k)

    def ask(self, system, user, max_tokens=32000):
        if not self.key:
            raise RuntimeError("no OPENROUTER_TRANSLATE_KEY")
        body = json.dumps({"model": MODEL, "temperature": 0.2, "max_tokens": max_tokens,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
        for attempt in range(6):
            req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", body, {
                "Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                "X-Title": "DMM site translations"})
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    data = json.load(r)
                self.sent += 1
                choice = data["choices"][0]
                # an empty or cut-off reply fails this piece only (the caller's checks reject ""), not the run
                if choice.get("finish_reason") == "length" or not choice["message"].get("content"):
                    return ""
                return choice["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code in (401, 402, 403):  # bad key or the monthly limit: no point retrying
                    self.api_error = f"OpenRouter {e.code}: {e.read()[:300]!r}"
                    raise RuntimeError(self.api_error)
                time.sleep(min(60, 2 ** attempt * 3))
            except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError):
                time.sleep(min(60, 2 ** attempt * 3))
        self.api_error = "OpenRouter kept failing"
        raise RuntimeError(self.api_error)

    def save(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        keep = {k: v for k, v in self.cache.items() if k in self.used}  # drop what no page uses any more
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False, indent=0, sort_keys=True)
            f.write("\n")


def unfence(s):
    s = s.strip("\n")
    m = re.fullmatch(r"```[a-z]*\n(.*)\n```", s.strip(), re.S)
    return m.group(1) if m else s


# ---------------------------------------------------------------- Markdown

FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def split_front_matter(text):
    m = re.match(r"---\n(.*?\n)---\n", text, re.S)
    return (m.group(1), text[m.end():]) if m else ("", text)


def protect_code(chunk):
    """Fenced code blocks become ⟦Cn⟧ lines; the model never sees them."""
    lines, out, blocks, i = chunk.split("\n"), [], [], 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            out.append(lines[i]); i += 1; continue
        indent, fence, j = m.group(1), m.group(2), i + 1
        while j < len(lines) and not re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", lines[j]):
            j += 1
        blocks.append("\n".join(lines[i:j + 1]))
        out.append(f"{indent}⟦C{len(blocks) - 1}⟧")
        i = j + 1
    return "\n".join(out), blocks


def restore_code(text, blocks):
    for n, block in enumerate(blocks):
        text = re.sub(rf"^[^\n]*⟦C{n}⟧[^\n]*$", lambda _: block, text, count=1, flags=re.M)
    return text


def sections(body):
    """Split at headings outside code, then cut long sections at blank lines (outside code and tables)."""
    lines, parts, cur, fence = body.split("\n"), [], [], None
    for line in lines:
        m = FENCE.match(line)
        if fence is None and m:
            fence = m.group(2)[0]
        elif fence and re.match(rf"^\s*{re.escape(fence)}{{3,}}\s*$", line):
            fence = None
        elif fence is None and HEADING.match(line) and cur:
            parts.append(cur); cur = []
        cur.append(line)
    parts.append(cur)
    out = []
    for p in parts:
        piece, words, fence = [], 0, None
        for line in p:
            m = FENCE.match(line)
            if fence is None and m:
                fence = m.group(2)[0]
            elif fence and re.match(rf"^\s*{re.escape(fence)}{{3,}}\s*$", line):
                fence = None
            if fence is None and line.strip() == "" and words > 1200 and not (piece and piece[-1].lstrip().startswith("|")):
                out.append("\n".join(piece)); piece, words = [], 0
            piece.append(line); words += len(line.split())
        out.append("\n".join(piece))
    return out


def retype_slug(heading, seen):
    t = re.sub(r"\s*\{[#.][^}]*\}\s*$", "", heading)
    t = re.sub(r"\[!\w+[^\]]*\]", "", t)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = t.replace("`", "").replace("*", "").lower().strip()
    t = re.sub(r"[^\w\s-]", "", t).replace(" ", "-")
    n = seen.get(t, 0)
    seen[t] = n + 1
    return t if n == 0 else f"{t}-{n}"


CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")


def shape(text):
    """What a translation must keep: headings, tables, Retype markers, code spans, link targets, placeholders."""
    lines = text.split("\n")
    return {
        "headings": [HEADING.match(l).group(1) for l in lines if HEADING.match(l)],
        "table rows": [len(re.findall(r"(?<!\\)\|", CODE_SPAN.sub("", l))) for l in lines if l.lstrip().startswith("|")],
        "markers": [l.strip()[:3] for l in lines if l.strip()[:3] in ("+++", "===", "!!!")],
        "code spans": sorted(m.group(0) for m in CODE_SPAN.finditer(text)),
        "link targets": sorted(re.findall(r"\]\(([^)\s]+)", text)),
        "placeholders": sorted(re.findall(r"⟦C\d+⟧", text)),
    }


def check(src, out):
    if not out.strip():
        return "empty reply"
    ratio = len(out) / max(1, len(src))
    if not 0.2 < ratio < 4:
        return f"length ratio {ratio:.2f}"
    a, b = shape(src), shape(out)
    for k in a:
        if k == "code spans":  # every span must survive; an extra pair of backticks around a name is harmless
            missing = collections.Counter(a[k]) - collections.Counter(b[k])
            if missing:
                return f"code spans differ ({next(iter(missing))[:40]})"
        elif a[k] != b[k]:
            return f"{k} differ"


def family_link(url, lang):
    """Point a link at another family site to the same page in this language."""
    m = re.match(r"https://(" + "|".join(map(re.escape, FAMILY)) + r")(/[^\s)\"'#?]*)?(.*)$", url)
    if not m:
        return url
    path = m.group(2) or "/"
    last = path.rsplit("/", 1)[-1]
    if "." in last and not last.endswith(".html"):
        return url  # a file, not a page
    if re.match(rf"^/({'|'.join(LANGS)})(/|$)", path):
        return url
    return f"https://{m.group(1)}/{lang}{path}{m.group(3)}"


def translate_md_chunk(tr, chunk):
    if not re.search(r"[A-Za-z]", re.sub(r"`[^`]*`", "", protect_code(chunk)[0])):
        return chunk
    hit = tr.cached("md", chunk)
    if hit is not None:
        return hit
    masked, blocks = protect_code(chunk)
    system, user, err = RULES.format(lang=tr.name), masked, None
    for _ in range(3):
        if not tr.key:
            break
        try:
            out = unfence(tr.ask(system, user))
        except RuntimeError as e:
            err = str(e); break
        err = check(masked, out)
        if not err:
            lead, trail = chunk[:len(chunk) - len(chunk.lstrip("\n"))], chunk[len(chunk.rstrip("\n")):]
            out = lead + restore_code(out.strip("\n"), blocks) + trail
            tr.store("md", chunk, out)
            return out
        user = f"{masked}\n\n(An earlier translation was rejected: {err}. Keep the structure exactly.)"
    if tr.key:
        tr.failed += 1
        print(f"  [{tr.lang}] left English: {err}: {chunk.strip()[:70]!r}", file=sys.stderr)
    return None


def translate_strings(tr, kind, strings, rules):
    """Short strings (front matter, nav labels, HTML fragments), in batches as a JSON array."""
    todo = [s for s in dict.fromkeys(strings) if tr.cached(kind, s) is None]
    batches = [todo[i:i + 40] for i in range(0, len(todo), 40)] if tr.key else []
    with cf.ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda batch: translate_batch(tr, kind, batch, rules), batches))
    for s in todo:
        if tr.cached(kind, s) is None and tr.key:
            tr.failed += 1
            print(f"  [{tr.lang}] left English: {s[:70]!r}", file=sys.stderr)
    return {s: (tr.cached(kind, s) or s) for s in strings}


def translate_batch(tr, kind, batch, rules):
    for attempt in range(3):
        try:
            out = json.loads(unfence(tr.ask(rules.format(lang=tr.name), json.dumps(batch, ensure_ascii=False))))
        except RuntimeError:
            break
        except ValueError:  # not JSON: ask again
            continue
        if isinstance(out, list) and len(out) == len(batch) and all(isinstance(x, str) for x in out):
            for s, t in zip(batch, out):
                if kind != "html" or html_shape(s) == html_shape(t):
                    tr.store(kind, s, t)
            break


FM_KEYS = ("label", "title", "description")
LABEL_RULES = RULES + """

You get a JSON array of short texts (page titles, headings, menu labels). Reply with a JSON array of their \
translations, same length and order. Keep any backticks, Markdown links and {{#id}} or [!badge] parts as they are."""


def md_page(tr, text):
    fm, body = split_front_matter(text)
    if fm:
        unquote = lambda v: v[1:-1] if len(v) > 1 and v[0] == v[-1] and v[0] in "'\"" else v
        vals = [unquote(m.group(2).strip()) for m in re.finditer(rf"^({'|'.join(FM_KEYS)}):\s*(.+)$", fm, re.M)]
        done = translate_strings(tr, "fm", vals, LABEL_RULES)
        # always quoted: a translated label often gains a colon, which breaks unquoted YAML
        fm = re.sub(rf"^({'|'.join(FM_KEYS)}):\s*(.+)$", lambda m: f"{m.group(1)}: " + json.dumps(done.get(unquote(m.group(2).strip()), unquote(m.group(2).strip())), ensure_ascii=False), fm, flags=re.M)
    # A section starts with its heading. Headings go as short strings of their own (a model sometimes drops
    # the heading of a section that is all table) and come back with the English anchor, so #links still land.
    heads, rests = [], []
    for c in sections(body):
        first, _, rest = c.partition("\n")
        m = HEADING.match(first)
        heads.append(m if m else None)
        rests.append(rest if m else c)
    titles = translate_strings(tr, "heading", [m.group(2) for m in heads if m], LABEL_RULES)
    with cf.ThreadPoolExecutor(6) as ex:
        outs = list(ex.map(lambda c: translate_md_chunk(tr, c), rests))
    seen, result = {}, []
    for m, src, out in zip(heads, rests, outs):
        if m:
            hid = retype_slug(m.group(2), seen)
            title = titles.get(m.group(2), m.group(2))
            result.append(f"{m.group(1)} {title}" + ("" if title == m.group(2) or re.search(r"\{#[^}]*\}\s*$", title) else f" {{#{hid}}}"))
        text = src if out is None else out
        masked, blocks = protect_code(text)
        masked = re.sub(r"(\]\()([^)\s]+)", lambda x: x.group(1) + family_link(x.group(2), tr.lang), masked)
        result.append(restore_code(masked, blocks))
    return (f"---\n{fm}---\n" if fm else "") + "\n".join(result)


def run_md(src, out, langs):
    files = sorted(os.path.relpath(os.path.join(d, f), src) for d, ds, fs in os.walk(src)
                   for f in fs if f.endswith(".md") and f != "README.md"
                   if not re.match(rf"(node_modules|\.retype[^/]*|\.git|i18n|{re.escape(os.path.relpath(out, src))})(/|$)", os.path.relpath(d, src)))
    skip = rf"(node_modules|\.retype[^/]*|\.git|\.github|i18n|{re.escape(os.path.relpath(out, src))})(/|$)"
    others = sorted(os.path.relpath(os.path.join(d, f), src) for d, ds, fs in os.walk(src) for f in fs
                    if os.path.relpath(d, src) != "." and not f.endswith(".md") and not re.match(skip, os.path.relpath(d, src)))

    def one(lang):
        tr = Translator(lang)
        dest = os.path.join(out, lang)
        shutil.rmtree(dest, ignore_errors=True)
        with cf.ThreadPoolExecutor(3) as ex:
            pages = list(ex.map(lambda rel: md_page(tr, open(os.path.join(src, rel), encoding="utf-8").read()), files))
        for rel, page in zip(files, pages):
            os.makedirs(os.path.dirname(os.path.join(dest, rel)) or dest, exist_ok=True)
            open(os.path.join(dest, rel), "w", encoding="utf-8").write(page)
        for rel in others:  # images, includes, data files the pages link to
            os.makedirs(os.path.dirname(os.path.join(dest, rel)), exist_ok=True)
            shutil.copy2(os.path.join(src, rel), os.path.join(dest, rel))
        write_retype_yml(tr, src, dest)
        tr.save()
        print(f"{lang}: {len(files)} pages, {tr.sent} requests, {tr.failed} left English", file=sys.stderr)
        return tr
    with cf.ThreadPoolExecutor(len(langs) or 1) as ex:
        return list(ex.map(one, langs))


def lang_menu(current, link):
    items = "".join(f"\n      - text: {n}\n        link: {link(c)}" for c, n in [ENGLISH] + [(c, v[1]) for c, v in LANGS.items()] if c != current)
    name = dict([ENGLISH] + [(c, v[1]) for c, v in LANGS.items()])[current]
    return f"\n  - text: {name}\n    icon: globe\n    items:{items}\n"


MENU = re.compile(r"\n  - text: [^\n]+\n    icon: globe\n    items:(\n      - text: [^\n]+\n        link: [^\n]+)+\n")


def write_retype_yml(tr, src, dest):
    y = MENU.sub("\n", open(os.path.join(src, "retype.yml"), encoding="utf-8").read())
    texts = re.findall(r"^\s*- text:\s*(.+)$", y, re.M)
    done = translate_strings(tr, "fm", texts, LABEL_RULES)
    y = re.sub(r"^(\s*- text:\s*)(.+)$", lambda m: m.group(1) + done.get(m.group(2), m.group(2)), y, flags=re.M)
    y = re.sub(r"^(\s*link:\s*)(\S+)", lambda m: m.group(1) + family_link(m.group(2), tr.lang), y, flags=re.M)
    url = re.search(r"^url:\s*(\S+)", y, re.M).group(1).rstrip("/")
    y = re.sub(r"^url:.*$", f"url: {url}/{tr.lang}", y, flags=re.M)
    y = re.sub(r"^output:.*$", f"output: .retype-{tr.lang}", y, flags=re.M)
    y = re.sub(r"^locale:.*\n", "", y, flags=re.M) + f"locale: {tr.lang}\n"
    y = re.sub(r"^links:\n", "links:" + lang_menu(tr.lang, lambda c: f"{url}/{'' if c == 'en' else c + '/'}#lang") + "\n", y, count=1, flags=re.M)
    open(os.path.join(dest, "retype.yml"), "w", encoding="utf-8").write(y)


# ---------------------------------------------------------------- HTML

INLINE = {"a", "abbr", "b", "br", "code", "em", "i", "img", "kbd", "mark", "s", "small", "span", "strong", "sub", "sup", "time", "u", "wbr", "svg", "path"}
SKIP = {"script", "style", "pre", "noscript", "template", "textarea", "svg"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
ATTRS = ("title", "alt", "aria-label", "placeholder")
META = re.compile(r"^(description|og:title|og:description|twitter:title|twitter:description|og:image:alt|twitter:image:alt)$")


def html_shape(s):
    return (re.findall(r"</?([a-zA-Z0-9]+)", s), sorted(re.findall(r'(?:href|src)="([^"]*)"', s)),
            sorted(re.findall(r"<code>(.*?)</code>", s, re.S)))


class Segments(HTMLParser):
    """Finds the text blocks to translate as character ranges, so everything else stays byte for byte."""
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.text, self.starts, self.stack, self.blocks, self.attrs, self.skip = text, [0], [], [], [], 0
        for line in text.split("\n"):
            self.starts.append(self.starts[-1] + len(line) + 1)
        self.feed(text); self.close()

    def at(self):
        line, col = self.getpos()
        return self.starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self.at()
        end = start + len(self.get_starttag_text())
        a = dict(attrs)
        if tag == "meta" and META.match(a.get("name") or a.get("property") or "") and a.get("content"):
            self.attrs.append((start, end, "content"))
        for k in ATTRS:
            if a.get(k) and re.search(r"[A-Za-z]", a[k]):
                self.attrs.append((start, end, k))
        if tag in VOID:
            return
        if self.stack and tag not in INLINE:
            self.stack[-1]["leaf"] = False
        if tag in SKIP:
            self.skip += 1
        self.stack.append({"tag": tag, "inner": end, "leaf": True, "text": False, "kids": []})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in VOID or not any(e["tag"] == tag for e in self.stack):
            return
        while self.stack:
            e = self.stack.pop()
            if e["tag"] in SKIP:
                self.skip -= 1
            if e["tag"] == tag:
                break
        if e["leaf"] and e["text"] and e["tag"] not in INLINE and e["tag"] not in SKIP and not self.skip:
            self.blocks.append((e["inner"], self.at()))
        elif not e["leaf"] and not self.skip:
            self.blocks += e["kids"]  # a link or span with text sitting beside blocks is a piece of its own
        if e["text"] and self.stack and e["tag"] in INLINE and e["tag"] not in SKIP:
            self.stack[-1]["kids"].append((e["inner"], self.at()))
        if e["text"] and self.stack:
            self.stack[-1]["text"] = True
            if e["tag"] not in INLINE:
                self.stack[-1]["leaf"] = False

    def handle_data(self, data):
        if self.stack and not self.skip and re.search(r"[A-Za-z]", data):
            self.stack[-1]["text"] = True


def page_link(value, page, lang):
    """Rewrite one href/src on a translated page: pages move under /<lang>/, files stay where they are."""
    if re.match(r"^(#|mailto:|javascript:|data:|tel:)", value):
        return value
    if re.match(r"^https?://", value):
        return family_link(value, lang)
    if not value.startswith("/"):
        joined = posixpath.normpath(posixpath.join(posixpath.dirname("/" + page), value))
        value = joined + ("/" if value.endswith("/") and not joined.endswith("/") else "")
    path = re.split(r"[?#]", value)[0]
    last = path.rsplit("/", 1)[-1]
    if path.endswith("/") or last.endswith(".html") or "." not in last:
        return f"/{lang}{value}"
    return value


def lang_bar(page, host):
    url = "/" + re.sub(r"(^|/)index\.html$", r"\1", page)
    links = " · ".join(f'<a href="{"" if c == "en" else "/" + c}{url}" hreflang="{c}" lang="{c}">{n}</a>'
                       for c, n in [ENGLISH] + [(c, v[1]) for c, v in LANGS.items()])
    alt = "".join(f'<link rel="alternate" hreflang="{c}" href="https://{host}{"" if c == "en" else "/" + c}{url}">'
                  for c in ["en"] + list(LANGS)) + f'<link rel="alternate" hreflang="x-default" href="https://{host}{url}">'
    bar = ('<nav class="i18n-langs" aria-label="Language" style="text-align:center;padding:18px 16px 28px;'
           f'font-size:13px;line-height:2;opacity:.75">{links}</nav>')
    style = ('<style>[dir=rtl] pre,[dir=rtl] code,[dir=rtl] .mono{direction:ltr;unicode-bidi:isolate}'
             '.i18n-langs a{color:inherit;white-space:nowrap}</style>')
    return alt + style, bar


def html_page(tr, text, page, host):
    seg = Segments(text)
    blocks = [text[a:b] for a, b in seg.blocks]
    attrs = []
    for s, e, k in seg.attrs:
        if any(a <= s and e <= b for a, b in seg.blocks):
            continue  # inside a block: the model translates it with the block
        m = re.search(rf'\s{k}="([^"]*)"', text[s:e])
        if m:
            attrs.append((s + m.start(1), s + m.end(1)))
    done = translate_strings(tr, "html", blocks + [html.unescape(text[a:b]) for a, b in attrs], HTML_RULES) if tr else {}
    edits = [(a, b, done.get(text[a:b], text[a:b])) for a, b in seg.blocks]
    edits += [(a, b, html.escape(done.get(html.unescape(text[a:b]), html.unescape(text[a:b])), quote=True)) for a, b in attrs]
    out = text
    for a, b, new in sorted(edits, reverse=True):
        out = out[:a] + new + out[b:]
    if tr:
        out = re.sub(r'(\s(?:href|src)=")([^"]*)(")', lambda m: m.group(1) + page_link(m.group(2), page, tr.lang) + m.group(3), out)
        out = re.sub(r'(<meta[^>]+property="og:url"[^>]+content=")([^"]*)', lambda m: m.group(1) + family_link(m.group(2), tr.lang), out)
        out = re.sub(r"<html([^>]*?)\slang=\"en\"", lambda m: f'<html{m.group(1)} lang="{tr.lang}"' + (' dir="rtl"' if tr.lang == "ar" else ""), out, count=1)
    head, bar = lang_bar(page, host)
    out = out.replace("</head>", head + "</head>", 1)
    out = out.replace("</footer>", bar + "</footer>", 1) if "</footer>" in out else out.replace("</body>", bar + "</body>", 1)
    return out


def run_html(src, out, langs, host):
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(src, out)
    pages = sorted(os.path.relpath(os.path.join(d, f), src) for d, _, fs in os.walk(src) for f in fs if f.endswith(".html"))
    for p in pages:
        open(os.path.join(out, p), "w", encoding="utf-8").write(html_page(None, open(os.path.join(src, p), encoding="utf-8").read(), p, host))
    def one(lang):
        tr = Translator(lang)
        for p in pages:
            dest = os.path.join(out, lang, p)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "w", encoding="utf-8").write(html_page(tr, open(os.path.join(src, p), encoding="utf-8").read(), p, host))
        tr.save()
        print(f"{lang}: {len(pages)} pages, {tr.sent} requests, {tr.failed} left English", file=sys.stderr)
        return tr
    with cf.ThreadPoolExecutor(len(langs) or 1) as ex:
        return list(ex.map(one, langs))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["md", "html"])
    ap.add_argument("--src", default=".")
    ap.add_argument("--out", required=True)
    ap.add_argument("--host", help="html mode: the site's hostname, for hreflang links")
    ap.add_argument("--langs", default=",".join(LANGS))
    a = ap.parse_args()
    langs = [l for l in a.langs.split(",") if l]
    if not os.environ.get("OPENROUTER_TRANSLATE_KEY"):
        print("OPENROUTER_TRANSLATE_KEY is not set: using cached translations only", file=sys.stderr)
    done = run_md(a.src, a.out, langs) if a.mode == "md" else run_html(a.src, a.out, langs, a.host)
    errors = {t.api_error for t in done if t.api_error}
    if errors:
        print("OpenRouter failed:", "; ".join(errors), file=sys.stderr)
    sys.exit(4 if errors else 3 if any(t.failed for t in done) else 0)
