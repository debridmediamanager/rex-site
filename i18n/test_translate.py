#!/usr/bin/env python3
"""Offline checks for translate.py (no API calls): python3 i18n/test_translate.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translate as T

# Code blocks never reach the model and come back exactly, indentation included.
md = "Run this:\n\n  ```bash\n  zurg setup\n  # not a heading\n  ```\n\nDone."
masked, blocks = T.protect_code(md)
assert "zurg setup" not in masked and "⟦C0⟧" in masked
assert T.restore_code(masked.replace("Run this", "Führe das aus"), blocks) == md.replace("Run this", "Führe das aus")

# Sections split at headings outside code only.
assert len(T.sections("## A\ntext\n```\n## not a heading\n```\n## B\nmore")) == 2

# A translation must keep code spans, link targets, tables and Retype markers; extra backticks are fine.
src = "Use `zurg setup` and [docs](../setup.md).\n\n| a | b |\n|---|---|\n\n+++ Linux"
assert T.check(src, "Nutze `zurg setup` und [Doku](../setup.md).\n\n| a | b |\n|---|---|\n\n+++ Linux") is None
assert T.check(src, "Nutze `zurg setup` auf `zen` und [Doku](../setup.md).\n\n| a | b |\n|---|---|\n\n+++ Linux") is None
assert "code spans" in T.check(src, "Nutze zurg setup und [Doku](../setup.md).\n\n| a | b |\n|---|---|\n\n+++ Linux")
assert "link targets" in T.check(src, "Nutze `zurg setup` und [Doku](../einrichtung.md).\n\n| a | b |\n|---|---|\n\n+++ Linux")
assert "table rows" in T.check(src, "Nutze `zurg setup` und [Doku](../setup.md).\n\n| a |\n|---|\n\n+++ Linux")
assert T.check(src, "") == "empty reply"

# A reply in the wrong language is rejected, even with the right shape. Real cached replies: German on the
# Chinese and Japanese pages, Spanish on Indonesian ones, English left as it was, "I don't see any text",
# and single bad lines in good sections: German sentences, the model's own "Wait, that's not right".
# Right ones pass, including English names, bold UI labels and quoted error messages.
import json
cases = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "wrong_language.json"), encoding="utf-8"))
for c in cases:
    assert bool(T.check(c.get("src", c["text"]), c["text"], c["lang"])) == c["wrong"], (c["lang"], c["text"][:80])
# Japanese on a Chinese page and Spanish on an Indonesian one (real pairs with their English source above);
# an accented name the English already has is fine.
assert T.check("Play Pokémon", "Mainkan Pokémon sekarang", "id") is None
assert T.check("Watch in the Plex apps", "Ver en las apps de Plex", "id")  # a real zurg-site heading
assert T.check("Watch in the Plex apps", "Tonton di aplikasi Plex", "id") is None
# The model's own notes ("Wait, I should not wrap in a code fence"), its echo of our retry hint ("An earlier
# translation was rejected") and a code fence the English does not have are rejected, from the cache too.
assert "code fences" in T.check("Step one.\n\n⟦C0⟧\n\nDone.", "```\n第一步。\n```\n\n第一步。\n\n⟦C0⟧\n\n完成。", "zh")
assert T.check("How translations work", "Cara kerja terjemahan (translations)", "id") is None  # the English has it
note = next(c for c in cases if "Wait, I should not wrap" in c["text"])
tr = T.Translator(note["lang"]); tr.store("md", note["src"], note["text"])
assert tr.cached("md", note["src"]) is None
# Short replies are told by script: zurg-site's Japanese page showed "Kostenlos" for "Free". Kept names pass.
assert T.check("Free for everyone", "Kostenlos für alle", "ja") and T.check("Free", "Kostenlos", "zh")
assert T.check("Plex Media Server", "Plex Media Server", "ja") is None and T.check("Free", "無料", "ja") is None
# and a wrong reply already in the cache counts as a miss, so the next run asks again
tr = T.Translator("ja")
tr.store("html", "Free", "Kostenlos"); tr.store("html", "Docs", "ドキュメント"); tr.store("md", cases[0]["text"], cases[0]["text"])
assert tr.cached("html", "Free") is None and tr.cached("html", "Docs") == "ドキュメント" and tr.cached("md", cases[0]["text"]) is None

# Translated headings keep Retype's English anchors (checked against a real build: 1,362 of 1,362).
seen = {}
assert [T.retype_slug(h, seen) for h in ["Use `zurg setup` now!", "A & B / C", "Dup", "Dup"]] == \
    ["use-zurg-setup-now", "a--b--c", "dup", "dup-1"]

# Links: pages move under /<lang>/, files stay put, other family sites point at the same language.
assert T.page_link("download.html", "index.html", "de") == "/de/download.html"
assert T.page_link("../", "jellyfin/index.html", "de") == "/de/"
assert T.page_link("tb.png", "jellyfin/index.html", "de") == "/jellyfin/tb.png"
assert T.page_link("/site.css?v=1", "index.html", "de") == "/site.css?v=1"
assert T.page_link("#access", "index.html", "de") == "#access"
assert T.family_link("https://notes.debridmediamanager.com/zurg/setup/#docker", "ja") == "https://notes.debridmediamanager.com/ja/zurg/setup/#docker"
assert T.family_link("https://zurg.debridmediamanager.com/install.sh", "ja") == "https://zurg.debridmediamanager.com/install.sh"
assert T.family_link("https://gatekeeper.debridmediamanager.com/", "ja") == "https://gatekeeper.debridmediamanager.com/"

# HTML pieces: text blocks with their inline markup, loose links beside blocks, nothing from code or scripts.
page = ('<div><p>Read <code>config.yml</code> first</p><a href="/x">Loose link</a></div>'
        '<pre>keep me</pre><script>var s = "no thanks";</script><img alt="A screenshot of it" src="a.png">')
seg = T.Segments(page)
assert [page[a:b] for a, b in seg.blocks] == ["Read <code>config.yml</code> first", "Loose link"]
assert [k for _, _, k in seg.attrs] == ["alt"]
# Links point at the URL Pages serves: /x.html answers with a 308 to /x.
assert T.served_href("/download.html#linux") == "/download#linux"
assert T.served_href("../jellyfin/index.html") == "../jellyfin/"
assert T.served_href("android.html") == "android"
assert T.served_href("https://zurg.debridmediamanager.com/download.html") == "https://zurg.debridmediamanager.com/download"
assert T.served_href("https://example.com/a.html") == "https://example.com/a.html"
assert T.served_href("/install.sh") == "/install.sh" and T.served_href("#top") == "#top"
out = T.html_page(None, '<html lang="en"><head></head><body><a href="/download.html">x</a></body></html>', "index.html", "h")
assert 'href="/download"' in out and 'href="/download.html"' not in out
nf = T.html_page(None, "<html><head></head><body></body></html>", "404.html", "h")
assert "hreflang" not in nf.split("</head>")[0] and 'href="/de/"' in nf and "/404" not in nf

tr = T.Translator("pt"); tr.key = None  # offline: no API calls, cached text only
pt = T.html_page(tr, '<html lang="en"><head><meta property="og:type" content="website"></head><body></body></html>', "index.html", "h")
assert '<meta property="og:locale" content="pt_BR">' in pt and 'lang="pt"' in pt

# seo(): every page names its translations, one sitemap lists all of them, served URLs only (no .html).
import tempfile
with tempfile.TemporaryDirectory() as site:
    def put(rel, text):
        os.makedirs(os.path.dirname(os.path.join(site, rel)) or site, exist_ok=True)
        open(os.path.join(site, rel), "w").write(text)
    page = "<html><head><title>x</title></head><body>x</body></html>"
    for rel in ("index.html", "download.html", "de/index.html", "de/download.html", "ja/index.html"):
        put(rel, page)
    put("old.html", '<html><head><meta http-equiv="refresh" content="0; url=/"></head></html>')
    T.seo(site, "example.org", ["de", "ja"])
    sm = open(os.path.join(site, "sitemap.xml")).read()
    assert sm.count("<loc>") == 5 and "download.html" not in sm and "old" not in sm
    assert '<loc>https://example.org/de/download</loc>' in sm
    head = open(os.path.join(site, "ja/index.html")).read()
    assert 'hreflang="de" href="https://example.org/de/"' in head and 'hreflang="x-default"' in head
    assert 'hreflang="ja"' not in open(os.path.join(site, "download.html")).read()  # no Japanese download page
    assert "Sitemap: https://example.org/sitemap.xml" in open(os.path.join(site, "robots.txt")).read()

print("translate.py: all checks pass")
