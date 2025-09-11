### Gab CLAPTON-style Selenium Scraper

This utility collects public Gab posts via Selenium and saves them as JSONL in a CLAPTON-style flat schema suitable for downstream annotation/analysis.

### Install

```bash
python -m pip install -r requirements.txt
```

Chrome/Chromium is required. The script will auto-manage the driver via `webdriver-manager`.

### Usage

- Headless, anonymous search (single run):
```bash
python gab_clapton_scraper.py --query "immigration" --max-posts 200 --headless --output gab_immigration.jsonl
```

- Authenticated session (more results, fewer blocks). Provide credentials via flags or env vars:
```bash
export GAB_USERNAME="your_email"
export GAB_PASSWORD="your_password"
python gab_clapton_scraper.py --query "#MAGA" --max-posts 500 --headless --login --output gab_maga.jsonl
```

- Automatic CLAPTON-style batch over built-in keywords (writes one JSONL per keyword):
```bash
export GAB_USERNAME="your_email"; export GAB_PASSWORD="your_password"
python gab_clapton_scraper.py --batch --output-dir out/gab_batch --max-posts 200 --headless --login
```

Flags (single run):
- `--query`: search term or hashtag (include leading `#` for hashtags)
- `--type`: search type, default `status` (future: `user`, `group`)
- `--max-posts`: maximum posts to collect
- `--headless`: run Chrome headlessly
- `--login`: enable login using `--username/--password` or env vars `GAB_USERNAME`/`GAB_PASSWORD`
- `--username/--password`: explicit credentials (overrides env vars)
- `--output`: JSONL output path
- `--delay-min/--delay-max`: human-like random delays (seconds) between actions

Flags (batch):
- `--batch`: run across built-in CLAPTON keyword list
- `--output-dir`: directory for per-keyword JSONL files
- other flags shared with single run

### Output schema (CLAPTON-style JSONL)
Each line is one post:
```json
{
  "platform": "gab",
  "post_id": "110987654321",
  "url": "https://gab.com/posts/110987654321",
  "text": "Example post text ...",
  "username": "@example",
  "display_name": "Example User",
  "author_url": "https://gab.com/example",
  "created_at": "2025-09-10T12:34:56Z",
  "collected_at": "2025-09-10T12:40:00Z",
  "like_count": 12,
  "reply_count": 3,
  "repost_count": 1,
  "hashtags": ["MAGA", "USA"],
  "mentions": ["someone"],
  "urls": ["https://example.com"],
  "media_urls": [],
  "query": "#MAGA",
  "source_type": "search-status"
}
```

Notes:
- Some fields may be null or 0 if not visible without interaction.
- Deduplication uses post URL/id.

### Legal and ethical considerations
- Review Gab's Terms of Service and robots.txt before scraping. Only collect public data for legitimate research purposes.
- Respect rate limits; use headless + delays; avoid aggressive concurrency.
- Handle personal data responsibly; consider anonymization where appropriate.

### Troubleshooting
- If Cloudflare/VPN challenges appear, authenticate and avoid VPNs/proxies.
- Ensure Chrome/Chromium is installed and compatible with your environment.
- Increase `--delay-min`/`--delay-max` if rate-limited.