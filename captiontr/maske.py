"""Hassas silme maskesi: yazının gerçekten değiştirdiği pikseller.

Yazı katmanı videonun üstünde SABİT durur, arka plan oynar. Bir pikselin zaman içindeki oynaklığı (S) çevresindeki
arka planın oynaklığından (Sç) belirgin düşükse o piksel yazı katmanının etkisindedir: tam opak yazı hiç oynamaz,
yarı saydam kenar/gölge oynaklığı kısmen bastırır. Arka plan da hareketsizse (tripod) aynı ölçü yazısız komşu
kareyle farktan çıkar.

Maske = beyaz harf tohumu ⊕ VERİDEN ÖLÇÜLEN çekirdek. Çekirdek: harfi her (dx, dy) kadar kaydırınca düşen
piksellerin ortanca "yazı etkisi"; etkili kaymalar kümesi. Böylece kenar kalınlığı, kenar yumuşatması ve gölgenin
yönü/uzunluğu her yazı için ayrı ölçülür (sabit genişletme yok). Emoji: tohuma yakın, satır boyunda sabit parçalar.
"""
import os

import cv2, numpy as np

DURGUN = 5.0       # çevre oynaklığı bunun altındaysa arka plan hareketsiz sayılır
FARK = 14          # yazısız kareyle fark eşiği (hareketsiz arka planda)
ETKI = 0.8         # piksel: oran bunun altı = yazı etkisi (1 = arka plan kadar oynuyor)
KES_OYNAK = 0.93   # kayma: o kaymada düşen piksellerin ORTANCA oranı bunun altı → yazı etkisi var (soluk gölge kuyruğu)
KES_FARK = 0.75    # kayma (hareketsiz arka plan): ortanca fark ≳ FARK/3
OPAK = 0.35        # emoji: oran bunun altı = (neredeyse) opak, hiç oynamayan piksel
GOLGE_UZAK = 0.3   # gölge kuyruğu tek yönde bu kadar uzanabilir (satır yüksekliği katı)
YON_FARK = 0.07    # bir yönün oranı karşı yönünkinden bu kadar düşükse o yön yazı etkisinde (gölge)
CEKIRDEK = 0.4     # en uzak kayma: satır yüksekliğinin bu katı (kalın kenar + yumuşatma; gölge ayrıca modellenir)


def _etki(ornk, tohum, kisit, bh, temiz, medyan):
    """Piksel başına yazı etkisi oranı r (1 ≈ saf arka plan, 0 = tam opak yazı), kayma eşiği ve yöntem."""
    S = ornk.std(axis=0).max(axis=2)
    yakin = cv2.dilate(tohum.astype(np.uint8), np.ones((int(1.2 * bh) | 1,) * 2, np.uint8)) > 0
    arka = ~yakin
    L = float(np.percentile(S[arka & kisit], 50)) if (arka & kisit).sum() > 100 else float(np.percentile(S[arka], 50))
    if L >= DURGUN:
        # yerel arka plan oynaklığı: yazıdan uzak piksellerin normalize konvolüsyonu (yazı yakınını taşır)
        s = max(3, int(bh)) | 1
        pay = cv2.GaussianBlur((S * arka).astype(np.float32), (0, 0), s)
        ag = cv2.GaussianBlur(arka.astype(np.float32), (0, 0), s)
        Sc = np.maximum(pay / np.maximum(ag, 1e-3), DURGUN)
        r = S / Sc
        # emoji için dayanıklı oynaklık (MAD): belirme/kaybolma geçiş kareleri opak pikseli "oynak" göstermesin
        med = np.median(ornk, axis=0)
        r_opak = 1.4826 * np.median(np.abs(ornk - med), axis=0).max(axis=2) / Sc
        if temiz is not None and medyan is not None:
            # yarı hareketsiz sahne (tripod + el): yazının yanındaki duran zemin de az oynar → yazısız kareyle
            # fark da "yazı" demeli (kamera oynuyorsa fark her yerde büyüktür, oynaklık belirleyici kalır)
            D = np.abs(medyan.astype(np.float32) - temiz.astype(np.float32)).max(axis=2)
            rf = 1.0 / (1.0 + D / FARK) / KES_FARK * KES_OYNAK
            return np.maximum(r, rf), np.maximum(r_opak, rf), KES_OYNAK, "oynaklik+fark"
        return r, r_opak, KES_OYNAK, "oynaklik"
    if temiz is not None and medyan is not None:
        D = np.abs(medyan.astype(np.float32) - temiz.astype(np.float32)).max(axis=2)
        rf = 1.0 / (1.0 + D / FARK)
        return rf, rf, KES_FARK, "fark"
    return None, None, None, None


