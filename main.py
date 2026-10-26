# -*- coding: utf-8 -*-
"""Satranç Antrenman Asistanı — chess.com / Lichess bot & antrenman oyunları için.

Modlar:
  - İpucu (F10)        : bir basışta tek en iyi hamleyi okla gösterir.
  - Canlı ok (F11)     : açık olduğu sürece en iyi hamleyi sürekli oklar.
  - Otomatik (F12)     : motor hamleleri kendi oynatır (tıkla-tıkla).

Kullanım: YALNIZCA bilgisayara (bot) karşı oyunlar ve antrenman için.
"""
import ctypes
import json
import math
import os
import sys
import threading
import time


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP = app_dir()
sys.path.insert(0, APP)

import boardgeom
import vision
from engine import StockfishEngine

from PyQt6.QtCore import QObject, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QTextEdit, QVBoxLayout, QWidget,
)

STATE = {
    "rect": None,            # [x, y, w, h]
    "flip": False,           # siyah altta oynuyorsan işaretle
    "auto_queen": True,
    "movetime": 400,
    "thresh": 26.0,
    "side": "w",             # sıra takibi (otomatik güncellenir)
    "auto_side": "w",        # oto modun oynayacağı taraf
    "only_my_turn": True,    # okları sadece kendi sıramda göster
    "templates": {},
    "profile": "",
    "engine_path": "stockfish/stockfish.exe",
    "live": False,
    "auto": False,
    "busy_hint": False,
    "last_placement": None,
}
LOCK = threading.Lock()
CFG_PATH = os.path.join(APP, "config.json")
PROFILE_DIR = os.path.join(APP, "profiles")

CFG_KEYS = ["rect", "flip", "auto_queen", "movetime", "thresh", "side",
            "auto_side", "only_my_turn", "engine_path", "profile"]


def load_cfg():
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k in CFG_KEYS:
            if k in data:
                STATE[k] = data[k]
        if STATE["rect"] is not None:
            STATE["rect"] = list(STATE["rect"])
    except Exception:
        pass


def save_cfg():
    try:
        data = {k: STATE[k] for k in CFG_KEYS}
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    except Exception:
        pass


def log(msg):
    HUB.sig_log.emit(str(msg))


# ---------------------------------------------------------------- sinyaller

class Hub(QObject):
    sig_log = pyqtSignal(str)
    sig_arrow = pyqtSignal(list)      # [(from_sq, to_sq), ...]
    sig_clear = pyqtSignal()
    sig_eval = pyqtSignal(str)
    sig_status = pyqtSignal(str)
    sig_rect = pyqtSignal(tuple)      # (x, y, w, h)
    sig_hint = pyqtSignal()
    sig_live = pyqtSignal()
    sig_auto = pyqtSignal()


HUB = Hub()

ENGINE = None
ENG_LOCK = threading.Lock()


def resolve_engine_path():
    raw = (STATE.get("engine_path") or "").strip()
    cands = [raw, os.path.join(APP, raw), os.path.join("stockfish", "stockfish.exe"),
             os.path.join(APP, "stockfish", "stockfish.exe")]
    for p in cands:
        if p and os.path.isfile(p):
            return p
    return None


def get_engine():
    global ENGINE
    with ENG_LOCK:
        if ENGINE is None:
            path = resolve_engine_path()
            if not path:
                log("Stockfish bulunamadı. Motor yolu ayarını kontrol et "
                    "(stockfish klasörünü programın yanına koy).")
                return None
            try:
                ENGINE = StockfishEngine(path)
                log("Motor hazır: " + os.path.basename(path))
            except Exception as e:
                log("Motor başlatılamadı: %s" % e)
                return None
        return ENGINE


def engine_best(fen):
    eng = get_engine()
    if eng is None:
        return None, None
    return eng.best(fen, movetime=int(STATE["movetime"]))


def fmt_score(score):
    if not score:
        return "—"
    t, v = score
    if t == "mate":
        return "Mat %d" % abs(v)
    return "%+.2f" % (v / 100.0)


# ---------------------------------------------------------------- tahta okuma

