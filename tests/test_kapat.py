"""Kesin kurallar: eski yazı silinmez, opak siyah kutuyla örtülür; yeni yazı orijinal boyda; CTA zorunlu."""
import os

import cv2, numpy as np

from captiontr import cevir, ortak
from test_temel import H, W, Y0, Y1, kare, kutulu_video, video   # noqa: F401  (fixture'lar)


def _ortulu(org, yeni, y0=Y0, y1=Y1):
    """Yeni metin tek "." iken eski yazının her pikseli (beyaz harf + 3 px kenar çizgisi) opak siyah kutuda kalmalı."""
    eski = cv2.dilate(cevir.beyaz(org[y0:y1]).astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    b = yeni[y0:y1].astype(int)
    nokta = cv2.dilate((b.min(axis=2) > 60).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)   # yeni "."
    return ((b.max(axis=2) < 30) | nokta)[eski].mean(), nokta[eski].mean()


def _harf_kutusu(f):
    ys, xs = np.nonzero(cevir.beyaz(f[Y0:Y1]))
    return ys.max() - ys.min() + 1, xs.max() - xs.min() + 1


def test_kapatma_varsayilan_eskisi_hic_gorunmez(video):
    ayar = {"kaynak": str(video / "kaynak.mp4"), "cikti": str(video / "TR_kapat.mp4"), "bant": [Y0, Y1],
            "altyazilar": [{"ornek_sn": 2.0, "satirlar": ["."]}]}
    a = str(video / "ayar_kapat.json"); ortak.yaz_json(a, ayar)
    cikti, _ = cevir.cevir(a)
    for i in (21, 40, 58):   # yazının başı, ortası, sonu
        org, yeni = kare(ayar["kaynak"], i), kare(cikti, i)
        ortu, nokta = _ortulu(org, yeni)
        assert ortu > 0.999 and nokta < 0.03, f"{i}. karede kutu eski yazıyı tam örtmüyor: {ortu:.3f}"
    assert not os.path.exists(os.path.splitext(cikti)[0] + "_dolgu.json"), "kapatmada silme/dolgu çalışmamalı"


def test_yeni_yazi_orijinal_boyda(video):
    # aynı metin basılırsa yeni harflerin yüksekliği ve satır genişliği orijinalle 1-1 olmalı
    ayar = {"kaynak": str(video / "kaynak.mp4"), "cikti": str(video / "TR_boy.mp4"), "bant": [Y0, Y1],
            "altyazilar": [{"ornek_sn": 2.0, "orijinal": ["Hello world"], "satirlar": ["Hello world"]}]}
    a = str(video / "ayar_boy.json"); ortak.yaz_json(a, ayar)
    cikti, _ = cevir.cevir(a)
    (ho, wo), (hy, wy) = _harf_kutusu(kare(ayar["kaynak"], 40)), _harf_kutusu(kare(cikti, 40))
    assert abs(hy - ho) / ho < 0.12 and abs(wy - wo) / wo < 0.08, f"boy farklı: orijinal {ho}x{wo}, yeni {hy}x{wy}"


def test_kutulu_yazi_da_siyah_kutuyla_ortulur(kutulu_video):
    d = kutulu_video
    ayar = {"kaynak": str(d / "kaynak.mp4"), "cikti": str(d / "TR_kapat.mp4"), "bant": [140, 250], "stil": "kutulu",
            "altyazilar": [{"ornek_sn": 2.0, "orijinal": ["POV: you need", "this gadget"],
                            "kutular": [[int(W / 2 - 90), 162, int(W / 2 + 90), 188], [int(W / 2 - 75), 202, int(W / 2 + 75), 228]],
                            "satirlar": ["."]}]}
    a = str(d / "ayar_kapat.json"); ortak.yaz_json(a, ayar)
    cikti, _ = cevir.cevir(a)
    ortu, nokta = _ortulu(kare(ayar["kaynak"], 40), kare(cikti, 40), 140, 250)
    assert ortu > 0.999 and nokta < 0.03, f"kutulu yazı tam örtülmedi: {ortu:.3f}"


def test_cta_olmadan_render_edilmez(video, tmp_path):
    k = tmp_path / "v1"; k.mkdir()
    os.link(video / "kaynak.mp4", k / "kaynak.mp4")
    ayar = {"kaynak": str(k / "kaynak.mp4"), "cikti": str(k / "TR.mp4"), "bant": [Y0, Y1], "cevrildi": True,
            "altyazilar": [{"ornek_sn": 2.0, "satirlar": ["Merhaba"]}]}
    ortak.yaz_json(str(k / ortak.AYAR), ayar)
    assert cevir.calistir(str(k / ortak.AYAR)) == 1 and not os.path.exists(ayar["cikti"])
    ayar["son_yazi"] = {"metin": "Link profilde 👆", "sure": 1.0}
    ortak.yaz_json(str(k / ortak.AYAR), ayar)
    assert cevir.calistir(str(k / ortak.AYAR)) == 0 and os.path.exists(ayar["cikti"])


def test_rapidocr_motoru_yaziyi_okur():
    # Windows/Linux'un yazı okuyucusu (macOS'ta kurulu değilse atlanır; CI'da Windows ve Linux'ta koşar)
    import pytest
    pytest.importorskip("rapidocr")
    from captiontr import analiz
    from test_temel import arka_plan, yazi_bas
    f = yazi_bas(arka_plan(5), "Hello world")
    s = analiz.ocr(f, "rapid")
    assert any(analiz.benzer(x["metin"], "Hello world") > 0.8 for x in s), s
    x = s[0]; assert 150 < (x["y0"] + x["y1"]) / 2 < 240 and abs((x["x0"] + x["x1"]) / 2 - W / 2) < 20
