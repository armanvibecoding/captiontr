"""Komut satırı: reeltr indir | analiz | cevir | durum"""
import argparse, os, sys

from . import analiz, cevir, indir, ortak, plan, sec


def durum(proje):
    ortak.utf8()
    say = {"video": 0, "analiz": 0, "ceviri": 0, "render": 0}
    for k in ortak.is_klasorleri(proje):
        say["video"] += 1
        a = os.path.join(k, ortak.AYAR)
        satir = [os.path.basename(k)]
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
    ap = argparse.ArgumentParser(prog="reeltr", description=__doc__)
    alt = ap.add_subparsers(dest="komut", required=True)
    p = alt.add_parser("indir", help="listedeki videoları filigransız indir")
    p.add_argument("liste"); p.add_argument("hedef")
    p.add_argument("--cerez", metavar="TARAYICI", help="giriş gerekirse tarayıcı çerezi (ör. chrome)")
    p = alt.add_parser("bilgi", help="indirmeden beğeni/izlenme topla (aday seçimi)")
    p.add_argument("liste"); p.add_argument("cikti")
    p = alt.add_parser("analiz", help="yazıları OCR ile bul, taslak ayar.json + tablo.png yaz")
    p.add_argument("proje"); p.add_argument("--zorla", action="store_true")
    p = alt.add_parser("cevir", help="çevirisi dolu videoları render et")
    p.add_argument("hedef"); p.add_argument("--zorla", action="store_true")
    p = alt.add_parser("temizle", help="video(lar)ın tüm metadata'sını sil ve doğrula")
    p.add_argument("yollar", nargs="+")
    p = alt.add_parser("tekrar", help="aynı çekimi içeren (tekrar) videoları bul")
    p.add_argument("proje")
    p = alt.add_parser("temas", help="her videodan 3 kare: ürünle ilgisini gözle kontrol")
    p.add_argument("proje"); p.add_argument("cikti")
    p = alt.add_parser("plan", help="Meta Business Suite paylaşım planı + sıralı teslim klasörü")
    p.add_argument("proje"); p.add_argument("hedef"); p.add_argument("--baslangic", required=True, help="YYYY-AA-GG")
    p.add_argument("--saatler", default="12:30,20:30")
    p = alt.add_parser("dogrula", help="render sonrası: silinmemiş eski yazı kaldı mı (OCR)")
    p.add_argument("proje")
    p = alt.add_parser("durum", help="proje durumu")
    p.add_argument("proje")
    a = ap.parse_args()
    if a.komut == "indir": return indir.calistir(a.liste, a.hedef, a.cerez)
    if a.komut == "bilgi": return indir.bilgi_topla(a.liste, a.cikti)
    if a.komut == "analiz": return analiz.calistir(a.proje, a.zorla)
    if a.komut == "cevir": return cevir.calistir(a.hedef, a.zorla)
    if a.komut == "temizle": return temizle(a.yollar)
    if a.komut == "tekrar": sec.tekrarlar(a.proje); return 0
    if a.komut == "temas": print(sec.temas(a.proje, a.cikti)); return 0
    if a.komut == "plan": plan.olustur(a.proje, a.hedef, a.baslangic, tuple(a.saatler.split(","))); return 0
    if a.komut == "dogrula":
        from . import dogrula
        return 1 if dogrula.calistir(a.proje) else 0
    if a.komut == "durum": return durum(a.proje)


if __name__ == "__main__":
    sys.exit(main())
