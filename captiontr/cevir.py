"""Videoya gömülü (burned-in) beyaz yazıları silip yerine yeni metni aynı stilde basar.

ayar.json (bkz. analiz.py — taslağı otomatik üretir):
{
  "kaynak": ".../kaynak.mp4", "cikti": ".../TR.mp4",
  "bant": [170, 295],                    # yazıların olduğu yatay şerit (y0, y1)
  "altyazilar": [{"ornek_sn": 2.0, "satirlar": ["Saçına önem veren kızlar", "bunu çok sevecek👀"]}, ...]
}
İsteğe bağlı: "font_px", "kenar_px" (varsayılan 1.6 px @576 genişlik, orantılı), "hizala_orijinal".

captiontr'ye göre farklar:
  * Bellek: kareler belleğe toplanmaz (2 geçişli akış) — 1080p/60 sn video 8 GB makinede çalışır.
  * Yazısız aralıklar: orijinalde yazı olmayan karelere yeni yazı BASILMAZ.
  * Hız: inpaint yalnız yazı bandında yapılır.
  * Kenar kalınlığı çözünürlüğe göre ölçeklenir.
"""
import os, subprocess, sys, urllib.request

import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import ortak

GENISLIK_PAY = 0.92   # yeni yazının en geniş satırı ekran genişliğinin en çok bu kadarı
SS = 4            # süper örnekleme: yazı 4x çizilip küçültülür
ESLE = 0.55       # kare bu yazıya ait sayılır (beyaz maske örtüşmesi)
BOS = 0.20        # bunun altı: karede yazı yok
TITREME_SN = 0.3  # bundan kısa "yazı yok" aralıkları geçiş titremesidir, doldurulur
GECIS_SN = 0.35   # yazının belirme/kaybolma geçişi: eşleşmeyen soluk kareler de silinir
ORNEK_UST = 40    # her yazı için maske çıkarırken saklanan en fazla kare


def beyaz(b):
    hsv = cv2.cvtColor(b, cv2.COLOR_BGR2HSV)
    return (hsv[..., 2] > 215) & (hsv[..., 1] < 50)


# ---------- emoji ----------
def emoji_kumeleri(s):
    """metni [('metin', ...), ('emoji', ...)] parçalarına böl (ZWJ, FE0F, ten rengi birleşir)"""
    parca, i = [], 0
    def emojimi(c): return ord(c) >= 0x2190 and c not in "’“”–—…" and not (0xFB50 <= ord(c) <= 0xFEFF)
    while i < len(s):
        if emojimi(s[i]):
            j = i + 1
            while j < len(s) and (ord(s[j]) in (0x200D, 0xFE0F) or 0x1F3FB <= ord(s[j]) <= 0x1F3FF or (ord(s[j - 1]) == 0x200D)):
                j += 1
            parca.append(("emoji", s[i:j])); i = j
        else:
            j = i
            while j < len(s) and not emojimi(s[j]): j += 1
            parca.append(("metin", s[i:j])); i = j
    return parca


def emoji_png(e):
    os.makedirs(ortak.EMOJI, exist_ok=True)
    adaylar = ["-".join(f"{ord(c):x}" for c in e), "-".join(f"{ord(c):x}" for c in e if ord(c) != 0xFE0F)]
    for ad in adaylar:
        p = os.path.join(ortak.EMOJI, ad + ".png")
        if os.path.exists(p): return p
    for ad in adaylar:
        p = os.path.join(ortak.EMOJI, ad + ".png")
        try:
            urllib.request.urlretrieve(f"https://cdn.jsdelivr.net/npm/emoji-datasource-apple@16.0.0/img/apple/64/{ad}.png", p)
            return p
        except Exception:
            if os.path.exists(p): os.remove(p)
    raise RuntimeError(f"emoji PNG bulunamadı: {e} {adaylar}")


