# SocialPilot Auto Scheduler Bot v2

Render Background Worker üzerinde çalışacak otomatik planlama botu.

## Ana özellikler
- Kaynak Facebook sayfasından / SocialPilot geçmişinden içerik alma mantığı
- 01.01.2025 başlangıç hedefi
- Eskiden yeniye ilerleme
- Sadece secmeyemektarifleri.com linkli içerikler
- Başlıkları aslına sadık kalarak hafif özgünleştirme
- Görsel + first comment ile paylaşım
- 07:30 - ertesi gün 02:00 arası çalışma
- Her 20 dakikada bir içerik slotu
- Her içerikte sayfalar arası 1 dakika offset
- Gün sonunda tüm sayfalar aynı içerik setini tamamlar, ama sıralama sayfalara göre kayar
- Hata olursa o postu atlar ve sıradaki kaynak postla devam eder
- Kaldığı yeri state.json içinde saklar

## Render ayarları
Render > New + > Background Worker

Build Command:
pip install -r requirements.txt

Start Command:
python bot.py

## Environment Variables
SOCIALPILOT_API_BASE_URL
SOCIALPILOT_API_TOKEN
SOURCE_PAGE_LOGIN_ID
TARGET_LOGIN_IDS
DOMAIN_FILTER
START_DATE
DAILY_START_TIME
DAILY_END_TIME
SLOT_INTERVAL_MINUTES
PAGE_OFFSET_MINUTES
RUN_EVERY_SECONDS

Not:
SOCIALPILOT_API_BASE_URL ve SOCIALPILOT_API_TOKEN değerlerini Render kurulumunda birlikte netleştireceğiz.