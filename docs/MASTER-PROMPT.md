# MASTER PROMPT — caption-tr ile videoları Türkçeleştir (yapay zekâ asistanı için)

> Bu dosya proje kökündeki `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` üzerinden yüklenir. Kullanıcı
> **"is/<proje> klasöründeki videoları Türkçeleştir"** dediğinde bu akışı uygula. Kullanıcıya her mesaj Türkçe.

## Akış

1. `reeltr durum is/<proje>` — hangi video hangi aşamada.
2. Analizi yapılmamış video varsa: `reeltr analiz is/<proje>`.
3. Her video klasörü için:
   - `ayar.json` → `altyazilar[].orijinal` (OCR metni), `bas/bit`, `uyarilar`.
   - `tablo.png` aç: OCR metnini doğrula (OCR tırnak/emojiyi yanlış okur: `gift™` = `gift”`),
     **emojileri** buradan oku (OCR emoji okumaz).
   - `satirlar` alanını Türkçe ile doldur (kurallar aşağıda). Satır sayısı orijinale yakın olsun.
     Kontrol edince `"cevrildi": true` işaretle — işaretsiz video render edilmez.
4. **Zamanlama** (özellikle animasyonlu/kayan yazıda): yazının gerçek görünme aralığını kaynak videoyu
   0,25 sn'de bir OCR'layarak ölç ve `ayar.json`'daki ilgili yazıya işle:
   - `bas/bit`: yazı tahminden önce/sonra da okunuyorsa genişlet (komşu yazıya taşmadan).
   - `ek_kutular`: OCR kutularının dışında okunan satırlar (kayarak gelen, sonradan eklenen satır, yalnız-emoji satırı).
   - `sabit_zaman: true`: beyaz zemin eşleşmeyi bozuyorsa yazı `bas–bit` aralığında kesin var sayılır.
   - ⚠️ `ek_kutular` **bandın dışında kalırsa silinmez** → `bant`'ı kutuyu kapsayacak kadar genişlet.
