"""captiontr — gömülü yazıları Türkçeleştir. Sıra: ekle → marka → analiz → cevir → dogrula → teslim"""
import argparse, os, sys

from . import analiz, cevir, indir, marka, ortak, sec


def durum(proje):
    ortak.utf8()
    if not os.path.isdir(proje): print(f"özet: {proje} yok — önce: captiontr ekle <videolar>"); return 0
    say = {"video": 0, "analiz": 0, "ceviri": 0, "render": 0}
    for k in ortak.is_klasorleri(proje):
        say["video"] += 1
        a = os.path.join(k, ortak.AYAR)
        m = ortak.oku_json(os.path.join(k, ortak.META)) if os.path.exists(os.path.join(k, ortak.META)) else {}
        satir = [os.path.basename(k), f"[{m.get('marka') or 'marka yok'}]"]
        if m.get("teslim"): satir.append(f"✓teslim {m['teslim']}")
        if os.path.exists(a):
            say["analiz"] += 1
            ay = ortak.oku_json(a)
            dolu = bool(ay.get("altyazilar")) and all(x.get("satirlar") for x in ay["altyazilar"])
            say["ceviri"] += dolu
            satir.append(f"{len(ay.get('altyazilar', []))} yazı" + (" ✓çeviri" if dolu else " ·çeviri bekliyor"))
            if os.path.exists(ay["cikti"]): say["render"] += 1; satir.append("✓TR.mp4")
            if ay.get("uyarilar"): satir.append("⚠ " + "; ".join(ay["uyarilar"]))
        print("  ".join(satir))
    print(f"özet: {say['video']} video · {say['analiz']} analiz · {say['ceviri']} çeviri · {say['render']} render")
    return 0


def temizle(yollar):
    """Dosya ya da klasör (içindeki tüm .mp4/.mov) — yerinde temizler, kalan izi raporlar."""
    ortak.utf8()
    dosyalar = []
    for y in yollar:
        if os.path.isdir(y):
            dosyalar += [os.path.join(k, d) for k, _, ds in os.walk(y) for d in ds if d.lower().endswith((".mp4", ".mov"))]
        else: dosyalar.append(y)
    kirli = 0
    for d in sorted(dosyalar):
        try:
            ortak.metadata_temizle(d)
            kalan = ortak.metadata_rapor(d)
        except Exception as e: kalan = [f"HATA {e}"]
        kirli += bool(kalan)
        print(f"{'TEMİZ' if not kalan else 'KALAN'}  {d}" + (f"  {kalan}" if kalan else ""))
    print(f"özet: {len(dosyalar) - kirli}/{len(dosyalar)} temiz")
    return 1 if kirli else 0


def main():
    ap = argparse.ArgumentParser(prog="captiontr", description=__doc__)
    alt = ap.add_subparsers(dest="komut", required=True)
    IS = dict(nargs="?", default="is", help="çalışma alanı (varsayılan: is)")
    p = alt.add_parser("ekle", help="video dosyası / klasör / link → çalışma alanı + önizleme")
    p.add_argument("yollar", nargs="+"); p.add_argument("--proje", default="is"); p.add_argument("--cerez", metavar="TARAYICI")
    p = alt.add_parser("marka", help="videoları markaya bağla (yeni markada --urun gerekli)")
    p.add_argument("videolar", nargs="+", help="video klasör adları"); p.add_argument("--ad", required=True)
    p.add_argument("--urun", help="kısa ürün tanımı (yeni marka için)"); p.add_argument("--proje", default="is")
    p = alt.add_parser("markalar", help="kayıtlı markalar + markası atanmamış videolar")
    p.add_argument("proje", **IS)
    p = alt.add_parser("teslim", help="hazır videoları masaüstüne <Marka>/1.mp4, 2.mp4… + plan.csv")
    p.add_argument("proje", **IS); p.add_argument("--hedef", default=marka.VARSAYILAN_HEDEF)
    p.add_argument("--baslangic", help="YYYY-AA-GG (varsayılan: yarın)"); p.add_argument("--saat", default="18:00", help="ör. 18:00 ya da 10:00,18:00")
    p.add_argument("--gunluk", type=int, default=1, help="marka başına günde video")
    p = alt.add_parser("indir", help="CSV/txt listedeki linkleri indir")
    p.add_argument("liste"); p.add_argument("hedef", **IS)
    p.add_argument("--cerez", metavar="TARAYICI", help="giriş gerekirse tarayıcı çerezi (ör. chrome)")
    p = alt.add_parser("bilgi", help="indirmeden beğeni/izlenme topla (aday seçimi)")
    p.add_argument("liste"); p.add_argument("cikti")
    p = alt.add_parser("analiz", help="yazıları bul, taslak ayar.json + tablo.png yaz")
    p.add_argument("proje", **IS); p.add_argument("--zorla", action="store_true")
    p = alt.add_parser("cevir", help="çevirisi dolu videoları render et")
    p.add_argument("hedef", **IS); p.add_argument("--zorla", action="store_true")
    p = alt.add_parser("dogrula", help="render sonrası: silinmemiş eski yazı kaldı mı")
    p.add_argument("proje", **IS)
    p = alt.add_parser("temizle", help="video(lar)ın tüm metadata'sını sil ve doğrula")
    p.add_argument("yollar", nargs="+")
    p = alt.add_parser("tekrar", help="aynı çekimi içeren (tekrar) videoları bul")
    p.add_argument("proje", **IS)
    p = alt.add_parser("temas", help="her videodan 3 kare tek sayfada")
    p.add_argument("cikti"); p.add_argument("proje", **IS)
    p = alt.add_parser("durum", help="hangi video hangi aşamada")
    p.add_argument("proje", **IS)
    a = ap.parse_args()
    if a.komut == "ekle": return 1 if marka.ekle(a.yollar, a.proje, a.cerez)[1] else 0
    if a.komut == "marka": marka.marka_ata(a.videolar, a.ad, a.urun, a.proje); return 0
    if a.komut == "markalar": marka.markalar(a.proje); return 0
    if a.komut == "teslim": marka.teslim(a.proje, a.hedef, a.baslangic, a.saat, a.gunluk); return 0
    if a.komut == "indir": return indir.calistir(a.liste, a.hedef, a.cerez)
    if a.komut == "bilgi": return indir.bilgi_topla(a.liste, a.cikti)
    if a.komut == "analiz": return analiz.calistir(a.proje, a.zorla)
    if a.komut == "cevir": return cevir.calistir(a.hedef, a.zorla)
    if a.komut == "temizle": return temizle(a.yollar)
    if a.komut == "tekrar": sec.tekrarlar(a.proje); return 0
    if a.komut == "temas": print(sec.temas(a.proje, a.cikti)); return 0
    if a.komut == "dogrula":
        from . import dogrula
        return 1 if dogrula.calistir(a.proje) else 0
    if a.komut == "durum": return durum(a.proje)


if __name__ == "__main__":
    sys.exit(main())
