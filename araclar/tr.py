"""Türkçe ek motoru: ünlü uyumu, ünsüz yumuşaması, kaynaştırma harfleri."""

UNLU = "aeıioöuü"
INCE = "eiöü"
SERT = "çfhkpsşt"
_D4 = {"a": "ı", "ı": "ı", "e": "i", "i": "i", "o": "u", "u": "u", "ö": "ü", "ü": "ü"}


def son_unlu(w):
    for c in reversed(w.lower()):
        if c in UNLU:
            return c
    return "e"


def u2(w):
    return "e" if son_unlu(w) in INCE else "a"


def u4(w):
    return _D4[son_unlu(w)]


def buyuk(s):
    if not s:
        return s
    c = s[0]
    return {"i": "İ", "ı": "I"}.get(c, c.upper()) + s[1:]


def soru(w):
    """Soru eki (mi/mı/mu/mü) – ayrı yazılır."""
    return "m" + u4(w)


class Ad:
    """İsim öbeği. Ek yalnızca son kelimeye gelir.
    yum: ünlüyle başlayan ekte son kelimenin yumuşamış hali (uçak -> uçağ)
    iyelik: tamlama sonu iyelikli (polis karakolu -> karakolunu, karakoluna)
    ozel: özel isim, ek kesmeyle ayrılır (Vice City'ye)
    okunus: ünlü uyumu için okunuş (City -> siti)"""

    def __init__(self, en, tr, yum=None, iyelik=False, ozel=False, okunus=None, an=None):
        self.en = en
        self.tr = tr
        self.yum = yum.split(" ")[-1] if yum else None
        self.iyelik = iyelik
        self.ozel = ozel
        self.okunus = okunus
        self.an = an  # "a car" biçimi (yoksa None)

    def hal(self, h):
        if h == "yalin":
            return self.tr
        kel = self.tr.split(" ")
        son = kel[-1]
        p = (self.okunus or son).lower()
        unlu_son = p[-1] in UNLU
        sert = p[-1] in SERT
        a, i = u2(p), u4(p)
        if self.iyelik:
            ek = {"belirtme": "n" + i, "yonelme": "n" + a, "bulunma": "nd" + a,
                  "ayrilma": "nd" + a + "n", "ilgi": "n" + i + "n", "vasita": "yl" + a}[h]
            govde = son
        else:
            y = "y" if unlu_son else ""
            dt = "t" if sert else "d"
            ek = {"belirtme": y + i, "yonelme": y + a, "bulunma": dt + a,
                  "ayrilma": dt + a + "n", "ilgi": ("n" if unlu_son else "") + i + "n",
                  "vasita": y + "l" + a}[h]
            govde = son
            if self.yum and h in ("belirtme", "yonelme", "ilgi") and not self.ozel:
                govde = self.yum
        ayir = "'" if self.ozel else ""
        return " ".join(kel[:-1] + [govde + ayir + ek])

    # kısa adlar
    @property
    def yalin(self): return self.tr
    @property
    def ini(self): return self.hal("belirtme")
    @property
    def ine(self): return self.hal("yonelme")
    @property
    def inde(self): return self.hal("bulunma")
    @property
    def inden(self): return self.hal("ayrilma")
    @property
    def inin(self): return self.hal("ilgi")
    @property
    def ile(self): return self.hal("vasita")

    def bulunma_kisi(self, kisi):
        """Bankadayım / Bankadayız"""
        b = self.inde
        return b + "y" + u4(b) + {"ben": "m", "biz": "z"}[kisi]


class Fiil:
    """Fiil öbeği (son kelime fiil kökü). yum: ünlüyle başlayan ekte kök (git -> gid)."""

    def __init__(self, en, tr, yum=None):
        self.en = en
        self.tr = tr
        kel = tr.split(" ")
        self.on = " ".join(kel[:-1])
        self.kok = kel[-1]
        if yum:
            self.yk = yum
        elif self.kok == "git":
            self.yk = "gid"
        elif self.kok == "et":
            self.yk = "ed"
        else:
            self.yk = self.kok

    def _bir(self, kelime):
        return (self.on + " " + kelime).strip()

    # yardımcılar
    @property
    def _a(self): return u2(self.kok)
    @property
    def _y(self): return "y" if self.kok[-1] in UNLU else ""
    def _m(self, ek_e, ek_a): return self.kok + (ek_e if self._a == "e" else ek_a)
    def _v(self, ek_e, ek_a): return self.yk + self._y + (ek_e if self._a == "e" else ek_a)

    def emir(self): return self._bir(self.kok)
    def ucuncu_emir(self):
        return self._bir(self.kok + "s" + u4(self.kok) + "n")
    def olumsuz_emir(self): return self._bir(self._m("me", "ma"))
    def mastar(self): return self._bir(self._m("mek", "mak"))
    def gelecek(self, k):
        e = {"ben": ("eceğim", "acağım"), "biz": ("eceğiz", "acağız"), "o": ("ecek", "acak"),
             "sen?": ("ecek misin", "acak mısın"), "biz?": ("ecek miyiz", "acak mıyız")}[k]
        return self._bir(self._v(*e))
    def olumsuz_gelecek(self):
        return self._bir(self._m("meyeceğim", "mayacağım"))
    def istek(self, k):
        e = {"ben": ("eyim", "ayım"), "biz": ("elim", "alım")}[k]
        return self._bir(self._v(*e))
    def yeterlik(self, k):
        e = {"sen?": ("ebilir misin", "abilir misin"), "ben": ("ebilirim", "abilirim"),
             "biz": ("ebiliriz", "abiliriz"), "sen": ("ebilirsin", "abilirsin")}[k]
        return self._bir(self._v(*e))
    def olumsuz_yeterlik(self, k):
        e = {"ben": ("emem", "amam"), "biz": ("emeyiz", "amayız"), "sen": ("emezsin", "amazsın")}[k]
        return self._bir(self._v(*e))
    def gecmis(self, k):
        dt = "t" if self.kok[-1] in SERT else "d"
        i = u4(self.kok)
        g = self.kok + dt + i
        if k == "sen?":
            return self._bir(g + "n " + "m" + i)
        if k == "sen":
            return self._bir(g + "n")
        if k == "ben":
            return self._bir(g + "m")
        if k == "biz":
            return self._bir(g + "k")
        raise KeyError(k)
    def olumsuz_gecmis(self, k):
        e = {"ben": ("medim", "madım"), "biz": ("medik", "madık")}[k]
        return self._bir(self._m(*e))
    def sart(self, k):
        e = {"biz": ("sek", "sak"), "sen": ("sen", "san")}[k]
        return self._bir(self._m(*e))
    def isim(self, ek):
        """-me/-ma ile başlayan isim-fiil ekleri: mem, men, memiz, meme, mesini, meye, meyi, mene, me"""
        ek_a = ek.replace("e", "a").replace("i", "ı")
        return self._bir(self.kok + (ek if self._a == "e" else ek_a))
