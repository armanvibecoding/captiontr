# captiontr

Kısa dikey videolardaki (Reels / TikTok / Shorts) **ekrana gömülü yazıları bulur, siler ve aynı stilde
Türkçesini basar.** Çıktının metadata'sını temizler ve temizliği doğrular. macOS'ta çalışır.

> *English:* captiontr localizes burned-in captions on short vertical videos. It finds the on-screen text with
> Apple Vision OCR, removes it (temporal background fill / TELEA / cover box), re-renders the translation in the
> same style (font size, weight, outline, boxed captions, emoji), and strips container + bitstream metadata.

## Nasıl kullanılır (yapay zekâ asistanıyla — önerilen)

Klasörü Mac'te **Codex CLI**, Claude Code ya da Gemini CLI ile aç ve videoları (dosya ya da link) gönder.
`AGENTS.md` / `CLAUDE.md` / `GEMINI.md` asistanı [`docs/MASTER-PROMPT.md`](docs/MASTER-PROMPT.md)'deki çalışma
sistemine bağlar:

1. **Ürünü tanır, marka adını sorar.** Farklı ürünleri ayırır ("2 farklı ürün var, marka adları ne?"); sohbette
   sonradan yeni bir ürün gelirse "bu farklı bir ürün, marka adı ne?" der. Bilinen ürünü sormadan markasına ekler.
2. Yazıları siler, Türkçesini aynı stilde basar, her videoyu kontrol eder.
3. **Masaüstüne teslim eder:** `~/Desktop/CaptionTR/<Marka>/1.mp4, 2.mp4, 3.mp4…` + paylaşım planı `plan.csv`
   (tarih, saat, açıklama, hashtag). Numara ve takvim her teslimde kaldığı yerden devam eder.

Kullanıcıya sorulan tek şey marka adıdır; teknik ayrıntı konuşulmaz.

```bash
cd captiontr && codex
# "Bu videoları Türkçeleştir: ~/Downloads/videolar/"
```

## Komutlar

```
ekle ──► marka ──► analiz ──► çeviri (asistan) ──► cevir ──► dogrula ──► teslim
```

| Adım | Komut | Sonuç |
|---|---|---|
| Ekle | `captiontr ekle <dosya/klasör/link…>` | Her video `is/<ad>-<kod>/kaynak.mp4` (metadata temiz) + `onizleme.jpg`; aynı dosya iki kez eklenmez |
| Marka | `captiontr marka <video…> --ad Lumo --urun "gece lambası"` | Videoyu markaya bağlar; yeni marka `is/markalar.json`'a kaydedilir |
| Markalar | `captiontr markalar` | Kayıtlı markalar + markası atanmamış videolar |
| Analiz | `captiontr analiz` | OCR: yazılar, zamanları, satır kutuları, stil → taslak `ayar.json` + `tablo.png` |
| Çeviri | `ayar.json` → `satirlar`, `gonderi` | Türkçe satırlar + paylaşım açıklaması, `"cevrildi": true` |
| Render | `captiontr cevir` | Eski yazı silinir, yenisi basılır → `TR.mp4` + `TR_kontrol.png` |
| Doğrulama | `captiontr dogrula` | Çıktıda eski yazıdan okunabilen iz var mı |
| Teslim | `captiontr teslim [--baslangic 2026-12-01] [--saat 10:00,18:00]` | `~/Desktop/CaptionTR/<Marka>/N.mp4` + `plan.csv` (varsayılan: yarından itibaren marka başına günde 1, 18:00) |
| Metadata | `captiontr temizle <dosya/klasör>` | Herhangi bir videonun metadata'sını siler, kalan izi raporlar |
| Durum | `captiontr durum` | Hangi video hangi aşamada, markası, teslim yeri |
| Toplu indirme | `captiontr indir liste.csv` · `captiontr bilgi liste.csv aday.csv` | CSV'den indirme · indirmeden izlenme/beğeni |
| Tekrar avı | `captiontr tekrar` · `captiontr temas x.jpg` | Aynı çekimi içeren videolar (dHash) · kare kolajı |

Çalışma alanı varsayılan `is/`; başka bir klasör için komutun sonuna yolu yaz.

## Kurulum (macOS, Apple Silicon ya da Intel)

```bash
git clone https://github.com/armanvibecoding/captiontr && cd captiontr
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e ".[dev]"
.venv/bin/captiontr --help
.venv/bin/python -m pytest -q
```

- ffmpeg ayrıca kurulmaz, `imageio-ffmpeg` paketinden gelir.
- OCR için macOS Vision çerçevesi kullanılır (`pyobjc-framework-Vision`). Render ve testler OCR gerektirmez.
- 8 GB RAM yeterli: render iki geçişli ve akışlıdır (1080p 25 sn ≈ 1 GB).
- Telefon videosundaki döndürme bilgisi `ekle` sırasında görüntüye uygulanır (yalnız o durumda yeniden kodlanır).

## Klasör yapısı

```
is/
  markalar.json              # marka → ürün tanımı + önizleme
  proje.json                 # tüm videolara ortak ayar (ör. son_yazi), isteğe bağlı
  <ad>-<kod>/
    kaynak.mp4  meta.json  onizleme.jpg   # ekle (+ marka, teslim bilgisi meta.json'da)
    ayar.json   tablo.png                 # analiz (+ çeviri)
    TR.mp4      TR_kontrol.png            # cevir
~/Desktop/CaptionTR/<Marka>/
  1.mp4  2.mp4  …  plan.csv               # teslim
```

