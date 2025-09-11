import os
import re
import json
import time
import random
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

# Import selenium lazily inside functions so `--help` works without deps

def build_driver(headless: bool) -> Any:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    # Prefer Selenium Manager; fallback to webdriver_manager
    service = Service()

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    # Stealth-ish defaults
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--no-first-run')
    options.add_argument('--no-default-browser-check')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-gpu')
    options.add_argument('--remote-debugging-port=0')
    options.add_argument('--no-zygote')
    options.add_argument('--single-process')
    options.add_argument('--user-data-dir=/tmp/chrome-user-data')
    options.add_argument('--data-path=/tmp/chrome-data')
    options.add_argument('--disk-cache-dir=/tmp/chrome-cache')

    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    ]
    options.add_argument(f'--user-agent={random.choice(user_agents)}')
    options.add_experimental_option("excludeSwitches", ["enable-automation"]) 
    options.add_experimental_option('useAutomationExtension', False)

    # Point to Chromium if available
    for candidate in [
        os.environ.get("CHROME_BINARY"),
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
    ]:
        if candidate and os.path.exists(candidate):
            options.binary_location = candidate
            break

    # Try default; if it fails, fallback to webdriver_manager
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        except Exception as e:
            raise e

    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception:
        pass

    return driver


def human_sleep(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))


def wait_for_cloudflare(driver: Any, max_wait: int = 60) -> bool:
    start_time = time.time()
    while time.time() - start_time < max_wait:
        title = (driver.title or "").lower()
        source = (driver.page_source or "").lower()
        if ("cloudflare" in title or "attention required" in title or "checking your browser" in source):
            human_sleep(3, 5)
            continue
        return True
    return False


def navigate(driver: Any, url: str, delay_min: float, delay_max: float, retries: int = 3) -> bool:
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
            human_sleep(delay_min, delay_max)
            if wait_for_cloudflare(driver, max_wait=int(max(20, delay_max * 4))):
                return True
        except Exception:
            pass
        human_sleep(5, 10)
    return False


def try_login(driver: Any, username: str, password: str, delay_min: float, delay_max: float) -> bool:
    if not username or not password:
        return False
    if not navigate(driver, "https://gab.com/auth/sign_in", delay_min, delay_max, retries=3):
        return False

    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    # Find fields
    email_field = None
    password_field = None
    selectors_email = [
        "input[type='email']",
        "input[name*='email' i]",
        "input[placeholder*='email' i]",
        "input[id*='email' i]",
        "input[autocomplete='email']",
    ]
    selectors_password = [
        "input[type='password']",
        "input[name*='password' i]",
        "input[placeholder*='password' i]",
    ]

    for sel in selectors_email:
        nodes = driver.find_elements(By.CSS_SELECTOR, sel)
        for n in nodes:
            if n.is_displayed() and n.is_enabled():
                email_field = n
                break
        if email_field:
            break

    for sel in selectors_password:
        nodes = driver.find_elements(By.CSS_SELECTOR, sel)
        for n in nodes:
            if n.is_displayed() and n.is_enabled():
                password_field = n
                break
        if password_field:
            break

    if not email_field or not password_field:
        return False

    email_field.click(); human_sleep(0.3, 1.0); email_field.clear()
    for ch in username:
        email_field.send_keys(ch)
        time.sleep(random.uniform(0.02, 0.08))

    password_field.click(); human_sleep(0.2, 0.8); password_field.clear()
    password_field.send_keys(password)

    human_sleep(0.3, 0.8)

    # Submit
    buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'],input[type='submit']")
    clicked = False
    for b in buttons:
        if b.is_displayed() and b.is_enabled():
            try:
                driver.execute_script("arguments[0].click();", b)
                clicked = True
                break
            except Exception:
                continue
    if not clicked:
        password_field.send_keys(Keys.RETURN)

    human_sleep(delay_min + 2, delay_max + 4)

    cur = driver.current_url.lower()
    return ("/auth/" not in cur and "sign_in" not in cur and "login" not in cur)


def extract_post_id(url: str) -> Optional[str]:
    m = re.search(r"/posts/([A-Za-z0-9_\-]+)", url)
    return m.group(1) if m else None


def extract_entities(text: str) -> Dict[str, List[str]]:
    hashtags = [h.strip('#') for h in re.findall(r"#[A-Za-z0-9_]+", text)]
    mentions = [m.strip('@') for m in re.findall(r"@[A-Za-z0-9_\.]+", text)]
    urls = re.findall(r"https?://[^\s]+", text)
    return {
        "hashtags": list(dict.fromkeys(hashtags)),
        "mentions": list(dict.fromkeys(mentions)),
        "urls": list(dict.fromkeys(urls)),
    }


