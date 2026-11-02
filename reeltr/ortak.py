"""Ortak yardımcılar: yollar, ffmpeg, video bilgisi, iş klasörü düzeni."""
import json, os, subprocess, sys
from fractions import Fraction

import cv2

KOK = os.path.dirname(os.path.abspath(__file__))
VARLIK = os.path.join(KOK, "varliklar")
FONT = os.path.join(VARLIK, "TikTokSans.ttf")
EMOJI = os.path.join(VARLIK, "emoji_png")

# iş klasörü düzeni: <proje>/<urun>-<kod>/{kaynak.mp4, meta.json, ayar.json, tablo.png, TR.mp4, TR_kontrol.png}
KAYNAK, META, AYAR, TABLO, CIKTI = "kaynak.mp4", "meta.json", "ayar.json", "tablo.png", "TR.mp4"


def utf8():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def fps_kesir(video):
    """ffmpeg'in gördüğü kare hızı (ör. 30000/1001). cv2'nin float değerinden daha doğru."""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", video], capture_output=True, text=True)
    for satir in r.stderr.splitlines():
        if "Video:" in satir:
            for p in satir.split(","):
                p = p.strip()
                if p.endswith(" fps"):
                    try: return str(Fraction(p[:-4]).limit_denominator(1001))
                    except ValueError: pass
    cap = cv2.VideoCapture(video)
    return f"{cap.get(cv2.CAP_PROP_FPS):.6f}"


