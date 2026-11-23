"""Çeviri geçmişi: en yenisi başta, en çok 300 satır (%APPDATA%\\Cevirix\\gecmis.json)."""
import json
import os
import threading
import time

from .ayarlar import KLASOR

DOSYA = os.path.join(KLASOR, "gecmis.json")
EN_COK = 300


class Gecmis:
    def __init__(self):
        self._kilit = threading.Lock()
        self._kirli = False
        self.satirlar = []
        try:
            with open(DOSYA, encoding="utf-8") as f:
                for o in json.load(f).get("entries", []):
                    self.satirlar.append({"en": o.get("en", ""), "tr": o.get("tr", ""),
                                          "engine": o.get("engine", ""), "at": o.get("at", 0)})
        except Exception:
            self.satirlar = []

    def ekle(self, en, tr, motor):
        if not tr.strip() or motor == "Test":
            return
        with self._kilit:
            yeni = {"en": en[:500], "tr": tr[:500], "engine": motor, "at": int(time.time() * 1000)}
            if self.satirlar and self.satirlar[0]["en"] == en:
                self.satirlar[0] = yeni
            else:
                self.satirlar.insert(0, yeni)
                del self.satirlar[EN_COK:]
            self._kirli = True

    def liste(self):
        with self._kilit:
            return list(self.satirlar)

    def temizle(self):
        with self._kilit:
            self.satirlar = []
            self._kirli = True
        self.yaz()

    def yaz(self):
        with self._kilit:
            if not self._kirli:
                return
            veri = {"version": 1, "entries": list(self.satirlar)}
            self._kirli = False
        try:
            os.makedirs(KLASOR, exist_ok=True)
            tmp = DOSYA + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(veri, f, ensure_ascii=False)
            os.replace(tmp, DOSYA)
        except Exception:
            pass
