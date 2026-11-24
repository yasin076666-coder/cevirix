"""PS5 bağlantı durumunu chiaki-ng'nin oturum kayıtlarından izler.

chiaki-ng her bağlantı için %APPDATA%\\Chiaki\\Chiaki\\log içine yeni bir kayıt dosyası yazar:
- "Ctrl received Login message: success"  -> PS5'e bağlandı, görüntü geliyor
- "Session has quit"                       -> bağlantı kapandı
Kayıt kapanış satırı olmadan biterse ve chiaki penceresi de yoksa program çökmüştür.
"""
import glob
import os
import time

KLASOR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Chiaki", "Chiaki", "log")

YOK, BAGLANIYOR, BAGLI, KAPANDI, COKTU = "yok", "baglaniyor", "bagli", "kapandi", "coktu"


class BaglantiIzleyici:
    def __init__(self, klasor=KLASOR):
        self.klasor = klasor
        self.baslangic = time.time() - 5
        self.dosya = None
        self._konum = 0
        self.durum = YOK
        self.neden = ""

    def _en_yeni(self):
        try:
            dosyalar = glob.glob(os.path.join(self.klasor, "chiaki_session_*.log"))
        except Exception:
            return None
        dosyalar = [d for d in dosyalar if os.path.getmtime(d) >= self.baslangic]
        return max(dosyalar, key=os.path.getmtime) if dosyalar else None

    def yokla(self, pencere_var):
        """Yeni durumu döndürür; değişmediyse None."""
        onceki = self.durum
        d = self._en_yeni()
        if d and d != self.dosya:
            self.dosya, self._konum = d, 0
            self.durum, self.neden = BAGLANIYOR, ""
        if self.dosya:
            try:
                with open(self.dosya, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(self._konum)
                    yeni = f.read()
                    self._konum = f.tell()
            except Exception:
                yeni = ""
            for satir in yeni.splitlines():
                if "Login message: success" in satir:
                    self.durum = BAGLI
                elif "Session has quit" in satir:
                    self.durum = KAPANDI
                elif "Login message:" in satir and "success" not in satir:
                    self.durum, self.neden = KAPANDI, satir.split("Login message:", 1)[1].strip()
        if self.durum in (BAGLANIYOR, BAGLI) and not pencere_var:
            self.durum = COKTU
        return self.durum if self.durum != onceki else None
