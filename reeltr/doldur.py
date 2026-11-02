"""Zamansal arka plan doldurma: yazının altındaki gerçek görüntüyü başka karelerden getirir.

Kamera oynadıkça (ya da yazı gelmeden/gittikten sonra) yazının örttüğü arka plan başka karelerde görünür.
Her yazılı kare için yakın karelerden başlayarak: iki kare arasında homografi (ORB + RANSAC, yazı alanları
hariç) → aday kare hizalanır → o karede yazıyla örtülü OLMAYAN pikseller maskeli bölgeye kopyalanır.
Doldurulamayan pikseller TELEA ile yamanır ve oranı raporlanır (zor video = elenir).
"""
import cv2, numpy as np

from . import ortak

OLCEK = 0.35       # öznitelik için küçültme
PENCERE_SN = 4.0   # aday karelerin en uzak mesafesi
PAY = 160          # bant dışına taşan hizalama için üst/alt pay (px)
ADAY = 12          # her yönde denenecek aday kare sayısı
KALAN = 0.002      # bu orandan az boş piksel kalınca aramayı bırak (TELEA kapatır)


def _yazi_maskesi(etiket, maske, i, yari, Y0, Y1, H, kare_maske=None):
    """i. karede (±yarım sn) yazı olabilecek her yer (tam kare koordinatı)."""
    m = np.zeros((H, maske[0][0].shape[1] if maske else 1), np.uint8)
    for j in range(max(0, i - yari), min(len(etiket), i + yari + 1)):
        k = etiket[j]
        if k >= 0: m[Y0:Y1] |= (kare_maske or {}).get(j, maske[k][0])
    return m


def hazirla(video, etiket, maske, Y0, Y1, kare_maske=None):
    """Yazılı her kare için doldurulmuş bant (Y0:Y1) + yazı başına doldurma oranı."""
    b = ortak.bilgi(video); W, H, FPS = b["w"], b["h"], b["fps"]
    yari = int(FPS * 0.5); pen = int(FPS * PENCERE_SN)
    a0, a1 = max(0, Y0 - PAY), min(H, Y1 + PAY)
    orb = cv2.ORB_create(2500); eslestir = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    bant, oz = {}, {}
    gerekli = {i for i, e in enumerate(etiket) if e >= 0}
    yakin = set()
    for i in gerekli: yakin.update(range(max(0, i - pen), min(len(etiket), i + pen + 1)))
    for i, f in ortak.kareler(video):
        if i not in yakin: continue
        bant[i] = cv2.imencode(".jpg", f[a0:a1], [cv2.IMWRITE_JPEG_QUALITY, 96])[1]
        ym = _yazi_maskesi(etiket, maske, i, yari, Y0, Y1, H, kare_maske)
        g = cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), None, fx=OLCEK, fy=OLCEK)
        mm = cv2.resize(255 - cv2.dilate(ym, np.ones((25, 25), np.uint8)), (g.shape[1], g.shape[0]), interpolation=cv2.INTER_NEAREST)
        oz[i] = orb.detectAndCompute(g, mm)
    acik = lambda i: cv2.imdecode(bant[i], cv2.IMREAD_COLOR)
    S = np.array([[OLCEK, 0, 0], [0, OLCEK, 0], [0, 0, 1]]); Si = np.linalg.inv(S)
    T = np.array([[1, 0, 0], [0, 1, a0], [0, 0, 1]], float); Ti = np.linalg.inv(T)
    # aday uzaklıkları: yakından uzağa seyrekleşen ~24 mesafe (her mesafeyi denemek videoyu saatlerce sürdürür)
    adim = sorted({max(1, int(round(pen * (t / ADAY) ** 2))) for t in range(1, ADAY + 1)})
    sira = [s * d for d in adim for s in (-1, 1)]
    sonuc, oran, onceki = {}, {}, []
    for i in sorted(gerekli):
        k = etiket[i]; m = (kare_maske or {}).get(i, maske[k][0])
        hedef = np.zeros((a1 - a0, W), bool); hedef[Y0 - a0:Y1 - a0] = cv2.dilate(m, np.ones((5, 5), np.uint8)) > 0
        o = acik(i); bos = hedef.copy(); ki, di = oz[i]; esik = KALAN * hedef.sum(); ise = []
        for d in list(dict.fromkeys(onceki + sira)):   # bir önceki karede işe yarayan mesafeler önce
            j = i + d
            if bos.sum() <= esik: break
            if d == 0 or j not in oz or di is None: continue
            kj, dj = oz[j]
            if dj is None or len(kj) < 30: continue
            es = eslestir.match(dj, di)
            if len(es) < 40: continue
            p1 = np.float32([kj[t.queryIdx].pt for t in es]); p2 = np.float32([ki[t.trainIdx].pt for t in es])
            Hk, inl = cv2.findHomography(p1, p2, cv2.RANSAC, 2.0)
            if Hk is None or inl.sum() < 0.5 * len(es) or inl.sum() < 30: continue   # sahne kesmesi / güvensiz
            Hb = Ti @ Si @ Hk @ S @ T   # bant koordinatında j → i
            w = cv2.warpPerspective(acik(j), Hb, (W, a1 - a0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
            gecerli = np.ones((a1 - a0, W), np.uint8) * 255
            ym = _yazi_maskesi(etiket, maske, j, yari, Y0, Y1, H, kare_maske)[a0:a1]
            gecerli[cv2.dilate(ym, np.ones((9, 9), np.uint8)) > 0] = 0
            gw = cv2.warpPerspective(gecerli, Hb, (W, a1 - a0), flags=cv2.INTER_NEAREST, borderValue=0) > 0
            al = bos & gw
            if al.sum() < 20: continue
            o[al] = w[al]; bos &= ~al; ise.append(d)
        onceki = ise
        dolu = 1 - bos.sum() / max(1, hedef.sum())
        if bos.any(): o = cv2.inpaint(o, bos.astype(np.uint8) * 255, 6, cv2.INPAINT_TELEA)
        # dikiş: doldurulan bölgenin kenarını 3 px yumuşat
        al = cv2.GaussianBlur(hedef.astype(np.float32), (7, 7), 0)[..., None]
        o = (o * al + acik(i) * (1 - al)).astype(np.uint8)
        sonuc[i] = cv2.imencode(".jpg", o[Y0 - a0:Y1 - a0], [cv2.IMWRITE_JPEG_QUALITY, 97])[1]
        oran.setdefault(k, []).append(dolu)
    return sonuc, {k: float(np.mean(v)) for k, v in oran.items()}
