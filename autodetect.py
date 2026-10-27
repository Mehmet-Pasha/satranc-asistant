# -*- coding: utf-8 -*-
"""Ekran görüntüsünden satranç tahtasını otomatik bulma — çok stratejili.

v1'in kök sorunu tek yönteme (renk-blob) bağımlılık ve teşhis yokluğuydu:
  - Tahtaya bitişik düz kutular (oyuncu kartları, yan panel) blob'u tahtayla
    BİRLEŞTİRİYORDU; kutu kare olmadığı için kare tahmini kayıyor, doğrulama
    düşüyordu.
  - Segmentasyon başarısızınca (doku temalar, sıra dışı sayfa renkleri)
    yedek yöntem yoktu.
  - Başarısızlıkta NEDEN başarısız olduğu hiç bildirilmiyordu.

v2 stratejiler:
  A) Blok stratejisi: blob bbox'ı İÇİNDE kaba damalı tarama yapılır; tahtanın
     kutu içinde nerede olduğu tahmin edilmez, ölçülür (birleşik kart/panel
     durumunu çözer).
  B) Serbest tarama: segmentasyondan bağımsız — integral imajla tüm ekranda
     çok ölçekli 8x8 damalı yapı taraması (doku temalara da dayanıklı).

Her aday _snap_grid (alt-piksel ızgara oturtma) + _validate (damalı skor)
ile doğrulanır; en yüksek skor kazanır. detect_board_ex() teşhis bilgisi
döndürür — başarısızlıkta en iyi adaylar ve neden raporlanır.
"""

import numpy as np
from collections import deque

BG_SUM_DIFF = 30   # arka plan renginden kanal-farkları toplamı eşiği
SOLID_KEEP = 0.55  # komşuluğunun bu kadarı ön plan olan piksel kalır
NEIGH = 25         # komşuluk penceresi (küçük ölçek pikseli)
MIN_SIDE = 96      # tahtadan küçük kutu aday olamaz (küçük ölçek)
MIN_ORTH = 14.0    # komşu kare ort. renk farkı eşiği
MIN_SCORE = 12.0   # orth - diag skor eşiği
COARSE_MIN = 6.0   # kaba taramada aday sayma eşiği (ince doğrulama sonra)
SCAN_TOPK = 8      # serbest taramadan incelenecek aday sayısı
BLOB_TOP = 3       # incelenecek en büyük blob sayısı
SIDE_VARIANTS = (0.90, 0.95, 1.0, 1.05, 1.10)  # ölçek merdiveni boşluk kapatma


def _luma(img):
    """BGR görüntünün luminance'ı (float32)."""
    a = img.astype(np.float32)
    return 0.114 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.299 * a[:, :, 2]


def _fg_mask(img):
    """Arka planın baskın renginden (kanal-toplam uzaklık) farklı pikseller."""
    a = img.astype(np.float32)
    bg = np.median(a.reshape(-1, 3), axis=0)
    return np.abs(a - bg[None, None, :]).sum(axis=2) > BG_SUM_DIFF


def _box_frac(mask, k):
    """Her pikselin k×k komşuluğundaki ön plan oranı (integral imajıyla)."""
    m = mask.astype(np.float32)
    ii = np.pad(np.cumsum(np.cumsum(m, axis=0), axis=1), ((1, 0), (1, 0)))
    h, w = mask.shape
    r = k // 2
    ys = np.arange(h)
    xs = np.arange(w)
    y0 = np.clip(ys - r, 0, h)
    y1 = np.clip(ys + r + 1, 0, h)
    x0 = np.clip(xs - r, 0, w)
    x1 = np.clip(xs + r + 1, 0, w)
    total = ii[np.ix_(y1, x1)] - ii[np.ix_(y0, x1)] \
        - ii[np.ix_(y1, x0)] + ii[np.ix_(y0, x0)]
    area = np.minimum(np.minimum(y1, h) - y0, 2 * r + 1)[:, None] * \
        np.minimum(np.minimum(x1, w) - x0, 2 * r + 1)[None, :]
    return total / np.maximum(area, 1)


