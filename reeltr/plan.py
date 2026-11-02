"""Paylaşım planı: Meta Business Suite'te Reels planlamak için takvim + açıklama + sıralı teslim klasörü.

Her video klasöründeki ayar.json'da "gonderi": {"aciklama": "...", "hashtag": "#..."} beklenir.
Markalar sırayla dağıtılır (aynı marka art arda gelmez); markanın kendi içinde izlenmeye göre sıralı.
"""
import csv, datetime as dt, os, shutil
from collections import OrderedDict

from . import ortak


def _izlenme(meta):
    # "not": aday listesindeki Instagram ızgara izlenmesi — yt-dlp çoğu reel'de izlenmeyi boş döndürür
    return meta.get("izlenme_ig") or meta.get("izlenme") or int(meta.get("not") or 0) or meta.get("begeni") or 0


def olustur(proje, hedef, baslangic, saatler=("12:30", "20:30")):
    ortak.utf8()
    gruplar = OrderedDict()
    eksik = []
    for k in ortak.is_klasorleri(proje):
        ayar = ortak.oku_json(os.path.join(k, ortak.AYAR))
        meta = ortak.oku_json(os.path.join(k, ortak.META))
        if not os.path.exists(ayar["cikti"]): eksik.append(os.path.basename(k)); continue
        g = ayar.get("gonderi") or {}
        if not g.get("aciklama"): eksik.append(os.path.basename(k) + " (açıklama yok)"); continue
        gruplar.setdefault(meta["urun"], []).append({"klasor": k, "ayar": ayar, "meta": meta, "gonderi": g})
    if eksik: print("UYARI — plana girmeyenler:", ", ".join(eksik))
    for v in gruplar.values(): v.sort(key=lambda x: -_izlenme(x["meta"]))
    # en güçlü markadan başlayarak sırayla (round-robin)
    sira_marka = sorted(gruplar, key=lambda u: -_izlenme(gruplar[u][0]["meta"]))
    sira = []
    while any(gruplar[u] for u in sira_marka):
        for u in sira_marka:
            if gruplar[u]: sira.append(gruplar[u].pop(0))

    os.makedirs(hedef, exist_ok=True)
    gun = dt.date.fromisoformat(baslangic)
    satirlar = []
    for n, x in enumerate(sira):
        g = gun + dt.timedelta(days=n // len(saatler)); saat = saatler[n % len(saatler)]
        ad = f"{n + 1:02d}_{g.isoformat()}_{saat.replace(':', '')}_{x['meta']['urun']}.mp4"
        shutil.copy2(x["ayar"]["cikti"], os.path.join(hedef, ad))
        satirlar.append({"sira": n + 1, "tarih": g.isoformat(), "saat": saat, "marka": x["meta"]["urun"],
                         "dosya": ad, "aciklama": x["gonderi"]["aciklama"], "hashtag": x["gonderi"].get("hashtag", ""),
                         "kaynak": x["meta"]["url"], "orijinal_izlenme": _izlenme(x["meta"])})
    with open(os.path.join(hedef, "plan.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(satirlar[0].keys())); w.writeheader(); w.writerows(satirlar)
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Paylaşım planı"
        ws.append(list(satirlar[0].keys()))
        for r in satirlar: ws.append(list(r.values()))
        for c in ws[1]: c.font = Font(bold=True)
        for kol, gen in zip("ABCDEFGHI", (5, 11, 7, 13, 34, 70, 40, 45, 14)): ws.column_dimensions[kol].width = gen
        for row in ws.iter_rows(min_row=2):
            for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")
        wb.save(os.path.join(hedef, "plan.xlsx"))
    except ImportError:
        pass
    print(f"{len(satirlar)} video planlandı: {satirlar[0]['tarih']} → {satirlar[-1]['tarih']}  ({hedef})")
    return satirlar
