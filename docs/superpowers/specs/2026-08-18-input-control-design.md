# ScreenTracker — Faz 2: Uzaktan Input Kontrolü Tasarımı

**Tarih:** 2026-08-18
**Durum:** Onaylandı, implementasyon planı bekleniyor
**Kapsam:** Faz 1 + device pairing'in üzerine — viewer'daki dokunma/mouse/klavye
girdisini host'ta OS-seviyesi input'a çevirir. Sinyalizasyon protokolüne yeni
mesaj eklemez; mevcut WebRTC bağlantısına ikinci bir kanal (DataChannel) ekler.

## 0. Problem & Gereksinimler

### Problem tanımı

Faz 1 + device pairing ile kullanıcı kendi PC'sinin ekranını herhangi bir
cihazından, herhangi bir ağdan izleyebiliyor — ama sadece izleyebiliyor.
Orijinal motivasyonun bir parçası olan "elimde olmayan PC'de bir işlem
yapabilmek" (örn. League şampiyon seçimi, açık bir programı kapatmak,
indirilen bir dosyayı onaylamak) hâlâ karşılanmıyor.

### Fonksiyonel gereksinimler

- Viewer'da video üzerinde dokunma/tıklama → host'ta sol tık
- Uzun basış → host'ta sağ tık
- Basılı tutup sürükleme → host'ta mouse-down + move + mouse-up (drag)
- İki parmakla kaydırma (veya viewer'da fare tekerleği) → host'ta scroll
- Bir metin girişi alanına odaklanıldığında yazılan her şey (ekran klavyesi
  veya telefona/tablete bağlı harici klavye — ikisi de tarayıcıya aynı
  `KeyboardEvent` olarak gelir) → host'ta karşılık gelen tuş basımı
- Video elementinin gösterdiği alan ile host'un gerçek ekran çözünürlüğü
  farklı olabilir (farklı pencere boyutu, farklı cihaz) — koordinatlar bu
  farkı gözeterek doğru noktaya denk gelmeli

### Fonksiyonel olmayan gereksinimler

- **Yetkilendirme:** ayrı bir onay adımı yok — mevcut device pairing
  onayını almış (ekranı izleyebilen) her cihaz otomatik olarak input
  gönderebilir. Bu bilinçli bir kapsam kararı, aşağıda "Güvenlik" bölümünde
  gerekçelendirilir.
- **Gecikme:** mevcut WebRTC bağlantısı üzerinden (DataChannel), signaling
  server'a hiç uğramadan — Faz 1'in "saniyenin altı hedef değil" toleransı
  video için geçerliliğini korur, ama input event'leri kendi doğası gereği
  (DataChannel, ordered+reliable) düşük gecikmeli olacaktır
- **Platform:** host tarafında `pynput` — Windows/macOS/Linux'ta çalışır;
  macOS'ta Accessibility izni gerektirir (bkz. Hata Yönetimi)
- **Tek ekran varsayımı:** Faz 1'deki gibi host'un birincil monitörü (`mss`
  `monitor_index=1`) — çoklu monitör arası fare hareketi kapsam dışı

### Güvenlik: neden ayrı bir onay adımı yok

Pairing zaten "bu cihaza PC'nizin ekranını gösterecek kadar güveniyorum"
demek — ekranı görebilen bir cihaza ayrıca "ama kontrol edemez" demenin
kullanıcı için pratik bir faydası yok (kendi cihazları arası kullanım
senaryosu, üçüncü şahıslara paylaşılan bir link değil). Ekstra bir "input
izni" anahtarı, günlük kullanımda atlanan/unutulan bir adım olurdu. Bu,
bilinçli olarak kabul edilen bir risk: eşleştirilmiş **her** cihaz tam
kontrol kazanır.

## 1. Mimari

### DataChannel, sinyalizasyon protokolüne dokunmadan

WebRTC'nin `RTCDataChannel`'ı, mevcut offer/answer SDP değişimi içinde
otomatik olarak müzakere edilir — signaling server'a yeni bir mesaj tipi
eklemeye gerek yok. Host (offer'ı oluşturan taraf) `createOffer()`'dan önce
`pc.createDataChannel("input")` çağırır; viewer'ın `RTCPeerConnection`'ı
`ondatachannel` event'iyle kanalı otomatik alır. Kanal bidirectional'dır —
viewer üzerinden gönderir, host üzerinden dinler.

### Koordinat eşleme

Viewer, `<video>` elementinin gösterdiği alan üzerindeki pointer
koordinatını `(x / videoWidth, y / videoHeight)` şeklinde **normalize
edip** (0-1 arası) gönderir — video elementinin CSS boyutu host'un gerçek
ekran çözünürlüğünden farklı olsa da bu oran sabit kalır. Host, mesajı
alınca kendi bildiği ekran boyutuyla (`mss` monitor bilgisi) çarpıp gerçek
piksel koordinatını hesaplar.

## 2. Bileşenler

1. **`viewer-app/src/hooks/useInputControl.ts`** (yeni) — video elementine
   `pointerdown`/`pointermove`/`pointerup`/`wheel`/`keydown`/`keyup`
   dinleyicileri bağlar; tek dokunma / uzun basış (sağ tık) / sürükleme
   ayrımını yapar (basit bir zamanlayıcı + hareket eşiği ile); normalize
   koordinatlı mesajları DataChannel'a `send()` eder
2. **`viewer-app/src/components/VideoPlayer.tsx`** (mevcut, genişletilecek)
   — `useInputControl`'ü bağlamak için video elementine ref + input
   kontrolünün açık/kapalı olduğunu gösteren küçük bir görsel gösterge
3. **`host-app/screentracker_host/input_injector.py`** (yeni) — `pynput`
   sarmalayıcısı: `move_to`, `press`/`release` (mouse + klavye), `scroll`;
   normalize koordinatı gerçek piksele çeviren saf fonksiyon ayrı test
   edilebilir olacak şekilde
4. **`host-app/screentracker_host/webrtc_peer.py`** (mevcut, genişletilecek)
   — `HostPeerConnection`, offer öncesi `createDataChannel("input")`
   çağırır, kanalın `on("message")` handler'ını `input_injector`'a bağlar

## 3. Mesaj Formatı (DataChannel, JSON, sinyalizasyon protokolünden bağımsız)

| Mesaj | Alanlar | Anlamı |
|---|---|---|
| `pointer-down` | `x, y` (0-1), `button: "left" \| "right"` | Basış başladı |
| `pointer-move` | `x, y` | Basılıyken hareket (drag) |
| `pointer-up` | `x, y`, `button` | Basış bitti — `down`/`up` aynı konumdaysa tık, farklıysa drag |
| `wheel` | `deltaX, deltaY` | Scroll |
| `key-down` | `key` (örn. `"a"`, `"Enter"`, `"Shift"`) | Tuşa basıldı |
| `key-up` | `key` | Tuş bırakıldı |

Uzun basış (sağ tık), viewer tarafında zaman eşiğiyle tespit edilip
`button: "right"` olarak tek bir `pointer-down`/`pointer-up` çiftine
çevrilir — host'a ayrı bir mesaj tipi olarak yansımaz.

## 4. Hata Yönetimi

- DataChannel henüz açılmadıysa (`readyState !== "open"`) viewer input
  event'lerini sessizce yok sayar — kullanıcıya hata gösterilmez, video
  akışı etkilenmez
- Host, gelen `x`/`y` değerlerini `[0, 1]` aralığına clamp'ler (bozuk/kötü
  niyetli bir mesaj ekran dışına fare göndermesin diye)
- macOS'ta `pynput` için Accessibility izni verilmemişse, ilk input
  mesajında bunu tespit edip **bir kez** konsola net bir uyarı basar
  (`"Input control requires Accessibility permission — see System
  Settings > Privacy & Security"`), sonraki input mesajlarını sessizce
  yok sayar; video akışı bundan etkilenmez
- `pynput` çağrısı beklenmedik bir istisna fırlatırsa (ör. desteklenmeyen
  tuş adı), host bunu loglar ve o tek mesajı atlar — host süreci çökmez
  (Task 10'da öğrenilen dersin burada da geçerli olması: input handler'daki
  hiçbir istisna host'un ana döngüsünü çökertmemeli)

## 5. Test Stratejisi

- **host-app:** `input_injector.py`'de saf koordinat-dönüşüm fonksiyonu
  (normalize → piksel, clamp davranışı) birim testli; `pynput` çağrıları
  mock'lanarak mesaj-tipi → doğru `pynput` metodu çağrısı eşlemesi
  doğrulanır
- **viewer-app:** `useInputControl` için gesture ayrımı (tık/uzun
  basış/sürükleme) sentetik pointer event'lerle test edilir; DataChannel
  kapalıyken event'lerin sessizce yok sayıldığı ayrıca test edilir
- **Manuel E2E:** gerçek cihazlarla (bugünkü Tailscale kurulumu üzerinden)
  tık, sağ tık, sürükleme, scroll, klavye — Faz 1/pairing'de olduğu gibi
  otomatikleştirmesi zor, manuel doğrulama + ledger'a not

## 6. Kapsam Dışı (bilinçli olarak bu spec'e dahil edilmedi)

- Host ekranında uzak cursor'ın konumunu gösteren bir overlay (nice-to-have,
  ayrı bir iyileştirme olarak ele alınabilir)
- Çoklu monitör arası fare hareketi
- Input kontrolü için ayrı bir izin/onay adımı (yukarıda gerekçelendirildi)
- Pano (clipboard) senkronizasyonu (kopyala/yapıştır) — ayrı bir özellik
- Dosya sürükle-bırak transferi — ayrı bir özellik