def track_and_fen(placement, verbose=True):
    last = STATE.get("last_placement")
    if last is None:
        STATE["last_placement"] = placement
    elif placement != last:
        mv = boardgeom.detect_move(last, placement)
        STATE["last_placement"] = placement
        if mv and verbose:
            log("Hamle görüldü: " + mv[0] + mv[1])
        STATE["side"] = "b" if STATE["side"] == "w" else "w"
    return boardgeom.placement_to_fen(placement, STATE["side"])


def read_fen(verbose=True):
    rect = STATE.get("rect")
    tpls = STATE.get("templates")
    if not rect or not tpls:
        if verbose:
            log("Önce Kalibrasyon + Referans Al.")
        return None
    img = vision.grab_screen()
    placement, err = vision.recognize(img, rect, float(STATE["thresh"]), tpls)
    if err:
        if verbose:
            log("Tahta okunamadı: " + err)
        return None
    return track_and_fen(placement, verbose)


# ---------------------------------------------------------------- hamle oynatma

def do_move(uci):
    try:
        import pyautogui
    except Exception as e:
        log("pyautogui yok: %s" % e)
        return False
    rect = STATE.get("rect")
    if not rect:
        return False
    centers = boardgeom.squares_from_rect(*rect, STATE["flip"])
    f_sq, t_sq = uci[:2], uci[2:4]
    if f_sq not in centers or t_sq not in centers:
        log("Hamle tahta dışında: " + uci)
        return False
    fx, fy = centers[f_sq]
    tx, ty = centers[t_sq]
    sq_h = rect[3] / 8.0
    pyautogui.FAILSAFE = False
    pyautogui.click(int(fx), int(fy))
    time.sleep(0.18)
    pyautogui.click(int(tx), int(ty))
    if len(uci) == 5 and STATE["auto_queen"]:
        time.sleep(0.5)
        dy = (0.95 * sq_h) if STATE["flip"] else (-0.95 * sq_h)
        pyautogui.click(int(tx), int(ty + dy))
    return True


# ---------------------------------------------------------------- mod işleri

def do_hint():
    if STATE["busy_hint"]:
        return

    def work():
        STATE["busy_hint"] = True
        try:
            fen = read_fen()
            if fen:
                best, score = engine_best(fen)
                if best and len(best) >= 4:
                    HUB.sig_arrow.emit([(best[:2], best[2:4])])
                    HUB.sig_eval.emit(fmt_score(score))
                    HUB.sig_status.emit("İpucu: " + best[:4])
                else:
                    log("Hamle alınamadı (sıra / tahta okunmasını kontrol et).")
        finally:
            STATE["busy_hint"] = False

    threading.Thread(target=work, daemon=True).start()


def live_loop():
    HUB.sig_status.emit("CANLI OK AÇIK")
    while STATE["live"]:
        try:
            fen = read_fen(verbose=False)
            if fen:
                side = fen.split()[1]
                if (not STATE["only_my_turn"]) or side == STATE["auto_side"]:
                    best, score = engine_best(fen)
                    if best and len(best) >= 4:
                        HUB.sig_arrow.emit([(best[:2], best[2:4])])
                        HUB.sig_eval.emit(fmt_score(score))
            time.sleep(1.2)
        except Exception as e:
            log("Canlı ok hata: %s" % e)
            time.sleep(1.0)
    HUB.sig_status.emit("CANLI OK KAPALI")
    HUB.sig_clear.emit()


def auto_loop():
    HUB.sig_status.emit("OTO AÇIK")
    try:
        import pyautogui  # noqa: F401  (varlık kontrolü)
    except Exception as e:
        log("pyautogui yok: %s" % e)
        STATE["auto"] = False
        return
    last_fen = None
    while STATE["auto"]:
        try:
            fen = read_fen(verbose=False)
            if not fen:
                time.sleep(0.5)
                continue
            side = fen.split()[1]
            if side != STATE["auto_side"]:
                time.sleep(0.4)   # rakip (bot) düşünüyor
                continue
            if fen == last_fen:
                time.sleep(0.35)
                continue
            best, score = engine_best(fen)
            if not best or len(best) < 4:
                time.sleep(0.4)
                continue
            HUB.sig_status.emit("Oto: %s  (%s)" % (best[:4], fmt_score(score)))
            ok = do_move(best)
            time.sleep(1.0)
            nf = read_fen(verbose=False)
            last_fen = nf or fen
            if not ok:
                time.sleep(0.6)
        except Exception as e:
            log("Oto hata: %s" % e)
            time.sleep(1.0)
    HUB.sig_status.emit("OTO KAPALI")
    HUB.sig_clear.emit()


