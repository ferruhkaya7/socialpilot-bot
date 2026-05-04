import os
import json
import time
import requests
from datetime import datetime, timedelta
from dateutil import tz

STATE_FILE = "state.json"
CONFIG_FILE = "config.example.json"

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    def env_list(name, default):
        raw = os.getenv(name)
        if not raw:
            return default
        return [int(x.strip()) for x in raw.split(",") if x.strip()]

    cfg["source_page_login_id"] = int(os.getenv("SOURCE_PAGE_LOGIN_ID", cfg["source_page_login_id"]))
    cfg["target_login_ids"] = env_list("TARGET_LOGIN_IDS", cfg["target_login_ids"])
    cfg["domain_filter"] = os.getenv("DOMAIN_FILTER", cfg["domain_filter"])
    cfg["start_date"] = os.getenv("START_DATE", cfg["start_date"])
    cfg["daily_start_time"] = os.getenv("DAILY_START_TIME", cfg["daily_start_time"])
    cfg["daily_end_time"] = os.getenv("DAILY_END_TIME", cfg["daily_end_time"])
    cfg["slot_interval_minutes"] = int(os.getenv("SLOT_INTERVAL_MINUTES", cfg["slot_interval_minutes"]))
    cfg["page_offset_minutes"] = int(os.getenv("PAGE_OFFSET_MINUTES", cfg["page_offset_minutes"]))
    return cfg

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"cursor_page": None, "cursor_post_id": None, "used_links": [], "last_run": None}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def normalize_title(text):
    if not text:
        return ""
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if not lines:
        return ""
    title = lines[0]
    replacements = {
        "Kolay": "Pratik",
        "Muhteşem": "Lezzetli",
        "Lokum Gibi": "Lokum Kıvamında",
        "Çıtır": "Çıtır Çıtır"
    }
    for a, b in replacements.items():
        title = title.replace(a, b)
    return title

def comment_line(comment):
    c = (comment or "").lower()
    if "tarif" in c:
        return "Tarif İlk Yorumda"
    return "Bilgi İlk Yorumda"

def extract_comment(extra):
    if isinstance(extra, dict):
        return extra.get("comment", "") or ""
    return ""

def socialpilot_headers():
    token = os.getenv("SOCIALPILOT_API_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def api_base():
    base = os.getenv("SOCIALPILOT_API_BASE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("SOCIALPILOT_API_BASE_URL eksik")
    return base

def fetch_source_posts_socialpilot(cfg, page=1, limit=100):
    url = f"{api_base()}/posts/delivered"
    params = {
        "account": cfg["source_page_login_id"],
        "platform": "facebook",
        "limit": limit,
        "page": page
    }
    r = requests.get(url, headers=socialpilot_headers(), params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("response", {}).get("list", [])

def upload_media(image_url):
    url = f"{api_base()}/media/upload"
    payload = {"mediaType": "IMAGE", "media": [{"url": image_url}], "openaiFileIdRefs": []}
    r = requests.post(url, headers=socialpilot_headers(), json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["response"]["mediaIds"][0]["mediaId"]

def create_post(login_id, desc, media_id, comment, schedule_time):
    url = f"{api_base()}/posts/create"
    payload = {
        "shareType": 3,
        "scheduleDateTime": schedule_time.strftime("%Y-%m-%d %H:%M"),
        "loginIds": [login_id],
        "postData": {
            "postDesc": desc,
            "mediaId": [media_id],
            "comment": comment
        }
    }
    r = requests.post(url, headers=socialpilot_headers(), json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

def make_slots(cfg, count):
    ist = tz.gettz(cfg.get("timezone", "Europe/Istanbul"))
    now = datetime.now(ist)
    start_h, start_m = map(int, cfg["daily_start_time"].split(":"))
    end_h, end_m = map(int, cfg["daily_end_time"].split(":"))

    t = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    if now > t:
        t = now.replace(second=0, microsecond=0)
        mod = t.minute % cfg["slot_interval_minutes"]
        if mod:
            t += timedelta(minutes=(cfg["slot_interval_minutes"] - mod))

    slots = []
    while len(slots) < count:
        minutes = t.hour * 60 + t.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        allowed = (minutes >= start_minutes) or (minutes <= end_minutes)
        if allowed:
            slots.append(t)
        t += timedelta(minutes=cfg["slot_interval_minutes"])
    return slots

def rotate(items, n):
    if not items:
        return items
    n %= len(items)
    return items[n:] + items[:n]

def valid_source_post(post, cfg, used_links):
    comment = extract_comment(post.get("extraData", {}))
    if cfg["domain_filter"] not in comment:
        return False
    if comment in used_links:
        return False
    imgs = post.get("postImage") or post.get("thumbImage") or []
    return bool(imgs)

def prepare_items(cfg, state):
    used = set(state.get("used_links", []))
    selected = []

    # Büyükten küçüğe gitme mantığı: en eski sayfaları yakalamak için.
    # Render testinde API pagination doğrulanınca bu aralık ayarlanacak.
    for page in range(999, 0, -1):
        try:
            batch = fetch_source_posts_socialpilot(cfg, page=page, limit=100)
        except Exception as e:
            print(f"Kaynak sayfa {page} okunamadı: {e}")
            continue

        if not batch:
            continue

        for post in reversed(batch):
            if valid_source_post(post, cfg, used):
                selected.append(post)
                used.add(extract_comment(post.get("extraData", {})))
            if len(selected) >= cfg["batch_posts_per_day"]:
                return selected
    return selected

def schedule_item_all_pages(post, cfg, slot, rotation_index):
    comment = extract_comment(post.get("extraData", {}))
    images = post.get("postImage") or post.get("thumbImage") or []
    if not comment or not images:
        print("Eksik comment/görsel, skip:", post.get("postId"))
        return False

    title = normalize_title(post.get("postDesc", ""))
    desc = f"{title}\n{comment_line(comment)}"
    media_id = upload_media(images[0])

    targets = rotate(cfg["target_login_ids"], rotation_index)

    ok_count = 0
    for i, login_id in enumerate(targets):
        page_time = slot + timedelta(minutes=i * cfg["page_offset_minutes"])
        try:
            create_post(login_id, desc, media_id, comment, page_time)
            ok_count += 1
            print("OK", page_time.strftime("%Y-%m-%d %H:%M"), login_id, title)
        except Exception as e:
            print("FAIL", login_id, title, e)
    return ok_count > 0

def run_once():
    cfg = load_config()
    state = load_state()
    print("Bot başladı:", datetime.now().isoformat())

    items = prepare_items(cfg, state)
    if not items:
        print("Uygun içerik bulunamadı.")
        return

    slots = make_slots(cfg, len(items))
    used_links = state.get("used_links", [])

    for idx, post in enumerate(items):
        try:
            ok = schedule_item_all_pages(post, cfg, slots[idx], idx)
            if ok:
                comment = extract_comment(post.get("extraData", {}))
                if comment not in used_links:
                    used_links.append(comment)
                state["cursor_post_id"] = post.get("postId")
                state["last_run"] = datetime.now().isoformat()
                state["used_links"] = used_links[-10000:]
                save_state(state)
        except Exception as e:
            print("Post tamamen atlandı:", post.get("postId"), e)
            continue

    print("Bot tamamlandı.")

if __name__ == "__main__":
    while True:
        run_once()
        time.sleep(int(os.getenv("RUN_EVERY_SECONDS", "86400")))