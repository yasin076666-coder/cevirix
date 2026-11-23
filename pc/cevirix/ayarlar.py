"""Ayarlar: %APPDATA%\\Cevirix\\ayarlar.json"""
import json
import os

from .gemini import VARSAYILAN_MODEL, VARSAYILAN_TERIMLER

KLASOR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Cevirix")
DOSYA = os.path.join(KLASOR, "ayarlar.json")

VARSAYILAN = {
    "gemini_anahtar": "",
    "gemini_model": VARSAYILAN_MODEL,
    # Altyazı alanı: PS5 görüntüsüne oranla (sol, üst, genişlik, yükseklik)
    "alan": [0.12, 0.74, 0.76, 0.22],
    "yazi_boyutu": 30,
    "konum": "kapat",          # kapat = İngilizcenin üstüne; ust = ekranın üstüne
    "okuma_araligi_ms": 250,
    "gizleme_sn": 1.5,
    "terimler": VARSAYILAN_TERIMLER,
    "chiaki_yolu": "",
}


def yukle():
    a = dict(VARSAYILAN)
    try:
        with open(DOSYA, encoding="utf-8") as f:
            a.update(json.load(f))
    except Exception:
        pass
    return a


def kaydet(a):
    try:
        os.makedirs(KLASOR, exist_ok=True)
        tmp = DOSYA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(a, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DOSYA)
    except Exception:
        pass
