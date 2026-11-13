# Movie File Formatter

A lightweight, Dockerized background service that watches a downloads folder, cleans up messy torrent movie and TV series filenames using the Google Gemini API, and copies the renamed media and subtitles into an organized library folder.

Built as a practical home-server project to explore integrating Google AI (`google-genai`) API calls—specifically **structured Pydantic outputs** and **Google Search grounding**—into a real, continuously running application.

## What It Does

1. **Polls for new downloads** — Periodically scans `DOWNLOAD_DIR` for standalone video files or multi-file folders, skipping items already processed or without video files.
2. **Identifies titles with Gemini (Structured Output)** — Sends all pending items in a single batched `generate_content` call using a Pydantic `response_schema` to pick the real video files (ignoring samples, extras, and `.nfo`/`.txt` clutter) and extract the clean title, original language, release year, and series flag.
3. **Verifies titles with Gemini + Google Search Grounding** — Runs a second batched call with the `GoogleSearch` tool enabled to confirm each movie or TV series actually exists and fetch its canonical title in its original language.
4. **Copies & renames safely** — Copies (never moves or deletes) verified files into `MOVIE_OUTPUT` as `Title (Year).ext` or `Title (Year) S01E01.ext` for series episodes, along with matching subtitle files. Unverified or low-confidence items are copied with their original filenames.
5. **Tracks state & handles API limits** — Persists processed items to `STATE_DIR/processed.json` so restarts don't reprocess files, backs off automatically on Gemini `429`/`5xx` responses, and updates a heartbeat file for Docker healthchecks.

## Running with Docker

1. Copy `.env.example` to `.env` and add your Gemini API key:

   ```bash
   cp .env.example .env
   ```

2. Update the host bind-mount `source` paths in `docker-compose.yaml` to match your server's directories (`/downloads`, `/movies`, and `/state`).

3. Build and start the container:

   ```bash
   docker compose up -d --build
   ```

The container includes a built-in healthcheck (`python -m app.healthcheck`) that verifies the mounted directories exist and the scan loop heartbeat is fresh.

## Configuration

| Variable | Description | Default (`app/config.py`) | `docker-compose.yaml` |
| --- | --- | --- | --- |
| `GEMINI_API_KEY` | Google Gemini API key | *(required)* | `${GEMINI_API_KEY}` |
| `GEMINI_MODEL` | Gemini model ID | `gemini-3.8-flash` | `gemini-3.8-flash` |
| `DOWNLOAD_DIR` | Input directory inside container | `/data/input` | `/downloads` |
| `MOVIE_OUTPUT` | Output directory inside container | `/data/output` | `/movies` |
| `STATE_DIR` | Directory for `processed.json` | `/data/state` | `/state` |
| `POLL_INTERVAL_SECONDS` | Delay between scans (seconds) | `60` | `60` |
| `MIN_VERIFICATION_CONFIDENCE` | Minimum confidence (`0`–`1`) to rename | `0.6` | — |
| `VIDEO_EXTENSIONS` | Comma-separated video extensions | `mkv,mp4,avi,mov,m4v,wmv,flv` | — |
| `SUBTITLE_EXTENSIONS` | Comma-separated subtitle extensions | `srt,sub,ass,ssa,vtt,idx` | — |
| `HEARTBEAT_FILE` | Path to loop heartbeat file | `/tmp/movie-file-formatter.heartbeat` | — |
| `HEARTBEAT_MAX_AGE_SECONDS` | Max heartbeat age before unhealthy | `1800` | — |

## Development & Testing

```bash
pip install -r requirements-dev.txt
pytest
```
