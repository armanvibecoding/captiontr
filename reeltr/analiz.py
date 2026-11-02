"""Videodaki gömülü yazıları OTOMATİK bulur (Apple Vision OCR) ve taslak ayar.json yazar.

Çıktı (video klasörüne):
  tablo.png  — saniye etiketli kare tablosu (y cetvelli), gözle kontrol için
  ayar.json  — bant, her yazının zamanı/örnek anı/orijinal metni; "satirlar" BOŞ bırakılır,
               çeviriyi Claude (veya insan) doldurur → sonra `reeltr cevir`.
Emojiler OCR'da okunmaz; tablo.png'ye bakıp çeviriye eklenir.
Mevcut ve çevirisi doldurulmuş ayar.json'un üstüne yazılmaz (--zorla hariç).
"""
import difflib, os, re
from collections import Counter

import cv2, numpy as np

from . import ortak
from .cevir import govde

ADIM_SN = 0.25        # OCR örnekleme aralığı
GUVEN = 0.5           # Vision güven eşiği
BEYAZ_PAY = 0.06      # kutudaki beyaz piksel oranı: altyazı beyazdır, ürün/ambalaj yazısı genelde değil
KUTU_BEYAZ = 0.66     # kutulu: OCR kutusunun çoğu beyaz zemin…
KUTU_GOVDE = 0.07     # …ve koyu pikseller kalın harf gövdesi (kenarlı yazıda koyu = ince kenar çizgisi)
IZ_SN = 1.0           # bir satır altyazı sayılmak için en az bu kadar aynı yerde durmalı
BOSLUK_SN = 1.0       # aynı metnin bundan kısa kesintileri tek yazı sayılır


def beyaz(b):
    hsv = cv2.cvtColor(b, cv2.COLOR_BGR2HSV)
    return (hsv[..., 2] > 215) & (hsv[..., 1] < 50)


def ocr(kare):
    import Vision
    from Foundation import NSData
    ok, buf = cv2.imencode(".png", kare)
    veri = NSData.dataWithBytes_length_(buf.tobytes(), len(buf))
    istek = Vision.VNRecognizeTextRequest.alloc().init()
    istek.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    istek.setUsesLanguageCorrection_(False)
    Vision.VNImageRequestHandler.alloc().initWithData_options_(veri, None).performRequests_error_([istek], None)
    H, W = kare.shape[:2]
    sonuc = []
    for o in istek.results() or []:
        c = o.topCandidates_(1)[0]
        if c.confidence() < GUVEN: continue
        bb = o.boundingBox()
        x0 = int(bb.origin.x * W); w = int(bb.size.width * W)
        y0 = int((1 - bb.origin.y - bb.size.height) * H); h = int(bb.size.height * H)
        x0, y0 = max(0, x0), max(0, y0)
        kutu = kare[y0:y0 + h, x0:x0 + w]
        if kutu.size == 0: continue
        oran = float(beyaz(kutu).mean())
        if oran < BEYAZ_PAY: continue
        metin = c.string().strip()
        if len(re.sub(r"\W", "", metin)) < 2: continue
        koyu = cv2.cvtColor(kutu, cv2.COLOR_BGR2HSV)[..., 2] < 90
        sonuc.append({"metin": metin, "x0": x0, "y0": y0, "x1": x0 + w, "y1": y0 + h, "beyaz": oran,
                      "koyu_govde": govde(koyu) / max(1, h)})
    return sorted(sonuc, key=lambda s: s["y0"])


def stil_bul(kutular):
    """Beyaz zemin üstündeki kenarlı yazı ile beyaz kutulu yazıyı ayırır (gerçek videolarla kalibre)."""
    b = np.median([k["beyaz"] for k in kutular]); g = np.median([k["koyu_govde"] for k in kutular])
    return "kutulu" if b > KUTU_BEYAZ and g > KUTU_GOVDE else "kenarli"


def norm(s):
    return re.sub(r"[^0-9a-zçğıöşü]+", "", s.lower())


