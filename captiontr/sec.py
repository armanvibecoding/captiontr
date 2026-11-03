"""Aday seçimi: tekrar eden videoları bul + gözle kontrol için temas sayfası.

Tekrar: her videodan saniyede 1 karenin dHash'i. A'nın karelerinin çoğunun B'de yakın eşi varsa
(hamming ≤ ESIK) aynı çekimdir — farklı altyazı, kırpılmış baş/son veya yeniden yükleme yakalanır.
"""
import os

import cv2, numpy as np

from . import ortak

ESIK = 10        # 64 bitlik dHash'te yakın kare
ORTAK_PAY = 0.5  # karelerin bu kadarı eşleşirse tekrar


def dhash(f):
    g = cv2.cvtColor(cv2.resize(f, (9, 8), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return np.packbits((g[:, 1:] > g[:, :-1]).flatten())


def parmak_izi(video):
    b = ortak.bilgi(video); adim = max(1, int(round(b["fps"])))
    return np.array([dhash(f) for i, f in ortak.kareler(video) if i % adim == 0])


def benzerlik(a, b):
    """a'nın karelerinden b'de yakın eşi olanların oranı."""
    if not len(a) or not len(b): return 0.0
    x = np.unpackbits(a, axis=1)[:, None, :] != np.unpackbits(b, axis=1)[None, :, :]
    return float((x.sum(axis=2).min(axis=1) <= ESIK).mean())


def tekrarlar(proje):
    ortak.utf8()
    klasorler = ortak.is_klasorleri(proje)
    iz = {k: parmak_izi(os.path.join(k, ortak.KAYNAK)) for k in klasorler}
    ciftler = []
    for i, a in enumerate(klasorler):
        for b in klasorler[i + 1:]:
            s = max(benzerlik(iz[a], iz[b]), benzerlik(iz[b], iz[a]))
            if s >= ORTAK_PAY: ciftler.append((s, a, b))
    for s, a, b in sorted(ciftler, reverse=True):
        print(f"TEKRAR %{s * 100:.0f}  {os.path.basename(a)}  ≈  {os.path.basename(b)}")
    print(f"özet: {len(klasorler)} video, {len(ciftler)} tekrar çifti")
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