def ref_kareler(video, indeksler):
    cap = cv2.VideoCapture(video); out = {}
    for i in sorted(set(indeksler)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = cap.read()
        if ok: out[i] = f
    cap.release()
    return out


def etiketle(skorlar, fps):
    """kare → yazı no; -2 = yazı yok (dokunulmaz)."""
    et = []
    for s in skorlar:
        m = max(s)
        et.append(int(np.argmax(s)) if m >= ESLE else (-2 if m < BOS else -1))
    # belirsiz (-1) geçiş kareleri komşu yazıya bağlanır
    for i in range(len(et)):
        if et[i] == -1 and i and et[i - 1] >= 0: et[i] = et[i - 1]
    for i in range(len(et) - 1, -1, -1):
        if et[i] == -1: et[i] = et[i + 1] if i + 1 < len(et) and et[i + 1] >= 0 else -2
    # kısa "yazı yok" boşlukları (titreme) aynı yazı arasında kalıyorsa doldur
    i, kisa = 0, int(TITREME_SN * fps)
    while i < len(et):
        if et[i] == -2:
            j = i
            while j < len(et) and et[j] == -2: j += 1
            if i and j < len(et) and j - i <= kisa and et[i - 1] >= 0: et[i:j] = [et[i - 1]] * (j - i)
            i = j
        else: i += 1
    return et


def satirlari_bul(sabit_beyaz):
    prof = sabit_beyaz.sum(axis=1) > 3
    satir, bas = [], None
    for y, v in enumerate(list(prof) + [False]):
        if v and bas is None: bas = y
        if not v and bas is not None:
            if y - bas >= 8: satir.append((bas, y))
            bas = None
    return satir


def fark_maskesi(medyan, temiz, kisit, esik=28):
    """Sabit sahnede yazılı kare(ler)in medyanı − yazısız komşu kare = yazı + gölge + emoji."""
    f = np.abs(medyan.astype(np.int16) - temiz.astype(np.int16)).max(axis=2) > esik
    if kisit is not None: f &= kisit
    return cv2.morphologyEx(f.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)


def maske_cikar(sabit_beyaz, sabit, satir, W, kisit=None, temiz=None, medyan=None, sabit_gevsek=None):
    """Silinecek alan: beyaz yazı + ona bitişik HAREKETSİZ pikseller (siyah kenar, emoji).
    Arka plan oynadıkça yazı/emoji sabit kalır; beyazdan başlayıp sabit komşulara doğru büyütülür."""
    m = sabit_beyaz.copy()
    for (a, b) in satir:
        bh = b - a; pad = int(0.35 * bh)
        r0, r1 = max(0, a - pad), min(m.shape[0], b + pad)
        xs = np.nonzero(sabit_beyaz[a:b].any(axis=0))[0]
        if not len(xs): continue
        c0, c1 = max(0, xs.min() - bh), min(W, xs.max() + int(3.5 * bh))
        R = sabit[r0:r1, c0:c1]
        if R.mean() > 0.5:
            # arka plan da sabit (tripod çekim): büyütme sızar → eski yöntem, satır sonundaki sabit kolonlar
            x_son = xs.max()
            bolge = sabit[r0:r1, x_son:min(W, x_son + int(bh * 3.2))]
            kolon = np.nonzero(bolge.mean(axis=0) > 0.2)[0]
            if len(kolon):
                uc = kolon[0]
                for c in kolon:
                    if c - uc > max(6, int(bh * 1.2)): break
                    uc = c
                m[r0:r1, x_son:x_son + uc + 4] = True
            continue
        g = sabit_beyaz[r0:r1, c0:c1].copy()
        cek = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(0.6 * bh)), max(3, int(0.3 * bh))))
        for _ in range(8):
            yeni = g | (R & cv2.dilate(g.astype(np.uint8), cek).astype(bool))
            if (yeni == g).all(): break
            g = yeni
        m[r0:r1, c0:c1] |= g
    if kisit is None:   # OCR yoksa satırların çevresi
        kisit = np.zeros_like(sabit_beyaz)
        for (a, b) in satir:
            bh = b - a; xs = np.nonzero(sabit_beyaz[a:b].any(axis=0))[0]
            if not len(xs): continue
            kisit[max(0, a - bh // 2):b + bh // 2, max(0, xs.min() - 2 * bh):xs.max() + int(3.5 * bh)] = True
    if sabit[kisit].mean() < 0.5:
        # arka plan oynuyor: OCR çevresindeki tüm hareketsiz pikseller yazı/emoji (satır başı, ayrı satır emojiler dahil)
        m |= sabit & kisit
    elif temiz is not None and medyan is not None:
        # arka plan sabit: yazısız komşu kareyle fark (gölge ve emoji dahil eksiksiz)
        m |= fark_maskesi(medyan, temiz, kisit)
    if medyan is not None and sabit_gevsek is not None:
        # satır uçlarındaki doygun renkli, (gevşek eşikle) hareketsiz pikseller = emoji (sıkıştırma gürültüsüne dayanıklı)
        hsv = cv2.cvtColor(medyan.astype(np.uint8), cv2.COLOR_BGR2HSV)
        renkli = (hsv[..., 1] > 90) & (hsv[..., 2] > 90) & kisit & sabit_gevsek
        for (a, b) in satir:
            bh = b - a; xs = np.nonzero(sabit_beyaz[a:b].any(axis=0))[0]
            if not len(xs): continue
            r0, r1 = max(0, a - bh // 3), b + bh // 3
            # pencere satır içinden başlar: emojinin beyaz kısımları (göz, ağız) "yazı" ucunu emojinin içine kaydırır
            for c0, c1 in ((max(0, xs.min() - 2 * bh), xs.min() + bh), (max(0, xs.max() - bh), min(W, xs.max() + int(2.5 * bh)))):
                parca = renkli[r0:r1, c0:c1]
                if parca.mean() > 0.04:
                    ys2, xs2 = np.nonzero(parca)
                    m[r0 + ys2.min():r0 + ys2.max() + 1, c0 + xs2.min():c0 + xs2.max() + 1] = True
    bh = int(np.median([b - a for a, b in satir]))
    if kisit is not None and sabit[kisit].mean() >= 0.5:   # sabit sahne: yumuşak gölge için daha geniş pay
        m = cv2.dilate(m.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, bh // 5) | 1,) * 2)).astype(bool)
    m = cv2.morphologyEx(m.astype(np.uint8) * 255, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, bh // 4) | 1,) * 2))
    k = max(9, int(9 * W / 576)) | 1   # kenar + kenar yumuşatması da kalsın diye çözünürlükle ölçekli
    return cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))


def kenar_tahmin(sabit_beyaz, sabit, medyan, satir):
    """Orijinal siyah kenar kalınlığı ≈ beyazın etrafındaki sabit koyu alan / çevre uzunluğu."""
    a, b = satir[0][0], satir[-1][1]
    sb = sabit_beyaz[a:b].astype(np.uint8)
    koyu = sabit[a:b] & (cv2.cvtColor(medyan[a:b].astype(np.uint8), cv2.COLOR_BGR2HSV)[..., 2] < 90)
    halka = cv2.dilate(sb, np.ones((3, 3), np.uint8), iterations=max(2, (b - a) // 8)).astype(bool) & ~sb.astype(bool)
    cevre = (cv2.dilate(sb, np.ones((3, 3), np.uint8)).astype(bool) & ~sb.astype(bool)).sum()
    if not cevre: return 1.6
    k = float((koyu & halka).sum() / cevre)
    return 0.0 if k < 0.6 else float(min(k, 8.0))   # < 0.6 px: kenarsız (gölgesiz ince yazı)


def font_kalibre(alt, sabit_beyaz, satir):
    """Font boyunu orijinal satırın ölçülen genişliğine göre bul (OCR metni + kutusu varsa)."""
    org, kut = alt.get("orijinal") or [], alt.get("kutular") or []
    if len(org) != len(satir) or len(kut) != len(satir): return None
    font = ImageFont.truetype(ortak.FONT, 100)
    try: font.set_variation_by_axes([36, 100, 600, 0])
    except Exception: pass
    oran = []
    for metin, (a, b), (x0, _, x1, _) in zip(org, satir, kut):
        metin = "".join(c for c in metin if ord(c) < 0x2190).strip()
        if len(metin) < 6: continue
        pay = int(0.3 * (b - a))
        xs = np.nonzero(sabit_beyaz[a:b, max(0, x0 - pay):x1 + pay].any(axis=0))[0]
        if len(xs) < 10: continue
        oran.append(100 * (xs.max() - xs.min()) / font.getlength(metin))
    return round(float(np.median(oran))) if oran else None


AGIRLIKLAR = (300, 400, 500, 600, 700, 800)
_gövde_tablo = {}


def font_ac(px, agirlik=600, yol=None, egik=0):
    font = ImageFont.truetype(yol or ortak.FONT, px)
    if not yol:
        try: font.set_variation_by_axes([36, 100, agirlik, max(-6, min(0, egik))])   # opsz, wdth, wght, slnt (-6…0)
        except Exception: pass
    return font


def govde(maske):
    """Harf gövde kalınlığı (px): uzaklık dönüşümünün üst çeyreği × 2."""
    dt = cv2.distanceTransform(maske.astype(np.uint8), cv2.DIST_L2, 3)
    v = dt[dt > 0]
    return 2 * float(np.percentile(v, 75)) if len(v) else 0.0


def agirlik_tahmin(harf, font_px):
    """Orijinal harf kalınlığı / font boyu oranını TikTok Sans ağırlıklarıyla eşleştirir. harf: harf pikselleri (bool)."""
    if not font_px or not harf.any(): return 600
    olcu = govde(harf) / font_px
    if not _gövde_tablo:
        for w in AGIRLIKLAR:
            f = font_ac(100, w); img = Image.new("L", (1400, 160)); ImageDraw.Draw(img).text((10, 10), "Hamburgefonstiv", font=f, fill=255)
            _gövde_tablo[w] = govde(np.asarray(img) > 127) / 100
    return min(AGIRLIKLAR, key=lambda w: abs(_gövde_tablo[w] - olcu))


def kutu_olc(dolu, sabit_beyaz, medyan, alt, Y0):
    """Kutulu stil ölçüleri (bant koordinatında): satır merkezleri, kutu yüksekliği, iç boşluk, renkler."""
    kut = alt.get("kutular") or []
    if not kut: raise RuntimeError("kutulu stil için OCR satır kutuları gerekli (analiz)")
    merkez = [((x0 + x1) / 2, (y0 + y1) / 2 - Y0) for x0, y0, x1, y1 in kut]
    aralik = float(np.median(np.diff([m[1] for m in merkez]))) if len(merkez) > 1 else None
    yuks, pads = [], []
    for (x0, y0, x1, y1), (cx, cy) in zip(kut, merkez):
        col = dolu[:, int(cx)]; r = int(cy)
        if not col[min(r, len(col) - 1)]: continue
        u = r
        while u > 0 and col[u - 1]: u -= 1
        d = r
        while d < len(col) - 1 and col[d + 1]: d += 1
        satir_y = d - u + 1
        if aralik and satir_y > 1.5 * aralik: satir_y = aralik      # kaynaşmış çok satırlı kutu
        yuks.append(satir_y)
        row = dolu[r]; l, rr = int(cx), int(cx)
        while l > 0 and row[l - 1]: l -= 1
        while rr < len(row) - 1 and row[rr + 1]: rr += 1
        pads.append(max(0.0, ((rr - l) - (x1 - x0)) / 2))
    kutu_y = float(np.median(yuks)) if yuks else (y1 - y0) * 1.6
    kutu_renk = np.median(medyan[sabit_beyaz], axis=0) if sabit_beyaz.any() else np.array([255, 255, 255])
    x0, y0, x1, y1 = kut[0]
    ic = medyan[max(0, y0 - Y0):y1 - Y0, x0:x1].reshape(-1, 3)
    koyu = ic[ic.max(axis=1) < 110]
    yazi_renk = np.median(koyu, axis=0) if len(koyu) > 20 else np.array([0, 0, 0])
    return {"merkez": merkez, "aralik": aralik or kutu_y, "kutu_y": kutu_y,
            "pad_x": max(0.3 * kutu_y, float(np.median(pads)) if pads else 0.35 * kutu_y),
            "kutu_renk": tuple(int(c) for c in kutu_renk[::-1]), "yazi_renk": tuple(int(c) for c in yazi_renk[::-1])}


def ocr_kisiti(kutular, Y0, sekil, tur):
    """Maskeyi yazının OCR satır kutularının çevresiyle sınırla (iki yanda emoji payı, kutulu stilde kutu payı).
    kutular: OCR satırları + (varsa) ek_kutular — OCR'ın kaçırdığı satırlar, yalnız-emoji satırları."""
    if not kutular: return None
    m = np.zeros(sekil, bool)
    for x0, y0, x1, y1 in kutular:
        h = y1 - y0
        sol, sag, dy = (1.6 * h, 3.5 * h, 0.9 * h) if tur == "kutulu" else (1.6 * h, 3.5 * h, 0.45 * h)
        m[max(0, int(y0 - Y0 - dy)):max(0, int(y1 - Y0 + dy)), max(0, int(x0 - sol)):int(x1 + sag)] = True
    return m


def siki_kisit(kutular, Y0, sekil):
    """Yalnız OCR satır kutuları (küçük payla): beyaz yazı tohumu ve kare eşleştirme için."""
    if not kutular: return None
    m = np.zeros(sekil, bool)
    for x0, y0, x1, y1 in kutular:
        h = y1 - y0
        m[max(0, int(y0 - Y0 - 0.15 * h)):max(0, int(y1 - Y0 + 0.15 * h)), max(0, int(x0 - 0.25 * h)):int(x1 + 0.25 * h)] = True
    return m


def ocr_satirlari(kutular, Y0):
    return [(max(0, y0 - Y0), max(1, y1 - Y0)) for _, y0, _, y1 in sorted(kutular, key=lambda k: k[1])]


def kutu_dolu(sabit_beyaz):
    """Beyaz kutu + içindeki koyu harfler (delikler) tek parça (bool)."""
    m = sabit_beyaz.astype(np.uint8) * 255
    dolgu = cv2.copyMakeBorder(m, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    tasma = np.zeros((dolgu.shape[0] + 2, dolgu.shape[1] + 2), np.uint8)
    cv2.floodFill(dolgu, tasma, (0, 0), 128)
    d = ((m > 0) | (dolgu[1:-1, 1:-1] == 0)).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(d)
    buyuk = [st[i] for i in range(1, n) if st[i][4] >= 0.002 * d.size]
    if not buyuk: return d.astype(bool)
    h_kutu = int(np.median([b[3] for b in buyuk]))
    # kutuya değen emoji kutuyu böler: yatayda emoji kadar boşluğu kapatıp parçaları birleştir
    d = cv2.morphologyEx(d, cv2.MORPH_CLOSE, np.ones((1, max(3, int(1.3 * h_kutu))), np.uint8))
    n, _, st, _ = cv2.connectedComponentsWithStats(d)
    for i in range(1, n):   # kutu = yuvarlak dikdörtgen → dış dikdörtgeni doldur
        x, y, w, h, a = st[i]
        if a >= 0.002 * d.size: d[y:y + h, x:x + w] = 1
    return d.astype(bool)


def kutu_maske(dolu, W):
    k = max(7, int(7 * W / 576)) | 1
    return cv2.dilate(dolu.astype(np.uint8) * 255, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))


def font_px_genislikten(metinler, genislikler, agirlik=600, yol=None):
    f = font_ac(100, agirlik, yol); oran = []
    for t, g in zip(metinler, genislikler):
        t = "".join(c for c in t if ord(c) < 0x2190).strip()
        if len(t) >= 4 and g > 10: oran.append(100 * g / f.getlength(t))
    return round(float(np.median(oran))) if oran else None


def _parcalar_ciz(d, img, parca, x, y_orta, font, eh, renk, kenar):
    """Metin + emoji parçalarını dikey ortası y_orta olacak şekilde çizer."""
    for tur, t in parca:
        if tur == "metin":
            d.text((x, y_orta), t, font=font, fill=renk, anchor="lm",
                   stroke_width=int(round(kenar * SS)) if kenar else 0, stroke_fill=(0, 0, 0, 255))
            x += d.textlength(t, font=font)
        else:
            e = Image.open(emoji_png(t)).convert("RGBA").resize((eh, eh), Image.LANCZOS)
            img.alpha_composite(e, (int(x + SS), int(y_orta - eh / 2)))
            x += eh + SS


def _genislik(d, parca, font, eh):
    return sum(d.textlength(t, font=font) if tur == "metin" else eh + SS for tur, t in parca)


def katman_ciz(satirlar, stil, W, H):
    """Yeni yazıyı çizer; (x0, y0, BGR, alfa) kırpıntısı döner.
    stil: tur (kenarli|kutulu), font_px, agirlik, font (yol), orta_x, ve
      kenarli → ust (ilk satır harf üstü), aralik, kenar
      kutulu  → ilk_merkez_y, aralik, kutu_y, pad_x, kutu_renk, yazi_renk, yaricap
      kapak   → [x0, y0, x1, y1]: silinen alanın tamamını örten tek koyu kutu (kapak_renk, kapak_alfa)"""
    fp = stil["font_px"]
    font = font_ac(fp * SS, stil.get("agirlik", 600), stil.get("font"), stil.get("egik", 0))
    eh = int(fp * SS * 1.05)
    # Türkçe satır orijinalden uzunsa kenara taşmasın: en geniş satır (kutu/kenar payıyla) GENISLIK_PAY × W'yi aşarsa font küçülür
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    en = max(_genislik(d0, emoji_kumeleri(s), font, eh) for s in satirlar) / SS \
        + 2 * (stil.get("pad_x", 0) if stil["tur"] == "kutulu" else stil.get("kenar", 0))
    if en > GENISLIK_PAY * W:
        fp = fp * GENISLIK_PAY * W / en
        font = font_ac(fp * SS, stil.get("agirlik", 600), stil.get("font"), stil.get("egik", 0)); eh = int(fp * SS * 1.05)
    aralik = stil["aralik"]
    if stil["tur"] == "kutulu":
        ilk = stil["ilk_merkez_y"]; y_bas = max(0, int(ilk - stil["kutu_y"]))
    elif "ilk_merkez_y" in stil:
        ilk = stil["ilk_merkez_y"]; y_bas = max(0, int(ilk - 1.5 * fp))
    else:
        ilk = stil["ust"] + fp * 0.36; y_bas = max(0, int(stil["ust"] - fp))   # harf üstünden göz-ortasına
    y_son = min(H, int(ilk + aralik * len(satirlar) + stil.get("kutu_y", fp) + fp))
    kapak = stil.get("kapak")
    if kapak:
        pad = 0.4 * fp
        y_bas = max(0, min(y_bas, int(kapak[1] - pad) - 2)); y_son = min(H, max(y_son, int(kapak[3] + pad) + 2))
    img = Image.new("RGBA", (W * SS, (y_son - y_bas) * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    if kapak:   # silinen alan + yeni satırlar tek kutuda: silme izi hiç görünmez
        x0, y0, x1, y1 = kapak[0], kapak[1] - y_bas, kapak[2], kapak[3] - y_bas
        for si, s in enumerate(satirlar):
            gen = _genislik(d, emoji_kumeleri(s), font, eh) / SS
            yo = ilk - y_bas + si * aralik
            x0, x1 = min(x0, stil["orta_x"] - gen / 2), max(x1, stil["orta_x"] + gen / 2)
            y0, y1 = min(y0, yo - 0.6 * fp), max(y1, yo + 0.6 * fp)
        x0, x1 = max(0, x0 - pad), min(W, x1 + pad); y0, y1 = max(0, y0 - pad), y1 + pad
        d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=0.45 * fp * SS,
                            fill=tuple(stil.get("kapak_renk", (0, 0, 0))) + (int(255 * stil.get("kapak_alfa", 0.88)),))
    for si, s in enumerate(satirlar):
        parca = emoji_kumeleri(s)
        gen = _genislik(d, parca, font, eh)
        x = stil["orta_x"] * SS - gen / 2
        y_orta = (ilk - y_bas + si * aralik) * SS
        if stil["tur"] == "kutulu":
            ky, px = stil["kutu_y"] * SS, stil["pad_x"] * SS
            d.rounded_rectangle([x - px, y_orta - ky / 2, x + gen + px, y_orta + ky / 2 + (SS if si < len(satirlar) - 1 else 0)],
                                radius=stil.get("yaricap", 0.28) * ky, fill=tuple(stil["kutu_renk"]) + (int(255 * stil.get("kutu_alfa", 1)),))
    for si, s in enumerate(satirlar):   # kutular önce, yazılar üstte (kaynaşan kutular yazıyı örtmesin)
        parca = emoji_kumeleri(s)
        gen = _genislik(d, parca, font, eh)
        x = stil["orta_x"] * SS - gen / 2
        y_orta = (ilk - y_bas + si * aralik) * SS
        renk = tuple(stil.get("yazi_renk", (255, 255, 255))) + (255,)
        _parcalar_ciz(d, img, parca, x, y_orta, font, eh, renk, stil.get("kenar", 0) if stil["tur"] == "kenarli" and not kapak else 0)
    k = np.asarray(img.resize((W, y_son - y_bas), Image.LANCZOS)).astype(np.float32)
    ys, xs = np.nonzero(k[..., 3] > 0)
    if not len(ys): raise RuntimeError("yeni yazı boş çizildi")
    a0, a1, b0, b1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    k = k[a0:a1, b0:b1]
    return (int(b0), int(y_bas + a0), k[..., 2::-1].copy(), k[..., 3:4] / 255.0)


def satir_kutulari_1e1(kutular, emoji):
    """Okunan dikdörtgenler → orijinal satır başına bir kutu. Dikeyde çakışan dikdörtgenler (emojinin ayrı okunan
    parçası, ör. "QQ") aynı satırdır, birleşir. emoji[j]: satırın SAĞINDAKİ emoji sayısı ya da [sol, sağ]
    (tırnak işareti ≈ 0.5); kutu metin dikdörtgeninden o kadar genişler."""
    satirlar = []
    for q in sorted(kutular, key=lambda q: q[1]):
        for g in satirlar:
            ust = max(g["y0"], q[1]); alt_ = min(g["y1"], q[3])
            if alt_ - ust > 0.5 * min(g["y1"] - g["y0"], q[3] - q[1]): g["parca"].append(q); break
        else: satirlar.append({"y0": q[1], "y1": q[3], "parca": [q]})
    kk = []
    for j, g in enumerate(satirlar):
        metin = max(g["parca"], key=lambda q: q[2] - q[0])   # en geniş parça = metin
        x0, x1 = min(q[0] for q in g["parca"]), max(q[2] for q in g["parca"])
        y0, y1 = min(q[1] for q in g["parca"]), max(q[3] for q in g["parca"])
        h = metin[3] - metin[1]; e = emoji[j] if j < len(emoji) else 0
        sol, sag = (e if isinstance(e, (list, tuple)) else (0, e))
        if sol: x0 = min(x0, metin[0] - sol * 1.05 * h - 0.1 * h)
        if sag: x1 = max(x1, metin[2] + sag * 1.05 * h + 0.1 * h)
        p2 = max(3, round(0.06 * h))
        kk.append((int(x0) - p2, y0 - p2, int(x1) + p2, y1 + p2))
    return kk


def katman_1e1(satirlar, stil, W, H):
    """Siyah kutular orijinal satırların tam yerinde ve boyunda; yeni yazı her kutuda ortalı, orijinal font boyunda
    (en uzun satır kutusuna sığmazsa tüm satırlar birlikte küçülür). Orijinalden fazla satır son kutunun altına eklenir."""
    kut = [list(q) for q in stil["kutular_1e1"]]
    while len(kut) < len(satirlar):   # fazla satır: son kutunun aralığıyla alta
        x0, y0, x1, y1 = kut[-1]; ad = (y1 - kut[-2][3]) if len(kut) > 1 else (y1 - y0) + 4
        kut.append([x0, y0 + ad, x1, y1 + ad])
    kut = kut[:len(satirlar)] if len(satirlar) < len(kut) else kut
    if len(satirlar) < len(stil["kutular_1e1"]):   # az satır: son kutu kalan orijinal satırları da örter
        kut[-1] = [min(q[0] for q in stil["kutular_1e1"][len(satirlar) - 1:]), kut[-1][1],
                   max(q[2] for q in stil["kutular_1e1"][len(satirlar) - 1:]), stil["kutular_1e1"][-1][3]]
    fp = stil["font_px"]; ag = stil.get("agirlik", 600)
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for _ in range(30):   # en dar orana göre ortak font
        font = font_ac(fp * SS, ag, stil.get("font"), stil.get("egik", 0)); eh = int(fp * SS * 1.05)
        tasma = max(_genislik(d0, emoji_kumeleri(s), font, eh) / SS / max(1, (q[2] - q[0]) - 0.5 * fp) for s, q in zip(satirlar, kut))
        if tasma <= 1 or fp <= 10: break
        fp = max(10, int(fp / tasma))
    y_bas = max(0, min(q[1] for q in kut) - 2); y_son = min(H, max(q[3] for q in kut) + 2)
    img = Image.new("RGBA", (W * SS, (y_son - y_bas) * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    for i, (x0, y0, x1, y1) in enumerate(kut):   # kutular (bitişik satırlar arasında boşluk kalmasın)
        y1b = kut[i + 1][1] if i + 1 < len(kut) and kut[i + 1][1] - y1 < 0.25 * fp else y1
        d.rounded_rectangle([max(0, x0) * SS, (y0 - y_bas) * SS, min(W, x1) * SS, (y1b - y_bas) * SS],
                            radius=0.22 * (y1 - y0) * SS, fill=tuple(stil.get("kutu_renk", (0, 0, 0))) + (int(255 * stil.get("kutu_alfa", 1)),))
    renk = tuple(stil.get("yazi_renk", (255, 255, 255))) + (255,)
    for s, (x0, y0, x1, y1) in zip(satirlar, kut):
        parca = emoji_kumeleri(s); gen = _genislik(d, parca, font, eh)
        _parcalar_ciz(d, img, parca, (x0 + x1) / 2 * SS - gen / 2, ((y0 + y1) / 2 - y_bas) * SS, font, eh, renk, 0)
    k = np.asarray(img.resize((W, y_son - y_bas), Image.LANCZOS)).astype(np.float32)
    return (0, int(y_bas), k[..., 2::-1].copy(), k[..., 3:4] / 255.0)


def son_yazi_katmani(cfg, W, H):
    """Videonun sonuna çağrı yazısı (CTA): siyah kutu, beyaz yazı, ortalı. Çok uzunsa kelimeden 2+ satıra böler."""
    fp = int(cfg.get("font_oran", 0.058) * W)   # 0.042 siyah tulum üstünde okunmuyordu (2026-11-04 ölçüldü)
    font = font_ac(fp, cfg.get("agirlik", 700))
    sinir = 0.84 * W - 2 * 0.45 * fp
    satirlar, simdi = [], ""
    olcer = ImageDraw.Draw(Image.new("L", (1, 1)))
    for kelime in cfg["metin"].split():
        aday = (simdi + " " + kelime).strip()
        if simdi and _genislik(olcer, emoji_kumeleri(aday), font, int(fp * 1.05)) > sinir: satirlar.append(simdi); simdi = kelime
        else: simdi = aday
    satirlar.append(simdi)
    kutu_y = fp * 1.55
    stil = {"tur": "kutulu", "font_px": fp, "agirlik": cfg.get("agirlik", 700), "orta_x": W / 2, "aralik": kutu_y,
            "kutu_y": kutu_y, "pad_x": 0.45 * fp, "yaricap": 0.3,
            "ilk_merkez_y": cfg.get("y_oran", 0.70) * H - (len(satirlar) - 1) * kutu_y / 2,
            "kutu_renk": tuple(cfg.get("kutu_renk", (0, 0, 0))), "yazi_renk": tuple(cfg.get("yazi_renk", (255, 255, 255)))}
    return katman_ciz(satirlar, stil, W, H)


YORUM_BASLIK = {"tiktok": "{k} adlı kullanıcının yorumuna yanıt", "instagram": "@{k} adlı kullanıcıya yanıt"}


def _sar(d, metin, font, eh, sinir):
    satirlar, simdi = [], ""
    for kelime in metin.split():
        aday = (simdi + " " + kelime).strip()
        if simdi and _genislik(d, emoji_kumeleri(aday), font, eh) > sinir: satirlar.append(simdi); simdi = kelime
        else: simdi = aday
    return satirlar + ([simdi] if simdi else [])


def yorum_katmani(y, W, H):
    """TikTok/Instagram yoruma-yanıt balonu: eski balonu TAMAMEN örten opak beyaz balon + Türkçe başlık/yorum.
    y: kutu [x0,y0,x1,y1] (eski balon), platform, kullanici, metin, (baslik), govde_px."""
    x0, y0, x1, y1 = y["kutu"]
    fp = max(10, int(y.get("font_px") or round(y.get("govde_px", 0.036 * W) * 0.9)))   # OCR satır kutusu ≈ 1,1 × font
    ig = y.get("platform") == "instagram"
    fb = font_ac(int(fp * 0.82) * SS, 450); fy = font_ac(fp * SS, y.get("agirlik", 550))
    eh, ehb = int(fp * SS * 1.05), int(fp * 0.82 * SS * 1.05)
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    baslik = y.get("baslik") or YORUM_BASLIK["instagram" if ig else "tiktok"].format(k=y.get("kullanici") or "kullanıcı")
    pad = 0.55 * fp; av = 0 if ig else 2.1 * fp
    sinir = (0.9 * W - 2 * pad - av - (0.45 * fp if av else 0)) * SS
    govde = _sar(d0, y["metin"], fy, eh, sinir)
    bas_g = _genislik(d0, emoji_kumeleri(baslik), fb, ehb) / SS
    if bas_g * SS > sinir:   # başlık sığmıyorsa kısalır
        while baslik and _genislik(d0, emoji_kumeleri(baslik + "…"), fb, ehb) > sinir: baslik = baslik[:-1]
        baslik += "…"; bas_g = _genislik(d0, emoji_kumeleri(baslik), fb, ehb) / SS
    ic_w = max([bas_g] + [_genislik(d0, emoji_kumeleri(g), fy, eh) / SS for g in govde])
    ic_h = 1.25 * fp * 0.82 + 1.3 * fp * len(govde)
    gw = max(x1 - x0 + 4, ic_w + 2 * pad + av + (0.45 * fp if av else 0))
    gh = max(y1 - y0 + 4, ic_h + 2 * pad)
    bx0 = min(max(0, x0 - 2), W - gw); by0 = max(0, y0 - 2)
    if bx0 < 0: bx0 = 0
    img = Image.new("RGBA", (int(gw * SS) + 2, int(gh * SS) + 2), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, gw * SS, gh * SS], radius=0.5 * fp * SS, fill=tuple(y.get("renk", (255, 255, 255))) + (255,))
    ust = (gh - ic_h) / 2
    tx = pad + (av + 0.45 * fp if av else 0)
    if av:
        cy = ust + ic_h / 2
        d.ellipse([pad * SS, (cy - av / 2) * SS, (pad + av) * SS, (cy + av / 2) * SS], fill=(196, 196, 200, 255))
    _parcalar_ciz(d, img, emoji_kumeleri(baslik), tx * SS, (ust + 0.62 * fp * 0.82) * SS, fb, ehb,
                  (0, 0, 0, 255) if ig else (120, 120, 128, 255), 0)
    for i, g in enumerate(govde):
        _parcalar_ciz(d, img, emoji_kumeleri(g), tx * SS, (ust + 1.25 * fp * 0.82 + (i + 0.5) * 1.3 * fp) * SS, fy, eh,
                      (22, 22, 24, 255), 0)
    k = np.asarray(img.resize((int(gw) + 1, int(gh) + 1), Image.LANCZOS)).astype(np.float32)
    k = k[:H - int(by0), :W - int(bx0)]
    return (int(bx0), int(by0), k[..., 2::-1].copy(), k[..., 3:4] / 255.0)


def bindir(o, katman):
    x0, y0, rgb, al = katman
    hh, ww = rgb.shape[:2]
    bolge = o[y0:y0 + hh, x0:x0 + ww].astype(np.float32)
    o[y0:y0 + hh, x0:x0 + ww] = (bolge * (1 - al) + rgb * al).clip(0, 255).astype(np.uint8)


def ayar_yukle(ayar_yol):
    """ayar.json + (varsa) üst klasörlerdeki proje.json — video ayarı proje ayarını ezer."""
    ayar = ortak.oku_json(ayar_yol)
    d = os.path.dirname(os.path.abspath(ayar_yol))
    for _ in range(3):
        d = os.path.dirname(d); pj = os.path.join(d, "proje.json")
        if os.path.exists(pj):
            proje = ortak.oku_json(pj)
            for k, v in proje.items(): ayar.setdefault(k, v)
            break
    return ayar


def yazilari_hazirla(ayar):
    """Kare → yazı etiketi, her yazının silme maskesi (bant koordinatında) ve yeni yazı katmanı."""
    alt = ayar.get("altyazilar") or []
    video = ayar["kaynak"]
    b = ortak.bilgi(video); FPS, W, H = b["fps"], b["w"], b["h"]
    Y0, Y1 = ayar.get("bant") or (0, 1)
    tur = ayar.get("stil", "kenarli")
    kapat = yazi_yontemi(ayar) == "kapat"

    etiket = [-2] * b["n"]; maske, katman = [None] * len(alt), [None] * len(alt)
    stiller = [None] * len(alt)
    sil, kare_maske = list(etiket), {}
    if alt:
        idx = [min(b["n"] - 1, int(a["ornek_sn"] * FPS)) for a in alt]
        rk = ref_kareler(video, idx)
        siki = [siki_kisit(a.get("kutular"), Y0, (Y1 - Y0, W)) if (a.get("stil") or tur) == "kenarli" else None for a in alt]
        # eşleştirme yalnız yazının kendi beyazıyla (arkadaki beyaz duvar/ürün sahne değişince eşleşmeyi bozmasın)
        refler = [beyaz(rk[i][Y0:Y1]) & sk if sk is not None else beyaz(rk[i][Y0:Y1]) for i, sk in zip(idx, siki)]
        # OCR'ın ölçtüğü zaman aralığı (±0,4 sn) dışında yazı aranmaz: arkadaki beyaz zemin yalancı eşleşme
        # üretmesin, örnek kareler de (maske medyanı) yazısız beyaz sahneden toplanmasın
        aralik = [(int((a["bas"] - 0.4) * FPS), int((a["bit"] + 0.4) * FPS))
                  if a.get("bas") is not None and a.get("bit") is not None else (0, b["n"]) for a in alt]
        # 1. geçiş: skorlar + her yazı için örnek bant kırpıntıları (sınırlı sayıda)
        skorlar, ornek, beyazlar = [], [[] for _ in alt], {}
        gecis = int(GECIS_SN * FPS)
        for i, f in ortak.kareler(video):
            bant = f[Y0:Y1]; w = beyaz(bant)
            if any(i0 - gecis <= i <= i1 + gecis for i0, i1 in aralik): beyazlar[i] = np.packbits(w, axis=1)   # kare kare maske için
            s = [(w & r).sum() / max(1, r.sum()) if i0 <= i <= i1 else 0.0 for r, (i0, i1) in zip(refler, aralik)]
            skorlar.append(s)
            k = int(np.argmax(s))
            if s[k] >= ESLE and i % 3 == 0:
                o = ornek[k]
                if len(o) < ORNEK_UST: o.append(bant.copy())
                else: o[np.random.randint(ORNEK_UST)] = bant.copy()
        etiket = etiketle(skorlar, FPS)
        # elle: "sabit_zaman" → yazı OCR'ın ölçtüğü bas–bit aralığında kesin var (beyaz zemin eşleşmeyi bozuyorsa)
        for k, a in enumerate(alt):
            if a.get("sabit_zaman"):
                for i in range(max(0, int(a["bas"] * FPS)), min(len(etiket), int(a["bit"] * FPS) + 1)): etiket[i] = k
        for k in range(len(alt)):
            ii = [i for i, e in enumerate(etiket) if e == k]
            if not ii: raise RuntimeError(f"{k}. yazı hiçbir karede bulunamadı (ornek_sn / bant yanlış?)")
            print(f"  yazı {k}: {ii[0] / FPS:.2f}-{(ii[-1] + 1) / FPS:.2f} sn")
        bos = sum(1 for e in etiket if e == -2)
        if bos: print(f"  yazısız kare: {bos} (dokunulmadı)")

        def temiz_kare(k):
            ii = [i for i, e in enumerate(etiket) if e == k]
            # belirme/kaybolma geçişinin dışından (soluk yazı hayaleti olmasın)
            aday = [i for i in (ii[0] - gecis - 2, ii[-1] + gecis + 2) if 0 <= i < len(etiket) and etiket[i] != k]
            aday = [i for i in aday if abs(i - (ii[0] if i < ii[0] else ii[-1])) <= FPS]
            if not aday: return None
            return ref_kareler(video, aday[:1])[aday[0]][Y0:Y1]

        kenar_olc = []; kisitlar, kalinlik = [None] * len(alt), [3] * len(alt)
        sira = sorted(range(len(alt)), key=lambda k: -len(alt[k]["satirlar"]))  # aralığı çok satırlılardan öğren
        bilinen_aralik = []
        for k in sira:
            ornk = np.stack(ornek[k]) if len(ornek[k]) >= 2 else np.stack([rk[idx[k]][Y0:Y1]] * 2)
            beyaz_oran = np.mean([beyaz(x) for x in ornk], axis=0)
            sabit_beyaz = beyaz_oran > 0.75
            yazi_tur = alt[k].get("stil") or tur
            kisit = ocr_kisiti((alt[k].get("kutular") or []) + (alt[k].get("ek_kutular") or []), Y0, sabit_beyaz.shape, yazi_tur)
            tohum = siki[k] if siki[k] is not None else kisit
            if tohum is not None: sabit_beyaz &= tohum   # bant içindeki diğer sabit beyaz nesneler (ürün, duvar, yatak) yazı sayılmaz
            medyan = np.median(ornk, axis=0)
            sabit = (np.abs(ornk.astype(np.int16) - medyan).max(axis=3) < 14).mean(axis=0) > 0.6
            # satır geometrisi: OCR varsa OCR kutuları (beyaz profili arka plandan etkilenir)
            satir = ocr_satirlari(alt[k]["kutular"], Y0) if alt[k].get("kutular") else satirlari_bul(sabit_beyaz)
            if not satir: raise RuntimeError(f"{k}. yazıda satır bulunamadı")
            xs = np.nonzero(sabit_beyaz.any(axis=0))[0]
            if alt[k].get("kutular"): xs = np.array([min(q[0] for q in alt[k]["kutular"]), max(q[2] for q in alt[k]["kutular"])])
            if not len(xs): raise RuntimeError(f"{k}. yazıda beyaz yazı pikseli bulunamadı")
            orta_x = (xs.min() + xs.max()) / 2 if ayar.get("hizala_orijinal") or kapat else W / 2
            if yazi_tur == "kutulu":
                dolu = kutu_dolu(sabit_beyaz)
                m = kutu_maske(dolu, W)
                if ayar.get("maske") == "hassas" and kisit is not None:
                    from . import maske as hm
                    m2, yontem = hm.hassas(ornk, dolu, kisit, satir, W, temiz_kare(k), medyan)
                    if m2 is not None: m = m2
                    print(f"  yazı {k}: hassas maske → {yontem or 'eski maske (bilgi yok)'}")
                olc = kutu_olc(dolu, sabit_beyaz, medyan, alt[k], Y0)
                kut = alt[k]["kutular"]
                fp = ayar.get("font_px") or font_px_genislikten(alt[k].get("orijinal", []), [x1 - x0 for x0, _, x1, _ in kut],
                                                                ayar.get("agirlik", 600), ayar.get("font")) or round(olc["kutu_y"] * 0.55)
                agirlik = ayar.get("agirlik") or agirlik_tahmin(dolu & ~sabit_beyaz, fp)   # koyu harfler
                stil = {"tur": "kutulu", "font_px": fp, "agirlik": agirlik, "font": ayar.get("font"), "egik": ayar.get("egik", 0),
                        "orta_x": orta_x, "ilk_merkez_y": Y0 + olc["merkez"][0][1], "aralik": olc["aralik"],
                        "kutu_y": olc["kutu_y"], "pad_x": olc["pad_x"],
                        "kutu_renk": ayar.get("kutu_renk") or olc["kutu_renk"], "yazi_renk": ayar.get("yazi_renk") or olc["yazi_renk"]}
                bilgi = f"kutu {olc['kutu_y']:.0f}px, pad {olc['pad_x']:.0f}px, ağırlık {agirlik}, yazı rengi {stil['yazi_renk']}"
            else:
                sabit_gevsek = (np.abs(ornk.astype(np.int16) - medyan).max(axis=3) < 25).mean(axis=0) > 0.6
                m = maske_cikar(sabit_beyaz, sabit, satir, W, kisit, temiz_kare(k), medyan, sabit_gevsek)
                if ayar.get("maske") == "hassas" and kisit is not None:
                    from . import maske as hm
                    # tohum: OCR + elle eklenen satır kutularındaki sabit beyaz; gec_beyaz: örneklerin yalnız bir
                    # kısmında beyaz olan (harf harf beliren yazının sonradan gelen harfleri) — ölçüme girmez, maskeye girer
                    siki_ek = siki_kisit((alt[k].get("kutular") or []) + (alt[k].get("ek_kutular") or []), Y0, beyaz_oran.shape)
                    m2, yontem = hm.hassas(ornk, (beyaz_oran > 0.75) & siki_ek, kisit, satir, W, temiz_kare(k), medyan,
                                           gec_beyaz=(beyaz_oran > 0.2) & siki_ek)
                    if m2 is not None: m2 = np.maximum(m2, (cv2.dilate(sabit_beyaz.astype(np.uint8), np.ones((3, 3), np.uint8)) * 255))
                    if m2 is not None: m = m2
                    print(f"  yazı {k}: hassas maske → {yontem or 'eski maske (bilgi yok)'}")
                if ayar.get("kenar_px") is None: kenar_olc.append(kenar_tahmin(sabit_beyaz, sabit, medyan, satir))
                merkez = [(a + bb) / 2 for a, bb in satir]
                if alt[k].get("aralik"):   # elle: boş satırla aralıklı bloklar (ör. üstte tek satır, altta 2 satır)
                    aralik = float(alt[k]["aralik"])
                elif len(merkez) > 1:
                    aralik = merkez[1] - merkez[0]; bilinen_aralik.append(aralik)
                else:
                    aralik = float(np.median(bilinen_aralik)) if bilinen_aralik else (satir[0][1] - satir[0][0]) * 1.55
                fp = ayar.get("font_px") or font_kalibre(alt[k], sabit_beyaz, satir) or round(aralik * 0.86)
                h_ocr = float(np.median([b2 - a2 for a2, b2 in satir]))
                if not ayar.get("font_px") and alt[k].get("kutular") and not (0.6 * h_ocr <= fp <= 1.3 * h_ocr):
                    fp = round(0.86 * h_ocr)   # ölçüm saçmaladıysa OCR satır yüksekliğinden
                agirlik = ayar.get("agirlik") or agirlik_tahmin(sabit_beyaz[satir[0][0]:satir[-1][1]], fp)
                kenar = ayar.get("kenar_px") if ayar.get("kenar_px") is not None else float(np.median(kenar_olc))
                stil = {"tur": "kenarli", "font_px": fp, "agirlik": agirlik, "font": ayar.get("font"), "egik": ayar.get("egik", 0), "orta_x": orta_x,
                        "ust": Y0 + satir[0][0], "aralik": aralik, "kenar": kenar, "yazi_renk": (255, 255, 255)}
                if alt[k].get("kutular"): stil["ilk_merkez_y"] = Y0 + (satir[0][0] + satir[0][1]) / 2
                bilgi = f"aralık {aralik:.0f}px, kenar {kenar:.1f}px, ağırlık {agirlik}"
            ys = np.nonzero(m.any(axis=1))[0]
            maske[k] = (m, max(0, ys.min() - 16), min(Y1 - Y0, ys.max() + 17))
            # ek_kutular: yazının kayarak geldiği/eklenen satırın yeri — kare kare maske orayı da silebilsin
            kisitlar[k] = (siki_kisit(alt[k]["kutular"] + alt[k]["ek_kutular"], Y0, (Y1 - Y0, W)) if alt[k].get("ek_kutular") else siki[k]) \
                if siki[k] is not None else kisit
            kalinlik[k] = max(2, round(0.15 * np.median([b2 - a2 for a2, b2 in satir])))
            kp = alt[k].get("kapak", ayar.get("kapak"))
            if kapat:
                pass   # kutu, kare kare maskeler belli olunca aşağıda kurulur
            elif kp == "satir":   # yalnız yazının arkası: satır başına sıkı koyu kutu, font biraz küçük
                fs = max(8, stil["font_px"] - ayar.get("kapak_font_eksi", 2))
                stil.update(tur="kutulu", font_px=fs, kutu_y=fs * 1.32, pad_x=fs * 0.32, yaricap=0.22,
                            ilk_merkez_y=stil.get("ilk_merkez_y", stil.get("ust", 0) + stil["font_px"] * 0.36),
                            aralik=max(stil["aralik"], fs * 1.32), kutu_renk=(0, 0, 0), yazi_renk=(255, 255, 255),
                            kutu_alfa=ayar.get("kapak_alfa", 0.88))
            elif kp:
                xs_m = np.nonzero(m.any(axis=0))[0]
                stil.update(kapak=[int(xs_m.min()), Y0 + int(ys.min()), int(xs_m.max()) + 1, Y0 + int(ys.max()) + 1],
                            kapak_alfa=ayar.get("kapak_alfa", 0.88), yazi_renk=(255, 255, 255))
                if stil["tur"] == "kutulu": stil["kutu_renk"] = (0, 0, 0)
            stiller[k] = stil
            print(f"  yazı {k} [{yazi_tur}]: {len(satir)}→{len(alt[k]['satirlar'])} satır, font {fp}px, {bilgi}")
        sil, kare_maske = gecis_ve_kare_maskeleri(etiket, maske, beyazlar, kisitlar, kalinlik, gecis, W)
        for k in range(len(alt)):
            stil = stiller[k]
            if kapat and ayar.get("kapat_kutu", "satir") == "satir" and alt[k].get("kutular") and stil["tur"] == "kenarli":
                # (orijinali beyaz kutulu yazıda beyaz kutu satır dikdörtgeninden geniş: tek büyük kutu — kapat_stili)
                # satır başına 1-1 kutu: orijinal satırın yeri ve boyu (+ emoji payı), yazı orijinal boyda
                stil = dict(stil, kutular_1e1=satir_kutulari_1e1(alt[k]["kutular"] + (alt[k].get("ek_kutular") or []),
                                                                alt[k].get("emoji") or []),
                            kutu_renk=(0, 0, 0), kutu_alfa=1.0, yazi_renk=(255, 255, 255))
                katman[k] = katman_1e1(alt[k]["satirlar"], stil, W, H)
                continue
            if kapat: stil = kapat_stili(stil, alt[k], k, maske, sil, kare_maske, Y0)
            katman[k] = katman_ciz(alt[k]["satirlar"], stil, W, H)

    return etiket, maske, katman, sil, kare_maske


def yazi_yontemi(ayar):
    """'kapat' (varsayılan, kesin kural): eski yazı silinmez; tamamen opak siyah kutu + beyaz Türkçe yazı, orijinal
    font boyunda ve orijinal yerinde. 'sil': eski yazıyı silip aynı stilde basar (eski yöntem, kapalı)."""
    return "sil" if ayar.get("yontem") == "sil" else "kapat"


def kapat_stili(stil, a, k, maske, sil, kare_maske, Y0):
    """Eski yazının görüldüğü her karedeki tüm piksellerini (+ OCR kutularını) örten tek opak siyah kutu."""
    m, _, _ = maske[k]; tum = m > 0
    for i, mk in kare_maske.items():
        if sil[i] == k: tum = tum | (mk > 0)
    ys, xs = np.nonzero(tum)
    x0, y0, x1, y1 = int(xs.min()), Y0 + int(ys.min()), int(xs.max()) + 1, Y0 + int(ys.max()) + 1
    for q in (a.get("kutular") or []) + (a.get("ek_kutular") or []):
        x0, y0, x1, y1 = min(x0, q[0]), min(y0, q[1]), max(x1, q[2]), max(y1, q[3])
    yeni = dict(stil, kapak=[x0, y0, x1, y1], kapak_alfa=1.0, kapak_renk=(0, 0, 0), yazi_renk=(255, 255, 255))
    if yeni["tur"] == "kutulu":   # orijinal beyaz kutulu yazı: tek siyah kutu içinde, satır kutusu çizilmez
        yeni.update(tur="kenarli", kenar=0)
    return yeni


def gecis_ve_kare_maskeleri(etiket, maske, beyazlar, kisitlar, kalinlik, gecis, W):
    """sil: yeni yazı basılmasa da SİLİNECEK kareler — yazının belirme/kaybolma geçişi (yazıdan önce/sonra en çok
    GECIS_SN; çok soluk yazı eşleşmeye girmez ama görünür). kare_maske: yazının sabit şablondan taştığı kareler
    (büyüyerek/kayarak gelen animasyon) için o kareye özel maske = şablon ∪ o karenin beyazı + kenar payı."""
    sil = list(etiket)
    for k in range(len(maske)):
        ii = [i for i, e in enumerate(etiket) if e == k]
        if not ii: continue
        for adim, bas in ((-1, ii[0] - 1), (1, ii[-1] + 1)):
            i = bas
            while 0 <= i < len(sil) and abs(i - bas) < gecis and sil[i] == -2:
                sil[i] = k; i += adim
    kare_maske = {}
    for i, k in enumerate(sil):
        if k < 0 or i not in beyazlar or maske[k] is None: continue
        w = np.unpackbits(beyazlar[i], axis=1, count=W).astype(bool)
        if kisitlar[k] is not None: w &= kisitlar[k]
        mk = maske[k][0] > 0
        tasan = w & ~mk
        # animasyon: karedeki beyazın belirgin kısmı şablonun dışında (zemindeki birkaç beyaz nokta değil)
        if tasan.sum() > max(50, 0.15 * (w & mk).sum()):
            r = kalinlik[k]
            ek = cv2.dilate(tasan.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2)) > 0
            kare_maske[i] = ((mk | ek) * 255).astype(np.uint8)
    if kare_maske: print(f"  kare kare maske: {len(kare_maske)} kare (animasyonlu yazı)")
    eklenen = sum(1 for a, b in zip(sil, etiket) if a != b)
    if eklenen: print(f"  geçiş kareleri: {eklenen} (yalnız silinir)")
    return sil, kare_maske


def kare_maskesi(sil, maske, kare_maske, i):
    """i. karenin silme maskesi (bant) ve satır aralığı; silinmeyecekse None."""
    k = sil[i] if i < len(sil) else -2
    if k < 0: return None
    if i in kare_maske:
        m = kare_maske[i]; ys = np.nonzero(m.any(axis=1))[0]
        return m, max(0, ys.min() - 16), min(m.shape[0], ys.max() + 17)
    return maske[k]


def _koyu(b):
    return cv2.cvtColor(b, cv2.COLOR_BGR2HSV)[..., 2] < 80


def gorunurluk(video, alt, sil, FPS, etiket=None):
    """silme yok: {kare: yazı no} — eski yazının o karede gerçekten göründüğü kareler.
    İki şablon (örnek andaki satır dikdörtgenlerinden): beyaz harf pikselleri ve harflerin siyah kenarı.
    oran = şablonun karede hâlâ beyaz/koyu olan payı. Yazılı (medyan) ve yazısız (en düşük) seviyeyi en iyi
    ayıran şablon seçilir; eşik aradaki %20'de. İlk ve son eşik-üstü kare arasındaki her kare dahil.
    Hiçbiri ayıramıyorsa (fark < 0.15) güvenli taraf: yazının eşleştiği kareler + geçiş payı (sil)."""
    goster = {}
    ilgili = {i for i, k in enumerate(sil) if k >= 0}
    if not ilgili: return goster
    pay = int(FPS * 0.5); bas, son = max(0, min(ilgili) - pay), max(ilgili) + pay
    sablon = {}
    cekirdek = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    for k, a in enumerate(alt):
        ii = [i for i, kk in enumerate(etiket if etiket is not None else sil) if kk == k]
        ornek_i = int(a["ornek_sn"] * FPS) if "ornek_sn" in a else (ii[len(ii) // 2] if ii else None)
        if ornek_i is None: continue
        ref = ref_kareler(video, [ornek_i])
        if not ref or not a.get("kutular"): continue
        f = next(iter(ref.values())); sablon[k] = []
        for q in a["kutular"]:
            parca = f[q[1]:q[3], q[0]:q[2]]; w = beyaz(parca)
            kenar = _koyu(parca) & (cv2.dilate(w.astype(np.uint8), cekirdek) > 0)
            sablon[k].append((q, w, kenar))
    oran = {}
    for i, f in ortak.kareler(video):
        if i < bas: continue
        if i > son: break
        k = sil[i] if i < len(sil) else -2
        kk = k if k >= 0 else next((sil[j] for j in range(max(0, i - pay), min(len(sil), i + pay)) if sil[j] >= 0), -1)
        if kk not in sablon: continue
        tw = sum(int(w.sum()) for _, w, _ in sablon[kk]) or 1; tk = sum(int(e.sum()) for _, _, e in sablon[kk]) or 1
        vw = vk = 0
        for q, w, e in sablon[kk]:
            parca = f[q[1]:q[3], q[0]:q[2]]; vw += int((beyaz(parca) & w).sum()); vk += int((_koyu(parca) & e).sum())
        oran[i] = (kk, vw / tw, vk / tk)
    for k in sablon:
        r = {i: v for i, v in oran.items() if v[0] == k}
        if not r: continue
        ic = [i for i in r if i < len(sil) and sil[i] == k] or list(r)
        en_iyi = None
        for j, ad in ((1, "beyaz"), (2, "kenar")):
            p = float(np.median([r[i][j] for i in ic])); b = min(v[j] for v in r.values())
            if en_iyi is None or p - b > en_iyi[0]: en_iyi = (p - b, j, ad, b + 0.2 * (p - b))
        fark, j, ad, esik = en_iyi
        if fark < 0.15:
            for i, kk in enumerate(sil):
                if kk == k: goster[i] = k
            print(f"  yazı {k}: görünürlük ölçülemedi, yazının eşleştiği kareler + geçiş payı kullanıldı")
            continue
        ust = [i for i, v in r.items() if v[j] >= esik]
        for i in range(min(ust), max(ust) + 1): goster[i] = k
        print(f"  yazı {k}: görünür kareler {min(ust) / FPS:.2f}–{(max(ust) + 1) / FPS:.2f} sn ({ad} şablonu, fark %{fark * 100:.0f})")
    for k in range(len(alt)):   # ölçülemeyen yazı (satır kutusu yok): yazının eşleştiği kareler + geçiş payı
        if k not in sablon:
            for i, kk in enumerate(sil):
                if kk == k: goster[i] = k
    for k, a in enumerate(alt):   # yazı okumanın eski yazıyı gördüğü aralık her durumda örtülür (baştaki/sondaki kaçak kareler)
        if "bas" not in a or "bit" not in a: continue
        for i in range(int(a["bas"] * FPS), min(len(sil), int(a["bit"] * FPS) + 1)): goster.setdefault(i, k)
    return goster


def cevir(ayar_yol):
    ayar = ayar_yukle(ayar_yol)
    alt = ayar.get("altyazilar") or []
    son = ayar.get("son_yazi") if (ayar.get("son_yazi") or {}).get("metin") else None
    yorumlar = ayar.get("yorumlar") or []
    if not alt and not son and not yorumlar: raise RuntimeError("ne altyazı ne son_yazi ne yorum var")
    for y in yorumlar:
        if not (y.get("metin") or "").strip(): raise RuntimeError("yorum balonunun Türkçe metni (metin) boş")
    for k, a in enumerate(alt):
        if not a.get("satirlar"): raise RuntimeError(f"{k}. yazının çevirisi (satirlar) boş")
    video, cikti = ayar["kaynak"], ayar["cikti"]
    b = ortak.bilgi(video); FPS, W, H = b["fps"], b["w"], b["h"]
    Y0, Y1 = ayar.get("bant") or (0, 1)
    tur = ayar.get("stil", "kenarli")

    if alt: etiket, maske, katman, sil, kare_maske = yazilari_hazirla(ayar)
    else: etiket, maske, katman, sil, kare_maske = [-1] * b["n"], {}, {}, {}, {}
    yk = [(int(y["bas"] * FPS), int(np.ceil(y["bit"] * FPS)), yorum_katmani(y, W, H), y) for y in yorumlar]
    for a0, a1, _, y in yk: print(f"  yorum balonu: {a0 / FPS:.2f}–{a1 / FPS:.2f} sn  «{y['metin']}»")
    yorum_kontrol = {}

    son_bas, son_katman = b["n"] + 1, None
    if son:
        if "y_oran" not in son and ayar.get("bant"):   # CTA altyazı şeridinin üstüne binmesin
            y0b, y1b = ayar["bant"][0] / H, ayar["bant"][1] / H
            son = dict(son, y_oran=0.70 if (y1b < 0.62 or y0b > 0.78) else (0.25 if y0b > 0.45 else 0.82))
        son_katman = son_yazi_katmani(son, W, H)
        son_bas = max(0, b["n"] - int(son.get("sure", 2.5) * FPS))
        print(f"  son yazı: {son_bas / FPS:.2f} sn → son  «{son['metin']}»")

    # 1,5. geçiş: yazının altındaki gerçek arka planı başka karelerden getir (doldurulamayan = TELEA)
    dolgu, oran = {}, {}
    kapat = yazi_yontemi(ayar) == "kapat"
    goster = {}
    if alt and kapat:
        for k in range(len(alt)):   # örtme denetimi: eski yazının okunan satır dikdörtgenlerinden kutu dışında kalan
            x0, y0, _, al = katman[k]; hh, ww = al.shape[:2]
            ort = np.zeros((H, W), bool); ort[y0:y0 + hh, x0:x0 + ww] = al[..., 0] > 0.95
            ocr = np.zeros((H, W), bool)
            for kx0, ky0, kx1, ky1 in (alt[k].get("kutular") or []) + (alt[k].get("ek_kutular") or []):
                ocr[max(0, ky0 + 2):ky1 - 2, max(0, kx0 + 2):kx1 - 2] = True
            acik = int((ocr & ~ort).sum())
            print(f"  yazı {k}: kutu dışında kalan eski yazı alanı: {acik} piksel")
            if acik > 80: print(f"  UYARI yazı {k}: eski yazının bir kısmı kutunun dışında")
        goster = gorunurluk(video, alt, sil, FPS, etiket)
    if alt and not kapat and ayar.get("silme", "zamansal") == "zamansal":
        from . import doldur
        dolgu, oran = doldur.hazirla(video, sil, maske, Y0, Y1, kare_maske)
        for k in sorted(oran): print(f"  yazı {k}: arka plan %{oran[k] * 100:.0f} gerçek görüntüyle dolduruldu")
        ortak.yaz_json(os.path.splitext(cikti)[0] + "_dolgu.json", {str(k): v for k, v in oran.items()})

    # 2. geçiş: sil + bas + yaz
    os.makedirs(os.path.dirname(os.path.abspath(cikti)), exist_ok=True)
    gecici = cikti + ".yaziliyor.mp4"
    p = subprocess.Popen([ortak.ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-r", ortak.fps_kesir(video), "-i", "-", "-i", video, "-map", "0:v", "-map", "1:a?",
                          "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
                          "-c:a", "copy", "-shortest", "-movflags", "+faststart", gecici], stdin=subprocess.PIPE)
    kontrol_i = {}
    for k in range(len(alt)):
        ii = [i for i, e in enumerate(etiket) if e == k]; kontrol_i[ii[len(ii) // 2]] = k
    kontrol, son_kontrol = {}, None
    for i, f in ortak.kareler(video):
        k = etiket[i] if i < len(etiket) else -2
        if kapat:   # silme yok: opak kutu yalnız eski yazının gerçekten göründüğü karelerde (bkz. gorunurluk)
            k = goster.get(i, -2); ms = None
        else: ms = kare_maskesi(sil, maske, kare_maske, i)
        o = f
        yorum_var = [z for z in yk if z[0] <= i < z[1]]
        if ms is not None or i >= son_bas or yorum_var: o = f.copy()
        if ms is not None:
            m, r0, r1 = ms
            if i in dolgu: o[Y0:Y1] = cv2.imdecode(dolgu[i], cv2.IMREAD_COLOR)
            else: o[Y0 + r0:Y0 + r1] = cv2.inpaint(f[Y0 + r0:Y0 + r1], m[r0:r1], 6, cv2.INPAINT_TELEA)
        if k >= 0:
            temiz = o[Y0:Y1].copy() if i in kontrol_i else None
            bindir(o, katman[k])
            if temiz is not None: kontrol[kontrol_i[i]] = np.hstack([f[Y0:Y1], o[Y0:Y1]] if kapat else [f[Y0:Y1], temiz, o[Y0:Y1]])
        for j, (a0, a1, kat, y) in enumerate(yk):
            if a0 <= i < a1:
                bindir(o, kat)
                if j not in yorum_kontrol and i >= (a0 + a1) // 2:
                    x0, y0 = kat[0], kat[1]; hh, ww = kat[2].shape[:2]
                    yorum_kontrol[j] = np.hstack([f[y0:y0 + hh, x0:x0 + ww], o[y0:y0 + hh, x0:x0 + ww]])
        if i >= son_bas:
            bindir(o, son_katman)
            if son_kontrol is None and i >= son_bas + int(FPS / 2): son_kontrol = o.copy()
        p.stdin.write(o.tobytes())
    p.stdin.close()
    if p.wait() != 0: raise RuntimeError("ffmpeg hata verdi")
    ortak.metadata_temizle(gecici, cikti)   # encoder imzası, x264 SEI, zaman damgası vb. kalmaz
    os.remove(gecici)
    kp = os.path.splitext(cikti)[0] + "_kontrol.png"
    olcek = 2 if W < 800 else 1
    parcalar = [cv2.resize(kontrol[k], None, fx=olcek, fy=olcek) for k in sorted(kontrol)]
    parcalar += [cv2.resize(yorum_kontrol[j], None, fx=olcek, fy=olcek) for j in sorted(yorum_kontrol)]   # eski | yeni balon
    if parcalar and son_kontrol is None:
        gen = max(x.shape[1] for x in parcalar)
        parcalar = [cv2.copyMakeBorder(x, 0, 4, 0, gen - x.shape[1], cv2.BORDER_CONSTANT) for x in parcalar]
    if son_kontrol is not None:   # son yazının olduğu tam kare (küçültülmüş)
        sk = cv2.resize(son_kontrol, (W * olcek // 3, H * olcek // 3))
        gen = max([x.shape[1] for x in parcalar] + [sk.shape[1]])
        parcalar.append(sk)
        parcalar = [cv2.copyMakeBorder(x, 0, 0, 0, gen - x.shape[1], cv2.BORDER_CONSTANT) for x in parcalar]
    cv2.imwrite(kp, np.vstack(parcalar))
    return cikti, kp


def cta_var(ayar):
    """Kesin kural: her videonun sonunda ekranda bir çağrı yazısı (CTA) olur."""
    return bool(((ayar.get("son_yazi") or {}).get("metin") or "").strip())


def calistir(hedef, zorla=False):
    """hedef: tek ayar.json ya da proje klasörü (çevirisi dolu ve güncel olmayanları işler)."""
    ortak.utf8()
    if hedef.endswith(".json"):
        isler = [hedef]
    else:
        isler = [os.path.join(k, ortak.AYAR) for k in ortak.is_klasorleri(hedef) if os.path.exists(os.path.join(k, ortak.AYAR))]
    hata = 0
    for a in isler:
        ad = os.path.basename(os.path.dirname(a))
        try:
            ayar = ayar_yukle(a)
            alt = ayar.get("altyazilar") or []
            yor = ayar.get("yorumlar") or []
            if not all(x.get("satirlar") for x in alt) or not all((y.get("metin") or "").strip() for y in yor) \
                    or (not alt and not yor and not (ayar.get("son_yazi") or {}).get("metin")):
                print(f"{ad:40} atlandı (çeviri eksik)"); continue
            if ayar.get("cevrildi") is not True:
                print(f"{ad:40} atlandı (cevrildi: true işaretli değil)"); continue
            if not cta_var(ayar):
                print(f"{ad:40} atlandı (CTA eksik: son_yazi.metin yaz — kesin kural)"); hata += 1; continue
            from . import hook
            t = hook.tekrar_eden(os.path.dirname(os.path.abspath(a)), ayar)
            if t and not ayar.get("hook_tekrar_izin"):
                print(f"{ad:40} atlandı (hook tekrarı %{t[0] * 100:.0f}: «{hook.hook(ayar)}» ≈ {os.path.basename(t[1])} «{t[2]}» — farklı giriş yaz)")
                hata += 1; continue
            c = ayar["cikti"]
            if not zorla and os.path.exists(c) and os.path.getmtime(c) > os.path.getmtime(a):
                print(f"{ad:40} atlandı (güncel)"); continue
            print(f"{ad:40} işleniyor…", flush=True)
            c, kp = cevir(a)
            print(f"{ad:40} TAMAM → {c}")
        except Exception as e:
            hata += 1; print(f"{ad:40} HATA: {e}")
    return 1 if hata else 0
