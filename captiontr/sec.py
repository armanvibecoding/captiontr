"""Tekrar avı (bkz. aynilik.py) + gözle kontrol için temas sayfası."""
import os

import cv2, numpy as np

from . import aynilik, ortak


def tekrarlar(proje):
    """Çalışma alanındaki tüm çiftler: aynı video / kısaltılmış hali / ortak çekim."""
    ortak.utf8()
    klasorler = ortak.is_klasorleri(proje)
    iz = {k: aynilik.iz_al(k) for k in klasorler}
    ciftler = []
    for i, a in enumerate(klasorler):
        for b in klasorler[i + 1:]:
            tur, oran = aynilik.karsilastir(iz[a], iz[b])
            if tur: ciftler.append((tur, oran, a, b))
    sira = {"aynı": 0, "parça": 1, "benzer": 2}
    for tur, oran, a, b in sorted(ciftler, key=lambda x: (sira[x[0]], -x[1])):
        print(f"{tur.upper():7} %{oran * 100:.0f}  {os.path.basename(a)}  ≈  {os.path.basename(b)}")
    print(f"özet: {len(klasorler)} video, {len(ciftler)} eşleşen çift")
    return ciftler


def temas(proje, cikti, anlar=(0.15, 0.5, 0.85), gen=180):
    """Her video bir satır: 3 kare + ad. Ürünle ilgisini gözle kontrol etmek için."""
    satirlar = []
    for k in ortak.is_klasorleri(proje):
        v = os.path.join(k, ortak.KAYNAK); b = ortak.bilgi(v)
        hedef = {int(b["n"] * a) for a in anlar}; kareler = []
        for i, f in ortak.kareler(v):
            if i in hedef: kareler.append(cv2.resize(f, (gen, int(f.shape[0] * gen / f.shape[1]))))
        yuk = int(gen * 16 / 9)
        kareler = [cv2.copyMakeBorder(x[:yuk], 0, max(0, yuk - x.shape[0]), 0, 4, cv2.BORDER_CONSTANT) for x in kareler]
        etiket = np.zeros((yuk, 260, 3), np.uint8)
        for j, parca in enumerate([os.path.basename(k)[i:i + 22] for i in range(0, len(os.path.basename(k)), 22)]):
            cv2.putText(etiket, parca, (6, 30 + j * 26), 0, 0.6, (255, 255, 255), 1)
        cv2.putText(etiket, f"{b['n'] / b['fps']:.0f} sn", (6, yuk - 12), 0, 0.6, (0, 255, 255), 1)
        satirlar.append(np.hstack([etiket] + kareler))
    cv2.imwrite(cikti, np.vstack(satirlar))
    return cikti
