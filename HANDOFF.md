# Handoff — ScreenTracker
Son güncelleme: 2026-08-18, güncelleyen: Claude Sonnet 5

## Şu an ne yapılıyor
Faz 1 (MVP) `feat/screen-view-mvp` dalında tamamlandı, PR #1 açık:
https://github.com/Efecancngz/ScreenTracker/pull/1. Local ağ üzerinden
(aynı WiFi, PC↔telefon) uçtan uca doğrulandı.

**Cihaz eşleştirme (device pairing) özelliği** ayrı bir plan olarak
(`docs/superpowers/plans/2026-08-17-device-pairing-and-deployment.md`)
subagent-driven-development ile uygulandı — **10/10 task tamamlandı.**
- Signaling server: `register-host`/`authenticate`/`pair-approved`/
  `pair-rejected`/`authenticate-failed`/`release-peer` mesajları, host_id
  bazlı session lookup
- Host app: kalıcı `host_identity.json`/`paired_devices.json`, 60s
  zaman aşımlı terminal onay prompt'u
- Viewer app: cihaz kimliği + kalıcı token (`localStorage`), otomatik
  authenticate akışı
- Deployment dokümantasyonu: Tailscale birincil/test edilmiş, Azure ve
  tünel servisleri test edilmemiş/topluluk-destekli olarak işaretli
- Final review'da 1 gerçek güvenlik açığı bulunup düzeltildi (device_id
  VE token ikisi de eksikse host onaysız stream başlatıyordu)
- **Task 10 sırasında bulunan gerçek bir hata düzeltildi**: host app'ın
  eşleştirme onay prompt'u (`input()`), stdin interaktif olmadığında
  (arka planda/subprocess/launcher script üzerinden çalıştırıldığında)
  `EOFError` fırlatıyordu ve bu hiçbir yerde yakalanmıyordu — host app'ın
  tamamen çökmesine sebep oluyordu. Viewer bu durumda sonsuza kadar
  "JOINING" durumunda kalıyordu (host'un WebSocket bağlantısı koptuğu
  için sessiz görünüyordu). Detaylar aşağıda ve
  `.superpowers/sdd/2026-08-17-device-pairing-and-deployment/progress.md`'de.

Tüm otomatik testler yeşil: signaling-server 44/44, host-app 27/27
(26 + yeni EOFError testi), viewer-app 24/24, `npm run build` temiz.
Manuel E2E ile de tüm senaryolar (onaylı, reddedilmiş, stdin'siz-çökme
düzeltmesi, token ile reconnect, yanlış token) gerçek sunucu + gerçek
host app ile doğrulandı.

## Dünkü hatanın kök nedeni (artık düzeltildi)
`host-app/screentracker_host/pairing.py`'deki `request_approval()`,
onay prompt'unu `loop.run_in_executor(None, input, ...)` ile çalıştırıyor.
Host app'ın stdin'i interaktif bir terminale bağlı değilse (ör. arka
planda bir launcher/subprocess'ten çalıştırıldığında), `input()` çağrısı
anında `EOFError` fırlatıyordu. Bu istisna hiçbir yerde yakalanmadığı
için `_handle_peer_joined` → `run()`'ın `async for` döngüsü boyunca
yükseliyor ve **host app'ı komple çökertiyordu**. Viewer tarafında bu,
hiçbir mesaj gelmeden sonsuz "JOINING" durumu olarak görünüyordu (host'un
WebSocket bağlantısı koptuğu için `peer-disconnected` gelebiliyordu ama
bu her zaman gözlemlenebilir değildi). Bu, "bir kez çalıştı, sonra
tekrarlanmadı" bulgusunu tam olarak açıklıyor: sadece host app gerçek bir
interaktif terminalde çalıştığında (insan y/n yazabildiğinde) EOFError
oluşmuyordu.

**Düzeltme:** `request_approval()`, `asyncio.TimeoutError`'ın yanında
`EOFError`'ı da yakalayıp `False` (reddedildi) dönüyor artık — timeout ile
aynı davranış. Tek satırlık, kök nedene yönelik düzeltme;
`test_returns_false_when_stdin_has_no_data` testi eklendi.

## Sıradaki adım
Device pairing planı tamamlandı (10/10 task). Sıradaki mantıklı adım: bu
değişiklikleri PR #1'e push edip (aynı branch üzerinde geliştirildi, ayrı
bir PR değil), gerekirse whole-branch final review'ı device pairing
commit'lerini de kapsayacak şekilde tekrar çalıştırmak. Sonrasında Faz 2
(input kontrolü) veya Azure/cross-network deploy testi konuşulabilir —
ikisi de şu an aktif değil.