def benzer(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def ayni_blok(a, b):
    return benzer(a, b) > 0.8 or a in b or b in a


def ayni_yer(a, b, W, H):
    return abs((a["x0"] + a["x1"]) - (b["x0"] + b["x1"])) / 2 < 0.05 * W and abs(a["y0"] - b["y0"]) < 0.03 * H


def tablo(video, cikti):
    """Saniyede 2 kare, 7 sütun; solda kırmızı y cetveli (orijinal piksel)."""
    b = ortak.bilgi(video); fps, w, h = b["fps"], b["w"], b["h"]
    adim = max(1, int(round(fps / 2)))
    tw = 288; th = int(h * tw / w); karolar = []
    for i, f in ortak.kareler(video):
        if i % adim: continue
        f = cv2.resize(f, (tw, th))
        for y in range(100, h, 100):
            yy = int(y * th / h); cv2.line(f, (0, yy), (12, yy), (0, 0, 255), 1)
            cv2.putText(f, str(y), (14, yy + 4), 0, 0.35, (0, 0, 255), 1)
        cv2.putText(f, f"{i / fps:.1f}s", (5, 20), 0, 0.6, (0, 255, 255), 2)
        karolar.append(f)
    kol = 7
    while len(karolar) % kol: karolar.append(np.zeros_like(karolar[0]))
    cv2.imwrite(cikti, np.vstack([np.hstack(karolar[i:i + kol]) for i in range(0, len(karolar), kol)]))


def analiz_et(klasor, zorla=False):
    klasor = os.path.abspath(klasor)
    video = os.path.join(klasor, ortak.KAYNAK)
    ayar_yol = os.path.join(klasor, ortak.AYAR)
    if os.path.exists(ayar_yol) and not zorla:
        return "atlandı (analiz var; yeniden için --zorla)"
    b = ortak.bilgi(video); fps, W, H = b["fps"], b["w"], b["h"]
    adim = max(1, int(round(fps * ADIM_SN)))

    ornekler = []                                   # (zaman, satır listesi)
    for i, f in ortak.kareler(video):
        if i % adim == 0: ornekler.append((i / fps, ocr(f)))

    # iz takibi: aynı yerde ve aynı metinle en az IZ_SN görünen satırlar altyazıdır;
    # kısa süre görünen ambalaj/ekran yazıları elenir
    izler = []
    for t, satirlar in ornekler:
        for s in satirlar:
            s["norm"] = norm(s["metin"])
            iz = next((z for z in izler if ayni_yer(s, z, W, H) and benzer(s["norm"], z["norm"]) > 0.7), None)
            if iz is None: iz = {**s, "say": 0}; izler.append(iz)
            iz["say"] += 1; s["iz"] = iz
    ornekler = [(t, [s for s in st if s["iz"]["say"] * ADIM_SN >= IZ_SN]) for t, st in ornekler]

    # ardışık örnekleri aynı metin bloğuna göre segmentlere böl
    segler = []
    for t, satirlar in ornekler:
        blok = norm(" ".join(s["metin"] for s in satirlar))
        if not blok: continue
        son = segler[-1] if segler else None
        if son and t - son["bit"] < BOSLUK_SN and ayni_blok(blok, son["blok"]):
            son["ornekler"].append((t, satirlar)); son["bit"] = t + ADIM_SN
            if len(blok) > len(son["blok"]): son["blok"] = blok   # kelime kelime beliren yazı: en uzun hali
        else:
            segler.append({"blok": blok, "bas": t, "bit": t + ADIM_SN, "ornekler": [(t, satirlar)]})
    segler = [s for s in segler if s["bit"] - s["bas"] >= 0.5]   # çok kısa = gürültü

    altyazilar, kutular, uyarilar = [], [], []
    for s in segler:
        n = len(s["ornekler"])
        # segmentin en az yarısında görünen izler = bu yazının satırları (y sırasıyla)
        say = Counter(id(x["iz"]) for _, st in s["ornekler"] for x in st)
        izs = {id(x["iz"]): x["iz"] for _, st in s["ornekler"] for x in st}
        satir_izleri = sorted((izs[i] for i, c in say.items() if c >= max(2, n * 0.5)), key=lambda z: z["y0"])
        if not satir_izleri: continue
        # ana bloğa bitişik olmayan satırlar (ürün üstündeki yazı vb.) ayrılır
        blok = [satir_izleri[0]]
        for z in satir_izleri[1:]:
            boy = blok[-1]["y1"] - blok[-1]["y0"]
            if z["y0"] - blok[-1]["y1"] < 1.5 * boy: blok.append(z)
            else: uyarilar.append(f"{s['bas']:.1f} sn: bloktan uzak satır atlandı: {z['metin']!r}")
        orijinal, satir_kutu, kutu_ozet = [], [], []
        for z in blok:
            gor = [x for _, st in s["ornekler"] for x in st if x["iz"] is z]
            orijinal.append(Counter(x["metin"] for x in gor).most_common(1)[0][0]); satir_kutu.extend(gor)
            kutu_ozet.append([int(np.median([x[k] for x in gor])) for k in ("x0", "y0", "x1", "y1")])
        kutular.extend(satir_kutu)
        # örnek an: tüm satırların birlikte okunduğu örneklerin ortası
        tam = [t for t, st in s["ornekler"] if all(any(x["iz"] is z for x in st) for z in blok)] or [t for t, _ in s["ornekler"]]
        orta = tam[len(tam) // 2]
        stil = stil_bul(satir_kutu)
        yeni = {"ornek_sn": round(orta, 2), "bas": round(s["bas"], 2), "bit": round(s["bit"], 2), "stil": stil,
                "orijinal": orijinal, "kutular": kutu_ozet, "satirlar": []}
        onceki = altyazilar[-1] if altyazilar else None
        # aynı metin, kısa arayla (arkadaki başka yazı yüzünden bölünmüş) → uzun olan parçayı esas alarak birleştir
        if onceki and yeni["bas"] - onceki["bit"] < BOSLUK_SN and benzer(norm(" ".join(onceki["orijinal"][:2])), norm(" ".join(orijinal[:2]))) > 0.8:
            uzun = yeni if yeni["bit"] - yeni["bas"] > onceki["bit"] - onceki["bas"] else onceki
            altyazilar[-1] = {**uzun, "bas": onceki["bas"], "bit": yeni["bit"]}
            continue
        altyazilar.append(yeni)
    ayar = {"kaynak": video, "cikti": os.path.join(klasor, ortak.CIKTI), "genislik": W, "yukseklik": H}
    if kutular:
        # kutulu stil: OCR kutusunun çoğu beyaz (beyaz zemin üstünde koyu yazı); kenarlı beyaz yazıda az
        ayar["stil"] = stil_bul(kutular)
        kutulu_var = any(a.get("stil") == "kutulu" for a in altyazilar)
        pay = int(0.02 * H) + (int(0.04 * H) if kutulu_var else 0)   # kutu, yazının çok dışına taşar
        ayar["bant"] = [max(0, min(k["y0"] for k in kutular) - pay), min(H, max(k["y1"] for k in kutular) + pay)]
        cx = np.median([(k["x0"] + k["x1"]) / 2 for k in kutular])
        if abs(cx - W / 2) > 0.04 * W: ayar["hizala_orijinal"] = True
    else:
        uyarilar.append("hiç beyaz altyazı bulunamadı (renkli/kutulu yazı olabilir) — tablo.png'ye bak")
    ayar["altyazilar"] = altyazilar
    if uyarilar: ayar["uyarilar"] = uyarilar
    ortak.yaz_json(ayar_yol, ayar)
    tablo(video, os.path.join(klasor, ortak.TABLO))
    return f"{len(altyazilar)} yazı" + (f", {len(uyarilar)} uyarı" if uyarilar else "")


def calistir(proje, zorla=False):
    ortak.utf8()
    for k in ortak.is_klasorleri(proje):
        try: durum = analiz_et(k, zorla)
        except Exception as e: durum = f"HATA: {e}"
        print(f"{os.path.basename(k):40} {durum}", flush=True)
    return 0
