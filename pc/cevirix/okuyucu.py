"""Altyazı şeridini okuyan OCR (RapidOCR, internetsiz, bilgisayarın içinde çalışır)."""
from .metin import satirlari_birlestir


class Okuyucu:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        # Yön sınıflandırıcıya gerek yok (altyazı hep düz)
        self.motor = RapidOCR()

    def oku(self, bgr):
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
        try:
            sonuc, _ = self.motor(bgr, use_cls=False)
        except TypeError:
            sonuc, _ = self.motor(bgr)
        if not sonuc:
            return ""
        kutular = []
        for kutu, metin, guven in sonuc:
            ys = [p[1] for p in kutu]
            xs = [p[0] for p in kutu]
            kutular.append((min(xs), min(ys), max(ys) - min(ys), metin, float(guven)))
        return satirlari_birlestir(kutular)


def degisti_mi(onceki, simdi, esik=2.5):
    """İki kare arasında altyazı şeridi değişti mi (OCR'yi boşuna çalıştırmamak için)."""
    import numpy as np
    if onceki is None or onceki.shape != simdi.shape:
        return True
    a = onceki[::4, ::4].astype(np.int16)
    b = simdi[::4, ::4].astype(np.int16)
    return float(np.abs(a - b).mean()) > esik
