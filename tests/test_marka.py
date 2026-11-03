"""Marka sistemi: ekle → marka → teslim (numara ve plan kaldığı yerden devam eder)."""
import csv, datetime as dt, os, shutil, subprocess

import numpy as np, pytest

from captiontr import marka, ortak


def _video(yol, renk, n=20):
    ff = subprocess.Popen([ortak.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "180x320",
                           "-r", "10", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                           "-metadata", "comment=ZZZ-iz", yol], stdin=subprocess.PIPE)
    for i in range(n):
        f = np.full((320, 180, 3), renk, np.uint8); f[i * 10 % 300:i * 10 % 300 + 20] = 255
        ff.stdin.write(f.tobytes())
    ff.stdin.close(); assert ff.wait() == 0
    return yol


@pytest.fixture
def alan(tmp_path):
    gelen = tmp_path / "gelen"; gelen.mkdir()
    for ad, renk in (("a", (40, 80, 160)), ("b", (160, 40, 80)), ("c", (80, 160, 40))):
        _video(str(gelen / f"{ad}.mp4"), renk)
    return tmp_path


def _hazirla(klasor):
    """render edilmiş gibi: TR.mp4 = kaynak kopyası, açıklama dolu."""
    shutil.copy2(os.path.join(klasor, ortak.KAYNAK), os.path.join(klasor, ortak.CIKTI))
    ortak.yaz_json(os.path.join(klasor, ortak.AYAR), {"cikti": os.path.join(klasor, ortak.CIKTI),
                                                     "gonderi": {"aciklama": "deneme"}})


def test_ekle_onizleme_metadata_ve_tekrar(alan):
    proje = str(alan / "is")
    yeni, hata = marka.ekle([str(alan / "gelen")], proje)
    assert hata == 0 and len(yeni) == 3
    for k in yeni:
        assert os.path.exists(os.path.join(k, marka.ONIZLEME))
        assert ortak.metadata_rapor(os.path.join(k, ortak.KAYNAK)) == []   # comment=ZZZ-iz silindi
    # kırma: kaynakta iz gerçekten vardı (kapı ölçüyor)
    assert any("ZZZ-iz" in x for x in ortak.metadata_rapor(str(alan / "gelen" / "a.mp4")))
    yeni2, _ = marka.ekle([str(alan / "gelen" / "a.mp4")], proje)
    assert yeni2 == []                                                      # aynı dosya ikinci kez eklenmez


def test_yeni_marka_urun_tanimi_ister(alan):
    proje = str(alan / "is"); yeni, _ = marka.ekle([str(alan / "gelen")], proje)
    with pytest.raises(RuntimeError, match="--urun"):
        marka.marka_ata([os.path.basename(yeni[0])], "Lumo", proje=proje)
    marka.marka_ata([os.path.basename(yeni[0])], "Lumo", "gece lambası", proje)
    marka.marka_ata([os.path.basename(yeni[1])], "Lumo", proje=proje)     # kayıtlı marka: tanım gerekmez
    kayit, bos = marka.markalar(proje)
    assert kayit["Lumo"]["urun"] == "gece lambası" and len(bos) == 1


def test_teslim_numara_ve_plan_kaldigi_yerden(alan):
    proje, hedef = str(alan / "is"), str(alan / "Masaustu")
    yeni, _ = marka.ekle([str(alan / "gelen")], proje)
    for k in yeni: _hazirla(k)
    marka.marka_ata([os.path.basename(k) for k in yeni[:2]], "Lumo", "gece lambası", proje)
    t = marka.teslim(proje, hedef, baslangic="2026-12-01")
    assert sorted(os.path.basename(x) for x in t) == ["1.mp4", "2.mp4"]
    marka.marka_ata([os.path.basename(yeni[2])], "Pati", "kedi oyuncağı", proje)
    assert marka.teslim(proje, hedef, baslangic="2026-12-01") == [os.path.join(hedef, "Pati", "1.mp4")]  # eskiler tekrar gitmez
    # yeni video aynı markaya → 3.mp4, tarih 3 Aralık
    _video(str(alan / "gelen" / "d.mp4"), (10, 10, 200))
    (d,), _ = marka.ekle([str(alan / "gelen" / "d.mp4")], proje); _hazirla(d)
    marka.marka_ata([os.path.basename(d)], "Lumo", proje=proje)
    assert marka.teslim(proje, hedef, baslangic="2026-12-01") == [os.path.join(hedef, "Lumo", "3.mp4")]
    with open(os.path.join(hedef, "Lumo", marka.PLAN), encoding="utf-8-sig") as f: plan = list(csv.DictReader(f))
    assert [(r["sira"], r["tarih"], r["saat"]) for r in plan] == \
        [("1", "2026-12-01", "18:00"), ("2", "2026-12-02", "18:00"), ("3", "2026-12-03", "18:00")]
    assert all(r["aciklama"] == "deneme" for r in plan)
    for x in os.listdir(os.path.join(hedef, "Lumo")):
        if x.endswith(".mp4"): assert ortak.metadata_rapor(os.path.join(hedef, "Lumo", x)) == []


def test_teslim_hazir_olmayani_ve_markasizi_beklet(alan):
    proje, hedef = str(alan / "is"), str(alan / "Masaustu")
    yeni, _ = marka.ekle([str(alan / "gelen")], proje)
    _hazirla(yeni[0])                                   # markasız ama hazır
    marka.marka_ata([os.path.basename(yeni[1])], "Lumo", "gece lambası", proje)   # markalı ama hazır değil
    assert marka.teslim(proje, hedef) == []
    assert not os.path.exists(os.path.join(hedef, "Lumo", "1.mp4"))


def test_gunde_iki_saat(alan):
    proje, hedef = str(alan / "is"), str(alan / "Masaustu")
    yeni, _ = marka.ekle([str(alan / "gelen")], proje)
    for k in yeni: _hazirla(k)
    marka.marka_ata([os.path.basename(k) for k in yeni], "Lumo", "gece lambası", proje)
    marka.teslim(proje, hedef, baslangic="2026-12-01", saat="10:00,18:00")
    with open(os.path.join(hedef, "Lumo", marka.PLAN), encoding="utf-8-sig") as f: plan = list(csv.DictReader(f))
    assert [(r["tarih"], r["saat"]) for r in plan] == [("2026-12-01", "10:00"), ("2026-12-01", "18:00"), ("2026-12-02", "10:00")]
