"""Videodaki gömülü yazıları OTOMATİK bulur (Apple Vision OCR) ve taslak ayar.json yazar.

Çıktı (video klasörüne):
  tablo.png  — saniye etiketli kare tablosu (y cetvelli), gözle kontrol için
  ayar.json  — bant, her yazının zamanı/örnek anı/orijinal metni; "satirlar" BOŞ bırakılır,
               çeviriyi Claude (veya insan) doldurur → sonra `captiontr cevir`.
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
# TikTok/Instagram "yoruma yanıt" balonu: başlık satırı bu kalıplardan birini taşır
YORUM_RE = re.compile(r"(?i)(repl(y|ying|ied)\s+to\b|[’'`]s\s+comment|yorumuna\s+yan[ıi]t|respond(ió|iendo)\s+a|antwort\s+auf)")


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


def _kullanici(baslik):
    m = re.search(r"(?i)repl(?:y|ying|ied)\s+to\s+@?(.+?)(?:[’'`]s\s+comment|$)", baslik)
    return (m.group(1).strip(" @:") if m else "")


def balon_kutu(kare, metin_kutu):
    """Balonun kendisi: yazı kutusunun çevresindeki beyaz zeminin bağlı bileşeni (avatar solda dahil)."""
    H, W = kare.shape[:2]; x0, y0, x1, y1 = metin_kutu; h = max(8, (y1 - y0) // 3); g = max(16, y1 - y0)
    a0, b0, a1, b1 = max(0, x0 - 2 * g), max(0, y0 - g), min(W, x1 + g), min(H, y1 + g)   # avatar solda ~2 satır boyu
    beyaz_m = beyaz(kare[b0:b1, a0:a1]).astype(np.uint8)
    beyaz_m = cv2.morphologyEx(beyaz_m, cv2.MORPH_CLOSE, np.ones((h, h), np.uint8))
    n, et, st, _ = cv2.connectedComponentsWithStats(beyaz_m)
    en, sec = 0, None
    for i in range(1, n):
        x, y, w, hh, _ = st[i]
        ortak_x = max(0, min(x + w, x1 - a0) - max(x, x0 - a0)); ortak_y = max(0, min(y + hh, y1 - b0) - max(y, y0 - b0))
        if ortak_x * ortak_y > en: en, sec = ortak_x * ortak_y, (a0 + x, b0 + y, a0 + x + w, b0 + y + hh)
    if sec is None or en < 0.5 * (x1 - x0) * (y1 - y0): return [x0 - 3 * h, y0 - h, x1 + h, y1 + h]
    return [int(min(sec[0], x0)), int(min(sec[1], y0)), int(max(sec[2], x1)), int(max(sec[3], y1))]


def yorumlari_ayir(ornekler, W, H):
    """Her örnekte yorum balonu satırlarını (başlık + altındaki yorum metni) altyazıdan ayırır.
    Döner: [(t, {"baslik", "govde": [satırlar], "kutu"})] — ornekler yerinde temizlenir."""
    bulunan = []
    for t, satirlar in ornekler:
        for s in [x for x in satirlar if YORUM_RE.search(x["metin"])]:
            if s not in satirlar: continue
            grup, h = [s], s["y1"] - s["y0"]
            for z in sorted(satirlar, key=lambda z: z["y0"]):
                if z is s or z["y0"] < s["y0"]: continue
                if z["y0"] - grup[-1]["y1"] < 1.3 * h and z["x0"] < s["x1"] + 3 * h and z["x1"] > s["x0"] - 3 * h and len(grup) < 5:
                    grup.append(z)
            for z in grup: satirlar.remove(z)
            bulunan.append((t, {"baslik": s["metin"], "govde": [z["metin"] for z in grup[1:]],
                                "kutu": [min(z["x0"] for z in grup), min(z["y0"] for z in grup),
                                         max(z["x1"] for z in grup), max(z["y1"] for z in grup)],
                                "govde_px": int(np.median([z["y1"] - z["y0"] for z in grup[1:]] or [h]))}))
    return bulunan


def yorum_gruplari(bulunan, video, W, H):
    """Zaman içinde aynı yerdeki balonları tek yoruma topla, balon kutusunu karede ölç."""
    gruplar = []
    for t, y in bulunan:
        k = y["kutu"]; g = gruplar[-1] if gruplar else None
        if g and t - g["bit"] < BOSLUK_SN and abs(k[1] - g["_k"][1]) < 0.04 * H and abs(k[0] - g["_k"][0]) < 0.06 * W:
            g["bit"] = t + ADIM_SN; g["_hepsi"].append(y)
        else:
            gruplar.append({"bas": t, "bit": t + ADIM_SN, "_k": k, "_hepsi": [y]})
    cap = cv2.VideoCapture(video); fps = ortak.bilgi(video)["fps"]; sonuc = []
    for g in gruplar:
        en_uzun = max(g["_hepsi"], key=lambda y: len(y["govde"]))
        metin_kutu = [int(np.median([y["kutu"][i] for y in g["_hepsi"]])) for i in range(4)]
        metin_kutu[3] = max(metin_kutu[3], en_uzun["kutu"][3])
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((g["bas"] + g["bit"]) / 2 * fps)); ok, f = cap.read()
        kutu = balon_kutu(f, metin_kutu) if ok else metin_kutu
        # kesin başlangıç/bitiş: balon alanının beyazlık oranı kare kare (örnekleme 0,25 sn'lik kaymayı giderir)
        x0, y0, x1, y1 = kutu; ilk, son = int(max(0, g["bas"] - 2 * ADIM_SN) * fps), int((g["bit"] + 2 * ADIM_SN) * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, ilk); oran = []
        for i in range(ilk, son):
            ok2, f2 = cap.read()
            if not ok2: break
            oran.append((i, float(beyaz(f2[y0:y1, x0:x1]).mean())))
        tepe = max([o for _, o in oran] or [0])
        var = [i for i, o in oran if o > 0.6 * tepe] if tepe > 0.3 else []
        bas_sn, bit_sn = (var[0] / fps, (var[-1] + 1) / fps) if var else (max(0, g["bas"] - ADIM_SN), g["bit"])
        baslik = Counter(y["baslik"] for y in g["_hepsi"]).most_common(1)[0][0]
        sonuc.append({"bas": round(bas_sn, 3), "bit": round(bit_sn, 3), "kutu": kutu,
                      "platform": "tiktok", "orijinal_baslik": baslik, "orijinal": en_uzun["govde"],
                      "kullanici": _kullanici(baslik), "govde_px": en_uzun["govde_px"], "metin": ""})
    cap.release()
    return sonuc


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
    yorumlar = yorum_gruplari(yorumlari_ayir(ornekler, W, H), video, W, H)   # balon satırları altyazı sayılmaz

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
    elif not yorumlar:
        uyarilar.append("hiç beyaz altyazı bulunamadı (renkli/kutulu yazı olabilir) — tablo.png'ye bak")
    ayar["altyazilar"] = altyazilar
    if yorumlar: ayar["yorumlar"] = yorumlar
    if uyarilar: ayar["uyarilar"] = uyarilar
    ortak.yaz_json(ayar_yol, ayar)
    tablo(video, os.path.join(klasor, ortak.TABLO))
    return f"{len(altyazilar)} yazı" + (f", {len(yorumlar)} yorum balonu" if yorumlar else "") + (f", {len(uyarilar)} uyarı" if uyarilar else "")


def calistir(proje, zorla=False):
    ortak.utf8()
    for k in ortak.is_klasorleri(proje):
        try: durum = analiz_et(k, zorla)
        except Exception as e: durum = f"HATA: {e}"
        print(f"{os.path.basename(k):40} {durum}", flush=True)
    return 0
