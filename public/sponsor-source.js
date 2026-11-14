// Sponsor links say which page sent the reader and where the reader came from (an AI answer, a search),
// so gatekeeper can stamp it on the purchase. Kept in this browser only, for 30 days. Same logic as notes' head.html.
(function () {
  var KEY = "dmm_via", DAY = 864e5, own = /(^|\.)debridmediamanager\.com$/;
  try {
    var utm = new URLSearchParams(location.search).get("utm_source");
    var host = document.referrer && new URL(document.referrer).hostname;
    var via = utm || (host && !own.test(host) ? host : "");
    var stored = JSON.parse(localStorage.getItem(KEY) || "null");
    if (via && (utm || !stored || Date.now() - stored.at > 30 * DAY)) localStorage.setItem(KEY, JSON.stringify({ via: via, at: Date.now() }));
  } catch (e) {}
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest('a[href^="https://gatekeeper.debridmediamanager.com"]');
    if (!a) return;
    var url = new URL(a.href);
    url.searchParams.set("ref", location.hostname.split(".")[0] + location.pathname.replace(/\.html$|\/$/, ""));
    try {
      var s = JSON.parse(localStorage.getItem(KEY) || "null");
      if (s && Date.now() - s.at <= 30 * DAY) url.searchParams.set("via", s.via);
    } catch (e) {}
    a.href = url.toString();
  }, true);
})();
