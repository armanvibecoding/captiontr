"""Aynı video mu? Görüntü parmak izi + sıralı kare eşleşmesi.

Parmak izi: saniyede 2 karenin 64 bitlik dHash'i, ayrıca aynalanmış karenin dHash'i. Düz kareler
(siyah geçiş, tek renk) izde yer almaz — her videoda aynı göründükleri için sahte eşleşme üretirler.

Karşılaştırma: A'nın karelerinden B'de **aynı sırayla** yakın eşi (hamming ≤ ESIK) bulunanların oranı.
Sıra şartı (en uzun artan alt dizi) iki farklı videonun tesadüfen benzeyen karelerini eler; kırpılmış
baş/son, farklı altyazı, yeniden kodlama, boyut değişimi ve aynalama yakalanır.

  aynı    iki yönde de ≥ AYNI     → aynı video (başka hesap, başka yazı, başka kalite)
  parça   tek yönde ≥ AYNI        → biri diğerinin kısaltılmış / uzatılmış hali
  benzer  kısa olanın ≥ BENZER    → ortak çekim (aynı ürün, yeniden kurgu)
"""
import bisect, os

import cv2, numpy as np

from . import ortak

ORNEK_HZ = 2      # saniyede örnek kare
ESIK = 12         # 64 bitte yakın kare (150 gerçek videoyla ayarlandı: 10 ölçek+kırpma kopyalarını kaçırıyor, 14 sahte eşleşme üretiyor)
DUZ = 8.0         # gri standart sapma bunun altındaysa kare düzdür, ize girmez
AYNI = 0.8
BENZER = 0.35
EN_AZ = 3         # bundan az geçerli karesi olan videoyla karşılaştırma yapılmaz


def _dhash(g):
    k = cv2.resize(g, (9, 8), interpolation=cv2.INTER_AREA)
    return np.packbits((k[:, 1:] > k[:, :-1]).flatten()).tobytes().hex()


def parmak_izi(video):
    """{"t": [sn…], "h": [hex…], "ayna": [hex…], "sure": sn}"""
    b = ortak.bilgi(video); fps = b["fps"] or 25
    adim = max(1, int(round(fps / ORNEK_HZ)))
    t, h, ayna = [], [], []
    for i, f in ortak.kareler(video):
        if i % adim: continue
        g = cv2.cvtColor(cv2.resize(f, (72, 128), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        if float(g.std()) < DUZ: continue
        t.append(round(i / fps, 2)); h.append(_dhash(g)); ayna.append(_dhash(g[:, ::-1]))
    return {"t": t, "h": h, "ayna": ayna, "sure": round(b["n"] / fps, 2)}


def _bitler(hexler):
    if not hexler: return np.zeros((0, 64), bool)
    return np.unpackbits(np.frombuffer(bytes.fromhex("".join(hexler)), np.uint8).reshape(-1, 8), axis=1).astype(bool)


def kapsama(a, b):
    """a'nın karelerinden b'de sırası bozulmadan yakın eşi bulunanların oranı (a, b: bit matrisleri)."""
    if len(a) < EN_AZ or len(b) < EN_AZ: return 0.0
    yakin = (a[:, None, :] != b[None, :, :]).sum(axis=2) <= ESIK
    uclar = []   # en uzun azalmayan alt dizi (her a karesi en çok bir kez)
    for satir in yakin:
        for j in np.nonzero(satir)[0][::-1]:
            p = bisect.bisect_right(uclar, j)
            if p == len(uclar): uclar.append(j)
            else: uclar[p] = j
    return len(uclar) / len(a)


def karsilastir(iz_a, iz_b):
    """(tür, oran): tür 'aynı' | 'parça' | 'benzer' | None. oran = kısa olanın kapsanma oranı."""
    a, b, a_ay, b_ay = _bitler(iz_a["h"]), _bitler(iz_b["h"]), _bitler(iz_a["ayna"]), _bitler(iz_b["ayna"])
    ab = max(kapsama(a, b), kapsama(a, b_ay))
    ba = max(kapsama(b, a), kapsama(b, a_ay))
    if min(ab, ba) >= AYNI: return "aynı", round(min(ab, ba), 2)
    if max(ab, ba) >= AYNI: return "parça", round(max(ab, ba), 2)
    if max(ab, ba) >= BENZER: return "benzer", round(max(ab, ba), 2)
    return None, round(max(ab, ba), 2)


def iz_al(klasor):
    """Klasörün parmak izi; meta.json'da yoksa hesaplar ve kaydeder."""
    mp = os.path.join(klasor, ortak.META)
    m = ortak.oku_json(mp) if os.path.exists(mp) else {}
    if (m.get("iz") or {}).get("hz") != ORNEK_HZ:
        m["iz"] = {**parmak_izi(os.path.join(klasor, ortak.KAYNAK)), "hz": ORNEK_HZ}
        ortak.yaz_json(mp, m)
    return m["iz"]


def eslesmeler(klasor, digerleri):
    """klasörün diğer klasörlerle eşleşmeleri, en güçlüsü önce: [(tür, oran, diğer_klasör)]."""
    iz = iz_al(klasor); sonuc = []
    sira = {"aynı": 0, "parça": 1, "benzer": 2}
    for d in digerleri:
        if os.path.abspath(d) == os.path.abspath(klasor): continue
        tur, oran = karsilastir(iz, iz_al(d))
        if tur: sonuc.append((tur, oran, d))
    return sorted(sonuc, key=lambda x: (sira[x[0]], -x[1]))


def karsilastirma(a, b, cikti, n=6, gen=150):
    """İki videodan eşit aralıklı n kare, üst satır a, alt satır b → asistan gözle doğrular."""
    satirlar = []
    for k in (a, b):
        v = os.path.join(k, ortak.KAYNAK); top = ortak.bilgi(v)["n"]
        hedef = {int((j + 0.5) * top / n) for j in range(n)}; kareler = []
        for i, f in ortak.kareler(v):
            if i in hedef: kareler.append(cv2.resize(f, (gen, int(f.shape[0] * gen / f.shape[1]))))
        yuk = int(gen * 16 / 9)
        kareler = [cv2.copyMakeBorder(x[:yuk], 0, max(0, yuk - x.shape[0]), 0, 3, cv2.BORDER_CONSTANT) for x in kareler]
        r = np.hstack(kareler)
        cv2.putText(r, os.path.basename(k)[:40], (6, 22), 0, 0.6, (0, 255, 255), 2)
        satirlar.append(r)
    g = max(x.shape[1] for x in satirlar)
    satirlar = [cv2.copyMakeBorder(x, 0, 6, 0, g - x.shape[1], cv2.BORDER_CONSTANT, value=(128, 128, 128)) for x in satirlar]
    cv2.imwrite(cikti, np.vstack(satirlar), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return cikti
