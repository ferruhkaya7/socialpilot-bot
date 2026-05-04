import os
import json
import time
from datetime import datetime, timedelta
from dateutil import tz
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

CONFIG_FILE = "config.example.json"
STATE_FILE = "state.json"

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    cfg["socialpilot_email"] = os.getenv("SOCIALPILOT_EMAIL", cfg.get("socialpilot_email", ""))
    cfg["socialpilot_password"] = os.getenv("SOCIALPILOT_PASSWORD", cfg.get("socialpilot_password", ""))
    cfg["domain_filter"] = os.getenv("DOMAIN_FILTER", cfg["domain_filter"])
    cfg["daily_start_time"] = os.getenv("DAILY_START_TIME", cfg["daily_start_time"])
    cfg["daily_end_time"] = os.getenv("DAILY_END_TIME", cfg["daily_end_time"])
    cfg["slot_interval_minutes"] = int(os.getenv("SLOT_INTERVAL_MINUTES", cfg["slot_interval_minutes"]))
    cfg["page_offset_minutes"] = int(os.getenv("PAGE_OFFSET_MINUTES", cfg["page_offset_minutes"]))
    cfg["headless"] = os.getenv("HEADLESS", "true").lower() != "false"
    return cfg

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"used_links": [], "cursor": None, "last_run": None}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def rewrite_title(text):
    lines = [x.strip() for x in (text or "").splitlines() if x.strip()]
    if not lines:
        return ""
    title = lines[0]
    replacements = {
        "Kolay": "Pratik",
        "Muhteşem": "Lezzetli",
        "Lokum Gibi": "Lokum Kıvamında",
        "Çıtır": "Çıtır Çıtır",
        "Yumuşacık": "Pamuk Gibi",
    }
    for a, b in replacements.items():
        title = title.replace(a, b)
    return title

def comment_line(comment):
    return "Tarif İlk Yorumda" if "tarif" in (comment or "").lower() else "Bilgi İlk Yorumda"

def make_slots(cfg, count):
    ist = tz.gettz("Europe/Istanbul")
    now = datetime.now(ist)
    sh, sm = map(int, cfg["daily_start_time"].split(":"))
    eh, em = map(int, cfg["daily_end_time"].split(":"))

    t = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    if now > t:
        t = now.replace(second=0, microsecond=0)
        mod = t.minute % cfg["slot_interval_minutes"]
        if mod:
            t += timedelta(minutes=cfg["slot_interval_minutes"] - mod)

    slots = []
    while len(slots) < count:
        m = t.hour * 60 + t.minute
        allowed = (m >= sh * 60 + sm) or (m <= eh * 60 + em)
        if allowed:
            slots.append(t)
        t += timedelta(minutes=cfg["slot_interval_minutes"])
    return slots

def rotate(items, n):
    if not items:
        return items
    n = n % len(items)
    return items[n:] + items[:n]

def login_socialpilot(page, cfg):
    page.goto(cfg["socialpilot_login_url"], wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # Zaten login ise dashboard'a yönlenmiş olabilir.
    if "login" not in page.url.lower():
        print("Already logged in")
        return

    email = cfg["socialpilot_email"]
    password = cfg["socialpilot_password"]
    if not email or not password:
        raise RuntimeError("SOCIALPILOT_EMAIL veya SOCIALPILOT_PASSWORD eksik")

    # Selectorlar UI değişebilir; birkaç yaygın selector denenir.
    email_selectors = ['input[type="email"]', 'input[name="email"]', 'input[placeholder*="Email"]']
    password_selectors = ['input[type="password"]', 'input[name="password"]']
    filled = False
    for s in email_selectors:
        try:
            page.fill(s, email, timeout=3000)
            filled = True
            break
        except Exception:
            pass
    if not filled:
        raise RuntimeError("Email alanı bulunamadı")

    for s in password_selectors:
        try:
            page.fill(s, password, timeout=3000)
            break
        except Exception:
            pass

    for s in ['button[type="submit"]', 'button:has-text("Login")', 'button:has-text("Sign in")']:
        try:
            page.click(s, timeout=3000)
            break
        except Exception:
            pass

    page.wait_for_timeout(6000)
    print("Login attempted, current url:", page.url)

def fetch_source_items_placeholder(cfg, state):
    """
    İlk stabil sürümde kaynak içerikleri SocialPilot delivered ekranından veya Facebook Graph/session ile çekeceğiz.
    Buraya test için manuel placeholder bıraktık.
    Kurulum sonrası ilk hedef: kaynak okuma selectorlarını canlı ekranda netleştirmek.
    """
    print("Source fetch placeholder. İlk canlı kurulumda kaynak okuma selectorları eklenecek.")
    return []

def open_create_post(page):
    # SocialPilot UI selectorları değişebilir. Yaygın buton metinleri denenir.
    candidates = [
        'text=Create Post',
        'text=Create',
        'text=New Post',
        'text=Posts',
    ]
    for c in candidates:
        try:
            page.click(c, timeout=4000)
            page.wait_for_timeout(2000)
            return
        except Exception:
            continue
    raise RuntimeError("Create post butonu bulunamadı")

def schedule_one_page(page, item, page_name, schedule_time):
    """
    Bu fonksiyon UI selectorlarını canlı SocialPilot ekranına göre kesinleştirilecek iskelet.
    """
    print(f"Would schedule: {page_name} at {schedule_time} - {item['title']}")
    # TODO canlı UI'ya göre:
    # 1 account dropdown seç
    # 2 caption gir
    # 3 media upload/url gir
    # 4 first comment gir
    # 5 schedule datetime seç
    # 6 submit

def run_once():
    cfg = load_config()
    state = load_state()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg["headless"])
        context = browser.new_context()
        page = context.new_page()

        login_socialpilot(page, cfg)

        items = fetch_source_items_placeholder(cfg, state)
        if not items:
            print("Şimdilik kaynak items yok. Bot UI login doğrulama modunda çalıştı.")
            browser.close()
            return

        slots = make_slots(cfg, len(items))

        for idx, item in enumerate(items):
            target_order = rotate(cfg["target_pages"], idx)
            for page_idx, page_name in enumerate(target_order):
                when = slots[idx] + timedelta(minutes=page_idx * cfg["page_offset_minutes"])
                try:
                    schedule_one_page(page, item, page_name, when)
                except Exception as e:
                    print("Schedule fail:", page_name, item.get("title"), e)
                    continue

        state["last_run"] = datetime.now().isoformat()
        save_state(state)
        browser.close()

if __name__ == "__main__":
    run_once()