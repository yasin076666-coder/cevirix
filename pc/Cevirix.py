"""Çevirix PC giriş noktası (PyInstaller bunu derler)."""
import sys


def oz_test(cikti):
    """Derleme sonrası denetim: OCR, sözlük ve ekran yakalama paketin içinde çalışıyor mu."""
    import json
    import traceback
    sonuc = {}
    try:
        import cv2
        import numpy as np
        from cevirix.okuyucu import Okuyucu
        img = np.zeros((120, 900, 3), dtype=np.uint8)
        cv2.putText(img, "We gotta get outta here, bro.", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                    (255, 255, 255), 3, cv2.LINE_AA)
        sonuc["ocr"] = Okuyucu().oku(img)
    except Exception:
        sonuc["ocr_hata"] = traceback.format_exc()
    try:
        from cevirix.sozluk import Sozluk
        from cevirix.uygulama import kaynak
        s = Sozluk(kaynak("sokak_sozlugu.json"))
        sonuc["sozluk"] = s.boyut
        sonuc["sozluk_ornek"] = s.cevir("What's up?")
    except Exception:
        sonuc["sozluk_hata"] = traceback.format_exc()
    try:
        from cevirix.ekran import Yakalayici
        sonuc["yakalama"] = list(Yakalayici().al(0, 0, 64, 32).shape)
    except Exception:
        sonuc["yakalama_hata"] = traceback.format_exc()
    with open(cikti, "w", encoding="utf-8") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--test":
        oz_test(sys.argv[2])
    else:
        from cevirix.uygulama import main
        main()
