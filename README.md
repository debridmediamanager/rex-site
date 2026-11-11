# rex-site

Source for **[rex.debridmediamanager.com](https://rex.debridmediamanager.com/)**, the
landing page for rex.

One hand-written `public/index.html` on the shared `site.css` from
[zurg-site](https://github.com/debridmediamanager/zurg-site). No framework. `public/` is the
English site; what ships is `dist/`, which adds a translated copy under `/<lang>/` (see Translations).

- Copy uses no commas, colons or em dashes, names no competitors and keeps Plex mentions
  to what describes compatibility.
- Screenshots come from a demo rex holding only public-domain films and Blender open
  movies, through the official web app at 2x. Keep account names, tokens and private
  libraries out of images.
- Benchmark figures come from a recorded run on a dedicated box; keep the date and the
  library size beside them.
- The Setup and Limits sections summarise rex's `README.md`. They change with it and with
  `docs/setup.md` and the notes guides `rex/with-zurg.md` and `rex/any-source.md`, in
  the same task. rex's CLAUDE.md lists all five.

A push to `main` that touches `public/` deploys to Cloudflare Pages project `rex` and purges the edge
cache; `./deploy.sh` does the same by hand. Verify with a cache-busted URL
(`?cb=1`); the zone cache can keep the bare URL stale after a deploy.


## Translations

Write English only. Every push to `main` translates what changed into Chinese, Spanish, Arabic, Indonesian,
Portuguese, French, Japanese, Russian and German with `i18n/translate.py` (OpenRouter, repository secret
`OPENROUTER_TRANSLATE_KEY`) and publishes each language under `/<lang>/`. Translations are cached in
`i18n/cache/` by a hash of the English text, so only changed text costs anything; the workflow commits the cache
back as `chore: translations for …`. Do not edit the cache by hand: change the English and the next push
translates it again. Text whose translation fails the checks (code, links, tables or markup changed) is published in
English and tried again on the next push (a warning on the run). If OpenRouter fails (key, monthly limit) the run goes red. The same `translate.py` lives in notes, zurg-site and rex-site; change it in one and copy it
to the other two.

---

**More from DMM:** [Debrid Media Manager](https://debridmediamanager.com/) · [zurg](https://zurg.debridmediamanager.com/) · [rex](https://rex.debridmediamanager.com/) · [Docs](https://notes.debridmediamanager.com/) · [Sponsor](https://gatekeeper.debridmediamanager.com/) · [Discord](https://discord.com/invite/7u4YjMThXP) · [Reddit](https://www.reddit.com/r/debridmediamanager/)