def bilgi(video):
    cap = cv2.VideoCapture(video)
    if not cap.isOpened(): raise RuntimeError(f"video açılamadı: {video}")
    b = dict(fps=cap.get(cv2.CAP_PROP_FPS), n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
             w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    cap.release()
    return b


def kareler(video):
    """Kareleri sırayla verir (belleğe hepsini almaz)."""
    cap = cv2.VideoCapture(video)
    i = 0
    while True:
        ok, f = cap.read()
        if not ok: break
        yield i, f
        i += 1
    cap.release()


def is_klasorleri(proje):
    """Projedeki video klasörleri (içinde kaynak.mp4 olanlar), sıralı."""
    if os.path.exists(os.path.join(proje, KAYNAK)): return [proje]
    return sorted(os.path.join(proje, d) for d in os.listdir(proje)
                  if os.path.exists(os.path.join(proje, d, KAYNAK)))


def oku_json(p):
    with open(p, encoding="utf-8") as f: return json.load(f)


def yaz_json(p, veri):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(veri, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


# ---------- metadata ----------
# dosya baytlarında aranan imzalar (kısa imzalar rastgele sıkıştırılmış veride de geçer → tam biçim aranır)
IZLER = [rb"Lav[fc]\d{2}\.\d+\.\d+", rb"x264 - core \d+", rb"x265 \(build", rb"VPC Coding", rb"[AH]?[VE]C Coding",
         rb"[Ii]nstagram", rb"[Tt]ik[Tt]ok", rb"vid:v\d", rb"<x:xmpmeta", rb"creation_time", rb"com\.apple\.quicktime",
         rb"\xa9too", rb"\xa9cmt", rb"\xa9xyz", rb"CapCut", rb"[Ll]avc\d"]
# 4 baytlık kutu adları sıkıştırılmış veride (mdat) tesadüfen geçer (252 videoda 3 kez ölçüldü) — yalnız başlıkta aranır
KUTU_IZLERI = (rb"\xa9too", rb"\xa9cmt", rb"\xa9xyz")


def _mdat_disi(veri):
    """Üst düzey MP4 kutularından mdat dışındakilerin baytları (kutu adı etiketleri yalnız orada yaşar)."""
    import struct
    parca, i = [], 0
    while i + 8 <= len(veri):
        boy, tip = struct.unpack(">I4s", veri[i:i + 8])
        if boy == 1 and i + 16 <= len(veri): boy = struct.unpack(">Q", veri[i + 8:i + 16])[0]
        elif boy == 0: boy = len(veri) - i
        if boy < 8: return veri   # bozuk/MP4 değil → tamamında ara
        if tip != b"mdat": parca.append(veri[i:i + boy])
        i += boy
    return b"".join(parca)


def _ffmpeg_bilgi(video):
    return subprocess.run([ffmpeg(), "-hide_banner", "-i", video], capture_output=True, text=True).stderr


def codec(video):
    for s in _ffmpeg_bilgi(video).splitlines():
        if "Video:" in s: return s.split("Video:")[1].split()[0].strip(",")
    return ""


def yan_veri(video):
    """Akış yan verileri (Side data): ortam ışığı (iPhone amve), HDR, döndürme vb."""
    satir, blok = [], False
    for s in _ffmpeg_bilgi(video).splitlines():
        if s.strip() == "Side data:": blok = True; continue
        if blok and s.startswith(" " * 8): satir.append(s.strip())
        else: blok = False
    return satir


def _remux(giris, cikis, ek):
    r = subprocess.run([ffmpeg(), "-v", "error", "-y", "-i", giris, *ek, cikis], capture_output=True, text=True)
    if r.returncode != 0:
        if os.path.exists(cikis): os.remove(cikis)
        raise RuntimeError(f"metadata temizlenemedi: {r.stderr.strip()[:300]}")


def metadata_temizle(giris, cikis=None):
    """Tüm metadata'yı kaldırır (yeniden kodlamadan): global + akış etiketleri, bölümler, oluşturma zamanı,
    encoder imzaları, kapak/veri akışları, cihaz yan verileri (ör. iPhone ortam ışığı);
    H.264/H.265'te akış içi SEI (x264 ayar imzası vb.) da silinir."""
    cikis = cikis or giris
    gecici = cikis + ".temiz.mp4"
    bsf = {"h264": ["-bsf:v", "filter_units=remove_types=6"], "hevc": ["-bsf:v", "filter_units=remove_types=39|40"]}.get(codec(giris), [])
    yan = yan_veri(giris)
    if any("displaymatrix" in y or "rotation" in y for y in yan):
        raise RuntimeError("videoda döndürme bilgisi var — temizlik yönü bozabilir, elle bakılmalı")
    kaynak = giris
    if yan:   # mp4→mp4 kopyada yan veriler taşınır; MKV ara adımı bunları düşürür
        kaynak = cikis + ".ara.mkv"
        _remux(giris, kaynak, ["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-map_metadata", "-1"])
    try:
        _remux(kaynak, gecici, ["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", *bsf,
               "-map_metadata", "-1", "-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1", "-map_chapters", "-1",
               "-metadata:s:v", "handler_name=", "-metadata:s:a", "handler_name=",
               "-metadata:s:v", "vendor_id=", "-metadata:s:a", "vendor_id=", "-metadata:s:v", "encoder=",
               "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", "-movflags", "+faststart"])
    finally:
        if kaynak != giris and os.path.exists(kaynak): os.remove(kaynak)
    os.replace(gecici, cikis)
    return cikis


def metadata_rapor(video):
    """Kalan izler: ffmpeg'in okuduğu etiketler + yan veriler + dosya baytlarındaki imzalar. Boş liste = temiz."""
    import re
    kalan = []
    zararsiz = ("major_brand", "minor_version", "compatible_brands", "handler_name", "vendor_id")
    blok = False
    for s in _ffmpeg_bilgi(video).splitlines():
        if s.strip() == "Metadata:": blok = True; continue
        if blok and ":" in s and s.startswith(" " * 4) and not s.strip().startswith(("Stream", "Duration", "Side data")):
            k, v = [x.strip() for x in s.split(":", 1)]
            if k not in zararsiz or (k == "handler_name" and v not in ("", "VideoHandler", "SoundHandler")) or (k == "vendor_id" and v.strip("[0]")):
                kalan.append(f"etiket {k}={v}")
        else: blok = False
    kalan += [f"yan veri {y}" for y in yan_veri(video)]
    with open(video, "rb") as f: veri = f.read()
    baslik = _mdat_disi(veri)
    for iz in IZLER:
        m = re.search(iz, baslik if iz in KUTU_IZLERI else veri)
        if m: kalan.append(f"bayt {m.group(0)[:40].decode('latin-1')}")
    return kalan
