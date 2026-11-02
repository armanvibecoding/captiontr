"""Maske ölçüm düzeneği: gerçek videolara BİLİNEN yazı basılır, maskenin kaçırdığı ve fazladan sildiği piksel ölçülür.

  python -m reeltr.maske_olc uret <cikti_klasor> <kaynak_klasor>...   → her kaynak × stil için sentetik video + doğru cevap
  python -m reeltr.maske_olc olc <cikti_klasor>                       → OCR + maske + karne

Doğru cevap kare kare bilinir (yazı katmanının alfası + yazısız orijinal kare), yani:
  kaçan  = yazının görünür (|yazılı − temiz| > GORUNUR) pikseli maskede değil → silinmeden kalan iz
  fazla  = maskede ama yazının etkilemediği piksel → boşuna yeniden boyanan arka plan (leke kaynağı)
"""
import json, os, subprocess, sys

import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import ortak

SURE, BAS, BIT = 6.0, 1.0, 5.0     # sn: klip, yazının girişi ve çıkışı
GORUNUR = 12                       # bu kadar renk farkı gözle seçilir sayılır
METIN = ["This changed my", "whole morning routine"]
STILLER = {
    # ad: kenar px (1080 genişlikte), gölge, kutu, emoji, animasyon
    "kenarli": dict(kenar=3),
    "golgeli": dict(golge=True),
    "sade": dict(anim="buyu"),
    "kutulu": dict(kutu=True),
    "emojili": dict(kenar=3, emoji="😭🔥", anim="belir"),
}


def _font(px):
    from .cevir import font_ac
    return font_ac(px, 600)


def katman(W, H, yc, stil, olcek=1.0):
    """RGBA yazı katmanı (tam kare). yc: blok dikey merkezi."""
    from .cevir import emoji_png
    k = W / 1080
    fp = int(50 * k * olcek); font = _font(fp); aralik = int(fp * 1.25)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    satirlar = list(METIN)
    eh = int(fp * 1.05); emo = stil.get("emoji")
    y_ilk = yc - aralik * (len(satirlar) - 1) / 2
    golge = Image.new("RGBA", (W, H), (0, 0, 0, 0)) if stil.get("golge") else None
    for si, s in enumerate(satirlar):
        gen = d.textlength(s, font=font) + (len(emo) * (eh + 4) if emo and si == len(satirlar) - 1 else 0)
        x = W / 2 - gen / 2; y = y_ilk + si * aralik
        if stil.get("kutu"):
            px, ky = 0.35 * fp, 1.45 * fp
            d.rounded_rectangle([x - px, y - ky / 2, x + gen + px, y + ky / 2], radius=0.28 * ky, fill=(255, 255, 255, 255))
        if golge is not None:
            ImageDraw.Draw(golge).text((x + 3 * k, y + 3 * k), s, font=font, fill=(0, 0, 0, 170), anchor="lm")
        renk = (0, 0, 0, 255) if stil.get("kutu") else (255, 255, 255, 255)
        kenar = int(round(stil.get("kenar", 0) * k))
        d.text((x, y), s, font=font, fill=renk, anchor="lm", stroke_width=kenar, stroke_fill=(0, 0, 0, 255))
        if emo and si == len(satirlar) - 1:
            ex = x + d.textlength(s, font=font) + 4
            for e in emo:
                p = Image.open(emoji_png(e)).convert("RGBA").resize((eh, eh), Image.LANCZOS)
                img.alpha_composite(p, (int(ex), int(y - eh / 2))); ex += eh + 4
    if golge is not None:
        golge = golge.filter(ImageFilter.GaussianBlur(3 * k))
        golge.alpha_composite(img); img = golge
    return np.asarray(img)


def _bos_yer(ayar, H):
    """OCR'daki orijinal yazılardan uzak bir dikey merkez."""
    kut = [k for a in (ayar or {}).get("altyazilar", []) for k in a.get("kutular", [])]
    for oran in (0.66, 0.74, 0.56, 0.45, 0.82):
        yc = oran * H
        if all(k[3] < yc - 0.1 * H or k[1] > yc + 0.1 * H for k in kut): return yc
    return 0.66 * H


