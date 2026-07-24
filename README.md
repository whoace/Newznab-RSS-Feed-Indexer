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
docker build -t whoace/rssindexer:latest .
docker run -d \
  --name newznab-rss-indexer \
  -p 5000:5000 \
  -e INDEXER_NAME="My RSS Indexer" \
  -e INDEXER_API_KEY="changeme" \
  -e RSS_SEARCH_URL_TEMPLATE="https://members.easynews.com/1.0/global5/index.html?&sbj={query}&sS=5" \
  -e RSS_AUTH_TYPE=basic \
  -e RSS_AUTH_USERNAME="your-easynews-username" \
  -e RSS_AUTH_PASSWORD="your-easynews-password" \
  -v $(pwd)/config:/config \
  whoace/rssindexer:latest
```

Or with `docker-compose.yml` (already points at `whoace/rssindexer:latest`;
edit the `environment:` block for your credentials first):

```bash
docker compose up -d
```

Open `http://<host>:5000` for the web GUI.

## Publishing to Docker Hub

```bash
# Log in once (prompts for username/password or a Docker Hub access token)
docker login

# Build, tagging for your repo
docker build -t whoace/rssindexer:latest .

# (Optional) also tag a versioned release alongside latest
docker tag whoace/rssindexer:latest whoace/rssindexer:1.0.0

# Push
docker push whoace/rssindexer:latest
docker push whoace/rssindexer:1.0.0   # if you tagged a version
```

After the first push, create the repo description on Docker Hub itself
(hub.docker.com → your repo → Edit), since Docker Hub doesn't pull that
from the Dockerfile. `unraid-template.xml` already points at
`whoace/rssindexer`, so once the image is public it'll pull correctly
from Unraid.

**Config without rebuilding:** drop a `config.py` into the mounted
`/config` volume (i.e. `./config/config.py` on the host) to override any
setting from `config.py` — useful for things env vars don't cover, like
`FIELD_MAP` or the full `CATEGORY_MAP`. It's loaded automatically on
startup if present.

## Running on Unraid

1. Push the image (see "Publishing to Docker Hub" above) so Unraid can
   pull `whoace/rssindexer:latest`.

2. `unraid-template.xml` already points at your repo. Optionally edit the
   `Support`/`Project` URLs and the `Icon` URL to your own GitHub repo/icon.

3. In Unraid: **Docker → Add Container → Template repositories**, add
   the raw URL to your `unraid-template.xml` (e.g. hosted on GitHub), or
   for a one-off local install, copy it to
   `/boot/config/plugins/dockerMan/templates-user/` on the Unraid box
   and it'll show up under **Add Container → select a template**.

4. Fill in the API key, RSS search URL, and Easynews credentials in the
   Unraid GUI, apply, and the **WebUI** button on the container's card
   will open the dashboard at `http://<unraid-ip>:5000`.

## Setup (running directly with Python)

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Edit `config.py`, or set the equivalent environment variables under
   Docker:
   - `API_KEY` — the key clients must supply (`?apikey=...`)
   - `RSS_SEARCH_URL_TEMPLATE` — your feed's search URL, with `{query}`
     as a placeholder for the URL-encoded search term
   - `RSS_AUTH_TYPE` / `RSS_AUTH_USERNAME` / `RSS_AUTH_PASSWORD` /
     `RSS_AUTH_TOKEN` — if the upstream feed needs credentials. Set
     `RSS_AUTH_TYPE=basic` with a username/password for feeds like
     Easynews' classic search endpoint, `bearer` for an
     `Authorization: Bearer` token, or `none` if the feed embeds a
     key/passkey directly in the URL itself.
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
- **Authentication to the source feed**: handled via `RSS_AUTH_TYPE`
  (`basic`/`bearer`/`none`) plus `RSS_AUTH_USERNAME`/`RSS_AUTH_PASSWORD`
  or `RSS_AUTH_TOKEN`. If your feed instead expects an API key/passkey
  as a query parameter, set `RSS_AUTH_TYPE=none` and bake the key
  straight into `RSS_SEARCH_URL_TEMPLATE`.
- This is unauthenticated beyond the single shared `apikey` — put it
  behind a reverse proxy with HTTPS if exposing it outside localhost.

## Testing it manually

```bash
curl "http://localhost:5000/api?t=caps"
curl "http://localhost:5000/api?t=search&q=example&apikey=changeme"
```
