"""Çevrimdışı sokak sözlüğü (dahili/assets/sokak_sozlugu.json ile aynı dosya).

Telefon sürümündeki OfflineSlang'in hazır kalıp kısmı: altyazı, sözlükteki bir
kalıba birebir uyuyorsa Gemini'ye gitmeden doğrudan Türkçesi gösterilir.
"""
import json
import re

_SPEAKER = re.compile(r"^([A-Z][A-Za-z0-9 .'\-]{0,24}):\s+(.+)$")
_SENT = re.compile(r"(?<=[.!?])\s+")
_GDROP = re.compile(r"\b([A-Za-z]+)in'(?![A-Za-z])")


def _java_to_py(rx: str) -> str:
    # Java ile Python düzenli ifadeleri büyük ölçüde aynı; yalnız \p{L} gibi
    # sınıflar farklı. Bunları kaba ama güvenli karşılıklarla değiştir.
    return (rx.replace(r"\p{L}", r"[^\W\d_]")
              .replace(r"\p{Lu}", r"[A-ZÇĞİÖŞÜ]")
              .replace(r"\p{Ll}", r"[a-zçğıöşü]"))


class Sozluk:
    def __init__(self, path=None):
        self.phrases = {}
        self.pre = []
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
        pre = []
        for pair in root.get("pre", []):
            try:
                pre.append((re.compile(_java_to_py(pair[0]), re.IGNORECASE), pair[1]))
            except Exception:
                pass
        self.pre = pre

    # --- İngilizce anahtar (telefon sürümüyle aynı kurallar)
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

    def _replace(self, rx, rep, t):
        # Java'daki $1 gruplarını Python'daki \1 biçimine çevir
        rep_py = re.sub(r"\$(\d)", r"\\\1", rep)
        try:
            return rx.sub(rep_py, t)
        except Exception:
            return t

    def _key(self, s):
        q = "?" if s.strip().endswith("?") else ""
        t = s.lower().replace("’", "'").replace("‘", "'")
        for rx, rep in self.pre:
            t = self._replace(rx, rep, t)
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

    def cevir(self, text):
        """Altyazının tamamı sözlükte varsa Türkçesini döndürür, yoksa None."""
        text = " ".join(text.split())
        if not text or not self.phrases:
            return None
        speaker = ""
        m = _SPEAKER.match(text)
        if m:
            speaker, text = m.group(1) + ": ", m.group(2)
        out = []
        for s in _SENT.split(text):
            s = s.strip()
            if not s:
                continue
            tr = self._lookup(s)
            if tr is None:
                return None
            out.append(tr)
        return speaker + " ".join(out) if out else None
