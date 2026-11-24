"""Yazı okuyucu (RapidOCR, internetsiz, bilgisayarın içinde çalışır).

Altyazı okuması ile GTA telefon / harita kartı okuması aynı motoru sırayla kullanır.
"""
import threading

from .metin import satirlari_birlestir


class Okuyucu:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        # Yön sınıflandırıcıya gerek yok (altyazı hep düz)
        self.motor = RapidOCR()
        self._kilit = threading.Lock()

    def _calistir(self, bgr):
        with self._kilit:
            try:
                sonuc, _ = self.motor(bgr, use_cls=False)
            except TypeError:
                sonuc, _ = self.motor(bgr)
        return sonuc or []

    def oku(self, bgr):
        """Altyazı şeridi -> tek metin."""
        import cv2
        h, w = bgr.shape[:2]
        if h < 8 or w < 8:
            return ""
        # Küçük ekranda (ör. 1366x768) yazı ufak kalır; büyütmek doğruluğu artırır.
        olcek = 1.0
        if h < 160:
            olcek = 1.6
        elif h < 240:
            olcek = 1.3
        if olcek != 1.0:
            bgr = cv2.resize(bgr, None, fx=olcek, fy=olcek, interpolation=cv2.INTER_CUBIC)
        kutular = []
        for kutu, metin, guven in self._calistir(bgr):
            ys = [p[1] for p in kutu]
            xs = [p[0] for p in kutu]
            kutular.append((min(xs), min(ys), max(ys) - min(ys), metin, float(guven)))
        return satirlari_birlestir(kutular)

    def satirlar(self, bgr, buyut_en=None, min_guven=0.5):
        """Satır satır okuma: [(metin, (sol, üst, sağ, alt))], kutular görüntüye göre 0-1.

        buyut_en: görüntü bundan darsa büyütülür (telefon ekranı küçük kalır). Hata olursa None.
        """
        import cv2
        try:
            h, w = bgr.shape[:2]
            if h < 16 or w < 16:
                return []
            if buyut_en and w < buyut_en:
                f = min(3.0, buyut_en / w)
                bgr = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
                h, w = bgr.shape[:2]
            out = []
            for kutu, metin, guven in self._calistir(bgr):
                metin = (metin or "").strip()
                if not metin or float(guven) < min_guven:
                    continue
                xs = [p[0] for p in kutu]
                ys = [p[1] for p in kutu]
                out.append((metin, (max(0.0, min(xs) / w), max(0.0, min(ys) / h),
                                    min(1.0, max(xs) / w), min(1.0, max(ys) / h))))
            out.sort(key=lambda s: s[1][1])
            return out
        except Exception:
            return None


def degisti_mi(onceki, simdi, esik=2.5):
    """İki kare arasında altyazı şeridi değişti mi (OCR'yi boşuna çalıştırmamak için)."""
    import numpy as np
    if onceki is None or onceki.shape != simdi.shape:
        return True
    a = onceki[::4, ::4].astype(np.int16)
    b = simdi[::4, ::4].astype(np.int16)
    return float(np.abs(a - b).mean()) > esik
