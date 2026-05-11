"""Tracking and analytics domain fragments. hrefs containing any of these are filtered out."""

TRACKING_FRAGMENTS: frozenset[str] = frozenset({
    # Google
    "google-analytics.com",
    "googletagmanager.com",
    "googleadservices.com",
    "googlesyndication.com",
    "doubleclick.net",
    "google.com/ads",
    # Meta
    "facebook.com/tr",
    "connect.facebook.net",
    "facebook.net/signals",
    # Microsoft
    "bing.com/action",
    "clarity.ms",
    "bat.bing.com",
    # Twitter/X
    "t.co/",
    "twitter.com/i/adsct",
    "ads-twitter.com",
    # Analytics
    "hotjar.com",
    "segment.com",
    "mixpanel.com",
    "amplitude.com",
    "heap.io",
    "fullstory.com",
    "logrocket.com",
    # Ads
    "adroll.com",
    "criteo.com",
    "taboola.com",
    "outbrain.com",
    "moatads.com",
    # Social pixels
    "snap.licdn.com",
    "analytics.twitter.com",
    "tiktok.com/i18n",
    "pinterest.com/ct",
    # CRMs / chat widgets (link-only, not interactive form elements)
    "intercom-attachments",
    "drift.com/track",
    # Common analytics paths
    "/ga.js",
    "/gtag/js",
    "/analytics.js",
    "/__utm",
    "/pixel",
})
