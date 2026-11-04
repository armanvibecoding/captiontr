# captiontr

Kısa dikey videolardaki (Reels / TikTok / Shorts) **ekrana gömülü yazıları bulur, opak siyah kutuyla
örter ve Türkçesini orijinal boyda basar**; sona CTA ekler. Çıktının metadata'sını temizler ve temizliği doğrular.
**macOS, Windows ve Linux'ta çalışır.**

> *English:* captiontr localizes burned-in captions on short vertical videos. It finds the on-screen text (Apple Vision OCR
> on macOS, RapidOCR on Windows/Linux), covers it with an opaque black box holding the translation at the original
> font size and position, appends a mandatory end-screen CTA, and strips container + bitstream metadata.

## Nasıl kullanılır (yapay zekâ asistanıyla — önerilen)

Klasörü **Codex CLI**, Claude Code ya da Gemini CLI ile aç ve videoları (dosya ya da link) gönder.
`AGENTS.md` / `CLAUDE.md` / `GEMINI.md` asistanı [`docs/MASTER-PROMPT.md`](docs/MASTER-PROMPT.md)'deki çalışma
sistemine bağlar:

1. **Kopyaları ayıklar.** Yeni gelen her video önceki tüm videolarla görüntüden karşılaştırılır: başka hesaptan,
   başka kalitede, aynalanmış ya da başka yazıyla gelen aynı video tekrar hazırlanmaz.
2. **Ürünü tanır, marka adını sorar.** Farklı ürünleri ayırır ("2 farklı ürün var, marka adları ne?"); sohbette
   sonradan yeni bir ürün gelirse "bu farklı bir ürün, marka adı ne?" der. Bilinen ürünü sormadan markasına ekler.
