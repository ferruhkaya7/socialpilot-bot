# SocialPilot Browser Automation Bot

Bu sürüm SocialPilot API kullanmaz. Playwright ile tarayıcıdan SocialPilot paneline giriş yapıp senin manuel yaptığın işlemleri otomatik yapar.

## Kurulum

Railway veya lokal bilgisayar için:

Build Command:
pip install -r requirements.txt && playwright install chromium

Start Command:
python bot.py

## Railway Variables

SOCIALPILOT_EMAIL
SOCIALPILOT_PASSWORD
DOMAIN_FILTER
DAILY_START_TIME
DAILY_END_TIME
SLOT_INTERVAL_MINUTES
PAGE_OFFSET_MINUTES

## Önemli

Bu sürüm UI otomasyonudur. İlk çalıştırmada SocialPilot giriş ekranı, 2FA veya captcha çıkarsa manuel session gerekebilir.
Session mantığı için ileride storage_state.json kullanılabilir.

## Bot mantığı

- Kaynak içerikleri toplar
- Sadece secmeyemektarifleri.com linkli içerikleri alır
- Başlığı aslına sadık kalarak özgünleştirir
- Görseli kullanır
- First comment linkini ekler
- 07:30 - 02:00 arası 20 dakikalık slot üretir
- Her sayfaya 1 dakika arayla planlar
- Gün sonunda tüm sayfalar aynı içerik setini tamamlar