## Bilinmesi gerekenler
- Azure for Students hesabı doğrulandı, kaynak oluşturma çalışıyor
- TURN sunucusu (coturn) kalıcı UDP port istediği için Azure App Service'e değil,
  ayrı bir VM/Container Instance'a kurulacak; config `infra/` altında
- **Tailscale birincil deployment yolu olarak seçildi** (Azure değil) —
  kullanıcının kendi cihazları arasında kullanım senaryosu için daha basit,
  TURN'e bile gerek kalmayabilir. `docs/deployment.md`'de adımlar var.
- Config repo kökündeki tek `.env` dosyasından okunuyor (viewer-app'in Vite
  ayarında `envDir: '..'`) — **worktree içinde çalışıyorsan bu, worktree'nin
  kendi kökü demek**, ana repo kökü değil. Bugün bu hatayı ben de tekrar
  yaptım (test için `.env.local`'ı yanlış yere koydum) — dikkat.
- aiortc trickle ICE yapmıyor: host'un tüm adayları offer SDP'sinin içinde
  gidiyor, yani `ice-candidate` mesajını sadece viewer gönderiyor
- Rate limiting bellekte, tek process — sabitler `signaling-server/app/rate_limiter.py`
  (FAILURE_THRESHOLD=5, MAX_BACKOFF_SECONDS=120, KICK_THRESHOLD=8)
- Pairing: `host_id` kalıcı (`host_identity.json`), oturum kodu hâlâ kısa
  ömürlü — ilk bağlantıda host terminalinde onay istenir, onaylanan cihaz
  bir daha kod girmeden bağlanır

## Bilinen açıklar (bilerek ertelendi, düzeltilmedi)
- **I7**: viewer'da ölü signaling bağlantısı için `onerror` / `isConnected`
  koruması yok — açık olmayan sokete `send()` uncaught hata fırlatıyor
- **I8**: ICE başarısızlığı için timeout/retry/kullanıcı mesajı yok (spec §5)
- Oturum kodu entropisi (~30 bit) planın orijinal 128-bit hedefinin altında —
  bilinçli UX tercihi, rate limiting ile kısmen telafi edildi

Minor'lar: ölü Vite template dosyaları, boilerplate README/index.html başlığı;
tsconfig.app.json'da `"strict": true` eksik; kullanılmayan
SIGNALING_SERVER_HOST/PORT değişkenleri; conftest.py'deki sys.modules hack'i.

## İlgili dosyalar
- docs/superpowers/specs/2026-08-17-remote-screen-view-design.md — Faz 1 tasarımı
- docs/superpowers/specs/2026-08-17-device-pairing-and-deployment.md — pairing tasarımı
- docs/superpowers/plans/2026-08-17-screentracker-mvp.md — Faz 1 planı
- docs/superpowers/plans/2026-08-17-device-pairing-and-deployment.md — pairing planı
- .superpowers/sdd/2026-08-17-device-pairing-and-deployment/progress.md —
  tüm task'ların ledger'ı, Task 10'un EOFError kök neden analizi burada
- docs/api-spec.md, docs/architecture.md, docs/deployment.md
- PR #1: https://github.com/Efecancngz/ScreenTracker/pull/1

## Son 3 commit
- 72be6c1 docs: add deployment guide and document device pairing
- aed3e74 feat: auto-authenticate paired devices and handle pairing states in the viewer
- 24c9fec feat: add viewer device identity and stored-pairing helpers
