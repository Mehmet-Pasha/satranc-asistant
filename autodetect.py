# -*- coding: utf-8 -*-
"""Ekran görüntüsünden satranç tahtasını otomatik bulma.

Yaklaşım:
  1) Ekranın baskın (arka plan) renginden farklı olan bölgeleri ayır.
  2) İnce çizgi/gürültüyü (metin, ikon) komşuluk filtresiyle temizle;
     geriye sağlam bloklar kalır (tahta, oyuncu kartları...).
  3) Blokların bbox'larından kare adaylar çıkar.
  4) Adayın 7 iç kılavuz çizgisini kenar profilinden fit ederek kutuyu
     tam ızgaraya oturt (snap), sonra 8x8 damalı doğrulamayla puanla:
     komşu kareler farklı, çapraz komşular aynı renk olmalı.

Düz renkli (tek renk kareler) temalarda çalışır; doku/foto temalarda
elle seçim gerekir. Tipik koşu süresi 2-6 saniyedir.
"""

import numpy as np
from collections import deque

BG_SUM_DIFF = 30   # arka plan renginden kanal-farkları toplamı eşiği
SOLID_KEEP = 0.55  # komşuluğunun bu kadarı ön plan olan piksel kalır
NEIGH = 25         # komşuluk penceresi (küçük ölçek pikseli)
MIN_SIDE = 96      # tahtadan küçük kutu aday olamaz (küçük ölçek)
MIN_ORTH = 14.0    # komşu kare ort. renk farkı eşiği
MIN_SCORE = 12.0   # orth - diag skor eşiği


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


def detect_board(img):
    """(x, y, w, h) fiziksel piksel kutusu döndürür; bulamazsa None."""
    H, W = img.shape[:2]
    scale = 1.0
    small = img
    if max(H, W) > 1280:
        stride = int(np.ceil(max(H, W) / 1280.0))
        scale = 1.0 / stride
        small = np.asarray(img[::stride, ::stride], dtype=img.dtype)
    Ls = _luma(small)
    fgs = _fg_mask(small)
    solids = _box_frac(fgs, NEIGH) >= SOLID_KEEP

    best = None
    for bx0, by0, bw, bh, _area in _components(solids, MIN_SIDE * MIN_SIDE)[:3]:
        side = int(min(bw, bh))
        if side < MIN_SIDE:
            continue
        x = bx0 + max(0, (bw - side) // 2)
        y = by0 + max(0, (bh - side) // 2)
        snap = _snap_grid(Ls, x, y, side)
        if snap is None:
            sx, sy, ss = float(x), float(y), float(side)
        else:
            sx, sy, ss = snap
        sc = _validate(Ls, sx, sy, ss)
        if sc > 0 and (best is None or sc > best[0]):
            best = (sc, sx, sy, ss)
    if best is None:
        return None

    # fiziksel çözünürlüğe çevir, orada tekrar snap + doğrula
    _, sx, sy, ss = best
    fx, fy, fs = sx / scale, sy / scale, ss / scale
    LF = _luma(img)
    snap = _snap_grid(LF, int(fx) - 2, int(fy) - 2, int(fs) + 4)
    if snap is None:
        snap = (fx, fy, fs)
    fx, fy, fs = snap
    if _validate(LF, fx, fy, fs) < 0:
        return None
    return int(round(fx)), int(round(fy)), int(round(fs)), int(round(fs))