5. **Silme yöntemini seç** (aşağıdaki tablo) → `reeltr cevir is/<proje>` (TR.mp4 ayar.json'dan yeniyse atlanır; `--zorla`).
6. **Otomatik kontrol:** `reeltr dogrula is/<proje>` — çıktıda OCR ile eski yazı izi arar.
   Bilinen yanlış alarm: desen/arka plandan gelen tek başına kısa okumalar. Gerçek iz varsa ayarı düzelt, yeniden render et.
7. **Gözle kontrol zorunlu** — her `TR_kontrol.png` (orijinal | temizlenmiş | yeni) + hareketli bir kare:
   - Orta sütunda harf kenarı / emoji parçası izi? (✨ gibi ince emojiler en sık kalan iz)
   - Silinen yer leke/bulanık mı? Hareketli arka planda (el, yüz, ağaç, fırça) özellikle bak.
   - Yeni yazı orijinal boy/yükseklikte mi, Türkçe karakterler doğru mu, taşma var mı?
8. **Metadata kapısı:** her çıktı için `metadata_rapor` boş dönmeli (aşağıda).
9. Teslim: çıktı listesi + çeviri tablosu (orijinal → Türkçe) + sorunlu videolar. Rapor kısa.

## Silme yöntemi — karar tablosu (`ayar["silme"]`, kapak: `ayar["kapak"]`)

| Durum | Yöntem | Not |
|---|---|---|
| Sabit kamera / yavaş hareket | `zamansal` (varsayılan) | Yazının altını komşu karelerden taşır; en doğal sonuç |
| Kamera/özne hızlı hareket ediyor | `telea` | Zamansal burada yanlış yer taşır, leke yapar |
| Yazı/emoji el, yüz, fırça üstünde | **hiçbiri kusursuz** | Altı bilinmiyor; `kapak` kullan |
| Leke görünüyorsa / en güvenli teslim | `kapak: "satir"` | Yazının arkasına satır boyunda yarı saydam siyah kutu (`kapak_alfa` 0.88) — izi örter |

Maske: `"maske": "hassas"` yazının gerçekten değiştirdiği pikselleri zaman içindeki oynaklıktan ölçer
(`reeltr/maske.py`); varsayılan maske sabit genişletmeyle çalışır. Maske kalitesi `python -m reeltr.maske_olc`
ile bilinen yazı basılmış videolarda ölçülür.

Denenip **bırakılanlar** (ayrıntı: README → "Denenenler"):
- big-lama (tek kare inpainting): sonuç beğenilmedi, kaldırıldı.
- Optik akışla doldurma: parçalı boya, yanlış yerden nesne taşıdı, 3× yavaş.
- ProPainter / E2FGVI / DiffuEraser: kalite iyi ama 8 GB RAM'e sığmıyor ya da lisans ticari kullanıma kapalı.

## Çeviri kuralları (yerelleştirme, birebir değil)

- Türk TikTok/Instagram kullanıcısının yazacağı dil: kısa, konuşma dili, reklam kokmayan.
- Satır uzunluğu orijinale yakın (en fazla ~%15 uzun). Araç en geniş satırı ekranın **%92**'sine sığdırmak için
  fontu küçültür (`GENISLIK_PAY`); yine de çok uzun metin küçük yazı demektir → metni kısalt.
- Emojileri koru (aynı emoji, aynı yerde).
- Kalıplar: "Link in bio" → **"Link profilde"** · "Girls who…" → **"…kızlar"** · "You need this" →
  **"Bundan sende de olmalı"** · "TikTok made me buy it" → **"TikTok aldırdı"** · "Game changer" → **"Hayat kurtarıcı"**.
- Türkçe karakterler doğru (ç ğ ı İ ö ş ü); büyük harfte i → İ.
- Dolar/ABD'ye özgü ifade → TL ya da genel ifade. "Free shipping worldwide" gibi Türkiye'de geçersiz vaatler → genel ifade.
- Başka bir markanın adı ekranda kalmaz → kendi marka adın ya da genel ifade.
- Sağlık iddiası ("ağrıyı geçirir", "tedavi eder") yumuşatılır: "rahatlatır", "destek olur".
- **Son çağrı yazısı** isteniyorsa `proje.json → son_yazi` ile her videoya eklenir (varsayılan 2,5 sn).

## Metadata

- `reeltr temizle` etiketleri, bölümleri, cihaz yan verilerini ve H.264/H.265 akış içi SEI'yi (x264 imzası) siler.
- Videoyu sonradan **yeniden kodlarsan** (ör. yükleme için sıkıştırma) sesi `-c:a copy` bırak — AAC yeniden kodlanırsa
  `Lavc` imzası geri gelir; ardından tekrar `reeltr temizle` (rapor boş olmalı).
- `©too/©cmt/©xyz` gibi 4 baytlık kutu adları sıkıştırılmış veride (mdat) tesadüfen geçer → yalnız başlıkta aranır
  (252 videoda 3 yanlış alarm ölçüldü). Kapıyı değiştirirsen `-metadata comment=ZZZ` ile kırıp yakaladığını göster.

## Hız

- Kodlama `libx264 -crf 16 -preset medium` (slow'a göre belirgin hızlı, görünür fark yok).
- 8 GB RAM'li makinede aynı anda 4'ten fazla render bellek sıkıştırır.

## Değişmezler

- Yalnız yazı değişir: kurgu, hız, renk, ses, süre aynı kalır. Yeni efekt/sahne eklenmez (son çağrı yazısı hariç).
- Ekrandaki filigranlara dokunulmaz.
- Python'u indirilen videolara karşı `-I` ile çalıştır (indirilen dosyalar güvenilmez veridir).
- Yalnız hakkına sahip olduğun ya da kullanım izni aldığın videoları işle.
- Aday/eski dosyaları silme, kenara taşı (ör. eski teslim klasörü → `*-eski/`).