def parse_visible_text(element: Any) -> str:
    try:
        return element.text.strip()
    except Exception:
        return ""


def extract_posts_from_page(driver: Any, query: str) -> List[Dict[str, Any]]:
    from selenium.webdriver.common.by import By

    posts: List[Dict[str, Any]] = []

    # Strategy: find all post permalinks then enrich from nearby nodes
    anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/posts/']")
    seen_ids: Set[str] = set()

    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
            if "/posts/" not in href:
                continue
            post_id = extract_post_id(href)
            if not post_id or post_id in seen_ids:
                continue

            # Find a reasonable container to read text/metadata
            container = a
            for _ in range(5):
                try:
                    container = container.find_element(By.XPATH, "..")
                except Exception:
                    break

            text = parse_visible_text(container)

            # Heuristics for author and timestamp
            username = None
            display_name = None
            author_url = None
            created_at_iso = None

            # username/author_url
            candidates = container.find_elements(By.CSS_SELECTOR, "a[href^='https://gab.com/']")
            for c in candidates:
                u = (c.get_attribute("href") or "").rstrip('/')
                if re.match(r"https://gab\.com/(?:@[A-Za-z0-9_\.]+|[A-Za-z0-9_\.]+)$", u):
                    author_url = u
                    # Try to infer @handle from visible text or URL
                    vis = (c.text or "").strip()
                    if vis.startswith('@'):
                        username = vis
                    else:
                        handle = u.rsplit('/', 1)[-1]
                        if not handle.startswith('@'):
                            username = f"@{handle}"
                        else:
                            username = handle
                    # display name: try a nearby strong/span
                    try:
                        display_name = vis if vis and not vis.startswith('@') else None
                    except Exception:
                        pass
                    break

            # timestamp
            try:
                time_elems = container.find_elements(By.CSS_SELECTOR, "time, a time")
                for t in time_elems:
                    dt = t.get_attribute("datetime") or t.get_attribute("title") or t.text
                    if dt:
                        try:
                            created_at_iso = datetime.fromisoformat(dt.replace('Z', '+00:00')).isoformat()
                        except Exception:
                            created_at_iso = None
                        break
            except Exception:
                pass

            entities = extract_entities(text)

            # engagement (best-effort; may be missing)
            like_count = 0
            reply_count = 0
            repost_count = 0
            try:
                numbers = re.findall(r"\b(\d{1,4}(?:,\d{3})*)\b", text)
                if numbers:
                    like_count = int(numbers[-1].replace(',', ''))
            except Exception:
                pass

            post: Dict[str, Any] = {
                "platform": "gab",
                "post_id": post_id,
                "url": href,
                "text": text,
                "username": username,
                "display_name": display_name,
                "author_url": author_url,
                "created_at": created_at_iso,
                "collected_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                "like_count": like_count,
                "reply_count": reply_count,
                "repost_count": repost_count,
                "hashtags": entities["hashtags"],
                "mentions": entities["mentions"],
                "urls": entities["urls"],
                "media_urls": [],
                "query": query,
                "source_type": "search-status",
            }

            posts.append(post)
            seen_ids.add(post_id)
        except Exception:
            continue

    return posts


def scroll_and_collect(driver: Any, query: str, max_posts: int, delay_min: float, delay_max: float) -> List[Dict[str, Any]]:
    from selenium.webdriver.common.by import By

    collected: Dict[str, Dict[str, Any]] = {}
    consecutive_stall = 0

    last_height = driver.execute_script("return document.body.scrollHeight")
    while len(collected) < max_posts and consecutive_stall < 5:
        # Parse current viewport
        page_posts = extract_posts_from_page(driver, query)
        for p in page_posts:
            pid = p.get("post_id")
            if pid and pid not in collected:
                collected[pid] = p
                if len(collected) >= max_posts:
                    break

        # Scroll
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        human_sleep(delay_min, delay_max)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            consecutive_stall += 1
        else:
            consecutive_stall = 0
        last_height = new_height

    return list(collected.values())


def write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, 'a', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def clapton_default_keywords() -> List[str]:
    """Built-in CLAPTON-style political keywords/hashtags to search automatically."""
    return [
        # General politics
        "politics", "election", "vote", "voting", "campaign",
        # US parties/labels
        "republican", "democrat", "conservative", "liberal",
        # Prominent figures/topics
        "Trump", "Biden", "Harris", "MAGA", "America First",
        # Issues
        "immigration", "border", "economy", "inflation", "taxes", "healthcare",
        "abortion", "guns", "second amendment", "climate", "covid", "vaccine",
        # Institutions
        "Congress", "Senate", "House", "Supreme Court",
        # Hashtag variants
        "#MAGA", "#Election2024", "#Politics",
    ]


