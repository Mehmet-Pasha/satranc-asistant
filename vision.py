# -*- coding: utf-8 -*-
"""Tahta görüntüsünden taş tanıma — numpy tabanlı imza eşleme.

Çalışma mantığı:
  1) Kullanıcı tahtanın ekran dikdörtgenini seçer (kalibrasyon).
  2) Oyun başlangıç dizilimindeyken "Referans Al" denir; her taşın
     arka-plandan-farklılık imzası (|piksel - zemin|) şablon olarak kaydedilir.
  3) Oyun sırasında her kare aynı şekilde imzalanır ve taş şablonlarıyla
     karşılaştırılır. İmza zemin renginden bağımsız olduğu için açık/koyu
     kare farkı sorun olmaz.
"""

import numpy as np

from boardgeom import FILES, RANKS, start_placement

INSET = 0.10         # kare kırpımında kenarlardan içeri girme oranı
PIECE_MIN = 45       # taş pikseli sayılabilmesi için zemin farkı eşiği


def grab_screen():
    """Birincil monitörün BGR görüntüsünü numpy olarak döndürür."""
    import mss
    with mss.mss() as s:
        raw = s.grab(s.monitors[1])
        arr = np.asarray(raw)[:, :, :3].astype(np.uint8)  # BGRA -> BGR
        return np.ascontiguousarray(arr)


def square_crops(img, rect):
    """rect=(x,y,w,h) ekran görüntüsünden 64 kare kırpımı: {kare: dizi}."""
    x, y, w, h = rect
    out = {}
    for r in range(8):
        for c in range(8):
            x0 = int(round(x + c * w / 8.0))
            y0 = int(round(y + r * h / 8.0))
            x1 = int(round(x + (c + 1) * w / 8.0))
            y1 = int(round(y + (r + 1) * h / 8.0))
            ix = max(1, int((x1 - x0) * INSET))
            iy = max(1, int((y1 - y0) * INSET))
            out[FILES[c] + RANKS[r]] = img[y0 + iy:y1 - iy, x0 + ix:x1 - ix]
    return out


def sig_from_crop(crop):
    """(imza HxW float, taş rengi BGR ort., enerji) döndürür."""
    a = crop.astype(np.float32)
    m = max(2, min(a.shape[0], a.shape[1]) // 16)
    corners = np.concatenate([
        a[:m, :m].reshape(-1, 3), a[:m, -m:].reshape(-1, 3),
        a[-m:, :m].reshape(-1, 3), a[-m:, -m:].reshape(-1, 3),
    ])
    bg = np.median(corners, axis=0)
    d = np.abs(a - bg[None, None, :]).sum(axis=2)
    mask = d > PIECE_MIN
    color = a[mask].mean(axis=0) if int(mask.sum()) > 30 else bg
    return d, tuple(float(v) for v in color), float(d.mean())


def extract_reference(img, rect):
    """Başlangıç dizilimi görüntüsünden şablonlar: {taş: [(imza, renk), ...]}"""
    crops = square_crops(img, rect)
    tpls = {}
    for sq, piece in start_placement().items():
        sig, col, _ = sig_from_crop(crops[sq])
        tpls.setdefault(piece, []).append((sig, col))
    return tpls


def _sig_diff(a, b):
    if a.shape != b.shape:
        return 1e9
    an = a / (a.max() + 1e-6)
    bn = b / (b.max() + 1e-6)
    return float(np.abs(an - bn).mean() * 100.0)


def _color_diff(c1, c2):
    return float(np.abs(np.array(c1) - np.array(c2)).mean())


def recognize(img, rect, thresh, tpls):
    """(yerleşim dict | None, hata | None) döndürür."""
    placement = {}
    crops = square_crops(img, rect)
    for sq, crop in crops.items():
        sig, col, en = sig_from_crop(crop)
        # Boş kare testi enerji ortalamasıyla değil, taş-gücü piksel varlığıyla
        # yapılır: ortalamalı eşik ekransal gürültü/AA'da sahte-dolu üretir.
        if not (sig > PIECE_MIN).any():
            continue  # boş kare
        best_piece, best_score = None, 1e9
        for piece, lst in tpls.items():
            for tsig, tcol in lst:
                s = _sig_diff(sig, tsig) + 0.35 * _color_diff(col, tcol)
                if s < best_score:
                    best_score, best_piece = s, piece
        if best_piece is None or best_score > thresh:
            return None, sq + " tanınamadı (skor %.1f)" % best_score
        placement[sq] = best_piece
    return placement, None


# ---- profil kayıt / yükleme ----

def save_profile(path, tpls, rect):
    arrs, meta = {}, []
    for piece, lst in tpls.items():
        meta.append("%s:%d" % (piece, len(lst)))
        for i, (sig, col) in enumerate(lst):
            arrs["sig_%s_%d" % (piece, i)] = sig
            arrs["col_%s_%d" % (piece, i)] = np.array(col, dtype=np.float32)
    arrs["rect"] = np.array(rect, dtype=np.float64)
    arrs["meta"] = np.array(meta)
    np.savez_compressed(path, **arrs)


def load_profile(path):
    z = np.load(path, allow_pickle=False)
    meta = [m.decode() for m in z["meta"]]
    tpls = {}
    for entry in meta:
        piece, n = entry.split(":")
        lst = []
        for i in range(int(n)):
            lst.append((z["sig_%s_%d" % (piece, i)],
                        tuple(float(v) for v in z["col_%s_%d" % (piece, i)])))
        tpls[piece] = lst
    rect = tuple(int(v) for v in z["rect"])
    return tpls, rect