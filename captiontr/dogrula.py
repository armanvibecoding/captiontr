"""Render sonrası otomatik kontrol: çıktıda eski (yabancı) yazıdan iz kaldı mı?

Her 0,5 sn'de kaynak ve TR karesi OCR'lanır. Kaynakta okunan ve analizdeki orijinal altyazılardan birine
benzeyen satır, TR karesinde aynı yerde benzer metinle hâlâ okunuyorsa → KALDI (silinmemiş yazı).
Ürün üstündeki logo/ambalaj yazıları altyazı olmadığı için sayılmaz.
"""
import os

import cv2

from . import analiz, ortak

ADIM_SN = 0.5
ESIK = 0.6


def _kareler(video, anlar):
    c = cv2.VideoCapture(video); out = {}
    for t in anlar:
        c.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, f = c.read()
        if ok: out[t] = f
    return out


def kontrol_et(klasor):
    ayar = ortak.oku_json(os.path.join(klasor, ortak.AYAR))
    cikti = ayar["cikti"]
    if not os.path.exists(cikti): return None
    orijinal = [s for a in ayar.get("altyazilar", []) for s in a.get("orijinal", [])]
    if not orijinal: return []
    b = ortak.bilgi(ayar["kaynak"]); sure = b["n"] / b["fps"]
    anlar = [round(i * ADIM_SN, 2) for i in range(int(sure / ADIM_SN))]
    kaynak, yeni = _kareler(ayar["kaynak"], anlar), _kareler(cikti, anlar)
    W, H = b["w"], b["h"]
    kalan = []
    for t in anlar:
        if t not in kaynak or t not in yeni: continue
        eski = [s for s in analiz.ocr(kaynak[t]) if max(analiz.benzer(s["metin"], o) for o in orijinal) > ESIK]
        if not eski: continue
        simdi = analiz.ocr(yeni[t])
        for s in eski:
            for y in simdi:
                if analiz.ayni_yer(s, y, W, H) and analiz.benzer(s["metin"], y["metin"]) > ESIK:
                    kalan.append((t, y["metin"]))
    return kalan


def calistir(proje):
    ortak.utf8()
    toplam = 0
    for k in ortak.is_klasorleri(proje):
        r = kontrol_et(k)
        if r is None: continue
        ad = os.path.basename(k)
        if r:
            toplam += 1
            ozet = "; ".join(f"{t:.1f}sn «{m}»" for t, m in r[:6])
            print(f"KALDI  {ad:30} {len(r)} kare: {ozet}")
        else:
            print(f"TEMİZ  {ad}")
    print(f"özet: {toplam} videoda silinmemiş yazı")
    return toplam
