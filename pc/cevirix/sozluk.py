"""Çevrimdışı sokak dili katmanı (dahili/assets/sokak_sozlugu.json ile aynı dosya).

Telefon sürümündeki OfflineSlang'in birebir karşılığı:
1) Hazır kalıplar: oyunlarda sık geçen cümleler doğrudan sokak ağzıyla eşleşir.
2) İngilizce sokak ağzı düzeltme: gonna/wanna/ain't... çeviriden önce düz İngilizceye çevrilir.
3) Türkçe sokak ağzı: çeviri çıktısındaki resmî dil (Siz, -misiniz...) samimileşir.
4) Hitaplar: "bro, man, dude" cümleden ayrılır, Türkçeye "kanka, lan, abi" olarak geri eklenir.
"""
import json
import re

_SPEAKER = re.compile(r"^([A-Z][A-Za-z0-9 .'\-]{0,24}):\s+(.+)$")
_SENT = re.compile(r"(?<=[.!?])\s+")
_GDROP = re.compile(r"\b([A-Za-z]+)in'(?![A-Za-z])")
_ISIMLER = {"Lucia", "Jason", "Vice", "Leonida", "Port", "Kirk", "Allah'ım"}


def _java_to_py(rx):
    """Java düzenli ifadesindeki Unicode sınıflarını Python karşılığına çevirir."""
    return (rx.replace(r"[\p{L}\p{N}]", r"[^\W_]")
              .replace(r"\p{L}", r"[^\W\d_]")
              .replace(r"\p{N}", r"\d")
              .replace(r"\p{Lu}", r"[A-ZÇĞİÖŞÜ]")
              .replace(r"\p{Ll}", r"[a-zçğıöşü]"))


def _java_rep(rep):
    """Java'daki $1 gruplarını Python'daki \\1 biçimine çevirir."""
    return re.sub(r"\$(\d)", r"\\g<\1>", rep.replace("\\", "\\\\"))


def _tr_ust(c):
    return {"i": "İ", "ı": "I"}.get(c, c.upper())


def _tr_alt(c):
    return {"I": "ı", "İ": "i"}.get(c, c.lower())


def buyuk_bas(s):
    return _tr_ust(s[0]) + s[1:] if s else s


def kucuk_bas(s):
    return _tr_alt(s[0]) + s[1:] if s else s


