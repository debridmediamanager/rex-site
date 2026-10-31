# rex-site

Source for **[rex.debridmediamanager.com](https://rex.debridmediamanager.com/)**, the
landing page for rex.

One hand-written `public/index.html` on the shared `site.css` from
[zurg-site](https://github.com/debridmediamanager/zurg-site). No framework and no build
step. `public/` holds exactly what ships.

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

`./deploy.sh` publishes Cloudflare Pages project `rex`. Verify with a cache-busted URL
(`?cb=1`); the zone cache can keep the bare URL stale after a deploy.

---

**More from DMM:** [Debrid Media Manager](https://debridmediamanager.com/) · [zurg](https://zurg.debridmediamanager.com/) · [rex](https://rex.debridmediamanager.com/) · [Docs](https://notes.debridmediamanager.com/) · [Sponsor](https://gatekeeper.debridmediamanager.com/) · [Discord](https://discord.com/invite/7u4YjMThXP) · [Reddit](https://www.reddit.com/r/debridmediamanager/)
