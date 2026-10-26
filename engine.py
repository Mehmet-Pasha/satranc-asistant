# -*- coding: utf-8 -*-
"""Minimal UCI istemcisi — resmi Stockfish ikilisiyle konuşur (stdlib only)."""

import re
import subprocess
import threading


class StockfishEngine:
    def __init__(self, path, args=None):
        self.path = path
        self.args = list(args or [])
        self.lock = threading.Lock()
        self.proc = None
        self._start()

    def _start(self):
        self.proc = subprocess.Popen(
            [self.path] + self.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._send("uci")
        self._wait("uciok")
        self._send("isready")
        self._wait("readyok")

    def _send(self, cmd):
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def _wait(self, token):
        for line in self.proc.stdout:
            if token in line:
                return line.rstrip("\n")
        raise RuntimeError("Motor yanıt vermiyor")

    def close(self):
        try:
            self._send("quit")
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    def best(self, fen, movetime=400):
        """(bestmove 'e2e4' | None, (tip, değer) | None) döndürür."""
        with self.lock:
            try:
                self._send("position fen " + fen)
                self._send("go movetime %d" % int(movetime))
                score = None
                best = None
                for line in self.proc.stdout:
                    if line.startswith("info") and "score" in line:
                        m = re.search(r"score (cp|mate) (-?\d+)", line)
                        if m:
                            score = (m.group(1), int(m.group(2)))
                    if line.startswith("bestmove"):
                        parts = line.split()
                        best = parts[1] if len(parts) > 1 else None
                        break
                if best in (None, "(none)"):
                    return None, score
                return best, score
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
                self._start()
                return None, None