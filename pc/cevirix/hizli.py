"""Hızlı çeviri (anahtarsız, ~0,2 sn): Gemini yokken ya da Gemini cevabı gelene kadar kullanılır.

Telefon sürümü burada telefonun içindeki ML Kit çevirisini kullanıyor. Windows'ta onun
yerine Google Çeviri'nin anahtarsız ucu kullanılır; çıktı sokak sözlüğüyle samimileştirilir.
"""
import json
import re
import ssl
import urllib.parse
import urllib.request

_URL = "https://translate.googleapis.com/translate_a/single"


class HizliCeviri:
    def __init__(self):
        self._ctx = ssl.create_default_context()

    def _ham(self, metin):
        q = urllib.parse.urlencode({"client": "gtx", "sl": "en", "tl": "tr", "dt": "t", "q": metin})
        req = urllib.request.Request(f"{_URL}?{q}", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4, context=self._ctx) as r:
            veri = json.loads(r.read().decode("utf-8", "replace"))
        return "".join(p[0] for p in (veri[0] or []) if p and p[0]).strip()

    def cevir(self, metin, terimler=()):
        """Terim sözlüğündeki adları koruyarak çevirir. Hata olursa None."""
        try:
            bulunan = [t for t in terimler if t[0] and t[0].lower() in metin.lower()]
            if not bulunan:
                return self._ham(metin) or None
            korunan, yerine = metin, {}
            for i, (kaynak, hedef) in enumerate(sorted(bulunan, key=lambda t: -len(t[0]))):
                jeton = f"ZQX{i}"
                yeni = re.sub(re.escape(kaynak), jeton, korunan, flags=re.IGNORECASE)
                if yeni != korunan:
                    korunan = yeni
                    yerine[jeton] = hedef or kaynak
            cikti = self._ham(korunan)
            if all(j in cikti for j in yerine):
                for j, h in yerine.items():
                    cikti = cikti.replace(j, h)
                return cikti or None
            return self._ham(metin) or None
        except Exception:
            return None


def terim_listesi(metin):
    """Terim sözlüğü metni -> [(kaynak, hedef ya da None)]"""
    out = []
    for raw in (metin or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            src, dst = (x.strip() for x in line.split("=", 1))
            if src:
                out.append((src, dst or None))
        else:
            out.append((line, None))
    return out