def toggle_live():
    STATE["live"] = not STATE["live"]
    if STATE["live"]:
        if not STATE["rect"] or not STATE["templates"]:
            log("Önce Kalibrasyon + Referans Al.")
            STATE["live"] = False
            return
        STATE["auto"] = False
        threading.Thread(target=live_loop, daemon=True).start()
    else:
        HUB.sig_clear.emit()


def toggle_auto():
    STATE["auto"] = not STATE["auto"]
    if STATE["auto"]:
        if not STATE["rect"] or not STATE["templates"]:
            log("Önce Kalibrasyon + Referans Al.")
            STATE["auto"] = False
            return
        STATE["live"] = False
        STATE["last_placement"] = None
        threading.Thread(target=auto_loop, daemon=True).start()
    else:
        HUB.sig_clear.emit()


# ---------------------------------------------------------------- oklar katmanı

class Overlay(QWidget):
    def __init__(self):
        super().__init__()
        self.arrows = []
        self.rect = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        scr = QApplication.primaryScreen().geometry()
        self.setGeometry(scr)
        self.setWindowTitle("oklar")
        self.show()
        HUB.sig_arrow.connect(self.set_arrows)
        HUB.sig_clear.connect(self.clear)
        HUB.sig_rect.connect(self.set_board)

    def set_board(self, rect):
        self.rect = rect
        self.update()

    def set_arrows(self, arrows):
        self.arrows = arrows
        self.update()

    def clear(self):
        self.arrows = []
        self.update()

    def paintEvent(self, ev):
        if not self.rect or not self.arrows:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        centers = boardgeom.squares_from_rect(*self.rect, STATE["flip"])
        sq = min(self.rect[2], self.rect[3]) / 8.0
        gold = QColor(255, 200, 40, 235)
        dark = QColor(25, 18, 0, 230)
        for f_sq, t_sq in self.arrows:
            if f_sq not in centers or t_sq not in centers:
                continue
            x1, y1 = centers[f_sq]
            x2, y2 = centers[t_sq]
            dx, dy = x2 - x1, y2 - y1
            d = math.hypot(dx, dy) or 1.0
            ux, uy = dx / d, dy / d
            sx, sy = x1 + ux * sq * 0.30, y1 + uy * sq * 0.30
            ex, ey = x2 - ux * sq * 0.28, y2 - uy * sq * 0.28
            # koyu kontur + altın gövde
            p.setPen(QPen(dark, sq * 0.22, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(sx, sy), QPointF(ex, ey))
            p.setPen(QPen(gold, sq * 0.13, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(sx, sy), QPointF(ex, ey))
            # ok ucu
            bx, by = ex - ux * sq * 0.34, ey - uy * sq * 0.34
            px, py = -uy, ux
            w = sq * 0.19
            tri = QPolygonF([QPointF(ex, ey),
                             QPointF(bx + px * w, by + py * w),
                             QPointF(bx - px * w, by - py * w)])
            p.setPen(QPen(dark, 2.0))
            p.setBrush(QBrush(gold))
            p.drawPolygon(tri)
        p.end()


class CalibOverlay(QWidget):
    """Tam ekran karartma; kullanıcı tahtanın üzerine dikdörtgen çizer."""
    rectPicked = pyqtSignal(tuple)

    def __init__(self):
        super().__init__()
        self.origin = None
        self.cur = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        scr = QApplication.primaryScreen().geometry()
        self.setGeometry(scr)
        self.show()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 130))
        if self.origin and self.cur:
            x = min(self.origin.x(), self.cur.x())
            y = min(self.origin.y(), self.cur.y())
            w = abs(self.origin.x() - self.cur.x())
            h = abs(self.origin.y() - self.cur.y())
            p.setPen(QPen(QColor(255, 200, 40), 3))
            p.setBrush(QBrush(QColor(255, 200, 40, 40)))
            p.drawRect(x, y, w, h)
        p.setPen(QPen(QColor(255, 255, 255)))
        p.drawText(30, 40, "Tahtanın KÖŞESİNDEN KÖŞESİNE sürükle, bırak. "
                           "İptal: ESC")
        p.end()

    def mousePressEvent(self, ev):
        self.origin = ev.globalPosition().toPoint()
        self.cur = self.origin
        self.update()

    def mouseMoveEvent(self, ev):
        if self.origin:
            self.cur = ev.globalPosition().toPoint()
            self.update()

    def mouseReleaseEvent(self, ev):
        if self.origin:
            a = self.origin
            b = ev.globalPosition().toPoint()
            x, y = min(a.x(), b.x()), min(a.y(), b.y())
            w, h = abs(a.x() - b.x()), abs(a.y() - b.y())
            self.close()
            if w > 60 and h > 60:
                self.rectPicked.emit((x, y, w, h))
        self.origin = None

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.close()


