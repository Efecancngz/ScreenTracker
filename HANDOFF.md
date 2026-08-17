# Handoff — ScreenTracker
Son güncelleme: 2026-08-17, güncelleyen: Claude Opus 5

## Şu an ne yapılıyor
Faz 1 (MVP) implementasyonu `feat/screen-view-mvp` dalında tamamlandı. Tüm 14 task
bitti, ardından dal geneli final review yapıldı ve çıkan 8 bulgu (C1–C3, I4, I6,
I9–I11) tek bir fix dalgasında düzeltildi. Fonksiyonel olarak Faz 1 bitmiş
durumda; son bir re-review bekliyor.

Çalışan uçtan uca akış (aynı makinede tarayıcı ekran görüntüsüyle doğrulandı):
host app oturum kodu üretiyor → viewer 6 haneli kodla katılıyor → WebRTC
handshake tamamlanıyor → ekran görüntüsü viewer'da akıyor.

Testler: signaling-server 20 test, host-app 10 test, viewer-app 14 test — hepsi
geçiyor.

## Sıradaki somut adım
Gerçek bir TURN dağıtımıyla **ağlar arası (cross-network) doğrulama**. Kod tarafı
artık hazır: her iki uç da baseline olarak public Google STUN kullanıyor,
`TURN_SERVER_URL` / `TURN_USERNAME` / `TURN_PASSWORD` (tarayıcı için `VITE_`
önekli) set edilirse coturn relay'i ICE listesine ekleniyor. Yapılması gereken:
coturn'ü bir VM/Container Instance'a kur, env değişkenlerini doldur, host ve
viewer'ı farklı ağlardan bağla.

Engeller: dev makinesinde Azure CLI kurulu değil ve repo'nun henüz bir GitHub
remote'u yok — dağıtım öncesi ikisi de halledilmeli.

## Bilinmesi gerekenler
- Azure for Students hesabı doğrulandı, kaynak oluşturma çalışıyor
- TURN sunucusu (coturn) kalıcı UDP port istediği için Azure App Service'e değil,
  ayrı bir VM/Container Instance'a kurulacak; config `infra/` altında
- Config artık repo kökündeki tek `.env` dosyasından okunuyor (viewer-app'in
  Vite ayarında `envDir: '..'`). `cp .env.example .env` yeterli; TURN satırları
  yorumda, coturn kurulunca açılacak
- aiortc trickle ICE yapmıyor: host'un tüm adayları offer SDP'sinin içinde gidiyor,
  yani `ice-candidate` mesajını sadece viewer gönderiyor

## Bilinen açıklar (bilerek ertelendi, düzeltilmedi)
Tam liste: `.superpowers/sdd/2026-08-17-screentracker-mvp/progress.md` →
"Final whole-branch review".

Önemli olanlar:
- **I5**: oturum kodu entropisi (~30 bit) planın 128-bit hedefinin altında ve
  join denemelerine rate limiting yok
- **I7**: viewer'da ölü signaling bağlantısı için `onerror` / `isConnected`
  koruması yok — açık olmayan sokete `send()` uncaught hata fırlatıyor
- **I8**: ICE başarısızlığı için timeout/retry/kullanıcı mesajı yok (spec §5)

Minor'lar: ölü Vite template dosyaları (App.css, index.css, hero.png, react.svg,
vite.svg, icons.svg), boilerplate viewer-app/README.md ve index.html başlığı;
tsconfig.app.json'da `"strict": true` eksik; kullanılmayan
SIGNALING_SERVER_HOST/PORT değişkenleri; SessionJoinForm sunucunun hiç üretmediği
belirsiz karakterleri kabul ediyor; modül seviyesi global state signaling-server'ı
tek process'e bağlıyor (Azure App Service scale-out için decisions log'a not);
conftest.py'deki sys.modules hack'i;
test_nonwebsocket_exception_still_cleans_up docstring'inin iddia ettiği kapsamı
gerçekte test etmiyor.

## İlgili dosyalar
- docs/superpowers/specs/2026-08-17-remote-screen-view-design.md — Faz 1 tasarımı
- docs/superpowers/plans/2026-08-17-screentracker-mvp.md — uygulama planı
- docs/api-spec.md — signaling WebSocket sözleşmesi
- docs/architecture.md — bileşenler, akış diyagramı, kararlar
- .superpowers/sdd/2026-08-17-screentracker-mvp/progress.md — task raporları ve
  review bulguları

## Son 3 commit
- f09cee9 fix: read the repo-root .env in the viewer app and guard a missing signaling URL
- c6af75c test: pin the viewer's real wire payload shapes against the signaling endpoint
- fd1b2a3 fix: log swallowed signaling-server errors
