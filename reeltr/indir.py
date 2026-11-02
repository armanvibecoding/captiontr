"""Toplu, filigransız video indirme (Instagram Reels / TikTok / YouTube Shorts — yt-dlp).

Liste: CSV (başlık satırı: urun,url[,not]) ya da her satırda bir URL olan .txt.
Her video kendi klasörüne iner: <hedef>/<urun>-<kod>/kaynak.mp4 + meta.json

Filigran: Instagram'ın CDN dosyası zaten filigransızdır (filigran yalnız uygulamadan
"kaydet/paylaş" ile eklenir). TikTok'ta yt-dlp filigranlı biçimi "watermarked" diye
işaretler; seçici bunları dışarıda bırakır, filigransız biçim yoksa video ATLANIR.
"""
import csv, os, random, re, shutil, time

from . import ortak

# en iyi görüntü + ses (birleştirilir); filigranlı biçimler hariç
BICIM = "bv*[format_note!*=watermarked]+ba/b[format_note!*=watermarked]"


def liste_oku(yol):
    satirlar = []
    with open(yol, encoding="utf-8-sig") as f:
        if yol.lower().endswith(".csv"):
            for r in csv.DictReader(f):
                if (r.get("url") or "").strip():
                    satirlar.append({"urun": (r.get("urun") or "video").strip(), "url": r["url"].strip(), "not": (r.get("not") or "").strip()})
        else:
            for s in f:
                s = s.strip()
                if s and not s.startswith("#"): satirlar.append({"urun": "video", "url": s, "not": ""})
    return satirlar


def kod(url):
    m = re.search(r"/(?:reel|reels|p|video|shorts)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else re.sub(r"\W+", "_", url)[-24:]


def guvenli(s):
    s = re.sub(r"[^\w-]+", "-", s.lower()).strip("-")
    return s[:40] or "video"


def indir_bir(satir, hedef, cerez_tarayici=None, deneme=3):
    import yt_dlp
    klasor = os.path.join(hedef, f"{guvenli(satir['urun'])}-{kod(satir['url'])}")
    son = os.path.join(klasor, ortak.KAYNAK)
    if os.path.exists(son) and os.path.getsize(son) > 0: return "atlandi", klasor
    os.makedirs(klasor, exist_ok=True)
    gecici = os.path.join(klasor, ".indiriliyor")
    shutil.rmtree(gecici, ignore_errors=True)
    secenek = {
        "format": BICIM, "merge_output_format": "mp4", "ffmpeg_location": ortak.ffmpeg(),
        "outtmpl": os.path.join(gecici, "v.%(ext)s"), "quiet": True, "no_warnings": True, "noprogress": True,
        "noplaylist": True, "retries": 3, "socket_timeout": 30,
    }
    if cerez_tarayici: secenek["cookiesfrombrowser"] = (cerez_tarayici,)
    hata = None
    for n in range(deneme):
        try:
            with yt_dlp.YoutubeDL(secenek) as y:
                info = y.extract_info(satir["url"], download=True)
            dosya = next((os.path.join(gecici, d) for d in os.listdir(gecici) if d.endswith(".mp4")), None)
            if not dosya: raise RuntimeError("mp4 oluşmadı")
            fmt = " ".join(str(f.get("format_note") or "") for f in (info.get("requested_formats") or [info]))
            if "watermark" in fmt.lower(): raise RuntimeError("yalnız filigranlı biçim var")
            ortak.metadata_temizle(dosya, son)   # platform/encoder metadata'sı silinir (yeniden kodlamadan)
            os.remove(dosya)
            shutil.rmtree(gecici, ignore_errors=True)
            b = ortak.bilgi(son)
            ortak.yaz_json(os.path.join(klasor, ortak.META), {
                "urun": satir["urun"], "url": satir["url"], "not": satir["not"], "kod": kod(satir["url"]),
                "hesap": info.get("uploader") or info.get("channel"), "aciklama": (info.get("description") or "")[:2000],
                "izlenme": info.get("view_count"), "begeni": info.get("like_count"), "yorum": info.get("comment_count"),
                "tarih": info.get("upload_date"), "sure_sn": info.get("duration"),
                "genislik": b["w"], "yukseklik": b["h"], "fps": round(b["fps"], 3), "bicim": fmt.strip(),
                "indirildi": time.strftime("%Y-%m-%d %H:%M"),
            })
            return "indi", klasor
        except Exception as e:  # ağ / hız sınırı: artan beklemeyle tekrar dene
            hata = str(e).splitlines()[0][:300]
            if n < deneme - 1: time.sleep(20 * (n + 1))
    shutil.rmtree(gecici, ignore_errors=True)
    return f"HATA: {hata}", klasor


def calistir(liste, hedef, cerez_tarayici=None, bekle=(4, 9)):
    ortak.utf8()
    satirlar = liste_oku(liste)
    os.makedirs(hedef, exist_ok=True)
    sonuc = {"indi": 0, "atlandi": 0, "hata": 0}
    for i, s in enumerate(satirlar, 1):
        durum, klasor = indir_bir(s, hedef, cerez_tarayici)
        anahtar = "hata" if durum.startswith("HATA") else durum
        sonuc[anahtar] += 1
        print(f"[{i}/{len(satirlar)}] {durum:8} {os.path.basename(klasor)}  {s['url']}", flush=True)
        if durum == "indi" and i < len(satirlar): time.sleep(random.uniform(*bekle))  # hesabı/IP'yi yormamak için
    print(f"özet: {sonuc['indi']} indi, {sonuc['atlandi']} zaten vardı, {sonuc['hata']} hata")
    return 1 if sonuc["hata"] else 0


def bilgi_topla(liste, cikti, bekle=(2, 4)):
    """İndirmeden metadata çeker, ürün başına beğeniye göre sıralı CSV yazar (aday seçimi için)."""
    import yt_dlp
    ortak.utf8()
    satirlar = liste_oku(liste); sonuc = []
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as y:
        for i, s in enumerate(satirlar, 1):
            try:
                info = y.extract_info(s["url"], download=False)
                r = {**s, "begeni": info.get("like_count") or 0, "izlenme": info.get("view_count") or "",
                     "sure": round(info.get("duration") or 0), "tarih": info.get("upload_date") or "",
                     "hesap": info.get("uploader") or "", "aciklama": (info.get("description") or "")[:120].replace("\n", " ")}
            except Exception as e:
                r = {**s, "begeni": -1, "izlenme": "", "sure": 0, "tarih": "", "hesap": "", "aciklama": f"HATA {str(e)[:80]}"}
            sonuc.append(r)
            print(f"[{i}/{len(satirlar)}] {r['urun']:12} {r['begeni']:>9} {r['sure']:>3}s {s['url']}", flush=True)
            time.sleep(random.uniform(*bekle))
    sonuc.sort(key=lambda r: (r["urun"], -r["begeni"]))
    with open(cikti, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sonuc[0].keys())); w.writeheader(); w.writerows(sonuc)
    return 0