# ---------------------------------------------------------------- panel

DARK_CSS = """
QWidget { background:#0e2117; color:#e8e0c8; font-size:13px; }
QPushButton { background:#1c3a2a; border:1px solid #3d6b4f; border-radius:6px;
              padding:6px 10px; color:#f0e6c8; }
QPushButton:hover { background:#27503a; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
   background:#0a1a11; border:1px solid #3d6b4f; border-radius:4px; padding:3px; }
QLabel#eval { color:#ffd75e; font-size:20px; font-weight:bold; }
QLabel#title { color:#ffd75e; font-size:15px; font-weight:bold; }
QCheckBox { spacing:6px; }
QGroupBox { border:1px solid #3d6b4f; border-radius:6px; margin-top:8px;
            padding-top:6px; }
QGroupBox::title { subcontrol-origin: margin; color:#9fd4a8; }
"""


class Panel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Satranç Antrenman Asistanı")
        self.setStyleSheet(DARK_CSS)
        self.calib = None

        HUB.sig_log.connect(self.append_log)
        HUB.sig_eval.connect(lambda s: self.eval_lbl.setText(s))
        HUB.sig_status.connect(lambda s: self.status.setText(s))
        HUB.sig_hint.connect(do_hint)
        HUB.sig_live.connect(toggle_live)
        HUB.sig_auto.connect(toggle_auto)

        root = QVBoxLayout(self)

        title = QLabel("♞ Satranç Antrenman Asistanı")
        title.setObjectName("title")
        root.addWidget(title)

        # --- kalibrasyon grubu
        g1 = QGroupBox("1) Kurulum (her site için bir kez)")
        v1 = QVBoxLayout(g1)
        row1 = QHBoxLayout()
        b_cal = QPushButton("① Kalibrasyon (tahtayı seç)")
        b_cal.clicked.connect(self.start_calib)
        b_ref = QPushButton("② Referans Al (başlangıç dizilimi)")
        b_ref.clicked.connect(self.take_reference)
        row1.addWidget(b_cal)
        row1.addWidget(b_ref)
        v1.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Profil:"))
        self.profile_name = QLineEdit(STATE.get("profile") or "chesscom")
        self.profile_name.setFixedWidth(90)
        b_save = QPushButton("Kaydet")
        b_save.clicked.connect(self.save_profile)
        self.profile_combo = QComboBox()
        self.profile_combo.setFixedWidth(110)
        b_load = QPushButton("Yükle")
        b_load.clicked.connect(self.load_profile)
        row2.addWidget(self.profile_name)
        row2.addWidget(b_save)
        row2.addWidget(self.profile_combo)
        row2.addWidget(b_load)
        v1.addLayout(row2)
        root.addWidget(g1)

        # --- modlar
        g2 = QGroupBox("2) Modlar")
        v2 = QGridLayout(g2)
        b_hint = QPushButton("İpucu (F10)")
        b_hint.clicked.connect(do_hint)
        self.b_live = QPushButton("Canlı Ok: KAPALI (F11)")
        self.b_live.clicked.connect(self.click_live)
        self.b_auto = QPushButton("Oto Oyna: KAPALI (F12)")
        self.b_auto.clicked.connect(self.click_auto)
        b_clear = QPushButton("Okları Sil (F9)")
        b_clear.clicked.connect(HUB.sig_clear.emit)
        v2.addWidget(b_hint, 0, 0)
        v2.addWidget(self.b_live, 0, 1)
        v2.addWidget(self.b_auto, 1, 0)
        v2.addWidget(b_clear, 1, 1)
        root.addWidget(g2)

        # --- ayarlar
        g3 = QGroupBox("3) Ayarlar")
        v3 = QGridLayout(g3)
        self.cb_flip = QCheckBox("Siyah altta (tahta çevik)")
        self.cb_flip.setChecked(bool(STATE["flip"]))
        self.cb_flip.toggled.connect(self.set_flip)
        v3.addWidget(self.cb_flip, 0, 0)

        self.cb_queen = QCheckBox("Terfi: otomatik vezir")
        self.cb_queen.setChecked(bool(STATE["auto_queen"]))
        self.cb_queen.toggled.connect(lambda v: self.set_state("auto_queen", v))
        v3.addWidget(self.cb_queen, 0, 1)

        self.cb_only = QCheckBox("Oklar sadece benim sıramda")
        self.cb_only.setChecked(bool(STATE["only_my_turn"]))
        self.cb_only.toggled.connect(lambda v: self.set_state("only_my_turn", v))
        v3.addWidget(self.cb_only, 1, 0, 1, 2)

        v3.addWidget(QLabel("Benim tarafım:"), 2, 0)
        self.side_combo = QComboBox()
        self.side_combo.addItems(["Beyaz (w)", "Siyah (b)"])
        self.side_combo.setCurrentIndex(0 if STATE["auto_side"] == "w" else 1)
        self.side_combo.currentIndexChanged.connect(self.set_side)
        v3.addWidget(self.side_combo, 2, 1)

        v3.addWidget(QLabel("Sıra başlangıcı:"), 3, 0)
        self.init_combo = QComboBox()
        self.init_combo.addItems(["Beyaz", "Siyah"])
        self.init_combo.setCurrentIndex(0 if STATE["side"] == "w" else 1)
        self.init_combo.currentIndexChanged.connect(self.set_init_side)
        v3.addWidget(self.init_combo, 3, 1)

        v3.addWidget(QLabel("Motor süre (ms):"), 4, 0)
        self.mt_spin = QSpinBox()
        self.mt_spin.setRange(100, 4000)
        self.mt_spin.setSingleStep(100)
        self.mt_spin.setValue(int(STATE["movetime"]))
        self.mt_spin.valueChanged.connect(lambda v: self.set_state("movetime", v))
        v3.addWidget(self.mt_spin, 4, 1)

        v3.addWidget(QLabel("Tanıma hassasiyeti:"), 5, 0)
        self.th_spin = QDoubleSpinBox()
        self.th_spin.setRange(8.0, 80.0)
        self.th_spin.setSingleStep(1.0)
        self.th_spin.setValue(float(STATE["thresh"]))
        self.th_spin.valueChanged.connect(lambda v: self.set_state("thresh", v))
        v3.addWidget(self.th_spin, 5, 1)

        v3.addWidget(QLabel("Motor yolu:"), 6, 0)
        self.engine_edit = QLineEdit(STATE["engine_path"])
        self.engine_edit.editingFinished.connect(self.set_engine_path)
        v3.addWidget(self.engine_edit, 6, 1)
        root.addWidget(g3)

        # --- durum
        self.eval_lbl = QLabel("—")
        self.eval_lbl.setObjectName("eval")
        self.eval_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.eval_lbl)
        self.status = QLabel("hazır")
        root.addWidget(self.status)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(110)
        root.addWidget(self.log_box)

        self.refresh_profiles()
        if STATE.get("rect"):
            HUB.sig_rect.emit(tuple(STATE["rect"]))
        self.resize(360, 640)

    # ---- yardımcılar
    def set_state(self, key, val):
        STATE[key] = val
        save_cfg()

    def set_flip(self, v):
        STATE["flip"] = bool(v)
        save_cfg()

    def set_side(self, idx):
        self.set_state("auto_side", "w" if idx == 0 else "b")

    def set_init_side(self, idx):
        self.set_state("side", "w" if idx == 0 else "b")

    def set_engine_path(self):
        self.set_state("engine_path", self.engine_edit.text().strip())

    def append_log(self, msg):
        self.log_box.append(msg)

    def click_live(self):
        toggle_live()
        self.sync_buttons()

    def click_auto(self):
        toggle_auto()
        self.sync_buttons()

    def sync_buttons(self):
        self.b_live.setText("Canlı Ok: %s (F11)" % ("AÇIK" if STATE["live"] else "KAPALI"))
        self.b_auto.setText("Oto Oyna: %s (F12)" % ("AÇIK" if STATE["auto"] else "KAPALI"))

    # ---- kurulum işleri
    def start_calib(self):
        self.calib = CalibOverlay()
        self.calib.rectPicked.connect(self.on_rect)

    def on_rect(self, rect):
        STATE["rect"] = list(rect)
        STATE["last_placement"] = None
        save_cfg()
        HUB.sig_rect.emit(tuple(rect))
        log("Tahta seçildi: %s. Şimdi oyunu BAŞLANGIÇ dizilimine getir ve "
            "'② Referans Al'a bas." % (rect,))

    def take_reference(self):
        if not STATE["rect"]:
            log("Önce ① Kalibrasyon ile tahtayı seç.")
            return
        try:
            img = vision.grab_screen()
            tpls = vision.extract_reference(img, STATE["rect"])
            STATE["templates"] = tpls
            STATE["last_placement"] = None
            n = sum(len(v) for v in tpls.values())
            log("Referans alındı: %d şablon. Artık modları kullanabilirsin." % n)
        except Exception as e:
            log("Referans hatası: %s" % e)

    def refresh_profiles(self):
        import glob
        self.profile_combo.clear()
        if os.path.isdir(PROFILE_DIR):
            for p in sorted(glob.glob(os.path.join(PROFILE_DIR, "*.npz"))):
                self.profile_combo.addItem(os.path.splitext(os.path.basename(p))[0])
        if STATE.get("profile"):
            i = self.profile_combo.findText(STATE["profile"])
            if i >= 0:
                self.profile_combo.setCurrentIndex(i)

    def save_profile(self):
        if not STATE["rect"] or not STATE["templates"]:
            log("Profil için önce kalibrasyon + referans gerekli.")
            return
        os.makedirs(PROFILE_DIR, exist_ok=True)
        name = "".join(ch for ch in self.profile_name.text() if ch.isalnum() or ch in "-_") or "profil"
        path = os.path.join(PROFILE_DIR, name + ".npz")
        try:
            vision.save_profile(path, STATE["templates"], STATE["rect"])
            STATE["profile"] = name
            save_cfg()
            self.refresh_profiles()
            log("Profil kaydedildi: " + name)
        except Exception as e:
            log("Profil kaydedilemedi: %s" % e)

    def load_profile(self):
        name = self.profile_combo.currentText()
        if not name:
            return
        path = os.path.join(PROFILE_DIR, name + ".npz")
        if not os.path.isfile(path):
            log("Profil bulunamadı: " + name)
            return
        try:
            tpls, rect = vision.load_profile(path)
            STATE["templates"] = tpls
            STATE["rect"] = list(rect)
            STATE["profile"] = name
            STATE["last_placement"] = None
            save_cfg()
            HUB.sig_rect.emit(tuple(rect))
            self.profile_name.setText(name)
            log("Profil yüklendi: " + name)
        except Exception as e:
            log("Profil yüklenemedi: %s" % e)

    def closeEvent(self, ev):
        STATE["live"] = False
        STATE["auto"] = False
        save_cfg()
        global ENGINE
        with ENG_LOCK:
            if ENGINE is not None:
                ENGINE.close()
                ENGINE = None
        QApplication.quit()


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    load_cfg()
    app = QApplication(sys.argv)
    panel = Panel()
    panel.show()
    Overlay()
    try:
        import keyboard
        keyboard.add_hotkey("f9", lambda: HUB.sig_clear.emit())
        keyboard.add_hotkey("f10", lambda: HUB.sig_hint.emit())
        keyboard.add_hotkey("f11", lambda: HUB.sig_live.emit())
        keyboard.add_hotkey("f12", lambda: HUB.sig_auto.emit())
    except Exception as e:
        log("Global kısayollar yüklenemedi (panel düğmelerini kullan): %s" % e)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()