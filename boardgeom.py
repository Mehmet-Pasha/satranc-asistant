# -*- coding: utf-8 -*-
"""Tahta geometrisi ve FEN yardımcıları (saf Python, bağımlılıksız)."""

FILES = "abcdefgh"
RANKS = "87654321"  # satır 0 = 8. rütbe (üst)


def start_placement():
    """Standart başlangıç dizilimi: {kare: 'wK' | 'bP' | ...}"""
    p = {}
    back = "RNBQKBNR"
    for i, f in enumerate(FILES):
        p[f + "1"] = "w" + back[i]
        p[f + "8"] = "b" + back[i]
        p[f + "2"] = "wP"
        p[f + "7"] = "bP"
    return p


def squares_from_rect(x, y, w, h, flip=False):
    """Ekran dikdörtgeninden kare adı -> (merkez cx, cy).
    flip=False: beyaz altta (a1 sol-alt). flip=True: siyah altta."""
    out = {}
    for r in range(8):
        for c in range(8):
            f = FILES[7 - c] if flip else FILES[c]
            rk = RANKS[7 - r] if flip else RANKS[r]
            out[f + rk] = (x + (c + 0.5) * w / 8.0, y + (r + 0.5) * h / 8.0)
    return out


def castling_rights(placement):
    """Taş yerleşiminden rok haklarını tahmin eder (yaklaşık)."""
    rights = ""
    if placement.get("e1") == "wK":
        if placement.get("h1") == "wR":
            rights += "K"
        if placement.get("a1") == "wR":
            rights += "Q"
    if placement.get("e8") == "bK":
        if placement.get("h8") == "bR":
            rights += "k"
        if placement.get("a8") == "bR":
            rights += "q"
    return rights or "-"


def placement_to_fen(placement, side="w"):
    """{kare: taş} -> FEN (yarım/hamle sayacı sabit '0 1')."""
    rows = []
    for r in range(8):
        row = ""
        empty = 0
        for c in range(8):
            sq = FILES[c] + RANKS[r]
            pc = placement.get(sq)
            if pc is None:
                empty += 1
            else:
                if empty:
                    row += str(empty)
                    empty = 0
                row += pc[1].upper() if pc[0] == "w" else pc[1].lower()
        if empty:
            row += str(empty)
        rows.append(row)
    return "/".join(rows) + " " + side + " " + castling_rights(placement) + " - 0 1"


def detect_move(a, b):
    """İki yerleşim arasındaki farkdan (kalkan_kare, gelen_kare) çıkarır.
    Anlaşılmazsa None döner (rok, geç alma vb.)."""
    if a == b:
        return None
    gone = {sq for sq in a if sq not in b}
    came = {sq for sq in b if sq not in a}
    changed = {sq for sq in a if sq in b and a[sq] != b[sq]}
    if len(gone) == 1 and len(came) == 1 and not changed:
        return gone.pop(), came.pop()
    if len(gone) == 1 and not came and len(changed) == 1:
        return gone.pop(), changed.pop()  # yakalama
    if len(gone) == 2 and len(came) == 2:
        kg = [s for s in gone if a[s][1] == "K"]
        kc = [s for s in came if b[s][1] == "K"]
        if kg and kc:
            return kg[0], kc[0]  # rok (şah hareketi)
    return None