def _kaydir(m, dx, dy):
    o = np.zeros_like(m); h, w = m.shape
    o[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = m[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
    return o


def cekirdek(tohum, r, kes, kisit, bh):
    """Etkili kaymalar (dx, dy) kümesi — orijinden bağlı."""
    R = max(2, int(CEKIRDEK * bh))
    K = np.zeros((2 * R + 1, 2 * R + 1), bool); K[R, R] = True
    # harfe uzaklık: kayan harfin düştüğü piksel, en yakın harfe en az kayma kadar uzaksa ölçülür
    # (yoksa başka harfin üstüne düşer ve "yazı etkisi" sahte çıkar)
    D = cv2.distanceTransform((~tohum).astype(np.uint8), cv2.DIST_L2, 5)
    # taban: yazıdan uzak (≥ R) zeminin oranı. Hareketsiz sahnede zemin de düşük çıkar → eşik tabana göre
    uzak = (D >= R) & (D <= R + max(4, bh // 2)) & kisit
    taban = float(np.median(r[uzak])) if uzak.sum() > 100 else 1.0
    kes = min(kes, 0.93 * taban)
    Rg = max(R, int(GOLGE_UZAK * bh))
    med = np.full((2 * Rg + 1, 2 * Rg + 1), np.nan)
    for dy in range(-Rg, Rg + 1):
        for dx in range(-Rg, Rg + 1):
            if dx * dx + dy * dy > Rg * Rg or (dx == 0 and dy == 0): continue
            P = _kaydir(tohum, dx, dy) & (D >= np.hypot(dx, dy) - 0.75) & kisit
            if P.sum() < 30: continue
            med[Rg + dy, Rg + dx] = np.median(r[P])
    ters = med[::-1, ::-1]
    # her yönde eşik altı (kenar, yumuşatma) YA DA karşı yönünden belirgin etkili (gölge: tek yöne uzanır)
    Kg = (med < kes) | (med < ters - YON_FARK)
    Kg[Rg, Rg] = True
    yy, xx = np.mgrid[-Rg:Rg + 1, -Rg:Rg + 1]
    Kg &= ((yy * yy + xx * xx <= R * R) | (med < ters - YON_FARK))
    R = Rg; K = Kg
    # orijine bağlı bileşen (gürültü kaymaları atılır) + iç boşluklar doldurulur
    n, et = cv2.connectedComponents(K.astype(np.uint8), connectivity=8)
    K = et == et[R, R]
    dolgu = K.astype(np.uint8).copy(); cv2.floodFill(dolgu, None, (0, 0), 2)
    return K | (dolgu == 0)


def emoji_bul(r, m, kisit, satir, bh, K, doygun=None):
    """Emoji = satır hizasında, satır boyunda, neredeyse tamamen OPAK (oynamayan) kare. Satır boyunca kayan
    pencereyle aranır; yazıya (ya da bulunmuş emojiye) bitişik olanlar zincirleme alınır."""
    opak = (r < OPAK) & kisit
    ek = np.zeros(m.shape, bool)
    s = int(0.85 * bh); adim = max(2, bh // 8)       # emoji ≈ yazı boyu; satır kutusu (bh) biraz daha yüksek
    for y0, y1 in satir:
        yc = (y0 + y1) // 2; a0, a1 = max(0, yc - s // 2), min(m.shape[0], yc + s // 2)
        if a1 - a0 < s // 2: continue
        bulunan = []
        for x in range(0, m.shape[1] - s, adim):
            p = opak[a0:a1, x:x + s]
            if p.sum() < 0.2 * s * s: continue
            # harf değil emoji: opak piksellerin belirgin kısmı RENKLİ (harfler beyaz + siyah kenar)
            if doygun is not None and doygun[a0:a1, x:x + s][p].mean() < 0.25: continue
            # emoji kompakt ve içi dolu: opak piksellerin dış hattı pencerenin ≥ %30'u ve hattın ≥ %60'ı opak
            # (hareketsiz zemindeki dağınık opak noktalar geniş ama seyrek bir hat verir)
            alan = cv2.contourArea(cv2.convexHull(np.argwhere(p)[:, ::-1].astype(np.int32)))
            if alan >= 0.3 * s * s and p.sum() >= 0.6 * alan: bulunan.append(x)
        # zincir: yazı maskesine ya da eklenmiş emojiye en fazla yarım satır uzak olanlar
        tamam = m.copy()
        degisti = True
        while degisti:
            degisti = False
            yakin = cv2.dilate(tamam.astype(np.uint8), np.ones((1, bh | 1), np.uint8)) > 0
            for x in list(bulunan):
                if yakin[a0:a1, x:x + s].any():
                    kare = np.zeros(m.shape, bool); kare[a0:a1, x:x + s] = opak[a0:a1, x:x + s]
                    # karenin opak kısmının dışbükey zarfı: emojinin iç beyazları/çizgileri dahil
                    pts = np.argwhere(kare)[:, ::-1].astype(np.int32)
                    z = np.zeros(m.shape, np.uint8)
                    if len(pts) >= 3: cv2.fillConvexPoly(z, cv2.convexHull(pts), 1)
                    tamam |= z.astype(bool); ek |= z.astype(bool); bulunan.remove(x); degisti = True
    return cv2.dilate(ek.astype(np.uint8), K.astype(np.uint8)) > 0


def golge_bul(tohum, m, medyan, kisit, bh):
    """Gölge = harfin kaydırılıp bulanıklaştırılmış koyu kopyası. Ortanca karedeki koyulaşmayı (yerel arka plana
    göre) bu modelle eşleştirir; iyi oturursa modelin gözle seçilir kısmını (alfa > %3) döner."""
    if medyan is None: return None, None
    gri = cv2.cvtColor(np.clip(medyan, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
    dis = (cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)) == 0)
    halka = dis & (cv2.dilate(m.astype(np.uint8), np.ones((int(0.6 * bh) | 1,) * 2, np.uint8)) > 0) & kisit
    if halka.sum() < 200: return None, None
    # yerel arka plan: yazıdan uzak piksellerden normalize bulanıklaştırma
    uzak = (cv2.dilate(m.astype(np.uint8), np.ones((int(0.8 * bh) | 1,) * 2, np.uint8)) == 0).astype(np.float32)
    s = max(3.0, bh / 2)
    B = cv2.GaussianBlur(gri * uzak, (0, 0), s) / np.maximum(cv2.GaussianBlur(uzak, (0, 0), s), 1e-3)
    d = np.clip(1 - gri / np.maximum(B, 1), 0, 1)                   # koyulaşma oranı ≈ gölge alfası
    dv = d[halka]
    if dv.std() < 0.01: return None, None
    R = max(3, int(0.15 * bh))       # gerçek gölgeler yakındır; uzak eşleşme arka plan dokusudur
    skor = {}
    for sig in (1.0, 2.0, 3.5, 5.0):
        for dy in range(1, R + 1):           # yazı gölgesi aşağı düşer (ışık yukarıdan)
            for dx in range(-R, R + 1):
                A = cv2.GaussianBlur(_kaydir(tohum, dx, dy).astype(np.float32), (0, 0), sig)
                av = A[halka]
                if av.std() < 1e-3: continue
                c = float((av * dv).sum() / max(1e-6, (av ** 2).sum()))
                skor[(dx, dy, sig)] = (float(np.corrcoef(av, dv)[0, 1]), c)
    if not skor: return None, None
    (dx, dy, sig), (r, c) = max(skor.items(), key=lambda kv: kv[1][0])
    # gerçek gölge yönlüdür: ters yöndeki aynı model belirgin kötü uyar (simetrik hale/ışıma ya da arka plan değil)
    At = cv2.GaussianBlur(_kaydir(tohum, -dx, -dy).astype(np.float32), (0, 0), sig)[halka]
    r_ters = float(np.corrcoef(At, dv)[0, 1]) if At.std() > 1e-3 else 0.0
    if os.environ.get("MASKE_IZ"): print(f"  gölge aday ({dx},{dy}) σ{sig} uyum {r:.3f} ters {r_ters:.3f} koyuluk {c:.2f}")
    # gerçek gölgeler yakın (≤ satırın %15i) ve belirgin koyudur; uzak/soluk eşleşme arka plan dokusudur
    if c > 1.0: return None, None          # alfa 1'i aşamaz: koyulaşmayı gölge değil arka plan yapıyor
    if np.hypot(dx, dy) < 2 or r < 0.08 or r - r_ters < 0.06 or c < 0.2: return None, None
    A = cv2.GaussianBlur(_kaydir(tohum, dx, dy).astype(np.float32), (0, 0), sig)
    return (c * A > 0.03) & kisit, f"({dx},{dy}) σ{sig} koyuluk {c:.2f} uyum {r:.2f}"


def hassas(ornk, tohum, kisit, satir, W, temiz=None, medyan=None, gec_beyaz=None):
    """ornk: N×h×W×3 yazılı örnek kareler (bant), tohum: sabit beyaz harf pikselleri (bool),
    kisit: OCR çevresi (bool), satir: [(y0, y1)], temiz: yazısız komşu kare (bant) ya da None.
    Dönüş: (uint8 maske 0/255, yöntem) — maske None ise çağıran eski maskeye düşmeli."""
    bh = int(np.median([b - a for a, b in satir]))
    tohum = tohum & kisit
    if tohum.sum() < 50: return None, None
    # hız: yalnız OCR çevresinin (+ yerel arka plan payı) dikdörtgeni işlenir
    ys, xs = np.nonzero(kisit); p = 2 * bh
    a0, a1, b0, b1 = max(0, ys.min() - p), min(kisit.shape[0], ys.max() + p + 1), max(0, xs.min() - p), min(kisit.shape[1], xs.max() + p + 1)
    tam = np.zeros(kisit.shape, np.uint8)
    kes = lambda x: None if x is None else x[a0:a1, b0:b1]
    m, yontem = _hassas_kirpik(ornk[:, a0:a1, b0:b1], tohum[a0:a1, b0:b1], kisit[a0:a1, b0:b1], bh, kes(temiz), kes(medyan),
                               [(y0 - a0, y1 - a0) for y0, y1 in satir], kes(gec_beyaz))
    if m is None: return None, None
    tam[a0:a1, b0:b1] = m
    return tam, yontem


def _hassas_kirpik(ornk, tohum, kisit, bh, temiz, medyan, satir_kirpik, gec_beyaz=None):
    r, r_opak, kes, yontem = _etki(ornk.astype(np.float32), tohum, kisit, bh, temiz, medyan)
    if r is None: return None, None
    etki = r < (ETKI if yontem.startswith("oynaklik") else 0.5)
    K = cekirdek(tohum, r, kes, kisit, bh)
    m = cv2.dilate(tohum.astype(np.uint8), K.astype(np.uint8)) > 0
    doygun = None
    if medyan is not None:
        hsv = cv2.cvtColor(np.clip(medyan, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV)
        doygun = (hsv[..., 1] > 90) & (hsv[..., 2] > 60)
    m |= emoji_bul(r_opak, m, kisit, satir_kirpik, bh, K, doygun)
    if gec_beyaz is not None:
        # sonradan beliren harfler: harf boyunda beyaz parçalar (zemindeki tek tük beyaz nokta değil)
        gb = (gec_beyaz & kisit & ~tohum).astype(np.uint8)
        n, et, st, _ = cv2.connectedComponentsWithStats(gb, connectivity=8)
        harf = np.isin(et, [i for i in range(1, n) if st[i][4] >= 0.01 * bh * bh and st[i][3] <= 1.3 * bh])
        if harf.any(): m |= cv2.dilate(harf.astype(np.uint8), K.astype(np.uint8)) > 0
    golge, gbilgi = golge_bul(tohum, m, medyan, kisit, bh)
    if golge is not None: m |= golge
    # kenar yumuşatması: 1 px (çekirdek zaten ölçülmüş etkiyi kapsar)
    m = cv2.dilate(m.astype(np.uint8) * 255, np.ones((3, 3), np.uint8))
    return m, f"{yontem}, çekirdek {int(K.sum())} kayma" + (f", gölge {gbilgi}" if gbilgi else "")