def uret(cikti, kaynaklar):
    os.makedirs(cikti, exist_ok=True)
    for kay in kaynaklar:   # "klasör@sn": yazısız aralığın başı (orijinal yazıyla aynı anda olmasın)
        kay, _, ofs = kay.partition("@"); ofs = float(ofs or 0)
        ad = os.path.basename(kay.rstrip("/"))
        video = os.path.join(kay, ortak.KAYNAK)
        b = ortak.bilgi(video); W, H, FPS = b["w"], b["h"], b["fps"]
        ayar_p = os.path.join(kay, ortak.AYAR)
        yc = _bos_yer(ortak.oku_json(ayar_p) if os.path.exists(ayar_p) else None, H)
        i0 = int(ofs * FPS); n = min(b["n"] - i0, int(SURE * FPS))
        for sad, stil in STILLER.items():
            d = os.path.join(cikti, f"{ad}__{sad}"); os.makedirs(d, exist_ok=True)
            if os.path.exists(os.path.join(d, "dogru.npz")): continue
            tam = katman(W, H, yc, stil)
            ff = subprocess.Popen([ortak.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                                   "-r", ortak.fps_kesir(video), "-i", "-", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                                   os.path.join(d, ortak.KAYNAK)], stdin=subprocess.PIPE)
            dogru, temiz = {}, {}
            for j, f in ortak.kareler(video):
                if j < i0: continue
                i = j - i0
                if i >= n: break
                t = i / FPS
                if BAS <= t < BIT:
                    a = stil.get("anim"); ilerle = min(1.0, (t - BAS) / 0.3)
                    if a == "buyu" and ilerle < 1: k = katman(W, H, yc, stil, olcek=0.6 + 0.4 * ilerle)
                    else: k = tam
                    rgba = k.astype(np.float32)
                    al = rgba[..., 3:4] / 255 * (ilerle if a == "belir" else 1.0)
                    o = (f.astype(np.float32) * (1 - al) + rgba[..., 2::-1] * al).clip(0, 255).astype(np.uint8)
                    ys, xs = np.nonzero(al[..., 0] > 0)
                    if not len(ys): ff.stdin.write(f.tobytes()); continue   # belirmenin ilk karesi: yazı henüz yok
                    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
                    # görünür etki: bu pikselde yazı arka planı ne kadar değiştirdi
                    etki = np.abs(o[y0:y1, x0:x1].astype(np.int16) - f[y0:y1, x0:x1]).max(axis=2).astype(np.uint8)
                    dogru[i] = (y0, x0, etki); temiz[i] = f[y0:y1, x0:x1]
                    f = o
                ff.stdin.write(f.tobytes())
            ff.stdin.close(); assert ff.wait() == 0
            np.savez_compressed(os.path.join(d, "dogru.npz"),
                                **{f"e{i}": v[2] for i, v in dogru.items()},
                                konum=np.array([[i, v[0], v[1]] for i, v in dogru.items()]))
            print("üretildi", os.path.basename(d), flush=True)


def _hazirla_ayar(d):
    """OCR (analiz) + her yazıya yer tutucu çeviri: maske üretimi için yeterli."""
    from . import analiz
    p = os.path.join(d, ortak.AYAR)
    if not os.path.exists(p): analiz.analiz_et(d)
    a = ortak.oku_json(p)
    for x in a.get("altyazilar", []): x.setdefault("satirlar", ["x"]); x["satirlar"] = x["satirlar"] or ["x"]
    a["cikti"] = os.path.join(d, "TR.mp4")
    ortak.yaz_json(p, a)
    return p


def olc_bir(d, maske_fn=None, ek=None):
    from . import cevir
    p = _hazirla_ayar(d)
    ayar = cevir.ayar_yukle(p); ayar.update(ek or {})
    z = np.load(os.path.join(d, "dogru.npz"))
    konum = {int(i): (int(y0), int(x0)) for i, y0, x0 in z["konum"]}
    b = ortak.bilgi(ayar["kaynak"]); W, H = b["w"], b["h"]
    if ayar.get("altyazilar"):
        _, maske, _, etiket, kare_maske = (maske_fn or cevir.yazilari_hazirla)(ayar)
        Y0, Y1 = ayar["bant"]
    else:
        etiket, maske, kare_maske, Y0, Y1 = [-2] * b["n"], [], {}, 0, 1
    kacan = gorunur = fazla = 0; kare_kacan = 0; toplam = 0
    for i, (y0, x0) in konum.items():
        e = z[f"e{i}"]; hh, ww = e.shape
        gor = e > GORUNUR; toplam += int(gor.sum())
        m = np.zeros((H, W), bool)
        k = etiket[i] if i < len(etiket) else -2
        if k >= 0: m[Y0:Y1] = kare_maske.get(i, maske[k][0]) > 0
        bolge = m[y0:y0 + hh, x0:x0 + ww]
        kc = gor & ~bolge
        kacan += int(kc.sum()); kare_kacan += int(kc.sum() > 0)
        gorunur += int((e[kc] > 40).sum())
        # fazla: yazının değmediği (etki 0) ama maskelenen pikseller, yazı çevresinde 2× yükseklik içinde
        pay = hh
        a0, a1, b0, b1 = max(0, y0 - pay), min(H, y0 + hh + pay), max(0, x0 - pay), min(W, x0 + ww + pay)
        dokunan = np.zeros((a1 - a0, b1 - b0), bool)
        dokunan[y0 - a0:y0 - a0 + hh, x0 - b0:x0 - b0 + ww] = e > 0
        fazla += int((m[a0:a1, b0:b1] & ~dokunan).sum())
    n = len(konum)
    return {"video": os.path.basename(d), "kare": n, "kacan_kare": kare_kacan,
            "kacan_px_kare": round(kacan / n, 1), "belirgin_kacan_px_kare": round(gorunur / n, 1),
            "fazla_oran": round(fazla / max(1, toplam), 2)}