3. Yazının üstünü opak siyah kutuyla kapatır, Türkçesini orijinal boyda ve yerinde beyaz basar; sona zorunlu
   CTA ekler (CTA'sız video render edilmez). **TikTok/Instagram yorum balonlarını** ("…'s comment'e yanıt") Türkçe
   balonla değiştirir. **Her videoya farklı bir hook** yazar; aynı markada tekrar eden giriş render edilmez.
4. Her videoyu kontrol eder.
5. **Masaüstüne teslim eder:** `~/Desktop/CaptionTR/<Marka>/1.mp4, 2.mp4, 3.mp4…` + paylaşım planı `plan.csv`
   (tarih, saat, açıklama, hashtag). Numara ve takvim her teslimde kaldığı yerden devam eder.

Kullanıcıya sorulan tek şey marka adıdır; teknik ayrıntı konuşulmaz.

```bash
cd captiontr && codex
# "Bu videoları Türkçeleştir: ~/Downloads/videolar/"
```

## Komutlar

```
ekle (+kopya kontrolü) ──► marka ──► analiz ──► çeviri + hook (asistan) ──► cevir ──► dogrula ──► teslim
```

| Adım | Komut | Sonuç |
|---|---|---|
| Ekle | `captiontr ekle <dosya/klasör/link…>` | Her video `is/<ad>-<kod>/kaynak.mp4` (metadata temiz) + `onizleme.jpg`; aynı dosya iki kez eklenmez; kopya / ortak çekim kontrolü (aşağıda) |
| Kopya kararı | `captiontr kopya <video> --evet\|--hayir` | Kopya şüphesi: `--evet` → `is/_kopyalar/`'a taşınır (silinmez), `--hayir` → işlenir |
| Marka | `captiontr marka <video…> --ad Lumo --urun "gece lambası"` | Videoyu markaya bağlar; yeni marka `is/markalar.json`'a kaydedilir |
| Markalar | `captiontr markalar` | Kayıtlı markalar + markası atanmamış videolar |
| Analiz | `captiontr analiz` | OCR: yazılar, zamanları, satır kutuları, stil → taslak `ayar.json` + `tablo.png` |
| Çeviri | `ayar.json` → `satirlar`, `yorumlar[].metin`, `gonderi` | Türkçe satırlar, yorum balonları, paylaşım açıklaması, `"cevrildi": true` |
| Hook | `captiontr hooklar [--marka Lumo]` | Markada kullanılmış hook'lar + aynı ürünün diğer videolarındaki yazılar (fikir havuzu) |
| Render | `captiontr cevir` | Eski yazı silinir, yenisi basılır, yorum balonu değişir → `TR.mp4` + `TR_kontrol.png`; hook'u aynı markada önceki bir videoyla %75+ benzeyen video atlanır |
| Doğrulama | `captiontr dogrula` | Çıktıda eski yazıdan okunabilen iz var mı |
| Teslim | `captiontr teslim [--baslangic 2026-12-01] [--saat 10:00,18:00]` | `~/Desktop/CaptionTR/<Marka>/N.mp4` + `plan.csv` (varsayılan: yarından itibaren marka başına günde 1, 18:00) |
| Metadata | `captiontr temizle <dosya/klasör>` | Herhangi bir videonun metadata'sını siler, kalan izi raporlar |
| Durum | `captiontr durum` | Hangi video hangi aşamada, markası, teslim yeri |
| Toplu indirme | `captiontr indir liste.csv` · `captiontr bilgi liste.csv aday.csv` | CSV'den indirme · indirmeden izlenme/beğeni |
| Tekrar avı | `captiontr tekrar` · `captiontr temas x.jpg` | Alandaki tüm aynı / kısaltılmış / ortak çekimli çiftler · kare kolajı |

Çalışma alanı varsayılan `is/`; başka bir klasör için komutun sonuna yolu yaz.

## Kurulum (macOS, Windows, Linux)

Tek gereksinim [`uv`](https://docs.astral.sh/uv/). Komutlar her sistemde aynı:

```bash
git clone https://github.com/armanvibecoding/captiontr && cd captiontr
uv run captiontr --help              # ilk çalıştırmada Python + paketler kurulur
uv run --extra dev pytest -q
```

- Yazı okuma: macOS'ta Apple Vision (`pyobjc-framework-Vision`), Windows/Linux'ta RapidOCR (PP-OCR, ONNX, çevrimdışı;
  ilk kullanımda ~35 MB model indirir). `CAPTIONTR_OCR=rapid` ile macOS'ta da RapidOCR seçilir. 40 gerçek videoda
  iki motor satırların %95'inde aynı metni ve aynı kutuyu (medyan fark genişliğin %1,5'i) buldu.
- Teslim klasörü masaüstü (Windows'ta OneDrive masaüstü de bulunur).
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
    kaynak.mp4  meta.json  onizleme.jpg   # ekle (+ marka, parmak izi, kopya/benzer, teslim bilgisi meta.json'da)
    karsilastir_<diğer>.jpg               # kopya / ortak çekim şüphesinde yan yana kareler
    ayar.json   tablo.png                 # analiz (+ çeviri)
    TR.mp4      TR_kontrol.png            # cevir
  _kopyalar/<ad>-<kod>/                # kopya olduğu onaylananlar (silinmez, aynı dosya/link yeniden alınmaz)
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

## Kopya kontrolü

`ekle` her yeni videonun görüntü parmak izini (saniyede 2 karenin 64 bitlik dHash'i + aynalanmışı; düz kareler hariç)
çıkarır ve alandaki tüm videolarla karşılaştırır. Ölçüt: A'nın karelerinden B'de **aynı sırayla** yakın eşi
(hamming ≤ 12) bulunanların oranı. Sıra şartı, tesadüfen benzeyen kareleri ve aynı sahnelerin başka kurgusunu eler.

| Sonuç | Koşul | Ne olur |
|---|---|---|
| aynı | iki yönde de ≥ %80 | `KOPYA?` — karşılaştırma görseli üretilir, asistan bakıp karar verir; karar yokken teslim edilmez |
| parça | tek yönde ≥ %80 | Kısaltılmış/uzatılmış hali — aynı muamele |
| benzer | kısa olanın ≥ %35'i | Ortak çekim: işlenir, marka eşinden önerilir, `plan.csv → not` |

Ayar 150 gerçek ürün videosuyla yapıldı (11.175 çift). Eşik 10 olunca küçültülmüş, kırpılmış ve aynalanmış yeniden
yüklemelerin yarısı kaçıyor; 14 olunca farklı ürünler eşleşmeye başlıyor. 12'de gözle bakılan "aynı" çiftlerin hepsi
farklı yazıyla yeniden paylaşılmış aynı çekimdi; "benzer" çiftler aynı çekimin girişi farklı kurgularıydı.

## Yorum balonları

TikTok/Instagram'daki "X'in yorumuna yanıt" çıkartması `analiz` sırasında başlık satırından ("Reply to …'s comment")
tanınır ve altyazıdan ayrılır (`ayar.json → yorumlar[]`). Balonun sınırı karede beyaz zeminden ölçülür (avatar dahil),
giriş ve çıkış anı kare kare bulunur. `cevir` eski balonu tamamen örten opak bir balon çizer: Türkçe başlık
("<kullanıcı> adlı kullanıcının yorumuna yanıt"), Türkçe yorum ve emoji. Altında silme yapılmadığı için iz kalmaz.
Kullanıcı adı orijinal kalır; profil resmi yerine nötr gri daire basılır.

## Yazı yöntemi: kapatma (varsayılan, kesin kural)

Eski yazı silinmez. Görüldüğü her karede (giriş/çıkış geçişleri ve animasyonlu kareler dahil) tüm piksellerini
örten tek, tam opak siyah kutu çizilir; Türkçesi içine beyaz, orijinal font boyunda ve orijinal merkezde basılır.
Testler: eski yazının her pikseli siyah kalır (`test_kapat.py`), aynı metin basılınca harf boyu ve satır genişliği
orijinalle %8–12 içinde.

CTA zorunludur: `son_yazi.metin` boşsa `cevir` videoyu atlar. CTA siyah kutuda beyaz yazıdır, altyazı şeridine
binmeyecek yüksekliğe otomatik yerleşir.

### Eski silme yöntemleri (kapalı, yalnız `"yontem": "sil"` ile)

| `ayar.json` | Ne yapar |
|---|---|
| `"silme": "zamansal"` | Yazının altındaki gerçek görüntüyü komşu karelerden getirir (ORB + RANSAC homografi); dolmayan pikseller TELEA |
| `"silme": "telea"` | OpenCV TELEA inpaint |
| `"maske": "hassas"` | Silme maskesini pikselin zaman içindeki oynaklığından ölçer |

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
- Yorum balonu başlık kalıbından tanınır (EN/TR/ES/DE "reply to … 's comment" biçimleri); tanınmayan balonu asistan
  `yorumlar[]`'a elle ekler. Kopya kontrolü görüntüye bakar, sese bakmaz.

## Sorumlu kullanım

Bu araç **hakkına sahip olduğun ya da kullanım izni aldığın** videoları yerelleştirmek içindir (kendi içeriğin,
lisansladığın ya da iş birliği yaptığın üreticinin içeriği). Başkasının videosunu izinsiz yeniden yayınlamak telif
hakkını ve platform kurallarını ihlal edebilir; sorumluluk kullanıcıdadır. Metadata temizliği gizlilik içindir
(konum, cihaz, yazılım izleri) — platformların içerik eşleştirmesini atlatmak için tasarlanmamıştır.

## Lisans

Kod: [MIT](LICENSE). Font: TikTok Sans, [SIL Open Font License 1.1](captiontr/varliklar/OFL.txt).
Emoji görselleri depoda yoktur; ilk kullanımda `emoji-datasource-apple` paketinden indirilir ve kendi lisansına tabidir.
