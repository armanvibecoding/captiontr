"""Kopya kontrolü: aynı video (başka kalite/boyut/ayna/kırpık/yazılı) yakalanır, farklı video karışmaz,
ortak çekim 'benzer' olur; marka sisteminde kopya teslim edilmez ve kenara taşınır."""
import os, shutil, subprocess

import cv2, numpy as np, pytest

from captiontr import aynilik, marka, ortak

W, H, FPS = 180, 320, 10


def sahne(tohum, i):
    """Her saniye başka bir sahne; sahne içinde yavaş kayma (gerçek çekim gibi düşük frekanslı doku)."""
    rng = np.random.default_rng(tohum)
    k = cv2.resize(rng.integers(0, 255, (12, 7, 3), dtype=np.uint8), (W + 40, H + 40), interpolation=cv2.INTER_CUBIC)
    d = i % FPS
    return k[d:d + H, d:d + W].copy()


def yaz(yol, tohumlar, ek=()):
    ff = subprocess.Popen([ortak.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", *ek, "-c:v", "libx264", "-pix_fmt", "yuv420p", yol], stdin=subprocess.PIPE)
    for t in tohumlar:
        for i in range(FPS): ff.stdin.write(sahne(t, i).tobytes())
    ff.stdin.close(); assert ff.wait() == 0
    return yol


def donustur(kaynak, yol):
    """Başka hesabın yeniden yüklemesi: ayna, küçültme, hafif kırpma, baş/son kesik, üstünde yazı, düşük kalite."""
    r = subprocess.run([ortak.ffmpeg(), "-v", "error", "-y", "-ss", "0.6", "-i", kaynak, "-t", "6.5",
                        "-vf", "hflip,scale=144:-2,crop=iw*0.96:ih*0.96,drawbox=x=10:y=100:w=110:h=24:color=white:t=fill",
                        "-c:v", "libx264", "-crf", "32", yol], capture_output=True)
    assert r.returncode == 0, r.stderr
    return yol


@pytest.fixture
def vid(tmp_path):
    g = tmp_path / "gelen"; g.mkdir()
    a = yaz(str(g / "a.mp4"), range(100, 108))                       # 8 sn
    return {"a": a, "kopya": donustur(a, str(g / "a_baska_hesap.mp4")),
            "farkli": yaz(str(g / "b.mp4"), range(200, 208)),
            "benzer": yaz(str(g / "c.mp4"), [100, 101, 102, 103, 300, 301, 302, 303])}   # ilk yarı a'nın çekimi


def test_parmak_izi_siniflar(vid):
    iz = {k: aynilik.parmak_izi(v) for k, v in vid.items()}
    assert aynilik.karsilastir(iz["a"], iz["kopya"])[0] in ("aynı", "parça")
    assert aynilik.karsilastir(iz["a"], iz["farkli"])[0] is None
    assert aynilik.karsilastir(iz["a"], iz["benzer"])[0] == "benzer"
    assert aynilik.karsilastir(iz["farkli"], iz["benzer"])[0] is None


def test_sira_sarti_karisik_sahneleri_eler(tmp_path):
    """Aynı sahneler ters sırada = başka kurgu: kopya sayılmaz (sıra şartı ölçülüyor mu?)."""
    a = aynilik.parmak_izi(yaz(str(tmp_path / "a.mp4"), range(100, 108)))
    ters = aynilik.parmak_izi(yaz(str(tmp_path / "t.mp4"), range(107, 99, -1)))
    assert aynilik.karsilastir(a, ters)[0] not in ("aynı", "parça")


def test_kopya_teslim_edilmez_ve_kenara_tasinir(vid, tmp_path):
    proje, hedef = str(tmp_path / "is"), str(tmp_path / "Masaustu")
    (ka,), _ = marka.ekle([vid["a"]], proje)
    marka.marka_ata([os.path.basename(ka)], "Lumo", "gece lambası", proje)
    (kk,), _ = marka.ekle([vid["kopya"]], proje)
    m = ortak.oku_json(os.path.join(kk, ortak.META))
    assert m["kopya_adayi"]["klasor"] == os.path.basename(ka) and os.path.exists(m["kopya_adayi"]["gorsel"])
    assert m["marka"] == "Lumo"                                    # aynı çekim → aynı ürün
    for k in (ka, kk): shutil.copy2(os.path.join(k, ortak.KAYNAK), os.path.join(k, ortak.CIKTI))
    assert marka.teslim(proje, hedef, baslangic="2026-12-01") == [os.path.join(hedef, "Lumo", "1.mp4")]   # kopya bekler
    tasindi = marka.kopya_karar(os.path.basename(kk), True, proje)
    assert os.path.exists(os.path.join(tasindi, ortak.KAYNAK)) and not os.path.exists(kk)
    assert marka.ekle([vid["kopya"]], proje)[0] == []              # aynı dosya yeniden gelirse yine alınmaz
    assert marka.teslim(proje, hedef) == []


def test_kopya_degil_karari_ve_benzer_notu(vid, tmp_path):
    proje, hedef = str(tmp_path / "is"), str(tmp_path / "Masaustu")
    (ka,), _ = marka.ekle([vid["a"]], proje)
    marka.marka_ata([os.path.basename(ka)], "Lumo", "gece lambası", proje)
    (kk,), _ = marka.ekle([vid["kopya"]], proje)
    marka.kopya_karar(os.path.basename(kk), False, proje)
    (kb,), _ = marka.ekle([vid["benzer"]], proje)
    mb = ortak.oku_json(os.path.join(kb, ortak.META))
    assert "kopya_adayi" not in mb and mb["benzer"][0]["klasor"] in (os.path.basename(ka), os.path.basename(kk))
    for k in (ka, kk, kb): shutil.copy2(os.path.join(k, ortak.KAYNAK), os.path.join(k, ortak.CIKTI))
    assert len(marka.teslim(proje, hedef, baslangic="2026-12-01")) == 3
    import csv
    with open(os.path.join(hedef, "Lumo", marka.PLAN), encoding="utf-8-sig") as f: plan = list(csv.DictReader(f))
    assert "ortak çekim" in plan[2]["not"] and "Lumo/" in plan[2]["not"]
