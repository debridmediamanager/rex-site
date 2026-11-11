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
print("translate.py: all checks pass")