class Sozluk:
    def __init__(self, path=None):
        self.phrases = {}
        self.pre = []
        self.post = []
        self.vocatives = {}
        self._bas_hitap = None
        self._son_hitap = None
        if path:
            self.load(path)

    @property
    def boyut(self):
        return len(self.phrases)

    def load(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                root = json.load(f)
        except Exception:
            return
        self.phrases = dict(root.get("phrases", {}))
        self.pre = self._kurallar(root.get("pre", []), re.IGNORECASE)
        self.post = self._kurallar(root.get("post", []), 0)
        self.vocatives = {k.lower(): v for k, v in (root.get("vocatives") or {}).items()}
        if self.vocatives:
            alt = "|".join(re.escape(k) for k in sorted(self.vocatives, key=len, reverse=True))
            self._bas_hitap = re.compile(rf"^({alt})[,!]?\s+(.+)$", re.IGNORECASE)
            self._son_hitap = re.compile(rf"^(.+?),\s*({alt})([.!?]*)$", re.IGNORECASE)

    @staticmethod
    def _kurallar(liste, bayrak):
        out = []
        for pair in liste:
            try:
                out.append((re.compile(_java_to_py(pair[0]), bayrak), _java_rep(pair[1])))
            except Exception:
                pass
        return out

    # ------------------------------------------------------------ İngilizce tarafı
    @staticmethod
    def _contractions(t):
        t = re.sub(r"\b([Cc])an't\b", lambda m: m.group(1) + "annot", t)
        t = re.sub(r"\b([Ww])on't\b", lambda m: m.group(1) + "ill not", t)
        t = re.sub(r"n't\b", " not", t, flags=re.I)
        t = re.sub(r"'re\b", " are", t, flags=re.I)
        t = re.sub(r"'m\b", " am", t, flags=re.I)
        t = re.sub(r"'ll\b", " will", t, flags=re.I)
        t = re.sub(r"'ve\b", " have", t, flags=re.I)
        t = re.sub(r"'d\b", " would", t, flags=re.I)
        return t

    @staticmethod
    def _uygula(kurallar, t):
        for rx, rep in kurallar:
            try:
                t = rx.sub(rep, t)
            except Exception:
                pass
        return t

    def _key(self, s):
        q = "?" if s.strip().endswith("?") else ""
        t = s.lower().replace("’", "'").replace("‘", "'")
        t = self._uygula(self.pre, t)
        t = _GDROP.sub(lambda m: m.group(1) + "ing", t)
        t = self._contractions(t).replace("'", "")
        k = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()
        return k + q if k else ""

    def _lookup(self, sentence):
        k = self._key(sentence)
        if not k:
            return None
        v = self.phrases.get(k)
        if v is None and k.endswith("?"):
            v = self.phrases.get(k[:-1])
        return v

    def ceviriye_hazirla(self, s):
        """Çeviri motoruna gidecek metin: büyük/küçük harf korunur, sokak ağzı düzeltilir."""
        t = s.replace("’", "'").replace("‘", "'")
        t = self._uygula(self.pre, t)
        t = _GDROP.sub(lambda m: m.group(1) + "ing", t)
        return self._contractions(t)

    # ------------------------------------------------------------ Türkçe tarafı
    def sokaklastir(self, s):
        t = self._uygula(self.post, s)
        t = re.sub(r"\s+", " ", t)
        t = re.sub(r"\s+([,.!?])", r"\1", t).strip()
        return buyuk_bas(t)

    # ------------------------------------------------------------ hitaplar
    def _hitap_ayir(self, s):
        if self._bas_hitap:
            m = self._bas_hitap.match(s)
            if m and len(m.group(2).strip()) >= 2:
                tr = self.vocatives.get(m.group(1).lower())
                if tr is not None:
                    return m.group(2).strip(), tr, True, ""
        if self._son_hitap:
            m = self._son_hitap.match(s)
            if m and len(m.group(1).strip()) >= 2:
                tr = self.vocatives.get(m.group(2).lower())
                if tr is not None:
                    noktalama = m.group(3) or "."
                    return m.group(1).strip() + noktalama[:1], tr, False, noktalama
        return None

    @staticmethod
    def _hitap_ekle(tr, hitap):
        _, kelime, basta, noktalama = hitap
        if not kelime.strip():
            return tr
        if basta:
            ilk = tr.split(" ", 1)[0].rstrip(",!?.")
            govde = tr if ilk in _ISIMLER else kucuk_bas(tr)
            return buyuk_bas(kelime) + ", " + govde
        son = re.search(r"[.!?]*$", tr).group(0)
        govde = tr[:len(tr) - len(son)].rstrip(", ")
        return f"{govde} {kelime}{son or noktalama}"

    # ------------------------------------------------------------ çeviri
    def _parcala(self, text):
        text = " ".join(text.split())
        m = _SPEAKER.match(text)
        konusan = m.group(1) if m else None
        govde = m.group(2) if m else text
        cumleler = [s.strip() for s in _SENT.split(govde) if s.strip()]
        return konusan, cumleler

    def _kalip(self, s):
        tr = self._lookup(s)
        if tr is not None:
            return tr
        h = self._hitap_ayir(s)
        if not h:
            return None
        tr = self._lookup(h[0])
        return self._hitap_ekle(tr, h) if tr is not None else None

    def cevir(self, text):
        """Altyazının tamamı kalıp sözlüğünde varsa Türkçesini döndürür, yoksa None."""
        if not self.phrases:
            return None
        konusan, cumleler = self._parcala(text)
        if not cumleler:
            return None
        out = []
        for s in cumleler:
            tr = self._kalip(s)
            if tr is None:
                return None
            out.append(tr)
        birlesik = " ".join(out)
        return f"{konusan}: {birlesik}" if konusan else birlesik

    def makine_ile_cevir(self, text, makine):
        """Kalıpta olmayan cümleleri makine(çeviri) ile çevirip sokak diline uyarlar."""
        konusan, cumleler = self._parcala(text)
        if not cumleler:
            return None
        out = []
        for s in cumleler:
            tr = self._lookup(s)
            if tr is None:
                h = self._hitap_ayir(s)
                if h:
                    tr = self._lookup(h[0])
                    if tr is None:
                        m = makine(self.ceviriye_hazirla(h[0]))
                        if not m:
                            return None
                        tr = self.sokaklastir(m)
                    tr = self._hitap_ekle(tr, h)
                else:
                    m = makine(self.ceviriye_hazirla(s))
                    if not m:
                        return None
                    tr = self.sokaklastir(m)
            out.append(tr)
        birlesik = " ".join(out)
        return f"{konusan}: {birlesik}" if konusan else birlesik
