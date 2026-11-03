# Yol haritası

## Metadata
- [ ] **Kırma testi:** bilinen izleri (`comment`, `©xyz` GPS, XMP `uuid`, `udta`) bilerek ekleyip temizliğin
      hepsini sildiğini ve raporun hepsini yakaladığını gösteren test.
- [ ] **Yapısal kutu taraması:** regex yerine MP4 kutu ağacını gezip `udta` / `meta` / `uuid` (XMP, C2PA) / `free`
      kutularını bulmak.
- [ ] **Sıkıştırma adımı:** yükleme için hedef boyuta yeniden kodlama (`ses copy`) + ardından otomatik temizlik ve rapor.
- [ ] **Döndürme bilgisi:** `displaymatrix` olan videoda görüntüyü fiziksel döndürüp sonra temizlemek (şu an hata verir).
- [ ] **Toplu rapor:** `captiontr temizle --rapor` → dosya başına temiz/kirli tablosu.

## Silme kalitesi (8 GB RAM sınırı içinde)
- [ ] `zamansal`: tek homografi yerine yerel (blok) hizalama + kaynak kare ile hedef kare arasında renk/ışık eşitleme.
- [ ] Dolgu oranı düşük ya da `dogrula` iz bulduğunda otomatik `kapak`'a düşme.
- [ ] `dogrula`'ya leke ölçümü: silinen bölgenin çevresine göre bulanıklık / doku farkı.
- [ ] Bellek dostu video inpainting modellerini lisans + RAM ölçümüyle değerlendirmek (ProPainter bellekten elendi).

## Kullanım
- [ ] Tüm `TR_kontrol.png`'leri tek HTML sayfada toplayan kontrol raporu.
- [ ] Kelime kelime beliren (karaoke) yazıda ara durumları da çevirmek.