`is/`, `*.mp4` ve indirilen emoji görselleri git'e girmez.

## Yazı stilleri

`analiz` her yazının stilini kendisi belirler (`altyazilar[].stil`):

- **kenarli:** beyaz yazı, varsa siyah kenarıyla. Font boyu orijinal satır genişliğinden, ağırlık harf kalınlığından
  (TikTok Sans 300–800), kenar kalınlığı orijinalden ölçülür.
- **kutulu:** beyaz kutu içinde koyu yazı ("arka planlı" stil). Kutu yüksekliği, iç boşluk, kutu ve yazı rengi
  orijinalden ölçülür; kutu ve içindeki harfler tek parça silinir.

Elle ezilebilen alanlar (`ayar.json`): `font_px`, `agirlik`, `kenar_px`, `font` (ör. `/System/Library/Fonts/NewYork.ttf`),
`kutu_renk`, `yazi_renk`, `bant`, `ornek_sn`, `aralik`, `ek_kutular`, `sabit_zaman`.

**Son çağrı yazısı:** `proje.json` her videoya uygulanır (videonun kendi ayarı önceliklidir):

```json
{"son_yazi": {"metin": "Yorumlara “ÜRÜN” yaz, linkini göndereyim 📩", "sure": 2.5, "y_oran": 0.70}}
```

## Silme yöntemleri

| `ayar.json` | Ne yapar | Ne zaman |
|---|---|---|
| `"silme": "zamansal"` (varsayılan) | Yazının altındaki gerçek görüntüyü komşu karelerden getirir (ORB + RANSAC homografi); dolmayan pikseller TELEA ile kapanır, oran `TR_dolgu.json`'a yazılır | Sabit kamera, yavaş hareket |
| `"silme": "telea"` | OpenCV TELEA inpaint | Hızlı kamera/özne hareketi |
| `"kapak": "satir"` | Yazının arkasına satır boyunda yarı saydam koyu kutu | Yazı el/yüz üstündeyse, en güvenli teslim |
| `"maske": "hassas"` | Silme maskesini pikselin zaman içindeki oynaklığından ölçer (kenar, yumuşatma, gölge) | İnce kenarlı / gölgeli yazı |

Maske kalitesi ölçülebilir: `python -m captiontr.maske_olc uret|olc` gerçek videolara **bilinen** yazı basar ve
maskenin kaçırdığı / fazladan sildiği pikselleri sayar.

### Denenip bırakılanlar

| Yöntem | Neden bırakıldı |
|---|---|
| big-lama (tek kare inpainting) | Videoda sonuç beğenilmedi |
| Optik akışla doldurma | Parçalı boya, yanlış yerden nesne taşıdı, 3× yavaş |
| ProPainter | Kalite iyi ama 8 GB RAM'e sığmıyor |
| E2FGVI / DiffuEraser | Bellek ya da lisans (ticari kullanım) engeli |

## Metadata

Her indirilen ve render edilen dosyada, **yeniden kodlamadan**:

- global ve akış etiketleri, oluşturma zamanı, bölümler, `handler_name` / `vendor_id` / `encoder`,
- kapak ve veri akışları (yalnız ilk video + ilk ses akışı tutulur),
- cihaz yan verileri (ör. iPhone ortam ışığı `amve`) — MKV ara adımıyla,
- H.264 SEI (NAL 6, x264 ayar imzası) / H.265 SEI (NAL 39/40)

silinir; `-fflags +bitexact` ile ffmpeg kendi imzasını yazmaz.

`metadata_rapor` iki katmanda doğrular: ffmpeg'in okuduğu etiketler + dosya baytlarında bilinen imzalar
(`Lavf`, `x264 - core`, XMP, `creation_time`, `©xyz` GPS, uygulama adları…). Boş liste = temiz. 4 baytlık kutu
adları sıkıştırılmış veride tesadüfen geçebildiği için yalnız `mdat` dışında aranır.

Döndürme bilgisi (`displaymatrix`) olan video temizlenmez, hata verir — temizlik yönü bozabilir.

## Sınırlar

- Yazının beyaz ya da beyaz kutulu olduğu varsayılır; renkli yazıda analiz uyarı verir.
- Ekranın uzak iki yerindeki eş zamanlı yazılar tek bant varsayımını bozar (analiz uyarır).
- Yazı el, yüz ya da hızlı hareket eden bir şeyin üstündeyse hiçbir yöntem kusursuz silmez → `kapak`.
- Ekrandaki filigranlara dokunulmaz.

## Sorumlu kullanım

Bu araç **hakkına sahip olduğun ya da kullanım izni aldığın** videoları yerelleştirmek içindir (kendi içeriğin,
lisansladığın ya da iş birliği yaptığın üreticinin içeriği). Başkasının videosunu izinsiz yeniden yayınlamak telif
hakkını ve platform kurallarını ihlal edebilir; sorumluluk kullanıcıdadır. Metadata temizliği gizlilik içindir
(konum, cihaz, yazılım izleri) — platformların içerik eşleştirmesini atlatmak için tasarlanmamıştır.

## Lisans

Kod: [MIT](LICENSE). Font: TikTok Sans, [SIL Open Font License 1.1](captiontr/varliklar/OFL.txt).
Emoji görselleri depoda yoktur; ilk kullanımda `emoji-datasource-apple` paketinden indirilir ve kendi lisansına tabidir.
