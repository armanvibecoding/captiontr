"""Marka sistemi: videoları içeri al → ürünü tanı / markaya bağla → masaüstüne numaralı ve planlı teslim.

Çalışma alanı varsayılan `is/`. Her video kendi klasöründe (`is/<ad>-<kod>/kaynak.mp4`).
Marka kaydı: `is/markalar.json` → {"Marka": {"urun": "kısa tanım", "onizleme": "...jpg"}}.
Videonun markası: `meta.json → marka`. Teslim edildiyse: `meta.json → teslim` (aynı video iki kez teslim edilmez).

Teslim: `<hedef>/<Marka>/1.mp4, 2.mp4, …` — numara markanın klasöründe kaldığı yerden devam eder;
aynı klasörde `plan.csv` (sıra, dosya, tarih, saat, açıklama). Tarih: markanın son planlı gününden sonraki gün,
markanın günde `gunluk` videosu.
"""
import csv, datetime as dt, hashlib, os, re, shutil, subprocess, time

import cv2, numpy as np

from . import indir, ortak

ONIZLEME = "onizleme.jpg"
KAYIT = "markalar.json"
VARSAYILAN_HEDEF = os.path.expanduser("~/Desktop/CaptionTR")
PLAN = "plan.csv"
PLAN_ALANLAR = ["sira", "dosya", "tarih", "saat", "aciklama", "hashtag", "kaynak"]
VIDEO_UZANTI = (".mp4", ".mov", ".m4v")


def _ozet(dosya, n=8):
    h = hashlib.sha1()
    with open(dosya, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""): h.update(parca)
    return h.hexdigest()[:n]


