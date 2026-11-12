# Developing Photo Cloud

Technical notes. For end-user instructions see the [README](../README.md).

Python 3.10+, standard library only. Frontend is plain ES modules (no build step).

## Run from source

```bash
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
python run.py --folder ~/Pictures
```

| Option | Meaning |
|---|---|
| `--source` | `local` (default), `dropbox`, `gdrive`, `gphotos` |
| `--folder` | Local path, Dropbox path (`/Photos`), or Drive folder link/ID |
| `--recursive` | Include subfolders |
| `--port N` | Default 8765. `0` = free port each run (Dropbox sign-in needs a fixed, registered port) |
| `--no-browser` | Don't open the browser |
| `--clear-cache` | Delete cached Dropbox/Drive images and exit |

## Cloud setup

Today each user creates their own OAuth app and puts its identifiers in
`~/.photocloud/credentials.json` (`C:\Users\<you>\.photocloud\credentials.json`
on Windows; `PHOTOCLOUD_HOME` overrides the folder):

```json
{
  "google":  { "client_id": "xxx.apps.googleusercontent.com", "client_secret": "..." },
  "dropbox": { "app_key": "..." }
}
```

Env vars win over the file: `PHOTOCLOUD_GOOGLE_CLIENT_ID`,
`PHOTOCLOUD_GOOGLE_CLIENT_SECRET`, `PHOTOCLOUD_DROPBOX_APP_KEY`.
Never commit this file.

### Dropbox

1. Create an app at https://www.dropbox.com/developers/apps: **Scoped access**,
   **Full Dropbox** (or "App folder").
2. Permissions: `files.metadata.read` and `files.content.read`, then **Submit**
   (before connecting; after changing permissions, Disconnect and Connect again).
3. Settings: add redirect URI `http://127.0.0.1:8765/oauth/callback` (must match the port).
4. Copy the **App key** into `credentials.json` (PKCE, no secret needed).

### Google (Drive and Photos)

1. Create a project in https://console.cloud.google.com/.
2. Enable **Google Drive API** and **Google Photos Picker API**.
3. OAuth consent screen: External, add yourself as a test user.
4. Credentials: **OAuth client ID**, type **Desktop app**; copy ID and secret.

Scopes: `drive.readonly` and `photospicker.mediaitems.readonly`. In "Testing"
status Google expires refresh tokens after 7 days.

## Behaviour per source

- **Local:** files read straight from disk.
- **Dropbox:** lists with `files/list_folder`; images fetched as 2048 px JPEG thumbnails
  (`get_thumbnail_v2`), falling back to the original; cached in `~/.photocloud/cache`.
- **Drive:** Drive API v3; originals downloaded on demand and cached.
- **Google Photos:** Picker API only (the Library API no longer allows reading a
  user's library since March 2025). The picked selection (max 200, ~2048 px) is
  stored in `~/.photocloud/gphotos` and reused on later runs.

## Layout

```
run.py                 entry point (CLI)
photocloud/
  errors.py            SourceError / AuthRequired
  config.py            ~/.photocloud, credentials.json, private token store
  oauth.py             OAuth code flow + PKCE, token refresh (Google, Dropbox)
  http.py, cache.py    urllib helper, on-disk image cache
  images.py            local folder validation + image discovery
  sources/             local, gdrive, dropbox, gphotos
  server.py            127.0.0.1-only server: static files, /api/*, /img/<id>, /oauth/*
web/
  index.html, css/style.css
  js/config.js         tunables (timings, opacity, speeds, photo count)
  js/cloud.js          background physics
  js/featured.js       foreground lifecycle state machine
  js/scene.js          DOM layers, render loop, resize handling
  js/main.js           settings UI, source switching, sign-in + picker flows
tests/
  test_images.py       local folder scanning
  test_sources.py      Drive/Dropbox/Photos/OAuth/server against a mock service
  cycle.test.mjs       simulates the featured-photo cycle (needs Node)
```

Tests: `python -m unittest discover -s tests` and `node tests/cycle.test.mjs`.
The cloud tests use a local mock server, so they need no network or accounts.
They do not replace trying each real service once.

## Security notes

- The server binds to 127.0.0.1, serves images only by index from the loaded list,
  and rejects requests whose Host/Origin is not 127.0.0.1/localhost.
- Tokens are stored in `~/.photocloud/tokens.json` (0600) and never sent to the browser.
- Tunables live in `web/js/config.js`; `maxPhotos` (60) bounds
  browser memory.

## Roadmap: a non-technical app

Things that stand between today's version and "download, double-click, sign in":

1. **Ship our own Dropbox/Google app registrations** so users just press *Sign in*
   instead of creating an OAuth app. Expect Google verification for the Drive
   scope (it is a restricted scope), and Dropbox apps start in development
   mode with a user limit until approved for production. Check the current rules
   of both before relying on this.
2. **Package it** (for example a PyInstaller or similar bundle, or a small desktop
   wrapper) so Python is not needed, and open a window or full-screen view directly.
3. **Pick the folder with a normal file dialog** instead of typing a path.
4. **A fixed, built-in sign-in port** (or a loopback flow that doesn't need
   pre-registered ports) so Dropbox works without configuration.
5. **Optional upload page / QR code** inside the app for guest uploads
   (needs the `files.content.write` Dropbox scope and a network-visible upload-only server).
6. **Friendlier errors** and a setup check screen instead of "Not set up (see README)".