def _components(mask, min_area):
    """Sağlam maskedeki büyük bileşenlerin bbox'ları:
    [(x, y, w, h, alan), ...] alan sırasına göre."""
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    out = []
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if seen[sy, sx]:
            continue
        q = deque([(sy, sx)])
        seen[sy, sx] = True
        miny = maxy = sy
        minx = maxx = sx
        area = 0
        while q:
            y, x = q.popleft()
            area += 1
            if y < miny:
                miny = y
            if y > maxy:
                maxy = y
            if x < minx:
                minx = x
            if x > maxx:
                maxx = x
            if y + 1 < h and mask[y + 1, x] and not seen[y + 1, x]:
                seen[y + 1, x] = True
                q.append((y + 1, x))
            if y and mask[y - 1, x] and not seen[y - 1, x]:
                seen[y - 1, x] = True
                q.append((y - 1, x))
            if x + 1 < w and mask[y, x + 1] and not seen[y, x + 1]:
                seen[y, x + 1] = True
                q.append((y, x + 1))
            if x and mask[y, x - 1] and not seen[y, x - 1]:
                seen[y, x - 1] = True
                q.append((y, x - 1))
        if area >= min_area:
            out.append((minx, miny, maxx - minx + 1, maxy - miny + 1, area))
    out.sort(key=lambda b: -b[4])
    return out


def cell_means(luma, x, y, side):
    """side×side kutuyu 8x8 hücre ortalamalarına indirger (float)."""
    n = side / 8.0
    cm = np.zeros((8, 8), dtype=np.float32)
    for r in range(8):
        y0 = int(round(y + r * n))
        y1 = int(round(y + (r + 1) * n))
        for c in range(8):
            x0 = int(round(x + c * n))
            x1 = int(round(x + (c + 1) * n))
            cm[r, c] = luma[y0:y1, x0:x1].mean()
    return cm


def checker_score(luma, x, y, side):
    """Damalı doğrulama skoru: komşu fark ort. - çapraz fark ort."""
    cm = cell_means(luma, x, y, side)
    orth, diag = [], []
    for r in range(8):
        for c in range(8):
            if c < 7:
                orth.append(abs(cm[r, c] - cm[r, c + 1]))
            if r < 7:
                orth.append(abs(cm[r, c] - cm[r + 1, c]))
            if c < 7 and r < 7:
                diag.append(abs(cm[r, c] - cm[r + 1, c + 1]))
            if c > 0 and r < 7:
                diag.append(abs(cm[r, c] - cm[r + 1, c - 1]))
    return float(np.mean(orth) - np.mean(diag))


def _snap_grid(luma, x, y, side):
    """Kutunun 7 iç kılavuz çizgisini fit ederek tam ızgaraya oturtur.
    Döner: (x, y, side) float veya None (fit güvenilir değilse)."""
    crop = luma[y:y + side, x:x + side]
    if crop.shape[0] < side - 1 or crop.shape[1] < side - 1:
        return None
    cell0 = side / 8.0
    fits = []
    for axis in (0, 1):
        if axis == 0:
            prof = np.abs(np.diff(crop, axis=1)).mean(axis=0)
        else:
            prof = np.abs(np.diff(crop, axis=0)).mean(axis=1)
        ks, ps = [], []
        for k in range(1, 8):
            lo = max(1, int(k * cell0 - 0.3 * cell0))
            hi = min(len(prof) - 1, int(k * cell0 + 0.3 * cell0))
            if hi <= lo:
                continue
            pk = lo + int(np.argmax(prof[lo:hi + 1]))
            ks.append(k)
            ps.append(pk)
        if len(ks) < 5:
            return None
        ks = np.array(ks, dtype=np.float32)
        ps = np.array(ps, dtype=np.float32)
        a, b = np.polyfit(ks, ps, 1)
        resid = float(np.abs(ps - (b + a * ks)).max())
        if a < cell0 * 0.7 or a > cell0 * 1.3 or resid > 0.25 * cell0:
            return None
        fits.append((float(a), float(b)))
    (cellx, lx), (celly, ly) = fits
    return (x + lx, y + ly, 8.0 * (cellx + celly) / 2.0)


def _validate(luma, x, y, side):
    """Damalı skor + kareler-arası kontrast şartı."""
    if side < MIN_SIDE * 0.5 or x < 0 or y < 0 \
            or x + side > luma.shape[1] or y + side > luma.shape[0]:
        return -1.0
    s = checker_score(luma, x, y, side)
    if s < MIN_SCORE:
        return -1.0
    cm = cell_means(luma, x, y, side)
    orth = float(np.mean([abs(cm[r, c] - cm[r, c + 1]) for r in range(8)
                          for c in range(7)]))
    if orth < MIN_ORTH:
        return -1.0
    return s


