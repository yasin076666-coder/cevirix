"""OCR sonucunu altyazı satırına çevirme, gürültü süzme ve benzerlik."""
import difflib
import re

_HARF = re.compile(r"[A-Za-z]")


def satirlari_birlestir(kutular, min_guven=0.6):
    """kutular: [(x, y, yukseklik, metin, guven)] -> tek altyazı metni.

    Aynı satırdakiler soldan sağa, satırlar yukarıdan aşağıya dizilir.
    """
    iyi = [k for k in kutular if k[4] >= min_guven and k[3].strip()]
    if not iyi:
        return ""
    iyi.sort(key=lambda k: (k[1], k[0]))
    satirlar = []
    for k in iyi:
        if satirlar and abs(satirlar[-1][0] - k[1]) < max(8, k[2] * 0.6):
            satirlar[-1][1].append(k)
        else:
            satirlar.append([k[1], [k]])
    out = []
    for _, parcalar in satirlar:
        parcalar.sort(key=lambda k: k[0])
        out.append(" ".join(p[3].strip() for p in parcalar))
    return temizle(" ".join(out))


def temizle(t):
    t = t.replace("|", "I").replace("’", "'").replace("‘", "'")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    return t


def diyalog_mu(t):
    """Menü/sayı/tek harf gibi şeyleri ele."""
    if len(t) < 2:
        return False
    harf = len(_HARF.findall(t))
    if harf < 2:
        return False
    return harf / max(1, len(t.replace(" ", ""))) >= 0.5


def benzer(a, b):
    if not a or not b:
        return 0.0
    a, b = a.lower(), b.lower()
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


class Dengeleyici:
    """Aynı metin art arda iki kez okunmadan çeviriye göndermez; titremeyi engeller."""

    def __init__(self, gerekli=2):
        self.gerekli = gerekli
        self.aday = ""
        self.sayac = 0
        self.son_gonderilen = ""

    def besle(self, metin):
        """Çevrilecek yeni metin varsa döndürür, yoksa None."""
        if not metin:
            self.aday, self.sayac = "", 0
            return None
        if benzer(metin, self.aday) >= 0.9:
            self.sayac += 1
            # Daha uzun okunan hâli tut (altyazı harf harf beliriyorsa)
            if len(metin) > len(self.aday):
                self.aday = metin
        else:
            self.aday, self.sayac = metin, 1
        if self.sayac >= self.gerekli and benzer(self.aday, self.son_gonderilen) < 0.85:
            self.son_gonderilen = self.aday
            return self.aday
        return None

    def sifirla(self):
        self.aday, self.sayac, self.son_gonderilen = "", 0, ""
