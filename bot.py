import os, json, time, threading, requests
from datetime import datetime, timedelta
from dateutil import tz
from flask import Flask, jsonify

app = Flask(__name__)
STATE_FILE = "state.json"
CONFIG_FILE = "config.example.json"
LAST_STATUS = {"status":"starting","last_run":None,"message":"starting"}

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    def env_list(name, default):
        raw = os.getenv(name)
        return [int(x.strip()) for x in raw.split(",") if x.strip()] if raw else default
    cfg["source_page_login_id"] = int(os.getenv("SOURCE_PAGE_LOGIN_ID", cfg["source_page_login_id"]))
    cfg["target_login_ids"] = env_list("TARGET_LOGIN_IDS", cfg["target_login_ids"])
    cfg["domain_filter"] = os.getenv("DOMAIN_FILTER", cfg["domain_filter"])
    cfg["start_date"] = os.getenv("START_DATE", cfg["start_date"])
    cfg["daily_start_time"] = os.getenv("DAILY_START_TIME", cfg["daily_start_time"])
    cfg["daily_end_time"] = os.getenv("DAILY_END_TIME", cfg["daily_end_time"])
    cfg["slot_interval_minutes"] = int(os.getenv("SLOT_INTERVAL_MINUTES", cfg["slot_interval_minutes"]))
    cfg["page_offset_minutes"] = int(os.getenv("PAGE_OFFSET_MINUTES", cfg["page_offset_minutes"]))
    cfg["batch_posts_per_day"] = int(os.getenv("BATCH_POSTS_PER_DAY", cfg["batch_posts_per_day"]))
    return cfg

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"cursor_post_id":None,"used_links":[],"last_run":None}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def api_base():
    b = os.getenv("SOCIALPILOT_API_BASE_URL", "").rstrip("/")
    if not b:
        raise RuntimeError("SOCIALPILOT_API_BASE_URL eksik")
    return b

def headers():
    t = os.getenv("SOCIALPILOT_API_TOKEN", "")
    if not t:
        raise RuntimeError("SOCIALPILOT_API_TOKEN eksik")
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

def extract_comment(extra):
    return extra.get("comment", "") if isinstance(extra, dict) else ""

def title_from(text):
    lines = [x.strip() for x in (text or "").splitlines() if x.strip()]
    if not lines:
        return ""
    title = lines[0]
    for a,b in {"Kolay":"Pratik","Muhteşem":"Lezzetli","Lokum Gibi":"Lokum Kıvamında","Çıtır":"Çıtır Çıtır"}.items():
        title = title.replace(a,b)
    return title

def comment_line(comment):
    return "Tarif İlk Yorumda" if "tarif" in (comment or "").lower() else "Bilgi İlk Yorumda"

def fetch_posts(cfg, page=1, limit=100):
    url = f"{api_base()}/posts/delivered"
    params = {"account": cfg["source_page_login_id"], "platform":"facebook", "limit":limit, "page":page}
    r = requests.get(url, headers=headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("response", {}).get("list", [])

def upload_media(img):
    r = requests.post(f"{api_base()}/media/upload", headers=headers(), json={
        "mediaType":"IMAGE","media":[{"url":img}],"openaiFileIdRefs":[]
    }, timeout=60)
    r.raise_for_status()
    return r.json()["response"]["mediaIds"][0]["mediaId"]

def create_post(login_id, desc, media_id, comment, schedule_time):
    r = requests.post(f"{api_base()}/posts/create", headers=headers(), json={
        "shareType":3,
        "scheduleDateTime":schedule_time.strftime("%Y-%m-%d %H:%M"),
        "loginIds":[login_id],
        "postData":{"postDesc":desc,"mediaId":[media_id],"comment":comment}
    }, timeout=60)
    r.raise_for_status()
    return r.json()

def rotate(items, n):
    return items[n % len(items):] + items[:n % len(items)] if items else items

def make_slots(cfg, count):
    ist = tz.gettz(cfg.get("timezone","Europe/Istanbul"))
    now = datetime.now(ist)
    sh, sm = map(int, cfg["daily_start_time"].split(":"))
    eh, em = map(int, cfg["daily_end_time"].split(":"))
    t = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    if now > t:
        t = now.replace(second=0, microsecond=0)
        mod = t.minute % cfg["slot_interval_minutes"]
        if mod:
            t += timedelta(minutes=cfg["slot_interval_minutes"]-mod)
    slots=[]
    while len(slots)<count:
        m = t.hour*60+t.minute
        allowed = (m >= sh*60+sm) or (m <= eh*60+em)
        if allowed:
            slots.append(t)
        t += timedelta(minutes=cfg["slot_interval_minutes"])
    return slots

def valid(post, cfg, used):
    c = extract_comment(post.get("extraData", {}))
    imgs = post.get("postImage") or post.get("thumbImage") or []
    return cfg["domain_filter"] in c and c not in used and bool(imgs)

def prepare_items(cfg, state):
    used=set(state.get("used_links", []))
    items=[]
    for page in range(999,0,-1):
        batch = fetch_posts(cfg,page=page,limit=100)
        if not batch:
            continue
        for p in reversed(batch):
            if valid(p,cfg,used):
                items.append(p)
                used.add(extract_comment(p.get("extraData", {})))
            if len(items)>=cfg["batch_posts_per_day"]:
                return items
    return items

def schedule_item(post, cfg, slot, rotation_index):
    comment = extract_comment(post.get("extraData", {}))
    imgs = post.get("postImage") or post.get("thumbImage") or []
    if not comment or not imgs:
        print("skip missing data", post.get("postId"), flush=True)
        return False
    media_id = upload_media(imgs[0])
    title = title_from(post.get("postDesc",""))
    desc = f"{title}\n{comment_line(comment)}"
    ok=0
    for i,login_id in enumerate(rotate(cfg["target_login_ids"], rotation_index)):
        when = slot + timedelta(minutes=i*cfg["page_offset_minutes"])
        try:
            create_post(login_id, desc, media_id, comment, when)
            ok += 1
            print("OK", when.strftime("%Y-%m-%d %H:%M"), login_id, title, flush=True)
        except Exception as e:
            print("FAIL", login_id, title, e, flush=True)
    return ok>0

def run_once():
    global LAST_STATUS
    print("Bot run started", datetime.now().isoformat(), flush=True)
    try:
        cfg=load_config()
        state=load_state()
        items=prepare_items(cfg,state)
        if not items:
            LAST_STATUS={"status":"idle","last_run":datetime.now().isoformat(),"message":"Uygun içerik yok veya auth eksik"}
            print("No items", flush=True)
            return
        slots=make_slots(cfg,len(items))
        used=state.get("used_links", [])
        for idx,post in enumerate(items):
            try:
                if schedule_item(post,cfg,slots[idx],idx):
                    c=extract_comment(post.get("extraData",{}))
                    if c not in used:
                        used.append(c)
                    state.update({"cursor_post_id":post.get("postId"),"used_links":used[-10000:],"last_run":datetime.now().isoformat()})
                    save_state(state)
            except Exception as e:
                print("SKIP", post.get("postId"), e, flush=True)
        LAST_STATUS={"status":"done","last_run":datetime.now().isoformat(),"message":"Tur tamamlandı"}
    except Exception as e:
        LAST_STATUS={"status":"error","last_run":datetime.now().isoformat(),"message":str(e)}
        print("BOT ERROR:", e, flush=True)

def loop():
    while True:
        run_once()
        time.sleep(int(os.getenv("RUN_EVERY_SECONDS","86400")))

@app.route("/")
def health():
    return jsonify(LAST_STATUS)

if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","8080")))