def goster(d, cikti, anlar=(0.1, 0.5), maske_fn=None, ek=None):
    """Teşhis görseli: yeşil = doğru silinen, kırmızı = KAÇAN (iz kalır), mavi = fazla silinen."""
    from . import cevir
    ayar = cevir.ayar_yukle(_hazirla_ayar(d)); ayar.update(ek or {})
    z = np.load(os.path.join(d, "dogru.npz")); konum = {int(i): (int(y0), int(x0)) for i, y0, x0 in z["konum"]}
    _, maske, _, etiket, kare_maske = (maske_fn or cevir.yazilari_hazirla)(ayar); Y0, Y1 = ayar["bant"]
    ii = sorted(konum); sec = [ii[int(a * (len(ii) - 1))] for a in anlar]
    c = cv2.VideoCapture(ayar["kaynak"]); satir = []
    for i in sec:
        c.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = c.read(); H, W = f.shape[:2]
        y0, x0 = konum[i]; e = z[f"e{i}"]; hh, ww = e.shape
        m = np.zeros((H, W), bool); k = etiket[i]
        if k >= 0: m[Y0:Y1] = kare_maske.get(i, maske[k][0]) > 0
        g = np.zeros((H, W), bool); g[y0:y0 + hh, x0:x0 + ww] = e > GORUNUR
        o = (f * 0.55).astype(np.uint8)
        o[g & m] = (0, 200, 0); o[g & ~m] = (0, 0, 255); o[m & ~g] = (255, 120, 0)
        pay = hh // 2
        a0, a1, b0, b1 = max(0, y0 - pay), min(H, y0 + hh + pay), max(0, x0 - pay), min(W, x0 + ww + pay)
        satir.append(np.hstack([f[a0:a1, b0:b1], o[a0:a1, b0:b1]]))
    gen = max(s.shape[1] for s in satir)
    cv2.imwrite(cikti, np.vstack([cv2.copyMakeBorder(s, 0, 4, 0, gen - s.shape[1], cv2.BORDER_CONSTANT) for s in satir]))


def olc(cikti, maske_fn=None, ek=None):
    ortak.utf8()
    sonuc = []
    for ad in sorted(os.listdir(cikti)):
        d = os.path.join(cikti, ad)
        if not os.path.exists(os.path.join(d, "dogru.npz")): continue
        try: r = olc_bir(d, maske_fn, ek)
        except Exception as e: r = {"video": ad, "hata": str(e)[:120]}
        sonuc.append(r); print(json.dumps(r, ensure_ascii=False), flush=True)
    iyi = [r for r in sonuc if "hata" not in r]
    if iyi:
        print(f"ÖZET: {len(iyi)} video | kaçan kare oranı %{100 * sum(r['kacan_kare'] for r in iyi) / sum(r['kare'] for r in iyi):.1f}"
              f" | kare başı kaçan px {np.mean([r['kacan_px_kare'] for r in iyi]):.0f}"
              f" (belirgin {np.mean([r['belirgin_kacan_px_kare'] for r in iyi]):.0f})"
              f" | fazla alan ×{np.median([r['fazla_oran'] for r in iyi]):.2f} yazı alanı (medyan)")
    return sonuc


if __name__ == "__main__":
    if sys.argv[1] == "uret": uret(sys.argv[2], sys.argv[3:])
    elif sys.argv[1] == "goster": goster(sys.argv[2], sys.argv[3], ek={"maske": sys.argv[4]} if len(sys.argv) > 4 else None)
    else: olc(sys.argv[2], ek={"maske": sys.argv[3]} if len(sys.argv) > 3 else None)
