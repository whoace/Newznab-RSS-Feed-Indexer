"""
Configuration for the Newznab-compliant RSS-backed indexer.

Edit the values below to match your API key preference and the
searchable RSS feed you're wrapping.
"""

import os
import json

# --------------------------------------------------------------------------
# Everything below can be overridden with environment variables, which is
# the primary way to configure this app when running under Docker/Unraid.
# For settings with no simple env equivalent (FIELD_MAP, full CATEGORY_MAP),
# either edit this file directly and rebuild the image, or bind-mount your
# own config.py over /app/config.py in the container.
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Indexer identity
# --------------------------------------------------------------------------

INDEXER_NAME = os.environ.get("INDEXER_NAME", "My RSS Indexer")
INDEXER_ID = os.environ.get("INDEXER_ID", "myrssindexer")

# Clients must pass ?apikey=<this value>. Leave as "" to disable auth
# (not recommended if this is exposed beyond localhost).
API_KEY = os.environ.get("INDEXER_API_KEY", "changeme")

# --------------------------------------------------------------------------
# Upstream searchable RSS feed
# --------------------------------------------------------------------------
# {query} is replaced with the URL-encoded search term. Adjust the query
# string to match whatever search parameter your RSS source expects
# (commonly "q", "search", "query", "term", etc.)
RSS_SEARCH_URL_TEMPLATE = os.environ.get(
    "RSS_SEARCH_URL_TEMPLATE",
    "https://members.easynews.com/1.0/global5/index.html?&sbj={query}&sS=5",
)

RSS_REQUEST_HEADERS = {
    "User-Agent": "newznab-rss-indexer/1.0",
}

RSS_REQUEST_TIMEOUT = 15  # seconds

# --------------------------------------------------------------------------
# Upstream feed authentication
# --------------------------------------------------------------------------
# RSS_AUTH_TYPE: "none" | "basic" | "bearer"
#   - "basic":  sends RSS_AUTH_USERNAME / RSS_AUTH_PASSWORD as HTTP Basic
#               Auth. This is what Easynews' classic search endpoint
#               (members.easynews.com) expects — use your Easynews member
#               username/password.
#   - "bearer": sends "Authorization: Bearer <RSS_AUTH_TOKEN>"
#   - "none":   no auth added (some feeds embed a key/passkey directly in
#               RSS_SEARCH_URL_TEMPLATE instead, which needs no extra config)
RSS_AUTH_TYPE = os.environ.get("RSS_AUTH_TYPE", "basic")
RSS_AUTH_USERNAME = os.environ.get("RSS_AUTH_USERNAME", "")
RSS_AUTH_PASSWORD = os.environ.get("RSS_AUTH_PASSWORD", "")
RSS_AUTH_TOKEN = os.environ.get("RSS_AUTH_TOKEN", "")

# --------------------------------------------------------------------------
# Field mapping: RSS <item> child-tag names in the SOURCE feed.
# Change these if your source feed uses non-standard tag names
# (e.g. a custom "size" or "category" element).
# --------------------------------------------------------------------------
FIELD_MAP = {
    "title": "title",
    "link": "link",
    "guid": "guid",
    "pubdate": "pubDate",
    "description": "description",
    "category": "category",
    "size": "size",  # only used as a fallback if <enclosure length=""> is absent
}

# --------------------------------------------------------------------------
# Category mapping: source feed category text (lowercased) -> Newznab
# category ID. Newznab's standard numbering is roughly:
#   2000 Movies, 3000 Audio, 5000 TV, 6000 XXX, 7000 Books, 8000 Other
# See https://newznab.readthedocs.io/en/latest/misc/api/#predefined-categories
# --------------------------------------------------------------------------
CATEGORY_MAP = {
    "movie": 2000,
    "movies": 2000,
    "tv": 5000,
    "television": 5000,
    "music": 3000,
    "audio": 3000,
    "book": 7000,
    "books": 7000,
    "ebook": 7030,
    # Used to render the <categories> block in the caps response.
    "_display": [
        (2000, "Movies"),
        (3000, "Audio"),
        (5000, "TV"),
        (7000, "Books"),
        (8000, "Other"),
    ],
}

DEFAULT_CATEGORY = 8000  # "Other" — used when no category mapping matches

# Optional: override/extend CATEGORY_MAP entirely via an env var containing
# JSON, e.g. INDEXER_CATEGORY_MAP_JSON='{"anime": 5070, "documentary": 5080}'
# Values are merged on top of the defaults above (the "_display" key is
# left untouched unless you also include it in your JSON).
_extra_categories = os.environ.get("INDEXER_CATEGORY_MAP_JSON")
if _extra_categories:
    try:
        CATEGORY_MAP.update(json.loads(_extra_categories))
    except (json.JSONDecodeError, TypeError):
        pass

# --------------------------------------------------------------------------
# Optional override file. If present, its contents are executed after
# everything above, so it can freely reassign any variable in this module
# (RSS_SEARCH_URL_TEMPLATE, FIELD_MAP, CATEGORY_MAP, etc.) without needing
# to rebuild the Docker image. In the Docker image this defaults to
# /config/config.py, which lines up with the persistent /config volume.
# --------------------------------------------------------------------------
_override_path = os.environ.get("CONFIG_OVERRIDE_PATH", "/config/config.py")
if os.path.exists(_override_path):
    with open(_override_path) as _f:
        exec(compile(_f.read(), _override_path, "exec"), globals())