def onizleme(klasor, anlar=(0.15, 0.5, 0.85), gen=360):
    """Videodan 3 kare yan yana → onizleme.jpg (asistan ürünü buradan tanır)."""
    v = os.path.join(klasor, ortak.KAYNAK); b = ortak.bilgi(v)
    hedef = {min(b["n"] - 1, int(b["n"] * a)) for a in anlar}; kareler = []
    for i, f in ortak.kareler(v):
        if i in hedef: kareler.append(cv2.resize(f, (gen, int(f.shape[0] * gen / f.shape[1]))))
    if not kareler: raise RuntimeError(f"kare okunamadı: {v}")
    yuk = max(x.shape[0] for x in kareler)
    kareler = [cv2.copyMakeBorder(x, 0, yuk - x.shape[0], 0, 6, cv2.BORDER_CONSTANT) for x in kareler]
    yol = os.path.join(klasor, ONIZLEME)
    cv2.imwrite(yol, np.hstack(kareler), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return yol


def _dosya_ekle(dosya, proje):
    kod = _ozet(dosya)
    for k in ortak.is_klasorleri(proje) if os.path.isdir(proje) else []:
        if k.endswith("-" + kod): return "atlandi", k
    ad = indir.guvenli(os.path.splitext(os.path.basename(dosya))[0])
    klasor = os.path.join(proje, f"{ad}-{kod}")
    os.makedirs(klasor, exist_ok=True)
    son = os.path.join(klasor, ortak.KAYNAK)
    try:
        ortak.metadata_temizle(dosya, son)   # kopya + temizlik (yeniden kodlamadan)
    except RuntimeError as e:
        if "döndürme" not in str(e): raise
        # telefon videosu: döndürme bilgisi görüntüye uygulanır (yeniden kodlama, ses aynen), sonra temizlenir
        ara = son + ".dondur.mp4"
        r = subprocess.run([ortak.ffmpeg(), "-v", "error", "-y", "-i", dosya, "-map", "0:v:0", "-map", "0:a:0?",
                            "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy", ara],
                           capture_output=True, text=True)
        if r.returncode != 0: raise RuntimeError(f"video döndürülemedi: {r.stderr.strip()[:200]}")
        ortak.metadata_temizle(ara, son); os.remove(ara)
    b = ortak.bilgi(son)
    ortak.yaz_json(os.path.join(klasor, ortak.META), {
        "urun": ad, "url": "", "kaynak_dosya": os.path.abspath(dosya), "kod": kod, "genislik": b["w"],
        "yukseklik": b["h"], "fps": round(b["fps"], 3), "sure_sn": round(b["n"] / max(b["fps"], 1), 2),
        "eklendi": time.strftime("%Y-%m-%d %H:%M:%S")})
    return "eklendi", klasor


def _girdiler(yollar):
    for y in yollar:
        if re.match(r"https?://", y): yield "url", y
        elif os.path.isdir(y):
            for d in sorted(os.listdir(y)):
                if d.lower().endswith(VIDEO_UZANTI) and not d.startswith("."): yield "dosya", os.path.join(y, d)
        elif os.path.isfile(y): yield "dosya", y
        else: yield "yok", y


def ekle(yollar, proje="is", cerez=None):
    """Video dosyası, klasör ya da link → çalışma alanına alır, önizleme üretir. Yeni klasörleri döndürür."""
    ortak.utf8(); os.makedirs(proje, exist_ok=True)
    yeni, hata = [], 0
    for tur, y in _girdiler(yollar):
        try:
            if tur == "yok": raise RuntimeError("dosya bulunamadı")
            if tur == "url":
                durum, klasor = indir.indir_bir({"urun": "video", "url": y, "not": ""}, proje, cerez)
                if durum.startswith("HATA"): raise RuntimeError(durum[6:])
                m = ortak.oku_json(os.path.join(klasor, ortak.META))
                if "eklendi" not in m: m["eklendi"] = time.strftime("%Y-%m-%d %H:%M:%S"); ortak.yaz_json(os.path.join(klasor, ortak.META), m)
            else:
                durum, klasor = _dosya_ekle(y, proje)
            if not os.path.exists(os.path.join(klasor, ONIZLEME)): onizleme(klasor)
            m = ortak.oku_json(os.path.join(klasor, ortak.META))
            print(f"{durum.upper():8} {klasor}  önizleme: {os.path.join(klasor, ONIZLEME)}  marka: {m.get('marka') or '—'}")
            if durum != "atlandi": yeni.append(klasor)
        except Exception as e:
            hata += 1; print(f"HATA     {y}  {str(e)[:200]}")
    print(f"özet: {len(yeni)} yeni video, {hata} hata")
    return yeni, hata


def kayit_oku(proje="is"):
    p = os.path.join(proje, KAYIT)
    return ortak.oku_json(p) if os.path.exists(p) else {}


def _klasor_bul(proje, ad):
    if os.path.isdir(ad) and os.path.exists(os.path.join(ad, ortak.KAYNAK)): return ad
    p = os.path.join(proje, ad)
    if os.path.exists(os.path.join(p, ortak.KAYNAK)): return p
    raise RuntimeError(f"video klasörü yok: {ad}")


def marka_ata(videolar, marka, urun=None, proje="is"):
    """Videoları markaya bağlar; marka yeni ise kayda ürün tanımı + önizlemeyle ekler."""
    ortak.utf8()
    marka = marka.strip()
    if not marka or re.search(r'[/\\:*?"<>|]', marka): raise RuntimeError(f"geçersiz marka adı: {marka!r}")
    kayit = kayit_oku(proje)
    klasorler = [_klasor_bul(proje, v) for v in videolar]
    if marka not in kayit:
        if not urun: raise RuntimeError(f"yeni marka «{marka}» için --urun (kısa ürün tanımı) gerekli")
        kayit[marka] = {"urun": urun, "onizleme": os.path.join(klasorler[0], ONIZLEME) if klasorler else "",
                        "olusturuldu": time.strftime("%Y-%m-%d %H:%M")}
    elif urun and not kayit[marka].get("urun"): kayit[marka]["urun"] = urun
    for k in klasorler:
        mp = os.path.join(k, ortak.META); m = ortak.oku_json(mp)
        m["marka"] = marka
        ortak.yaz_json(mp, m)
        print(f"{os.path.basename(k)} → {marka}")
    ortak.yaz_json(os.path.join(proje, KAYIT), kayit)
    return kayit


def markalar(proje="is"):
    """Kayıtlı markalar (ürün tanımı + video sayısı) ve markası atanmamış videolar."""
    ortak.utf8()
    kayit = kayit_oku(proje); say, bos = {}, []
    for k in ortak.is_klasorleri(proje) if os.path.isdir(proje) else []:
        m = ortak.oku_json(os.path.join(k, ortak.META))
        if m.get("marka"): say[m["marka"]] = say.get(m["marka"], 0) + 1
        else: bos.append(k)
    for ad, v in kayit.items():
        print(f"MARKA  {ad}  ({say.get(ad, 0)} video)  ürün: {v.get('urun', '')}  önizleme: {v.get('onizleme', '')}")
    for k in bos: print(f"ATANMAMIŞ  {k}  önizleme: {os.path.join(k, ONIZLEME)}")
    print(f"özet: {len(kayit)} marka, {len(bos)} markasız video")
    return kayit, bos


def _plan_oku(p):
    if not os.path.exists(p): return []
    with open(p, encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))


