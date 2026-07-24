# Newznab-Compliant RSS Indexer

A lightweight Flask service that wraps any **searchable RSS feed** and
exposes it as a **Newznab-compliant API**, so it can be added to apps
that expect a Newznab indexer (Sonarr, Radarr, NZBHydra2, Lidarr,
custom Jackett-style integrations, etc.).

## How it works

```
Client (Sonarr/Radarr/etc.)
      |
      |  GET /api?t=search&q=foo&apikey=...
      v
This Flask app
      |
      |  GET https://your-source.example/rss?q=foo
      v
Your searchable RSS feed
      |
      v
RSS <item> elements --> converted into Newznab <item> + <newznab:attr> XML
      |
      v
Response returned to client
```

## Running with Docker

```bash
docker build -t newznab-rss-indexer .
docker run -d \
  --name newznab-rss-indexer \
  -p 5000:5000 \
  -e INDEXER_NAME="My RSS Indexer" \
  -e INDEXER_API_KEY="changeme" \
  -e RSS_SEARCH_URL_TEMPLATE="https://example.com/rss?q={query}" \
  -v $(pwd)/config:/config \
  newznab-rss-indexer
```

Or with `docker-compose.yml` (edit the `environment:` block first):

```bash
docker compose up -d
```

Open `http://<host>:5000` for the web GUI.

**Config without rebuilding:** drop a `config.py` into the mounted
`/config` volume (i.e. `./config/config.py` on the host) to override any
setting from `config.py` — useful for things env vars don't cover, like
`FIELD_MAP` or the full `CATEGORY_MAP`. It's loaded automatically on
startup if present.

## Running on Unraid

1. Push the image to a registry Unraid can pull from (Docker Hub, GHCR,
   etc.) — `unraid-template.xml` assumes Docker Hub:

   ```bash
   docker build -t yourdockerhubuser/newznab-rss-indexer:latest .
   docker push yourdockerhubuser/newznab-rss-indexer:latest
   ```

2. Edit `unraid-template.xml`: replace `yourdockerhubuser`, the
   `Support`/`Project` URLs, and the `Icon` URL with your own.

3. In Unraid: **Docker → Add Container → Template repositories**, add
   the raw URL to your `unraid-template.xml` (e.g. hosted on GitHub), or
   for a one-off local install, copy it to
   `/boot/config/plugins/dockerMan/templates-user/` on the Unraid box
   and it'll show up under **Add Container → select a template**.

4. Fill in the API key and RSS search URL fields in the Unraid GUI, apply,
   and the **WebUI** button on the container's card will open the
   dashboard at `http://<unraid-ip>:5000`.

## Setup (running directly with Python)

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Edit `config.py`:
   - `API_KEY` — the key clients must supply (`?apikey=...`)
   - `RSS_SEARCH_URL_TEMPLATE` — your feed's search URL, with `{query}`
     as a placeholder for the URL-encoded search term
   - `FIELD_MAP` — only needed if your feed's `<item>` uses non-standard
     child tag names (default assumes standard RSS: `title`, `link`,
     `guid`, `pubDate`, `description`, `category`)
   - `CATEGORY_MAP` — maps your feed's category text to Newznab category
     IDs (2000=Movies, 3000=Audio, 5000=TV, 7000=Books, 8000=Other)

3. Run it:

   ```bash
   python app.py
   ```

   By default it listens on `http://0.0.0.0:5000`.

4. Add it to your client app as a "Newznab" indexer:
   - URL: `http://<host>:5000`
   - API path: `/api`
   - API key: whatever you set in `config.py`

## Supported Newznab operations

| `t` value    | Purpose                          |
|--------------|-----------------------------------|
| `caps`       | Capabilities discovery            |
| `search`     | General search (`q`)              |
| `tvsearch`   | TV search (`q`, `season`, `ep`)   |
| `movie`      | Movie search (`q`, `imdbid` passthrough) |
| `music`      | Music search (`q`)                |
| `book`       | Book search (`q`)                 |

Also supported: `offset`, `limit`, `cat` (comma-separated Newznab
category IDs to filter results by, matched against `CATEGORY_MAP`).

## Notes & things you'll likely need to adjust

- **Size**: pulled from `<enclosure length="...">` on the source item
  if present, otherwise falls back to a `size` field in `FIELD_MAP`.
  If your feed has no size info at all, results will show `size=0`.
- **Season/episode filtering**: done client-side by substring-matching
  `S01`/`E02`-style patterns in the title, since most RSS feeds don't
  support structured season/episode query params. If your source feed
  *does* support them, pass them through in `fetch_source_rss()`
  instead for more accurate results.
- **imdbid/tvdbid**: declared in `caps` for compatibility but not
  currently forwarded to the upstream feed — wire this up in
  `fetch_source_rss()` if your source feed can filter by them.
- **Authentication to the source feed**: if your RSS feed needs an API
  key or auth header, add it to `RSS_REQUEST_HEADERS` or as a query
  param in `RSS_SEARCH_URL_TEMPLATE`.
- This is unauthenticated beyond the single shared `apikey` — put it
  behind a reverse proxy with HTTPS if exposing it outside localhost.

## Testing it manually

```bash
curl "http://localhost:5000/api?t=caps"
curl "http://localhost:5000/api?t=search&q=example&apikey=changeme"
```