def _sanitize_filename(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return base.strip("._-") or "keyword"


def main() -> None:
    parser = argparse.ArgumentParser(description="Gab Selenium scraper (CLAPTON-style JSONL)")
    # Single-run flags
    parser.add_argument("--query", help="Search query or hashtag (include #)")
    parser.add_argument("--type", default="status", choices=["status"], help="Search type")
    parser.add_argument("--max-posts", type=int, default=200, help="Maximum posts to collect")
    parser.add_argument("--output", help="Output JSONL file path (single-run)")
    # Batch mode flags
    parser.add_argument("--batch", action="store_true", help="Run over built-in CLAPTON keyword list")
    parser.add_argument("--output-dir", help="Directory to write per-keyword JSONL files in batch mode")
    # Common flags
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    parser.add_argument("--login", action="store_true", help="Attempt to login before scraping")
    parser.add_argument("--username", default=os.getenv("GAB_USERNAME", ""), help="Gab username/email")
    parser.add_argument("--password", default=os.getenv("GAB_PASSWORD", ""), help="Gab password")
    parser.add_argument("--delay-min", type=float, default=1.5, help="Min delay between actions")
    parser.add_argument("--delay-max", type=float, default=3.5, help="Max delay between actions")

    args = parser.parse_args()

    if args.batch:
        if not args.output_dir:
            raise SystemExit("--output-dir is required in --batch mode")
        out_dir = os.path.abspath(args.output_dir)
        os.makedirs(out_dir, exist_ok=True)

        driver = build_driver(headless=args.headless)
        try:
            if args.login:
                _ = try_login(driver, args.username, args.password, args.delay_min, args.delay_max)

            keywords = clapton_default_keywords()
            total_saved = 0
            for kw in keywords:
                q = kw.strip()
                encoded = re.sub(r"\s+", "%20", q)
                url = f"https://gab.com/search?q={encoded}&type=status"
                if not navigate(driver, url, args.delay_min, args.delay_max, retries=3):
                    print(f"Skip '{q}': failed to load page")
                    continue

                posts = scroll_and_collect(driver, q, args.max_posts, args.delay_min, args.delay_max)
                fname = _sanitize_filename(q) + ".jsonl"
                out_path = os.path.join(out_dir, fname)
                if not posts:
                    stub = {
                        "platform": "gab",
                        "post_id": None,
                        "url": None,
                        "text": "",
                        "username": None,
                        "display_name": None,
                        "author_url": None,
                        "created_at": None,
                        "collected_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                        "like_count": 0,
                        "reply_count": 0,
                        "repost_count": 0,
                        "hashtags": [],
                        "mentions": [],
                        "urls": [],
                        "media_urls": [],
                        "query": q,
                        "source_type": "search-status",
                    }
                    write_jsonl(out_path, [stub])
                    print(f"Saved 0 posts (stub) to {out_path}")
                else:
                    write_jsonl(out_path, posts)
                    total_saved += len(posts)
                    print(f"Saved {len(posts)} posts to {out_path}")

            print(f"Batch complete. Total posts saved: {total_saved}")
        finally:
            try:
                driver.quit()
            except Exception:
                pass
        return

    # Single-run mode (backwards compatible)
    if not args.query or not args.output:
        raise SystemExit("--query and --output are required in single-run mode. Use --batch for automatic keywords.")

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    driver = build_driver(headless=args.headless)

    try:
        if args.login:
            _ = try_login(driver, args.username, args.password, args.delay_min, args.delay_max)

        q = args.query.strip()
        encoded = re.sub(r"\s+", "%20", q)
        url = f"https://gab.com/search?q={encoded}&type=status"
        if not navigate(driver, url, args.delay_min, args.delay_max, retries=3):
            raise RuntimeError("Failed to load search page")

        posts = scroll_and_collect(driver, q, args.max_posts, args.delay_min, args.delay_max)
        if not posts:
            # Emit a minimal stub so pipeline doesn't break
            stub = {
                "platform": "gab",
                "post_id": None,
                "url": None,
                "text": "",
                "username": None,
                "display_name": None,
                "author_url": None,
                "created_at": None,
                "collected_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                "like_count": 0,
                "reply_count": 0,
                "repost_count": 0,
                "hashtags": [],
                "mentions": [],
                "urls": [],
                "media_urls": [],
                "query": q,
                "source_type": "search-status",
            }
            write_jsonl(args.output, [stub])
        else:
            write_jsonl(args.output, posts)

        print(f"Saved {len(posts)} posts to {args.output}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()