"""Hook (videonun ilk yazısı) çeşitliliği.

Aynı markanın her videosu farklı bir girişle açılmalı. `hooklar()` asistana markanın kullanılmış Türkçe hook'larını
ve aynı ürünün diğer videolarındaki orijinal yazıları (fikir havuzu) gösterir. `tekrar_eden()` render öncesi kapıdır:
hook'u aynı markadaki başka bir videonunkine çok benzeyen video render edilmez.
"""
import difflib, os, re

from . import ortak

BENZERLIK = 0.75


def _oku(k, ad):
    p = os.path.join(k, ad)
    return ortak.oku_json(p) if os.path.exists(p) else {}


def hook(ayar):
    """İlk altyazının Türkçe satırları — videonun girişi."""
    for a in sorted(ayar.get("altyazilar") or [], key=lambda a: a.get("bas", 0)):
        if a.get("satirlar"): return " ".join(a["satirlar"])
    return ""


def _norm(s):
    s = s.replace("İ", "i").replace("I", "ı").lower()
    return re.sub(r"[^0-9a-zçğıöşü ]+", "", s).strip()


def benzer(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b: return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _sira(k):
    m = _oku(k, ortak.META)
    return (m.get("eklendi") or m.get("indirildi") or "", os.path.basename(k))


def _ayni_marka(klasor):
    """Aynı markada (markasızsa diğer markasızlar) bu videodan ÖNCE gelen ya da teslim edilmiş videolar —
    hook önce gelenin hakkıdır, sonradan gelen değiştirir."""
    proje = os.path.dirname(os.path.abspath(klasor)); m = _oku(klasor, ortak.META); marka = m.get("marka")
    return [k for k in ortak.is_klasorleri(proje)
            if os.path.abspath(k) != os.path.abspath(klasor) and _oku(k, ortak.META).get("marka") == marka
            and not m.get("teslim") and (_oku(k, ortak.META).get("teslim") or _sira(k) < _sira(klasor))]


def tekrar_eden(klasor, ayar=None):
    """(benzerlik, diğer klasör, diğer hook) — en çok benzeyen, eşik üstündeyse; yoksa None."""
    ayar = ayar or _oku(klasor, ortak.AYAR); h = hook(ayar)
    if not h: return None
    en = max(((benzer(h, hook(_oku(k, ortak.AYAR))), k) for k in _ayni_marka(klasor)), default=(0, None))
    if en[0] >= BENZERLIK: return round(en[0], 2), en[1], hook(_oku(en[1], ortak.AYAR))
    return None


def hooklar(proje="is", marka=None):
    """Markanın (yoksa tüm alanın) kullanılmış hook'ları + orijinal yazı havuzu."""
    ortak.utf8()
    kullanilan, havuz = [], []
    for k in ortak.is_klasorleri(proje):
        m, a = _oku(k, ortak.META), _oku(k, ortak.AYAR)
        if marka and m.get("marka") != marka: continue
        ad = m.get("teslim") or os.path.basename(k)
        if hook(a): kullanilan.append((ad, hook(a)))
        for x in a.get("altyazilar") or []:
            if x.get("orijinal"): havuz.append((ad, " / ".join(x["orijinal"])))
        for y in a.get("yorumlar") or []:
            havuz.append((ad, "[yorum] " + " ".join(y.get("orijinal") or [])))
    print(f"KULLANILAN HOOK ({len(kullanilan)}) — bunları tekrar etme:")
    for ad, h in kullanilan: print(f"  {ad}: {h}")
    print(f"FİKİR HAVUZU ({len(havuz)}) — aynı ürünün diğer videolarındaki orijinal yazılar:")
    for ad, h in havuz: print(f"  {ad}: {h}")
    return kullanilan, havuz