def _eklenme(k):
    m = ortak.oku_json(os.path.join(k, ortak.META))
    return m.get("eklendi") or m.get("indirildi") or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(k)))


def teslim(proje="is", hedef=VARSAYILAN_HEDEF, baslangic=None, saat="18:00", gunluk=1):
    """Render'ı bitmiş, markası atanmış, henüz teslim edilmemiş videoları <hedef>/<Marka>/N.mp4 olarak kopyalar
    ve markanın plan.csv'sine ekler. Teslim edilenleri döndürür."""
    ortak.utf8()
    saatler = [s.strip() for s in saat.split(",") if s.strip()]
    gunluk = max(gunluk, len(saatler))
    bugun = dt.date.today()
    ilk_gun = dt.date.fromisoformat(baslangic) if baslangic else bugun + dt.timedelta(days=1)
    gruplar, atla = {}, []
    for k in ortak.is_klasorleri(proje):
        m = ortak.oku_json(os.path.join(k, ortak.META))
        if m.get("teslim"): continue
        ayar_p = os.path.join(k, ortak.AYAR)
        ayar = ortak.oku_json(ayar_p) if os.path.exists(ayar_p) else {}
        cikti = ayar.get("cikti") or os.path.join(k, ortak.CIKTI)
        if not os.path.exists(cikti): atla.append(f"{os.path.basename(k)} (henüz hazır değil)"); continue
        if not m.get("marka"): atla.append(f"{os.path.basename(k)} (marka yok)"); continue
        gruplar.setdefault(m["marka"], []).append((k, m, ayar, cikti))
    teslim_edilen = []
    for marka, liste in sorted(gruplar.items()):
        liste.sort(key=lambda x: _eklenme(x[0]))
        klasor = os.path.join(hedef, marka); os.makedirs(klasor, exist_ok=True)
        plan_p = os.path.join(klasor, PLAN); plan = _plan_oku(plan_p)
        numaralar = [int(os.path.splitext(d)[0]) for d in os.listdir(klasor) if re.fullmatch(r"\d+\.mp4", d)]
        n = max(numaralar + [int(r["sira"]) for r in plan if str(r.get("sira", "")).isdigit()] + [0])
        # tarih: markanın son planlı gününün ertesi (o gün dolmadıysa aynı gün) — en erken ilk_gun
        son = [dt.date.fromisoformat(r["tarih"]) for r in plan if r.get("tarih")]
        gun, sira_gun = ilk_gun, 0
        if son and max(son) >= ilk_gun:
            gun = max(son); sira_gun = sum(1 for d in son if d == gun)
            if sira_gun >= gunluk: gun, sira_gun = gun + dt.timedelta(days=1), 0
        for k, m, ayar, cikti in liste:
            n += 1
            ad = f"{n}.mp4"; yol = os.path.join(klasor, ad)
            if os.path.exists(yol): raise RuntimeError(f"{yol} zaten var — üzerine yazılmaz")
            shutil.copy2(cikti, yol)
            if ortak.metadata_rapor(yol): ortak.metadata_temizle(yol)
            kalan = ortak.metadata_rapor(yol)
            g = ayar.get("gonderi") or {}
            satir = {"sira": n, "dosya": ad, "tarih": gun.isoformat(), "saat": saatler[sira_gun % len(saatler)],
                     "aciklama": g.get("aciklama", ""), "hashtag": g.get("hashtag", ""),
                     "kaynak": m.get("url") or os.path.basename(m.get("kaynak_dosya", ""))}
            plan.append(satir)
            m["teslim"] = os.path.join(marka, ad); ortak.yaz_json(os.path.join(k, ortak.META), m)
            teslim_edilen.append(yol)
            print(f"{marka}/{ad}  {satir['tarih']} {satir['saat']}  ← {os.path.basename(k)}" + (f"  ⚠ metadata: {kalan}" if kalan else ""))
            sira_gun += 1
            if sira_gun >= gunluk: gun, sira_gun = gun + dt.timedelta(days=1), 0
        with open(plan_p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=PLAN_ALANLAR, extrasaction="ignore"); w.writeheader(); w.writerows(plan)
    for a in atla: print(f"BEKLİYOR  {a}")
    print(f"özet: {len(teslim_edilen)} video teslim edildi → {hedef}")
    return teslim_edilen
