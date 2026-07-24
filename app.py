"""
Newznab-compliant indexer that proxies a searchable RSS feed.

It exposes a single /api endpoint that speaks the Newznab API dialect
(t=caps, t=search, t=tvsearch, t=movie, t=music, t=book) so it can be
added to Sonarr, Radarr, NZBHydra2, Jackett-consuming apps, etc. as a
custom/generic Newznab indexer.

Under the hood, every request is translated into a GET request against
your target RSS feed's own search endpoint, and the returned RSS items
are re-serialized into Newznab's XML attribute format.

Run:
    pip install -r requirements.txt
    python app.py

Then point your app at:
    http://<host>:5000/api?apikey=<APIKEY>&t=search&q=example
"""

import os
import time
import hashlib
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, format_datetime
from xml.sax.saxutils import escape

import requests
import xml.etree.ElementTree as ET
from flask import Flask, request, Response, render_template, jsonify

from config import (
    API_KEY,
    INDEXER_NAME,
    INDEXER_ID,
    RSS_SEARCH_URL_TEMPLATE,
    RSS_REQUEST_HEADERS,
    RSS_REQUEST_TIMEOUT,
    RSS_AUTH_TYPE,
    RSS_AUTH_USERNAME,
    RSS_AUTH_PASSWORD,
    RSS_AUTH_TOKEN,
    CATEGORY_MAP,
    DEFAULT_CATEGORY,
    FIELD_MAP,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("newznab-indexer")

app = Flask(__name__)

NEWZNAB_NS = "http://www.newznab.com/DTD/2010/feeds/attributes/"
ATOM_NS = "http://www.w3.org/2005/Atom"


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def check_api_key():
    key = request.args.get("apikey", "")
    if API_KEY and key != API_KEY:
        return False
    return True


def error_response(code, description, status=200):
    """Newznab-style <error> XML response."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<error code="{code}" description="{escape(description)}"/>'
    )
    return Response(xml, mimetype="application/xml", status=status)


# --------------------------------------------------------------------------
# caps
# --------------------------------------------------------------------------

def build_caps_response():
    category_entries = "\n".join(
        f'    <category id="{cid}" name="{escape(name)}"/>'
        for cid, name in CATEGORY_MAP.get("_display", [])
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server version="1.0" title="{escape(INDEXER_NAME)}" strapline="RSS-backed Newznab proxy"/>
  <limits max="100" default="50"/>
  <retention days="3000"/>
  <registration available="no" open="no"/>
  <searching>
    <search available="yes" supportedParams="q"/>
    <tv-search available="yes" supportedParams="q,season,ep,imdbid,tvdbid"/>
    <movie-search available="yes" supportedParams="q,imdbid"/>
    <music-search available="yes" supportedParams="q"/>
    <book-search available="yes" supportedParams="q"/>
  </searching>
  <categories>
{category_entries}
  </categories>
</caps>"""
    return Response(xml, mimetype="application/xml")


# --------------------------------------------------------------------------
# RSS fetch + parse
# --------------------------------------------------------------------------

def build_source_auth_and_headers():
    """Return (auth, extra_headers) for the upstream RSS request based on
    RSS_AUTH_TYPE."""
    auth = None
    extra_headers = {}

    if RSS_AUTH_TYPE == "basic":
        if RSS_AUTH_USERNAME or RSS_AUTH_PASSWORD:
            auth = (RSS_AUTH_USERNAME, RSS_AUTH_PASSWORD)
        else:
            log.warning(
                "RSS_AUTH_TYPE is 'basic' but RSS_AUTH_USERNAME/RSS_AUTH_PASSWORD "
                "are not set — requests to the upstream feed will likely 401."
            )
    elif RSS_AUTH_TYPE == "bearer":
        if RSS_AUTH_TOKEN:
            extra_headers["Authorization"] = f"Bearer {RSS_AUTH_TOKEN}"
        else:
            log.warning(
                "RSS_AUTH_TYPE is 'bearer' but RSS_AUTH_TOKEN is not set — "
                "requests to the upstream feed will likely fail."
            )
    # "none" (or anything else): no auth added, e.g. feeds with a key baked
    # into RSS_SEARCH_URL_TEMPLATE already.

    return auth, extra_headers


def fetch_source_rss(query, extra_params=None):
    url = RSS_SEARCH_URL_TEMPLATE.format(query=requests.utils.quote(query or ""))
    auth, extra_headers = build_source_auth_and_headers()
    headers = {**RSS_REQUEST_HEADERS, **extra_headers}
    try:
        resp = requests.get(
            url,
            headers=headers,
            auth=auth,
            timeout=RSS_REQUEST_TIMEOUT,
            params=extra_params or {},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Failed to fetch source RSS %s: %s", url, exc)
        return None
    return resp.content


def parse_source_items(rss_bytes):
    """Parse the upstream RSS into a list of normalized dicts."""
    items = []
    if not rss_bytes:
        return items

    try:
        root = ET.fromstring(rss_bytes)
    except ET.ParseError as exc:
        log.error("Could not parse upstream RSS: %s", exc)
        return items

    channel = root.find("channel")
    node_list = channel.findall("item") if channel is not None else root.findall(".//item")

    for item in node_list:
        def text(tag, default=""):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else default

        title = text(FIELD_MAP["title"])
        link = text(FIELD_MAP["link"])
        guid = text(FIELD_MAP["guid"]) or link or hashlib.sha1(title.encode()).hexdigest()
        pub_date_raw = text(FIELD_MAP["pubdate"])
        description = text(FIELD_MAP["description"])
        category_raw = text(FIELD_MAP["category"])

        # size: prefer <enclosure length="">, fall back to a custom field
        size = 0
        enclosure = item.find("enclosure")
        if enclosure is not None and enclosure.get("length"):
            try:
                size = int(enclosure.get("length"))
            except ValueError:
                size = 0
        if not size:
            size_text = text(FIELD_MAP.get("size", "size"))
            if size_text.isdigit():
                size = int(size_text)

        download_url = None
        if enclosure is not None and enclosure.get("url"):
            download_url = enclosure.get("url")
        else:
            download_url = link

        try:
            pub_dt = parsedate_to_datetime(pub_date_raw) if pub_date_raw else datetime.now(timezone.utc)
        except (TypeError, ValueError):
            pub_dt = datetime.now(timezone.utc)

        category_id = CATEGORY_MAP.get(category_raw.lower(), DEFAULT_CATEGORY)

        items.append(
            {
                "title": title or "Untitled",
                "guid": guid,
                "link": link,
                "download_url": download_url,
                "pub_date": pub_dt,
                "description": description,
                "size": size,
                "category_id": category_id,
            }
        )

    return items


# --------------------------------------------------------------------------
# Filtering helpers for tvsearch / movie params
# --------------------------------------------------------------------------

def apply_extra_filters(items, args):
    season = args.get("season")
    ep = args.get("ep")
    if season:
        needle = f"s{int(season):02d}" if season.isdigit() else season.lower()
        items = [i for i in items if needle.lower() in i["title"].lower()]
    if ep:
        needle = f"e{int(ep):02d}" if ep.isdigit() else ep.lower()
        items = [i for i in items if needle.lower() in i["title"].lower()]
    return items


# --------------------------------------------------------------------------
# Newznab XML rendering
# --------------------------------------------------------------------------

def render_newznab_rss(items, offset=0, total=None):
    total = total if total is not None else len(items)
    entries = []
    for it in items:
        pub_rfc822 = format_datetime(it["pub_date"])
        entries.append(
            f"""    <item>
      <title>{escape(it['title'])}</title>
      <guid isPermaLink="false">{escape(it['guid'])}</guid>
      <link>{escape(it['download_url'] or '')}</link>
      <comments>{escape(it['link'] or '')}</comments>
      <pubDate>{pub_rfc822}</pubDate>
      <category>{escape(str(it['category_id']))}</category>
      <description>{escape(it['description'])}</description>
      <enclosure url="{escape(it['download_url'] or '')}" length="{it['size']}" type="application/x-nzb"/>
      <newznab:attr name="category" value="{it['category_id']}"/>
      <newznab:attr name="size" value="{it['size']}"/>
      <newznab:attr name="guid" value="{escape(it['guid'])}"/>
    </item>"""
        )

    items_xml = "\n".join(entries)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:newznab="{NEWZNAB_NS}" xmlns:atom="{ATOM_NS}">
  <channel>
    <title>{escape(INDEXER_NAME)}</title>
    <description>Newznab-compliant proxy over a searchable RSS feed</description>
    <atom:link href="{escape(request.url)}" rel="self" type="application/rss+xml"/>
    <newznab:response offset="{offset}" total="{total}"/>
{items_xml}
  </channel>
</rss>"""
    return Response(xml, mimetype="application/rss+xml")


# --------------------------------------------------------------------------
# Route
# --------------------------------------------------------------------------

@app.route("/api", methods=["GET"])
def api():
    t = request.args.get("t", "search")

    if t == "caps":
        return build_caps_response()

    if not check_api_key():
        return error_response(100, "Incorrect user credentials", status=401)

    if t not in ("search", "tvsearch", "movie", "music", "book"):
        return error_response(202, f"Unsupported function: {t}")

    query = request.args.get("q", "")
    offset = int(request.args.get("offset", 0) or 0)
    limit = int(request.args.get("limit", 50) or 50)

    rss_bytes = fetch_source_rss(query)
    if rss_bytes is None:
        return error_response(500, "Failed to reach upstream RSS source", status=200)

    items = parse_source_items(rss_bytes)
    items = apply_extra_filters(items, request.args)

    if request.args.get("cat"):
        wanted = set(request.args["cat"].split(","))
        items = [i for i in items if str(i["category_id"]) in wanted]

    total = len(items)
    page = items[offset: offset + limit]

    return render_newznab_rss(page, offset=offset, total=total)


def masked_api_key():
    if not API_KEY:
        return "(disabled)"
    if len(API_KEY) <= 4:
        return "*" * len(API_KEY)
    return API_KEY[:2] + "*" * (len(API_KEY) - 4) + API_KEY[-2:]


@app.route("/", methods=["GET"])
def index():
    """Web GUI: status dashboard + live search tester."""
    if RSS_AUTH_TYPE == "basic":
        auth_status = f"Basic Auth (user: {RSS_AUTH_USERNAME or '(not set)'})"
    elif RSS_AUTH_TYPE == "bearer":
        auth_status = "Bearer token" if RSS_AUTH_TOKEN else "Bearer (token not set)"
    else:
        auth_status = "None"

    return render_template(
        "index.html",
        indexer_name=INDEXER_NAME,
        indexer_id=INDEXER_ID,
        api_key_masked=masked_api_key(),
        api_key_for_test_form=API_KEY,
        rss_template=RSS_SEARCH_URL_TEMPLATE,
        rss_auth_status=auth_status,
        auth_enabled=bool(API_KEY),
    )


@app.route("/health", methods=["GET"])
def health():
    """Lightweight liveness endpoint for Docker HEALTHCHECK."""
    return jsonify(status="ok", indexer=INDEXER_NAME), 200


@app.route("/api/info", methods=["GET"])
def info():
    """Machine-readable info, formerly served at '/'."""
    return jsonify(
        name=INDEXER_NAME,
        id=INDEXER_ID,
        api="/api",
        caps="/api?t=caps",
        example_search="/api?t=search&q=example&apikey=YOUR_KEY",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
