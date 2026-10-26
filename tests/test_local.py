# -*- coding: utf-8 -*-
"""Yerel testler (Windows'a gitmez): geometri/FEN + UCI protokolü + görüntü."""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boardgeom  # noqa: E402


class TestGeom(unittest.TestCase):
    def test_start_placement(self):
        p = boardgeom.start_placement()
        self.assertEqual(p["e1"], "wK")
        self.assertEqual(p["a8"], "bR")
        self.assertEqual(len(p), 32)

    def test_fen_start(self):
        fen = boardgeom.placement_to_fen(boardgeom.start_placement(), "w")
        self.assertEqual(
            fen.split()[0],
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR",
        )
        self.assertTrue(fen.endswith("w KQkq - 0 1"))

    def test_fen_after_e4(self):
        p = boardgeom.start_placement()
        del p["e2"]
        p["e4"] = "wP"
        fen = boardgeom.placement_to_fen(p, "b")
        self.assertEqual(fen.split()[0],
                         "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR")
        self.assertTrue(fen.split()[1] == "b")

    def test_squares_normal(self):
        c = boardgeom.squares_from_rect(0, 0, 800, 800)
        self.assertEqual(c["a1"], (50, 750))
        self.assertEqual(c["h8"], (750, 50))
        self.assertEqual(c["e4"], (450.0, 450.0))

    def test_squares_flip(self):
        c = boardgeom.squares_from_rect(0, 0, 800, 800, flip=True)
        self.assertEqual(c["a1"], (750, 50))   # siyah altta: a1 sağ-üst
        self.assertEqual(c["h8"], (50, 750))

    def test_detect_move(self):
        a = boardgeom.start_placement()
        b = dict(a)
        del b["e2"]
        b["e4"] = "wP"
        self.assertEqual(boardgeom.detect_move(a, b), ("e2", "e4"))

    def test_detect_capture(self):
        a = boardgeom.start_placement()
        del a["e2"]
        a["e4"] = "wP"
        a["d5"] = "bP"
        b = dict(a)
        del b["e4"]
        del b["d5"]
        b["d5"] = "wP"
        self.assertEqual(boardgeom.detect_move(a, b), ("e4", "d5"))

    def test_detect_castling(self):
        a = {"e1": "wK", "h1": "wR", "a2": "wP", "e8": "bK"}
        b = {"g1": "wK", "f1": "wR", "a2": "wP", "e8": "bK"}
        self.assertEqual(boardgeom.detect_move(a, b), ("e1", "g1"))


FAKE_ENGINE = r'''
import sys
for line in sys.stdin:
    line = line.strip()
    if line == "uci":
        print("id name FakeFish"); print("uciok", flush=True)
    elif line == "isready":
        print("readyok", flush=True)
    elif line.startswith("go"):
        print("info depth 12 score cp 85 pv e2e4", flush=True)
        print("bestmove e2e4 ponder e7e5", flush=True)
    elif line == "quit":
        break
'''


class TestEngineUci(unittest.TestCase):
    def test_bestmove(self):
        import tempfile
        fake = os.path.join(tempfile.gettempdir(), "fake_engine.py")
        with open(fake, "w", encoding="utf-8") as f:
            f.write(FAKE_ENGINE)
        from engine import StockfishEngine
        eng = StockfishEngine(sys.executable, args=[fake])
        try:
            best, score = eng.best(
                "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                movetime=300,
            )
            self.assertEqual(best, "e2e4")
            self.assertEqual(score, ("cp", 85))
        finally:
            eng.close()


class TestVisionSynthetic(unittest.TestCase):
    """numpy ile sentetik tahta: referans çıkar -> tanı -> başlangıç FEN'i."""

    def run_test(self):
        import numpy as np
        import vision

        SIZE = 640
        cell = SIZE // 8
        yy, xx = np.mgrid[0:SIZE, 0:SIZE]

        def board_img():
            img = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
            for r in range(8):
                for c in range(8):
                    light = (r + c) % 2 == 1
                    img[r*cell:(r+1)*cell, c*cell:(c+1)*cell] = \
                        (168, 162, 170) if light else (96, 108, 76)  # BGR
            return img

        def draw_disc(img, cx, cy, rad, color, hollow=False):
            d2 = (xx - cx) ** 2 + (yy - cy) ** 2
            if hollow:
                m = (d2 < rad*rad) & (d2 > (rad*0.55)**2)
            else:
                m = d2 < rad*rad
            img[m] = color

        def draw_square(img, cx, cy, half, color):
            img[cy-half:cy+half, cx-half:cx+half] = color

        def draw_cross(img, cx, cy, half, color):
            img[cy-3:cy+3, cx-half:cx+half] = color
            img[cy-half:cy+half, cx-3:cx+3] = color

        SHAPE = {  # taş türü -> çizim fonksiyonu (radyan/half px)
            "K": lambda im, cx, cy, col: draw_disc(im, cx, cy, 24, col),
            "Q": lambda im, cx, cy, col: (draw_disc(im, cx, cy, 20, col),
                                          draw_disc(im, cx, cy, 26, col, hollow=True)),
            "R": lambda im, cx, cy, col: draw_square(im, cx, cy, 19, col),
            "N": lambda im, cx, cy, col: draw_cross(im, cx, cy, 22, col),
            "B": lambda im, cx, cy, col: draw_disc(im, cx, cy, 22, col, hollow=True),
            "P": lambda im, cx, cy, col: draw_disc(im, cx, cy, 13, col),
        }
        COL = {"w": (232, 232, 224), "b": (38, 38, 42)}

        img = board_img()
        for sq, piece in boardgeom.start_placement().items():
            c = boardgeom.FILES.index(sq[0])
            r = boardgeom.RANKS.index(sq[1])
            cx, cy = c*cell + cell//2, r*cell + cell//2
            SHAPE[piece[1]](img, cx, cy, COL[piece[0]])

        rect = (0, 0, SIZE, SIZE)
        tpls = vision.extract_reference(img, rect)

        # bozulma: her kareye azıcık gürültü ekle ( gerçek ekran AA benzeri )
        rng = np.random.default_rng(7)
        noisy = img.astype(np.int16) + rng.integers(-6, 7, img.shape)
        noisy = np.clip(noisy, 0, 255).astype(np.uint8)

        placement, err = vision.recognize(noisy, rect, 26.0, tpls)
        self.assertIsNone(err)
        self.assertEqual(placement, boardgeom.start_placement())

        # hamle sonrası: e2 -> e4
        game = boardgeom.start_placement()
        del game["e2"]
        game["e4"] = "wP"
        img2 = board_img()
        for sq, piece in game.items():
            c = boardgeom.FILES.index(sq[0])
            r = boardgeom.RANKS.index(sq[1])
            cx, cy = c*cell + cell//2, r*cell + cell//2
            SHAPE[piece[1]](img2, cx, cy, COL[piece[0]])
        p2, err2 = vision.recognize(img2, rect, 26.0, tpls)
        self.assertIsNone(err2)
        self.assertEqual(p2, game)

    def run_if_numpy(self):
        try:
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("numpy yok")
        self.run_test()

    def test_vision(self):
        self.run_if_numpy()


class TestImports(unittest.TestCase):
    """main.py'de kullanılan her Q* adı mutlaka import edilmiş olmalı
    (PyQt6 uygulaması burada çalıştırılamaz; AST ile statik denetler)."""

    def test_qt_names_imported(self):
        import ast
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(root, "main.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    imported.add(a.asname or a.name)
        used = {n.id for n in ast.walk(tree)
                if isinstance(n, ast.Name) and n.id.startswith("Q")}
        self.assertEqual(used - imported, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)