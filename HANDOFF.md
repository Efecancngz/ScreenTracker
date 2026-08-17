# Handoff — ScreenTracker
Son güncelleme: 2026-08-17, güncelleyen: Claude Sonnet 5

## Şu an ne yapılıyor
Faz 1 (MVP) implementasyonu `feat/screen-view-mvp` dalında tamamlandı, PR #1
açık: https://github.com/Efecancngz/ScreenTracker/pull/1. Final whole-branch
review'da çıkan 8 kritik/önemli bulgu (C1–C3, I4, I6, I9–I11) tek bir fix
dalgasında düzeltildi ve re-review temiz geldi.

**Local ağ üzerinden uçtan uca doğrulandı** (aynı WiFi'de PC↔telefon, farklı
cihazlar): host app oturum kodu üretiyor → viewer 6 haneli kodla katılıyor →
WebRTC handshake tamamlanıyor → ekran görüntüsü telefonun tarayıcısında canlı
akıyor. Bunu doğrularken karşılaşılan gerçek engeller (ve çözümleri, gelecekte
tekrar karşılaşılabilir): Windows Firewall Public ağda 8000/5173'ü
engelliyordu (izin kuralı eklendi), `.env` dosyasının worktree kökünde mi
gerçek repo kökünde mi okunduğu net değildi (worktree'nin kendi köküne göre
`envDir: '..'` çözümleniyor — worktree'de çalışıyorsan `.env` worktree
kökünde olmalı, ana repo kökünde değil).

Ardından kullanıcı isteğiyle **join denemelerine rate limiting** eklendi:
5 başarısız denemeden sonra üstel artan bekleme (2s→4s→8s...2 dakika tavan),
8 başarısız denemeden sonra bağlantı kapatılıyor.

Testler: signaling-server 30, host-app 10, viewer-app 15 (5 dosya) — hepsi
geçiyor (55 toplam).

## Sıradaki somut adım
Gerçek bir TURN dağıtımıyla **ağlar arası (cross-network, örn. mobil veri)
doğrulama**. Kod tarafı hazır: her iki uç da baseline olarak public Google
STUN kullanıyor, `TURN_SERVER_URL` / `TURN_USERNAME` / `TURN_PASSWORD`
(tarayıcı için `VITE_` önekli) set edilirse coturn relay'i ICE listesine
ekleniyor. Yapılması gereken: coturn'ü bir VM/Container Instance'a kur, env
değişkenlerini doldur, host ve viewer'ı gerçekten farklı ağlardan bağla.

Engel: dev makinesinde Azure CLI hâlâ kurulu değil — GitHub remote artık var
(bu handoff'un kendisi PR #1'e push edildi), o kısım halloldu.

## Bilinmesi gerekenler
- Azure for Students hesabı doğrulandı, kaynak oluşturma çalışıyor
- TURN sunucusu (coturn) kalıcı UDP port istediği için Azure App Service'e değil,
  ayrı bir VM/Container Instance'a kurulacak; config `infra/` altında
- Config repo kökündeki tek `.env` dosyasından okunuyor (viewer-app'in Vite
  ayarında `envDir: '..'`) — **worktree içinde çalışıyorsan bu, worktree'nin
  kendi kökü demek**, ana repo kökü değil. `cp .env.example .env` her ikisinde
  de (worktree ve ana checkout) ayrı ayrı yapılmalı
- aiortc trickle ICE yapmıyor: host'un tüm adayları offer SDP'sinin içinde
  gidiyor, yani `ice-candidate` mesajını sadece viewer gönderiyor
- Rate limiting bellekte, tek process — sabitler `signaling-server/app/rate_limiter.py`
  (FAILURE_THRESHOLD=5, MAX_BACKOFF_SECONDS=120, KICK_THRESHOLD=8)

## Bilinen açıklar (bilerek ertelendi, düzeltilmedi)
- **I7**: viewer'da ölü signaling bağlantısı için `onerror` / `isConnected`
  koruması yok — açık olmayan sokete `send()` uncaught hata fırlatıyor
- **I8**: ICE başarısızlığı için timeout/retry/kullanıcı mesajı yok (spec §5)
- Oturum kodu entropisi (~30 bit) planın orijinal 128-bit hedefinin altında —
  bilinçli UX tercihi (kısa, elle yazılabilir kod), rate limiting eklenmesiyle
  kısmen telafi edildi ama tam çözüm değil

Minor'lar: ölü Vite template dosyaları (App.css, index.css, hero.png, react.svg,
vite.svg, icons.svg), boilerplate viewer-app/README.md ve index.html başlığı;
tsconfig.app.json'da `"strict": true` eksik; kullanılmayan
SIGNALING_SERVER_HOST/PORT değişkenleri; SessionJoinForm sunucunun hiç üretmediği
belirsiz karakterleri kabul ediyor; modül seviyesi global state signaling-server'ı
tek process'e bağlıyor (Azure App Service scale-out için decisions log'a not);
conftest.py'deki sys.modules hack'i.

## İlgili dosyalar
- docs/superpowers/specs/2026-08-17-remote-screen-view-design.md — Faz 1 tasarımı
- docs/superpowers/plans/2026-08-17-screentracker-mvp.md — uygulama planı
- docs/api-spec.md — signaling WebSocket sözleşmesi (rate limiting dahil)
- docs/architecture.md — bileşenler, akış diyagramı, kararlar
- PR #1: https://github.com/Efecancngz/ScreenTracker/pull/1 — final review
  bulgularının ve fix dalgasının tam kaydı yorumlarda

## Son 3 commit
- 07ee4c2 chore: raise rate-limit free-attempt threshold to 5, max backoff to 2 minutes
- adafc3d docs: document join rate limiting in the API spec
- 4fcac61 feat: show wait time when the viewer is rate-limited