def _integral(L):
    """Luminance integral imajı: ii[y, x] = L[:y, :x] toplamı."""
    return np.pad(np.cumsum(np.cumsum(L.astype(np.float64), axis=0), axis=1),
                  ((1, 0), (1, 0)))


def _scan_region(L, ii, x0, y0, x1, y1, sides, stride_frac=0.5, topk=6):
    """Bölge [x0:x1, y0:y1] içinde çok konumlu damalı aday taraması.

    Konum adımı hücre/2: yarım hücreden fazla kayan konum hücre ort.-
    lamalarını bulanıklaştırıp skoru sıfırlar; adım hücreden küçük olmalı.
    Döner: [(skor, x, y, s), ...] skor sıralı, en fazla topk aday.
    """
    H, W = L.shape
    out = []
    for s in sides:
        s = int(round(s))
        if s < 64 or s > min(H, W):
            continue
        cell = s / 8.0
        bx0, by0 = max(0, int(x0)), max(0, int(y0))
        bx1, by1 = min(W, int(x1) - s + 1), min(H, int(y1) - s + 1)
        if bx1 - bx0 < 1 or by1 - by0 < 1:
            continue
        xs = np.rint(np.arange(bx0, bx1, cell * stride_frac)).astype(np.int64)
        ys = np.rint(np.arange(by0, by1, cell * stride_frac)).astype(np.int64)
        if not len(xs) or not len(ys):
            continue
        offs = np.rint(np.arange(9) * cell).astype(np.int64)
        Yc = np.clip(ys[:, None] + offs[None, :], 0, H)    # (Ny, 9)
        Xc = np.clip(xs[:, None] + offs[None, :], 0, W)    # (Nx, 9)
        G = ii[Yc[:, :, None, None], Xc[None, None, :, :]]  # (Ny, 9ky, Nx, 9kx)
        # hücre toplamları → (Ny, 8r, Nx, 8c)
        S = (G[:, 1:, :, 1:] - G[:, :-1, :, 1:]
             - G[:, 1:, :, :-1] + G[:, :-1, :, :-1])
        ay = np.diff(offs).astype(np.float64)
        area = ay[:, None] * ay[None, :]
        cm = S / area[None, :, None, :]
        a = np.abs(cm[:, :-1, :, :] - cm[:, 1:, :, :]).sum(axis=(1, 3))  # dikey
        b = np.abs(cm[:, :, :, :-1] - cm[:, :, :, 1:]).sum(axis=(1, 3))  # yatay
        orth = (a + b) / 112.0
        d1 = np.abs(cm[:, :-1, :, :-1] - cm[:, 1:, :, 1:]).sum(axis=(1, 3))
        d2 = np.abs(cm[:, :-1, :, 1:] - cm[:, 1:, :, :-1]).sum(axis=(1, 3))
        diag = (d1 + d2) / 98.0
        score = orth - diag
        idx = np.argwhere(score >= COARSE_MIN)
        if len(idx):
            sc = score[idx[:, 0], idx[:, 1]]
            order = np.argsort(-sc)[:topk]
            for o in order:
                iy, ix = int(idx[o, 0]), int(idx[o, 1])
                out.append((float(sc[o]), int(xs[ix]), int(ys[iy]), s))
    out.sort(key=lambda t: -t[0])
    return out[:topk]


def _try(L, x, y, side):
    """Adayı snap + doğrula. Döner: (skor, sx, sy, ss) veya None."""
    snap = _snap_grid(L, int(x) - 2, int(y) - 2, int(side) + 4)
    if snap is None:
        snap = (float(x), float(y), float(side))
    sc = _validate(L, snap[0], snap[1], snap[2])
    if sc < 0:
        return None
    return (sc, snap[0], snap[1], snap[2])


def _refine(L, coarse, strategy):
    """Kaba adayları ölçek varyantlarıyla ince doğrula.
    Döner: [(skor, x, y, s, strateji), ...] skor sıralı."""
    out = []
    for sc, x, y, s in coarse:
        for f in SIDE_VARIANTS:
            r = _try(L, x, y, s * f)
            if r:
                out.append((r[0], r[1], r[2], r[3], strategy))
    out.sort(key=lambda t: -t[0])
    return out


