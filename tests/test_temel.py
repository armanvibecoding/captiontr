"""Sentetik videoyla uçtan uca testler (ağ ve OCR gerektirmez).

Video: hareketli gürültülü arka plan; 1.0–3.0 sn arasında beyaz+siyah kenarlı yazı, öncesi/sonrası YAZISIZ.
"""
import os, subprocess

import cv2, numpy as np, pytest
from PIL import Image, ImageDraw, ImageFont

from captiontr import cevir, ortak

W, H, FPS, SURE = 360, 640, 20, 4.0
Y0, Y1 = 150, 260


def arka_plan(i):
    rng = np.random.default_rng(i)
    x = np.linspace(0, 6, W)[None, :] + i * 0.15
    taban = ((np.sin(x + np.linspace(0, 3, H)[:, None]) + 1) * 90 + 20).astype(np.uint8)
    f = np.dstack([taban, np.roll(taban, i * 3, axis=1), 255 - taban])
    return np.clip(f.astype(np.int16) + rng.integers(-12, 12, f.shape), 0, 255).astype(np.uint8)


def yazi_bas(f, metin):
    img = Image.fromarray(f[..., ::-1]); d = ImageDraw.Draw(img)
    font = ImageFont.truetype(ortak.FONT, 34)
    d.text((W / 2, 190), metin, font=font, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0), anchor="mt")
    return np.asarray(img)[..., ::-1].copy()


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    d = tmp_path_factory.mktemp("v")
    p = str(d / "kaynak.mp4")
    ff = subprocess.Popen([ortak.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", p], stdin=subprocess.PIPE)
    for i in range(int(SURE * FPS)):
        f = arka_plan(i)
        if 1.0 <= i / FPS < 3.0: f = yazi_bas(f, "Hello world")
        ff.stdin.write(f.tobytes())
    ff.stdin.close(); assert ff.wait() == 0
    return d


def kare(p, i):
    c = cv2.VideoCapture(p); c.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = c.read(); return f


def test_emoji_kumeleri():
    assert cevir.emoji_kumeleri("çok zor 👎😭") == [("metin", "çok zor "), ("emoji", "👎"), ("emoji", "😭")]
    assert cevir.emoji_kumeleri("💪🏻") == [("emoji", "💪🏻")]


def test_etiketle_yazisiz_ve_titreme():
    s = [[0.0]] * 10 + [[0.9]] * 10 + [[0.1]] * 2 + [[0.9]] * 10 + [[0.0]] * 10
    et = cevir.etiketle(s, fps=20)
    assert et[:10] == [-2] * 10          # yazısız baş: dokunulmaz
    assert et[10:32] == [0] * 22          # 2 karelik titreme doldurulur
    assert et[32:] == [-2] * 10           # yazısız son


def test_render_yazisiz_karelere_dokunmaz(video):
    ayar = {"kaynak": str(video / "kaynak.mp4"), "cikti": str(video / "TR.mp4"), "bant": [Y0, Y1],
            "altyazilar": [{"ornek_sn": 2.0, "orijinal": ["Hello world"], "kutular": [], "satirlar": ["Merhaba dünya"]}]}
    a = str(video / "ayar.json"); ortak.yaz_json(a, ayar)
    cikti, kontrol = cevir.cevir(a)
    assert os.path.exists(cikti) and os.path.exists(kontrol)
    assert ortak.bilgi(cikti)["n"] == int(SURE * FPS)
    # yazısız kare (0.5 sn): bantta yeni beyaz yazı olmamalı
    bos = cevir.beyaz(kare(cikti, 10)[Y0:Y1]).mean()
    yazili = cevir.beyaz(kare(cikti, 40)[Y0:Y1]).mean()
    assert bos < 0.002, f"yazısız kareye yazı basılmış: {bos}"
    assert yazili > 0.01, "yazılı karede yeni yazı yok"


def test_eski_yazi_tamamen_silinir(video):
    # yeni yazı tek küçük karakter: eski yazının yerinde kalan beyaz = silinmemiş iz
    ayar = {"kaynak": str(video / "kaynak.mp4"), "cikti": str(video / "TR_sil.mp4"), "bant": [Y0, Y1],
            "altyazilar": [{"ornek_sn": 2.0, "satirlar": ["."]}]}
    a = str(video / "ayar_sil.json"); ortak.yaz_json(a, ayar)
    cikti, _ = cevir.cevir(a)
    org = cevir.beyaz(kare(ayar["kaynak"], 40)[Y0:Y1]); yeni = cevir.beyaz(kare(cikti, 40)[Y0:Y1])
    kalan = (org & yeni).sum() / max(1, org.sum())
    assert kalan < 0.03, f"eski yazıdan iz kaldı: {kalan:.3f}"


def test_metadata_temizligi(video):
    # kaynak ffmpeg+x264 ile üretildi: imzalı olmalı (dedektör gerçekten yakalıyor mu?)
    assert any("x264" in k for k in ortak.metadata_rapor(str(video / "kaynak.mp4")))
    cikti = str(video / "TR.mp4")   # render çıktısı otomatik temizlenmiş olmalı
    assert ortak.metadata_rapor(cikti) == []
    t = str(video / "kopya.mp4"); ortak.metadata_temizle(str(video / "kaynak.mp4"), t)
    assert ortak.metadata_rapor(t) == []
    assert ortak.bilgi(t)["n"] == ortak.bilgi(str(video / "kaynak.mp4"))["n"]


def test_tekrar_tespiti(video):
    from captiontr import sec
    a = sec.parmak_izi(str(video / "kaynak.mp4"))
    b = sec.parmak_izi(str(video / "TR.mp4"))          # aynı çekim, farklı altyazı
    assert sec.benzerlik(a, b) >= sec.ORTAK_PAY
    rng = np.random.default_rng(0)                      # bambaşka görüntü
    c = np.array([sec.dhash(rng.integers(0, 255, (64, 36, 3), dtype=np.uint8)) for _ in range(4)])
    assert sec.benzerlik(a, c) < sec.ORTAK_PAY


def kutulu_bas(f, satirlar):
    img = Image.fromarray(f[..., ::-1]); d = ImageDraw.Draw(img)
    font = ImageFont.truetype(ortak.FONT, 26)
    for i, s in enumerate(satirlar):
        w = d.textlength(s, font=font); y = 175 + i * 40
        d.rounded_rectangle([W / 2 - w / 2 - 12, y - 18, W / 2 + w / 2 + 12, y + 18], radius=10, fill=(255, 255, 255))
        d.text((W / 2, y), s, font=font, fill=(0, 0, 0), anchor="mm")
    return np.asarray(img)[..., ::-1].copy()


@pytest.fixture(scope="module")
def kutulu_video(tmp_path_factory):
    d = tmp_path_factory.mktemp("k"); p = str(d / "kaynak.mp4")
    ff = subprocess.Popen([ortak.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", p], stdin=subprocess.PIPE)
    for i in range(int(SURE * FPS)):
        ff.stdin.write(kutulu_bas(arka_plan(i), ["POV: you need", "this gadget"]).tobytes())
    ff.stdin.close(); assert ff.wait() == 0
    return d


def koyu_bant(f):
    return (f[Y0:Y1].max(axis=2) < 60)


def test_kutulu_stil(kutulu_video):
    d = kutulu_video
    ayar = {"kaynak": str(d / "kaynak.mp4"), "cikti": str(d / "TR.mp4"), "bant": [140, 250], "stil": "kutulu",
            "altyazilar": [{"ornek_sn": 2.0, "orijinal": ["POV: you need", "this gadget"],
                            "kutular": [[int(W / 2 - 90), 162, int(W / 2 + 90), 188], [int(W / 2 - 75), 202, int(W / 2 + 75), 228]],
                            "satirlar": ["Bu alet", "şart"]}]}
    a = str(d / "ayar.json"); ortak.yaz_json(a, ayar)
    cikti, _ = cevir.cevir(a)
    org = kare(ayar["kaynak"], 40); yeni = kare(cikti, 40)
    # yeni kısa metnin kutusu dışında kalan eski kutu alanı silinmiş olmalı (beyaz kalmamalı)
    kenar_bolge = (slice(150, 240), slice(int(W / 2 - 100), int(W / 2 - 70)))
    assert cevir.beyaz(org[kenar_bolge]).mean() > 0.2   # ön koşul: orijinalde eski kutu orada
    assert cevir.beyaz(yeni[kenar_bolge]).mean() < 0.1, "eski kutunun kenarı kalmış"
    # yeni yazı koyu renkte ve beyaz kutu içinde
    orta = (slice(160, 235), slice(int(W / 2 - 40), int(W / 2 + 40)))
    assert cevir.beyaz(yeni[orta]).mean() > 0.3, "yeni kutu yok"
    assert (yeni[orta].max(axis=2) < 80).mean() > 0.01, "kutuda koyu yazı yok"


def test_son_yazi_yalniz_sonda(video):
    ayar = {"kaynak": str(video / "kaynak.mp4"), "cikti": str(video / "TR_son.mp4"), "altyazilar": [],
            "son_yazi": {"metin": "Yorumlara ÜRÜN yaz, linki DM'den göndereyim 📩", "sure": 1.0, "y_oran": 0.7}}
    a = str(video / "ayar_son.json"); ortak.yaz_json(a, ayar)
    cikti, _ = cevir.cevir(a)
    y = slice(int(0.6 * H), int(0.8 * H))
    once = cevir.beyaz(kare(cikti, int((SURE - 2) * FPS))[y]).mean()
    sonda = cevir.beyaz(kare(cikti, int(SURE * FPS) - 3)[y]).mean()
    assert once < 0.01, f"son yazı erken görünüyor: {once}"
    assert sonda > 0.05, f"son yazı yok: {sonda}"


def test_ocr_zaman_araligi_disina_tasmaz(video):
    # yazı 1,0–3,0 sn'de; analiz aralığı 1,0–2,0 verilirse 2,4 sn sonrası (ör. arkadaki beyaz zemin) etiketlenmemeli
    ayar = {"kaynak": str(video / "kaynak.mp4"), "cikti": str(video / "TR_aralik.mp4"), "bant": [Y0, Y1],
            "altyazilar": [{"ornek_sn": 1.5, "bas": 1.0, "bit": 2.0, "satirlar": ["Merhaba dünya"]}]}
    a = str(video / "ayar_aralik.json"); ortak.yaz_json(a, ayar)
    cikti, _ = cevir.cevir(a)
    sonra = kare(cikti, int(2.8 * FPS)); org = kare(ayar["kaynak"], int(2.8 * FPS))
    # 2,8 sn'de orijinal İngilizce yazı olduğu gibi durmalı (aralık dışı = dokunulmaz)
    assert np.abs(sonra[Y0:Y1].astype(int) - org[Y0:Y1].astype(int)).mean() < 4


@pytest.fixture(scope="module")
def beyaz_sahne_video(tmp_path_factory):
    # 0–1,5 sn yazı; sonra uzun, sağ tarafı bembeyaz yazısız sahne (yatak/duvar): yazının sağ yarısıyla eşleşir
    d = tmp_path_factory.mktemp("b")
    p = str(d / "kaynak.mp4")
    ff = subprocess.Popen([ortak.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", p], stdin=subprocess.PIPE)
    rng = np.random.default_rng(1)
    for i in range(int(10 * FPS)):
        if i / FPS < 1.5: f = yazi_bas(arka_plan(i), "Hello world")
        else:
            f = np.full((H, W, 3), 200, np.uint8); f[:, 150:] = 250
            f = np.clip(f.astype(np.int16) + rng.integers(-3, 3, f.shape), 0, 255).astype(np.uint8)
        ff.stdin.write(f.tobytes())
    ff.stdin.close(); assert ff.wait() == 0
    return d


def test_ornek_kareler_ocr_araligindan(beyaz_sahne_video):
    # maske medyanı yazının kendi karelerinden çıkmalı; aralık dışındaki beyaz sahne örnekleri bozmamalı
    d = beyaz_sahne_video
    ayar = {"kaynak": str(d / "kaynak.mp4"), "cikti": str(d / "TR.mp4"), "bant": [Y0, Y1],
            "altyazilar": [{"ornek_sn": 0.75, "bas": 0.0, "bit": 1.5, "kutular": [[int(W / 2 - 95), 188, int(W / 2 + 95), 228]],
                            "satirlar": ["."]}]}
    a = str(d / "ayar.json"); ortak.yaz_json(a, ayar)
    cikti, _ = cevir.cevir(a)
    i = int(0.75 * FPS)
    org = cevir.beyaz(kare(ayar["kaynak"], i)[Y0:Y1]); yeni = cevir.beyaz(kare(cikti, i)[Y0:Y1])
    assert org.sum() > 200   # ön koşul: orijinalde yazı var
    kalan = (org & yeni).sum() / max(1, org.sum())
    assert kalan < 0.03, f"eski yazıdan iz kaldı: {kalan:.3f}"


def test_kapak_silinen_alani_orter(video):
    # kapak açıkken eski yazının bulunduğu bölge koyu kutu + beyaz yeni yazıdan ibaret olmalı (arka plan/silme izi görünmez)
    ayar = {"kaynak": str(video / "kaynak.mp4"), "cikti": str(video / "TR_kapak.mp4"), "bant": [Y0, Y1], "kapak": True,
            "altyazilar": [{"ornek_sn": 2.0, "satirlar": ["Merhaba"]}]}
    a = str(video / "ayar_kapak.json"); ortak.yaz_json(a, ayar)
    cikti, _ = cevir.cevir(a)
    org = kare(ayar["kaynak"], 40); yeni = kare(cikti, 40)
    ys, xs = np.nonzero(cevir.beyaz(org[Y0:Y1]))
    bolge = yeni[Y0 + ys.min():Y0 + ys.max() + 1, xs.min():xs.max() + 1].max(axis=2)
    yazi = cv2.dilate((bolge > 200).astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)   # yeni yazı + yumuşak kenarı
    ortulu = (bolge[~yazi] < 50).mean()
    assert ortulu > 0.95, f"kapak altında arka plan görünüyor: {ortulu:.2f}"


def test_hassas_maske_gorunur_her_pikseli_kapsar_fazlasi_az():
    """Oynayan arka planda beyaz+siyah kenarlı yazı: maske yazının görünür (|yazılı − temiz| > 12) HER pikselini
    kapsamalı (iz kalmasın) ve fazladan boyadığı alan yazı alanını aşmamalı (leke kaynağı küçük kalsın)."""
    from captiontr import maske
    kareler = [arka_plan(i) for i in range(20, 60, 2)]
    yazili = [yazi_bas(f, "Hello world") for f in kareler]
    bant = slice(Y0, Y1)
    ornk = np.stack([f[bant] for f in yazili])
    tohum = np.mean([cevir.beyaz(f) for f in ornk], axis=0) > 0.75
    gorunur = np.abs(yazili[5][bant].astype(np.int16) - kareler[5][bant]).max(axis=2) > 12
    ys, xs = np.nonzero(gorunur)
    kutu = [[int(xs.min()) + 2, int(ys.min()) + Y0 + 2, int(xs.max()) - 2, int(ys.max()) + Y0 - 2]]
    kisit = cevir.ocr_kisiti(kutu, Y0, tohum.shape, "kenarli")
    satir = cevir.ocr_satirlari(kutu, Y0)
    m, yontem = maske.hassas(ornk, tohum & cevir.siki_kisit(kutu, Y0, tohum.shape), kisit, satir, W,
                             None, np.median(ornk, axis=0))
    assert m is not None, yontem
    m = m > 0
    assert (gorunur & ~m).sum() == 0, f"{(gorunur & ~m).sum()} görünür yazı pikseli maskede değil"
    assert (m & ~gorunur).sum() <= gorunur.sum(), f"fazla alan {(m & ~gorunur).sum()} > yazı {gorunur.sum()}"
