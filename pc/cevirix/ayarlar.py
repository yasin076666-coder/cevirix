"""Ayarlar: %APPDATA%\\Cevirix\\ayarlar.json"""
import json
import os

from .gemini import VARSAYILAN_MODEL, VARSAYILAN_TERIMLER

KLASOR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Cevirix")
DOSYA = os.path.join(KLASOR, "ayarlar.json")

VARSAYILAN = {
    # Çeviri
    "gemini_acik": True,
    "gemini_anahtar": "",
    "gemini_model": VARSAYILAN_MODEL,
    "aninda_ceviri": True,      # önce hızlı çeviri, Gemini gelince yerine geçer
    "terimler": VARSAYILAN_TERIMLER,
    "gta_ekstra": True,         # GTA 6: oyun içi telefon mesajları ve harita kartı
    # Sesli okuma (canlı dublaj)
    "sesli_okuma": False,
    "konusma_hizi": 110,        # yüzde, 100 = normal
    "ses_adi": "",              # boş = Türkçe ses varsa o
    # Altyazı görünümü (bilgisayar ekranı ve TV aynı ayarları kullanır)
    "yazi_boyutu": 30,
    "alt_yukseklik": 70,        # alttan yükseklik (1080 satırlık ekrana göre)
    "arka_koyuluk": 170,        # 0-255
    "ingilizce_goster": False,
    "konum": "kapat",           # kapat = İngilizcenin üstüne, alt = alttan yükseklik, ust = ekranın üstü
    "pc_katman": True,          # bu bilgisayarın ekranında göster
    # Diğer ekranlar
    "tv_gonder": True,          # Çevirix TV (Philips / Android TV)
    "web_sayfa": True,          # tarayıcı altyazı sayfası (iPhone, tablet)
    # PS5 bağlantısı
    "baglaninca_don": True,     # PS5'e bağlanınca Çevirix penceresine dön
    "baglaninca_cevir": True,   # PS5'e bağlanınca çeviriyi kendiliğinden başlat
    # Okuma
    # Altyazı alanı: PS5 görüntüsüne oranla (sol, üst, genişlik, yükseklik)
    "alan": [0.12, 0.74, 0.76, 0.22],
    "okuma_araligi_ms": 250,
    "gizleme_sn": 1.5,
    "chiaki_yolu": "",
}

# Dışa aktarılırken gizli kalanlar
GIZLI = ("gemini_anahtar",)


def _eski_uyum(a):
    if a.get("yazi_boyutu", 30) < 16:
        a["yazi_boyutu"] = 16
    if a.get("konum") not in ("kapat", "alt", "ust"):
        a["konum"] = "kapat"
    return a


def yukle():
    a = dict(VARSAYILAN)
    try:
        with open(DOSYA, encoding="utf-8") as f:
            a.update(json.load(f))
    except Exception:
        pass
    return _eski_uyum(a)


def kaydet(a):
    try:
        os.makedirs(KLASOR, exist_ok=True)
        tmp = DOSYA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(a, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DOSYA)
    except Exception:
        pass


def disa_aktar(a, yol, anahtarla=False):
    veri = {k: v for k, v in a.items() if anahtarla or k not in GIZLI}
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)


def ice_aktar(a, yol):
    with open(yol, encoding="utf-8") as f:
        gelen = json.load(f)
    if not isinstance(gelen, dict):
        raise ValueError("Dosya Çevirix ayar dosyası değil")
    def sayi(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    for k, v in gelen.items():
        if k not in VARSAYILAN:
            continue
        ornek = VARSAYILAN[k]
        if type(v) is type(ornek) or (sayi(v) and sayi(ornek)):
            a[k] = v
    return _eski_uyum(a)