def detect_board_ex(img):
    """(rect|None, diag) döndürür. rect=(x, y, w, h) fiziksel piksel.
    diag: {'image', 'strategy', 'score', 'reason', 'candidates', 'blobs'}"""
    H, W = img.shape[:2]
    diag = {"image": "%dx%d" % (W, H), "strategy": None, "score": None,
            "reason": "", "candidates": [], "blobs": 0}
    scale = 1.0
    small = img
    if max(H, W) > 1280:
        stride = int(np.ceil(max(H, W) / 1280.0))
        scale = 1.0 / stride
        small = np.asarray(img[::stride, ::stride], dtype=img.dtype)
    Ls = _luma(small)
    hs, ws = Ls.shape

    # --- Strateji A: blob içinde mini tarama (birleşik kart/panel dayanıklı)
    refined = []
    try:
        fgs = _fg_mask(small)
        solids = _box_frac(fgs, NEIGH) >= SOLID_KEEP
        blobs = _components(solids, MIN_SIDE * MIN_SIDE)[:BLOB_TOP]
        diag["blobs"] = len(blobs)
        for bx0, by0, bw, bh, _area in blobs:
            smin = 0.55 * min(bw, bh)
            sides = np.linspace(smin, 1.05 * min(bw, bh), 7).tolist()
            sides += [min(bw, bh), max(bw, bh)]
            coarse = _scan_region(Ls, _integral(Ls), bx0, by0,
                                  bx0 + bw, by0 + bh, sides,
                                  stride_frac=0.5, topk=6)
            # kenar-hizalı adaylar: birleşik kart/panelde tahta kutunun bir
            # kenarına yaslanır (üst/alt/sol/sağ + ortalı) — mini taramanın
            # adım ızgarasına tam gelmeyebilecek hizaları kestirme olarak dene
            for s in (min(bw, bh), max(bw, bh)):
                if s < MIN_SIDE * 0.5 or bx0 + s > ws or by0 + s > hs:
                    continue
                for xx3 in (bx0, bx0 + max(0, (bw - s) // 2), bx0 + bw - s):
                    for yy3 in (by0, by0 + max(0, (bh - s) // 2), by0 + bh - s):
                        coarse.append((float(COARSE_MIN), int(xx3), int(yy3), int(s)))
            coarse.sort(key=lambda t: -t[0])
            refined.extend(_refine(Ls, coarse[:12], "blob"))
    except Exception as e:  # segmentasyon asla tüm aramayı öldürmesin
        diag["reason"] = "blob stratejisi istisna: %s; " % e

    # --- Strateji B: segmentasyondan bağımsız serbest tarama
    smin = max(64.0, MIN_SIDE * 0.5)
    smax = min(hs, ws) * 0.95
    if smax <= smin:
        sides = [float(min(hs, ws))]
    else:
        sides = np.unique(np.geomspace(smin, smax, 20)).astype(float).tolist()
    coarse = _scan_region(Ls, _integral(Ls), 0, 0, ws, hs, sides,
                          stride_frac=0.5, topk=SCAN_TOPK)
    refined.extend(_refine(Ls, coarse, "tarama"))

    refined.sort(key=lambda t: -t[0])
    diag["candidates"] = [
        {"strategy": st, "score": round(sc, 1),
         "rect": [int(round(x / scale)), int(round(y / scale)),
                  int(round(s / scale)), int(round(s / scale))]}
        for sc, x, y, s, st in refined[:5]]
    if not refined:
        diag["reason"] += "damalı aday yok (blob=%d); " % diag["blobs"]
        return None, diag

    sc, sx, sy, ss, st = refined[0]
    if sc < MIN_SCORE:
        diag["reason"] += "en iyi damalı skor %.1f < eşik %.1f (blob=%d); " \
            % (sc, MIN_SCORE, diag["blobs"])
        return None, diag

    # --- fiziksel çözünürlükte son snap + doğrulama
    fx, fy, fs = sx / scale, sy / scale, ss / scale
    LF = _luma(img)
    snap = _snap_grid(LF, int(fx) - 2, int(fy) - 2, int(fs) + 4)
    if snap is not None and _validate(LF, snap[0], snap[1], snap[2]) > 0:
        fx, fy, fs = snap
    if _validate(LF, fx, fy, fs) < 0:
        diag["reason"] += "tam çözünürlük doğrulaması geçmedi (skor %.1f); " \
            % _validate(LF, fx, fy, fs)
        return None, diag
    diag["strategy"] = st
    diag["score"] = round(float(sc), 1)
    return (int(round(fx)), int(round(fy)), int(round(fs)), int(round(fs))), diag


def detect_board(img):
    """(x, y, w, h) fiziksel piksel kutusu döndürür; bulamazsa None."""
    rect, _diag = detect_board_ex(img)
    return rect
