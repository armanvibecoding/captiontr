"""Yorum balonu (TikTok/Instagram yoruma yanıt) Türkçeleştirme + hook tekrarı kapısı. OCR gerektirmez."""
import os, subprocess

import cv2, numpy as np, pytest
from PIL import Image, ImageDraw, ImageFont

from captiontr import analiz, cevir, hook, ortak

W, H, FPS = 360, 640, 20
AVATAR = (120, 150, 210)      # BGR — eski balondaki profil resmi rengi; çıktıda kalmamalı
BALON = [30, 150, 290, 210]


def kare(i, balon):
    rng = np.random.default_rng(3)
    doku = cv2.resize(rng.integers(30, 200, (16, 9, 3), dtype=np.uint8), (W + 40, H + 40), interpolation=cv2.INTER_CUBIC)
    f = doku[i % 40:i % 40 + H, i % 40:i % 40 + W].copy()
    if not balon: return f
    img = Image.fromarray(f[..., ::-1]); d = ImageDraw.Draw(img)
    d.rounded_rectangle(BALON, radius=8, fill=(255, 255, 255))
    d.ellipse([38, 160, 78, 200], fill=AVATAR[::-1])
    d.text((86, 158), "Reply to emma's comment", font=ImageFont.truetype(ortak.FONT, 11), fill=(120, 120, 128))
    d.text((86, 176), "does it work on thick hair?", font=ImageFont.truetype(ortak.FONT, 15), fill=(20, 20, 20))
    return np.asarray(img)[..., ::-1].copy()


@pytest.fixture
def yorumlu(tmp_path):
    k = tmp_path / "v"; k.mkdir(); v = str(k / ortak.KAYNAK)
    p = subprocess.Popen([ortak.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", v], stdin=subprocess.PIPE)
    for i in range(60): p.stdin.write(kare(i, 10 <= i < 50).tobytes())
    p.stdin.close(); assert p.wait() == 0
    return k


def _avatar_pikseli(f):
    """Eski profil resminin olduğu yerde (yeni yazının emojisi bu bölgeye girmez) eski renk kaldı mı?"""
    return int((np.abs(f[156:204, 34:82].astype(int) - AVATAR).max(axis=2) < 30).sum())


def test_balon_kutusu_olculur(yorumlu):
    f = kare(20, True)
    k = analiz.balon_kutu(f, [86, 158, 280, 195])                 # yalnız yazının kutusu verilir
    assert k[0] <= BALON[0] + 2 and k[1] <= BALON[1] + 2 and k[2] >= BALON[2] - 2 and k[3] >= BALON[3] - 2   # avatar dahil


def test_balon_satirlari_altyaziya_karismaz():
    satir = lambda m, x0, y0, x1, y1: {"metin": m, "x0": x0, "y0": y0, "x1": x1, "y1": y1}
    ornekler = [(1.0, [satir("Reply to emma's comment", 86, 158, 240, 170), satir("does it work on thick hair?", 86, 176, 280, 194),
                       satir("You need this", 100, 500, 260, 530)])]
    bulunan = analiz.yorumlari_ayir(ornekler, W, H)
    assert [x["metin"] for x in ornekler[0][1]] == ["You need this"]   # altyazı olarak yalnız bu kaldı
    assert bulunan[0][1]["govde"] == ["does it work on thick hair?"]
    assert analiz._kullanici("Reply to emma.rose's comment") == "emma.rose"


def test_yorum_balonu_turkcelesir_eskisi_kalmaz(yorumlu):
    ayar = {"kaynak": str(yorumlu / ortak.KAYNAK), "cikti": str(yorumlu / ortak.CIKTI), "altyazilar": [],
            "yorumlar": [{"bas": 0.5, "bit": 2.5, "kutu": BALON, "platform": "tiktok", "kullanici": "emma",
                          "govde_px": 18, "metin": "Kalın saçta işe yarıyor mu? 🤔"}], "cevrildi": True}
    ortak.yaz_json(str(yorumlu / ortak.AYAR), ayar)
    cevir.cevir(str(yorumlu / ortak.AYAR))
    kaynak = dict(ortak.kareler(str(yorumlu / ortak.KAYNAK))); cikti = dict(ortak.kareler(str(yorumlu / ortak.CIKTI)))
    assert _avatar_pikseli(kaynak[30]) > 300                                  # kırma: eski balon kaynakta var
    assert all(_avatar_pikseli(cikti[i]) == 0 for i in range(10, 50))        # her karede tamamen örtüldü
    assert np.abs(cikti[30][BALON[1] + 5:BALON[3] - 5, BALON[0] + 5:BALON[2] - 5].astype(int)
                  - kaynak[30][BALON[1] + 5:BALON[3] - 5, BALON[0] + 5:BALON[2] - 5]).mean() > 5   # yeni yazı basıldı
    assert np.abs(cikti[55].astype(int) - kaynak[55]).mean() < 4              # balon bitince kareye dokunulmaz
    assert ortak.metadata_rapor(str(yorumlu / ortak.CIKTI)) == []


def _video_klasoru(proje, ad, marka, ilk):
    k = proje / ad; k.mkdir(parents=True); (k / ortak.KAYNAK).write_bytes(b"")
    ortak.yaz_json(str(k / ortak.META), {"marka": marka})
    ortak.yaz_json(str(k / ortak.AYAR), {"altyazilar": [{"bas": 0, "satirlar": ilk}]})
    return k


def test_hook_tekrari_ayni_markada_yakalanir(tmp_path):
    p = tmp_path / "is"
    _video_klasoru(p, "v1", "Lumo", ["Bundan sende de olmalı 😍"])
    v2 = _video_klasoru(p, "v2", "Lumo", ["Bundan sen de olmalı!"])         # neredeyse aynı giriş
    v3 = _video_klasoru(p, "v3", "Lumo", ["Gece 3'te uyanınca ışık açmak zorunda kalanlar"])
    v4 = _video_klasoru(p, "v4", "Pati", ["Bundan sende de olmalı 😍"])     # başka marka: serbest
    assert hook.tekrar_eden(str(v2))[1].endswith("v1")
    assert hook.tekrar_eden(str(p / "v1")) is None                         # önce gelen bekletilmez
    assert hook.tekrar_eden(str(v3)) is None
    assert hook.tekrar_eden(str(v4)) is None
    kullanilan, _ = hook.hooklar(str(p), "Lumo")
    assert len(kullanilan) == 3
