# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Nino contributors
# Çevirix PC uyarlaması: Nino'nun GTA 6 telefon ve harita kartı okuması (PhoneLocator, PhoneChat, MapCard,
# ScreenItems, FrameTrace, RgbImage) Python'a çevrildi. Kutular hep karenin oranı (0-1): (sol, üst, sağ, alt).
"""GTA 6 oyun içi telefon mesajları ve harita/görev kartı.

Telefon sürümündeki GtaReader'ın birebir karşılığı: oyundaki telefonu bulur, sohbeti okur, mesajları
çevirip telefonun yanında balonlar olarak gösterir; harita kartının Türkçesini kartın altına koyar.
Öğeler Çevirix TV'nin "screen" biçimindedir (TV'ye aynen gider, bilgisayarda da aynı çizilir).
"""
import json
import math
import os
import re
import threading
import time

import numpy as np

# ================================================================ yardımcılar
_SENTENCE_END = set(".!?…")
_CLOSING = set("\"'”’)]»")


def anahtar(text):
    """Küçük harf; harf ve rakam dışı her şey boşluk; boşluklar teke iner."""
    out, bosluk = [], False
    for ch in text.lower():
        if ch.isalnum():
            if bosluk and out:
                out.append(" ")
            out.append(ch)
            bosluk = False
        else:
            bosluk = True
    return "".join(out)


def _levenshtein(a, b):
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if a[i - 1] == b[j - 1] else 1))
        prev = cur
    return prev[len(b)]


def benzerlik(a, b):
    x, y = anahtar(a), anahtar(b)
    if not x or not y:
        return 0.0
    return 1.0 - _levenshtein(x, y) / max(len(x), len(y))


def cumle_bitti(text):
    t = text.rstrip()
    i = len(t) - 1
    while i >= 0 and t[i] in _CLOSING:
        i -= 1
    return i >= 0 and t[i] in _SENTENCE_END


def sozcukler(text):
    return [t for t in re.split(r"\s+", text) if t]


def turkce_harf_var(text):
    return any(c in "ğışçöüĞİŞÇÖÜ" for c in text)


def yuvarla(v):
    """Kotlin roundToInt (yarım yukarı)."""
    return int(math.floor(v + 0.5))


def kutu_birlesim(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def kutu_dict(b):
    return {"left": b[0], "top": b[1], "right": b[2], "bottom": b[3]}


def bolgeden_kareye(bolge, b):
    """bolge=(üst, alt, sol, sağ); b bölgeye göre kutu -> kareye göre."""
    t, bt, l, r = bolge
    w, h = r - l, bt - t
    return (l + b[0] * w, t + b[1] * h, l + b[2] * w, t + b[3] * h)


def kareden_bolgeye(bolge, b):
    t, bt, l, r = bolge
    w, h = r - l, bt - t
    return ((b[0] - l) / w, (b[1] - t) / h, (b[2] - l) / w, (b[3] - t) / h)


def _hex(rgb):
    return "#%06x" % (rgb & 0xFFFFFF)


def _parlaklik(rgb):
    return (((rgb >> 16) & 0xFF) * 299 + ((rgb >> 8) & 0xFF) * 587 + (rgb & 0xFF) * 114) // 1000


def mavi_mi(rgb):
    r, g, b = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
    return b >= 100 and b - r >= 10 and b - g >= 8


# ================================================================ görüntüler
class RgbResim:
    """Küçük renkli görüntü (telefonu bulmak için 240x135)."""
    W, H = 240, 135

    def __init__(self, rgb):
        self.rgb = rgb.astype(np.int32)
        self.height, self.width = rgb.shape[:2]
        self.mn = self.rgb.min(axis=2)
        self.mx = self.rgb.max(axis=2)
        self.spread = self.mx - self.mn
        self.luma = (self.rgb[:, :, 0] * 299 + self.rgb[:, :, 1] * 587 + self.rgb[:, :, 2] * 114) // 1000
        self.beyaz = (self.mn >= 118) & (self.spread <= 45)
        self.koyu_ekran = (self.mn + self.spread) <= 75

    @classmethod
    def kareden(cls, bgr):
        h, w = bgr.shape[:2]
        ys = np.clip(((np.arange(cls.H) + 0.5) * h / cls.H).astype(int), 0, h - 1)
        xs = np.clip(((np.arange(cls.W) + 0.5) * w / cls.W).astype(int), 0, w - 1)
        return cls(bgr[ys][:, xs][:, :, ::-1])

    def olcekli(self, f):
        return RgbResim(np.clip(np.floor(self.rgb * f + 0.5), 0, 255).astype(np.uint8))

    def _dilim(self, box):
        x0 = min(max(int(box[0] * self.width), 0), self.width - 1)
        x1 = min(max(int(box[2] * self.width), 0), self.width - 1)
        y0 = min(max(int(box[1] * self.height), 0), self.height - 1)
        y1 = min(max(int(box[3] * self.height), 0), self.height - 1)
        if x1 < x0 or y1 < y0:
            return None
        return self.rgb[y0:y1 + 1, x0:x1 + 1].reshape(-1, 3)

    def ortalama(self, box):
        p = self._dilim(box)
        if p is None or len(p) == 0:
            return None
        r, g, b = (int(v) for v in p.mean(axis=0))
        return (r << 16) | (g << 8) | b

    def balon(self, box):
        """Kutudaki noktaların parlak yarısının ortalaması (koyu yazı atılır)."""
        p = self._dilim(box)
        if p is None or len(p) == 0:
            return None
        lum = p[:, 0] * 299 + p[:, 1] * 587 + p[:, 2] * 114
        parlak = p[np.argsort(lum, kind="stable")][len(p) // 2:]
        r, g, b = (int(v) for v in parlak.mean(axis=0))
        return (r << 16) | (g << 8) | b


def gri(bgr):
    b = bgr.astype(np.int32)
    return ((b[:, :, 2] * 299 + b[:, :, 1] * 587 + b[:, :, 0] * 114) // 1000).astype(np.uint8)


def kirp(bolge, w, h):
    """Bölgenin piksel kırpması (sol, üst, en, boy); 16 pikselden küçükse None."""
    t, bt, l, r = bolge

    def cift(v):
        return (yuvarla(v) // 2) * 2
    x = min(max(cift(l * w), 0), w)
    y = min(max(cift(t * h), 0), h)
    ww = min(cift((r - l) * w), ((w - x) // 2) * 2)
    hh = min(cift((bt - t) * h), ((h - y) // 2) * 2)
    if ww < 16 or hh < 16:
        return None
    return x, y, ww, hh


def _sinirla(bolge):
    t, bt, l, r = bolge
    w = min(max(r - l, 0.05), 1.0)
    h = min(max(bt - t, 0.05), 1.0)
    l = min(max(l, 0.0), 1.0 - w)
    t = min(max(t, 0.0), 1.0 - h)
    return (t, t + h, l, l + w)


def iz(gri_duzlem, rect=None):
    """64x12 gri iz: her hücrenin ortasındaki piksel."""
    h, w = gri_duzlem.shape[:2]
    x0, y0, rw, rh = rect if rect else (0, 0, w, h)
    xs = x0 + np.clip(((np.arange(64) + 0.5) * rw / 64).astype(int), 0, rw - 1)
    ys = y0 + np.clip(((np.arange(12) + 0.5) * rh / 12).astype(int), 0, rh - 1)
    return gri_duzlem[ys][:, xs].astype(np.int16).ravel()


def degisim_payi(a, b):
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return float((np.abs(a[:n] - b[:n]) > 16).mean())


# ================================================================ telefonu bulma
class TelefonBulucu:
    HOLD_MS = 3000
    GUESS_W = 0.21

    def __init__(self):
        self.son = None
        self.son_gorulme = -10 ** 12

    def bul_veya_tut(self, img, simdi):
        bulunan = self.bul(img)
        if bulunan:
            self.son, self.son_gorulme = bulunan, simdi
            return bulunan
        p = self.son
        if p and not p["tahmin"] and simdi - self.son_gorulme <= self.HOLD_MS and self.hala_orada(img, p):
            return p
        return None

    # --------------------------------------------------------------
    @staticmethod
    def parlak_yuzdelik(img):
        hist = np.bincount(np.clip(img.luma, 0, 255).ravel(), minlength=256)
        hedef = int(img.width * img.height * 0.975)
        acc = np.cumsum(hist)
        idx = np.nonzero(acc >= hedef)[0]
        return int(idx[0]) if len(idx) else 255

    def bul(self, img):
        r = self._ara(img, False)
        if r:
            return r
        p = self.parlak_yuzdelik(img)
        if 40 <= p <= 117:
            r = self._ara(img.olcekli(225.0 / p), False)
            if r:
                return r
        if p > 117:
            r = self._ara(img.olcekli(1.3), False)
            if r:
                return r
        r = self._ara(img, True)
        if r:
            return r
        return self._ara(img, True, govde=img.olcekli(1.3)) if p > 117 else None

    @staticmethod
    def _seritler(img, y, koyu, min_w, max_w):
        if koyu:
            kenar = img.koyu_ekran[y]
            ya = kenar | (img.mn[y] >= 110)
        else:
            kenar = img.beyaz[y]
            ya = kenar
        # ya-maskesindeki ardışık öbekler; koyu ekranda şerit bir koyu noktayla başlamalı
        m = np.concatenate(([False], ya, [False]))
        d = np.diff(m.astype(np.int8))
        basl, son = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1
        parcalar = []
        for b, s in zip(basl, son):
            if koyu:
                ilk = np.nonzero(kenar[b:s + 1])[0]
                if len(ilk) == 0:
                    continue
                b = b + int(ilk[0])
            parcalar.append((int(b), int(s)))
        out = []
        g0 = 0
        while g0 < len(parcalar):
            g1 = g0
            while g1 + 1 < len(parcalar) and parcalar[g1 + 1][0] - parcalar[g1][1] - 1 <= 3:
                g1 += 1
            for i in range(g0, g1 + 1):
                for j in range(i, g1 + 1):
                    w = parcalar[j][1] - parcalar[i][0] + 1
                    if w > max_w:
                        break
                    if w >= min_w:
                        out.append((parcalar[i][0], parcalar[j][1]))
            g0 = g1 + 1
        return out

    def _ara(self, img, koyu, govde=None):
        govde = govde or img
        W, H = img.width, img.height
        min_w, max_w = yuvarla(W * 0.12), yuvarla(W * 0.30)
        satirlar = []
        toplam = 0
        for y in range(H):
            d = {}
            for l, r in self._seritler(img, y, koyu, min_w, max_w):
                d.setdefault(l, []).append(r)
            satirlar.append(d)
            toplam += len(d)
        if toplam < 8:
            return None
        adaylar = []
        s = -0.30
        while s <= 0.3001:
            oy = {}
            for y in range(H):
                for k in {yuvarla(l - s * y) for l in satirlar[y]}:
                    oy[k] = oy.get(k, 0) + 1
            adaylar += [(s, k, v) for k, v in oy.items() if v >= 8]
            s += 0.02
        puanli = []
        for egim, x0, _ in adaylar:
            rows = self._uyan_satirlar(satirlar, egim, x0)
            if len(rows) >= 8:
                puanli.append((egim, rows))
        puanli.sort(key=lambda t: -len(t[1]))
        for egim, rows in puanli[:32]:
            r = self._dene(img, rows, egim, koyu, govde)
            if r:
                return r
        return None

    @staticmethod
    def _uyan_satirlar(satirlar, egim, x0):
        genislik = {}
        bulunan = []
        for y, d in enumerate(satirlar):
            l = x0 + egim * y
            ws = set()
            for k in range(math.ceil(l - 1.5), math.floor(l + 1.5) + 1):
                for r in d.get(k, ()):
                    ws.add(yuvarla(r - l))
            if not ws:
                continue
            bulunan.append((y, ws))
            for w in ws:
                genislik[w] = genislik.get(w, 0) + 1
        if not genislik:
            return []
        en_iyi = max(genislik, key=lambda k: sum(genislik.get(k + i, 0) for i in (-1, 0, 1)) * 1000 + k)
        rows = []
        for y, ws in bulunan:
            if any(w >= en_iyi - 2 for w in ws):
                l = yuvarla(x0 + egim * y)
                rows.append((y, l, l + en_iyi))
        return TelefonBulucu._obek(rows)

    @staticmethod
    def _obek(rows):
        if not rows:
            return rows
        en_bosluk = int(RgbResim.H * 0.20)
        gruplar = []
        for r in rows:
            if gruplar and r[0] - gruplar[-1][-1][0] <= en_bosluk:
                gruplar[-1].append(r)
            else:
                gruplar.append([r])
        g = max(gruplar, key=len)
        aralik = g[-1][0] - g[0][0] + 1
        return g if len(g) >= aralik * 0.30 else []

    @staticmethod
    def _dene(img, rows, egim, koyu, govde_img):
        if len(rows) < 8:
            return None
        W, H = float(img.width), float(img.height)
        ust, alt = rows[0][0], rows[-1][0]
        sol = max(min(r[1] for r in rows), 0)
        sag = min(max(r[2] for r in rows), img.width - 1)
        boy = (alt - ust + 1) / H
        if not 0.38 <= boy <= 0.86:
            return None
        oran = (alt - ust + 1) / (rows[0][2] - rows[0][1] + 1)
        if not 1.2 <= oran <= 2.6:
            return None
        orta = (sol + sag + 1) / 2.0 / W
        if not 0.30 <= orta <= 0.80:
            return None
        if ust / H < 0.04:
            return None

        def yan(r, dx):
            x = r[1] + dx if dx < 0 else r[2] + dx
            return x if 0 <= x < img.width else None

        n = float(len(rows))
        if not koyu:
            koyu_yan = beyaz_degil = cerceve = 0
            for r in rows:
                y = r[0]
                xs = [x for x in (yan(r, -2), yan(r, 2)) if x is not None]
                if len(xs) == 2 and all(img.mn[y, x] < 90 for x in xs):
                    koyu_yan += 1
                if all(not img.beyaz[y, x] for x in xs):
                    beyaz_degil += 1
                yakin = [x for i in (1, 2, 3) for x in (yan(r, -i), yan(r, i)) if x is not None]
                if any(img.mn[y, x] < 90 for x in yakin):
                    cerceve += 1
            if koyu_yan / n < 0.70 and not (beyaz_degil / n >= 0.85 and cerceve / n >= 0.35):
                return None
        else:
            def govde_var(r, yon):
                y0, y1 = max(0, r[0] - 3), min(img.height - 1, r[0] + 3)
                for i in range(1, 11):
                    x = yan(r, yon * i)
                    if x is not None and (govde_img.mn[y0:y1 + 1, x] >= 85).any():
                        return True
                return False
            govde = sum(1 for r in rows if govde_var(r, -1) and govde_var(r, 1))
            yazi = 0
            for r in rows:
                y0, y1 = max(0, r[0] - 1), min(img.height - 1, r[0] + 1)
                x0, x1 = max(0, r[1]), min(img.width - 1, r[2])
                if (img.mn[y0:y1 + 1, x0:x1 + 1] >= 110).any():
                    yazi += 1
            if govde / n < 0.70 or yazi / n < 0.15:
                return None
            if (alt + 1) / H > 0.96:
                return None
        return {"box": (sol / W, ust / H, (sag + 1) / W, (alt + 1) / H), "egim": egim, "koyu": koyu, "tahmin": False}

    @staticmethod
    def hala_orada(img, p):
        b = p["box"]
        x0 = min(max(int(b[0] * img.width), 0), img.width - 1)
        x1 = min(max(int(b[2] * img.width), 0), img.width - 1)
        y0 = min(max(int(b[1] * img.height), 0), img.height - 1)
        y1 = min(max(int(b[3] * img.height), 0), img.height - 1)
        maske = img.koyu_ekran if p["koyu"] else img.beyaz
        alan = maske[y0:y1 + 1, x0:x1 + 1]
        if alan.size == 0:
            return False
        return float(alan.mean()) >= (0.50 if p["koyu"] else 0.45)


# ================================================================ telefon yazıları
HEADER = 0.07
_BUTTONS = {"back", "done", "edit", "cancel", "close", "next", "menu", "select", "ok", "send"}
_LABELS = ["new message", "typing", "delivered", "read", "seen", "today", "yesterday", "sent", "now"]
_TIME = re.compile(r"^\d{1,2}[:.]\d{2}(\s?[ap]m)?$", re.IGNORECASE)
APP_WORDS = ["buckme", "ryde", "rydeme", "change destination", "book ryde", "steps today", "calories", "workout"]
_ENTITY = re.compile(r"&[a-z]+;|&#\d+;", re.IGNORECASE)
_APP_LINES = {"change destination", "book ryde", "choose ryde", "standard ryde", "trip details", "buckme", "rydeme"}
_PRICE = re.compile(r"\(\s*\$?\s*[\d.,]+\s*\)")
_NON_WORD = re.compile(r"[^\w]+|_")


def _kirp_harf_disi(s, harf_rakam=False):
    def tamam(c):
        return c.isalnum() if harf_rakam else c.isalpha()
    b, e = 0, len(s)
    while b < e and not tamam(s[b]):
        b += 1
    while e > b and not tamam(s[e - 1]):
        e -= 1
    return s[b:e]


def dugme_mi(s):
    return _kirp_harf_disi(s.lower().strip()) in _BUTTONS


def etiket_mi(s):
    l = _kirp_harf_disi(s.lower().strip(), True)
    return bool(_TIME.match(l)) or any(l == it or (l.startswith(it + " ") and len(l) < len(it) + 8) for it in _LABELS)


def uygulama_yazisi_mi(s):
    l = s.lower().strip()
    return any(w in l for w in APP_WORDS)


def tam_uygulama_satiri(s):
    l = _NON_WORD.sub(" ", _PRICE.sub(" ", s.lower().strip())).strip()
    return l in _APP_LINES


def uygulama_adi(lines):
    for l in (x.lower().strip() for x in lines):
        if "buckme" in l:
            return "BuckMe"
        if "ryde" in l:
            return "Ryde"
    return None


def cumle_mi(s):
    return len(sozcukler(s)) >= 3 or cumle_bitti(s)


def temizle(s):
    s = _ENTITY.sub(" ", s)
    s = "".join(c for c in s if c.isalnum() or c.isspace() or c in ".,!?;:'\"-()$%&/’…")
    out = []
    for t in sozcukler(s):
        if not out or out[-1].lower() != t.lower():
            out.append(t)
    return " ".join(out)


def benzer_mesaj(a, b):
    x, y = anahtar(a), anahtar(b)
    if x == y:
        return True
    if x and y and (x.startswith(y) or y.startswith(x) or x.endswith(y) or y.endswith(x)):
        return True
    return benzerlik(a, b) >= 0.75


def _mesaj(text, box, giden, renk):
    return {"text": text, "box": box, "giden": giden, "renk": renk}


def telefon_ekrani(satirlar, renk_al=lambda b: None):
    """Okunan satırlar (kutular telefon ekranına göre) -> ("chat", başlık, mesajlar, çevrilecekler) |
    ("list",) | ("app", ad, satırlar) | ("map",) | ("none",)"""
    ls = sorted([l for l in satirlar if l[1] is not None and l[0].strip()], key=lambda l: l[1][1])
    if not ls:
        return ("none",)
    texts = [l[0] for l in ls]
    if any("recenter" in t.lower() for t in texts):
        return ("map",)
    if liste_mi(ls):
        return ("list",)
    ad = uygulama_adi(texts)
    if ad:
        return ("app", ad, [_mesaj(temizle(t), b, False, renk_al(b)) for t, b in ls
                            if not etiket_mi(t) and not dugme_mi(t)])
    bas_t, hb = ls[0]
    if abs((hb[0] + hb[2]) / 2 - 0.5) > 0.12 or dugme_mi(bas_t) or hb[1] > 0.20:
        return ("none",)
    if len(ls) > 1:
        nb = ls[1][1]
        if (abs((nb[0] + nb[2]) / 2 - (hb[0] + hb[2]) / 2) < 0.03 and nb[1] - hb[3] < (hb[3] - hb[1]) * 0.8
                and abs((nb[2] - nb[0]) - (hb[2] - hb[0])) < 0.05):
            return ("none",)
    kesim = max(HEADER, hb[3]) + 0.012
    govde = [(t, b) for t, b in ls[1:] if b[1] >= kesim and b[3] <= 0.985 and not etiket_mi(t) and not dugme_mi(t)]
    mesajlar = grupla(govde, renk_al)
    if not any(cumle_mi(m["text"]) for m in mesajlar):
        return ("none",)
    cevrilecek = []
    for i, m in enumerate(mesajlar):
        b = m["box"]
        son_yarim = i == len(mesajlar) - 1 and b[3] > 0.93 and not cumle_bitti(m["text"]) and b[3] - b[1] > 0.06
        ilk_harf = next((c for c in m["text"] if c.isalpha()), "")
        ust_kesik = i == 0 and b[1] < kesim + 0.02 and ilk_harf.islower()
        if not son_yarim and not ust_kesik:
            cevrilecek.append(i)
    return ("chat", temizle(bas_t), mesajlar, cevrilecek)


def liste_mi(ls):
    uc = sum(1 for t, _ in ls if t.rstrip().endswith("…") or t.rstrip().endswith("..."))
    if uc >= 2:
        return True
    cift = 0
    for i in range(len(ls) - 1):
        a, b = ls[i][1], ls[i + 1][1]
        ad = len(sozcukler(ls[i][0])) <= 3 and not cumle_bitti(ls[i][0])
        if ad and abs(a[0] - b[0]) < 0.03 and -0.005 <= b[1] - a[3] <= (a[3] - a[1]) * 0.6 and a[0] < 0.45:
            cift += 1
    return cift >= 3


def grupla(satirlar, renk_al):
    gruplar = []
    for t, b in satirlar:
        if gruplar:
            p = gruplar[-1][-1][1]
            yakin = (b[1] - p[3] < 0.6 * max(p[3] - p[1], b[3] - b[1])
                     and (abs(b[0] - p[0]) < 0.03 or abs(b[2] - p[2]) < 0.03))
            if yakin:
                gruplar[-1].append((t, b))
                continue
        gruplar.append([(t, b)])
    out = []
    for i, g in enumerate(gruplar):
        tek = (len(g) == 1 and len(sozcukler(g[0][0])) == 1 and g[0][0][:1].isupper()
               and not cumle_bitti(g[0][0]))
        if tek and i + 1 < len(gruplar):
            continue  # gönderen adı
        box = g[0][1]
        for _, b in g[1:]:
            box = kutu_birlesim(box, b)
        renk = renk_al(box)
        giden = box[0] > 0.2 or (renk is not None and mavi_mi(renk))
        metin = temizle(" ".join(t.strip() for t, _ in g))
        if metin.strip():
            out.append(_mesaj(metin, box, giden, renk))
    return out


# ================================================================ ekran öğeleri ve kalkma histerezisi
class OgeTutucu:
    def __init__(self):
        self.alan = None
        self._ref = None
        self._kacan = 0
        self._ilk_kacis = 0

    def goruldu(self, alan, iz_):
        self.alan, self._ref, self._kacan = alan, iz_, 0

    def kayip(self, iz_, simdi):
        if self.alan is None:
            return False
        if self._kacan == 0:
            self._ilk_kacis = simdi
        self._kacan += 1
        if self._kacan < 3 or simdi - self._ilk_kacis < 4000:
            return False
        degisti = self._ref is None or iz_ is None or degisim_payi(self._ref, iz_) >= 0.05
        if not degisti:
            return False
        self.sifirla()
        return True

    def sifirla(self):
        self.alan, self._ref, self._kacan = None, None, 0


class EkranTahtasi:
    TURLER = ("telefon", "harita")

    def __init__(self):
        self._kilit = threading.RLock()
        self.tut = {t: OgeTutucu() for t in self.TURLER}
        self.ogeler = {}

    def goruldu(self, tur, alan, iz_, liste=None):
        with self._kilit:
            self.tut[tur].goruldu(alan, iz_)
            if liste is not None:
                self.ogeler[tur] = liste

    def goster(self, tur, liste):
        with self._kilit:
            self.ogeler[tur] = liste

    def kayip(self, tur, iz_, simdi):
        with self._kilit:
            if not self.tut[tur].kayip(iz_, simdi):
                return False
            self.ogeler.pop(tur, None)
            return True

    def birak(self, tur):
        with self._kilit:
            vardi = self.tut[tur].alan is not None or bool(self.ogeler.get(tur))
            self.tut[tur].sifirla()
            self.ogeler.pop(tur, None)
            return vardi

    def liste(self):
        with self._kilit:
            return [o for t in self.TURLER for o in self.ogeler.get(t, [])]

    def bos_mu(self):
        with self._kilit:
            return not any(self.ogeler.values())

    def sifirla(self):
        with self._kilit:
            for h in self.tut.values():
                h.sifirla()
            self.ogeler.clear()


# ================================================================ sohbet paneli
class SohbetPaneli:
    def __init__(self):
        self.baslik = None
        self.gosterilen = []
        self._aday = None

    def sohbet(self, ekran):
        _, baslik, mesajlar, cevrilecek = ekran
        msgs = [mesajlar[i] for i in cevrilecek]
        if self.baslik is not None and self.baslik != baslik:
            self.sifirla()
            self._aday, self.baslik = msgs, baslik
            return ("temizle",)
        self.baslik = baslik
        if self.gosterilen and self._ayni(self.gosterilen, msgs):
            kayma = max((abs(a["box"][1] - b["box"][1]) for a, b in zip(self.gosterilen, msgs)), default=0.0)
            if kayma > 0.02:
                self.gosterilen, self._aday = [], msgs
                return ("temizle",)
            return ("yok",)
        aday, self._aday = self._aday, msgs
        if aday is not None and msgs and self._ayni(aday, msgs):
            self.gosterilen = msgs
            return ("goster", baslik, msgs)
        return ("yok",)

    @staticmethod
    def _ayni(a, b):
        return len(a) == len(b) and all(benzer_mesaj(x["text"], y["text"]) for x, y in zip(a, b))

    def sifirla(self):
        self.baslik, self.gosterilen, self._aday = None, [], None


class TelefonHareketi:
    def __init__(self):
        self.sifirla()

    def telefon(self, box):
        if self._capa is None:
            self._capa = box
            return
        dx, dy = box[0] - self._capa[0], box[1] - self._capa[1]
        if abs(dx) >= 0.08 or abs(dy) >= 0.08:
            self._capa, self.ox, self.oy, self._yon = box, 0.0, 0.0, None
            return
        yon = ((1 if dx > 0 else -1) if abs(dx) > 0.009 else 0, (1 if dy > 0 else -1) if abs(dy) > 0.012 else 0)
        if yon == (0, 0):
            self._yon = None
            return
        if yon == self._yon:
            self.ox, self.oy = dx, dy
        self._yon = yon

    @property
    def panel_yerinde(self):
        return abs(self.ox) < 0.05 and abs(self.oy) < 0.05

    def sifirla(self):
        self._capa, self._yon, self.ox, self.oy = None, None, 0.0, 0.0


def telefondan_kareye(tel, b):
    w, h = tel[2] - tel[0], tel[3] - tel[1]
    return (tel[0] + b[0] * w, tel[1] + b[1] * h, tel[0] + b[2] * w, tel[1] + b[3] * h)


PANEL_W, PANEL_GAP = 0.27, 0.035


def sohbet_ogeleri(tel, baslik, ciftler, dx=0.0, dy=0.0):
    """Telefonun boş yanında dikey panel; gelenler solda, gidenler sağda (TV'deki balonlarla aynı)."""
    if not ciftler:
        return []
    sag_yan = (tel[0] + tel[2]) / 2 < 0.5
    sol = tel[2] + PANEL_GAP if sag_yan else tel[0] - PANEL_GAP - PANEL_W
    pl = min(max(sol, 0.0), 1.0 - PANEL_W) + dx
    ust = min(max(tel[1] + dy, 0.0), 0.9)
    alt = min(max(tel[3] + dy, ust + 0.1), 1.0)
    ogeler = [{"text": "", "box": kutu_dict((pl, ust, pl + PANEL_W, alt)), "backdrop": True, "alpha": 0.6}]
    baslik_h = 0.045
    ogeler.append({"text": baslik, "box": kutu_dict((pl + 0.01, ust + 0.01, pl + PANEL_W - 0.01, ust + 0.01 + baslik_h)),
                   "plain": True, "line": 0.03})
    satir_h = 0.028
    y = alt - 0.01
    balonlar = []
    for m, tr in reversed(ciftler):
        harf = len(tr)
        satir_basi = 26
        satirlar = max(1, (harf + satir_basi - 1) // satir_basi)
        h = satirlar * satir_h + 0.016
        ust0 = y - h
        if ust0 < ust + 0.02 + baslik_h:
            break
        w = min(max(min(harf, satir_basi) / satir_basi * (PANEL_W - 0.04), 0.08), PANEL_W - 0.04)
        bl = pl + PANEL_W - 0.01 - w if m["giden"] else pl + 0.01
        dolgu = m["renk"] if m["renk"] is not None else (0x2f7cf6 if m["giden"] else 0xe9e9eb)
        koyu = (_parlaklik(m["renk"]) < 140) if m["renk"] is not None else m["giden"]
        murekkep = 0xffffff if koyu else 0x111111
        balonlar.append({"text": tr, "box": kutu_dict((bl, ust0, bl + w, y)), "line": satir_h,
                         "fill": _hex(dolgu), "ink": _hex(murekkep), "alpha": 0.95, "side": True})
        y = ust0 - 0.008
    return ogeler + list(reversed(balonlar))


def uygulama_ogeleri(tel, ciftler):
    out = []
    for m, tr in ciftler:
        b = telefondan_kareye(tel, m["box"])
        dolgu = m["renk"] if m["renk"] is not None else 0xffffff
        out.append({"text": tr, "box": kutu_dict(b), "line": b[3] - b[1], "fill": _hex(dolgu),
                    "ink": _hex(0xffffff if _parlaklik(dolgu) < 140 else 0x111111), "alpha": 0.95})
    return out


# ================================================================ harita kartı
HARITA_BOLGESI = (0.03, 0.95, 0.30, 1.0)   # (üst, alt, sol, sağ); kart hep ekranın sağ tarafında
_DISTANCE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:km|mi|m|ft|yd)\b", re.IGNORECASE)
_PLACE = ["customs", "store", "shop", "bar", "club", "motel", "hotel", "diner", "garage", "ammu", "station",
          "market", "liquor", "pawn", "salon", "tattoo", "barber", "bank", "casino", "restaurant", "cafe", "gym",
          "dealership", "autos", "motors", "pharmacy", "clinic", "hospital", "boutique", "mart", "burger", "pizza", "taco"]
_FIXES = [("işaretli fatura", "işaretli banknot"), ("narkotik", "uyuşturucu"), ("Narkotik", "Uyuşturucu")]
MAP_BUTTONS = {"recenter", "2d view", "3d view", "add marker", "remove marker", "set destination",
               "remove destination", "close menu", "view on map", "markers", "cinematic"}


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def harita_ekrani_mi(lines):
    gorulen = {b for l in map(_norm, lines) for b in MAP_BUTTONS if b in l}
    return len(gorulen) >= 2


def kart_satiri(s):
    s = _DISTANCE.sub(" ", s)
    i = 0
    while i < len(s) and not s[i].isalnum() and s[i] not in "\"'":
        i += 1
    return re.sub(r"\s+", " ", s[i:]).strip()


def _kart_cumlesi(s):
    return len(sozcukler(s)) >= 3 and sum(1 for c in s if c.islower()) >= 6


def _buyuk_baslik(s):
    harfler = [c for c in s if c.isalpha()]
    return bool(harfler) and all(c.isupper() for c in harfler)


def kart_bul(lines):
    """lines: [(metin, kutu)] kareye göre. -> {"baslik", "cumleler", "box"} ya da None"""
    ls = sorted([(kart_satiri(t), b) for t, b in lines if b is not None and b[0] >= 0.30], key=lambda l: l[1][1])
    ls = [l for l in ls if l[0]]
    bas = next((i for i, l in enumerate(ls) if _kart_cumlesi(l[0])), -1)
    if bas < 0:
        return None
    ilk = ls[bas]
    fb = ilk[1]
    govde = [ilk]
    for t, b in ls[bas + 1:]:
        p = govde[-1][1]
        if (b[1] - p[3] > 1.2 * (p[3] - p[1]) or abs(b[0] - fb[0]) > 0.03
                or (not _kart_cumlesi(t) and sum(1 for c in t if c.islower()) < 3)):
            break
        govde.append((t, b))
    ust = None
    if bas > 0:
        t, b = ls[bas - 1]
        if _buyuk_baslik(t) and fb[1] - b[3] < 1.5 * (fb[3] - fb[1]) and abs(b[0] - fb[0]) < 0.05:
            ust = (t, b)
    box = govde[0][1]
    for _, b in ([ust] if ust else []) + govde[1:]:
        box = kutu_birlesim(box, b)
    kart = {"baslik": ust[0] if ust else None, "cumleler": [t for t, _ in govde], "box": box}
    return kart if _kart_gosterilir(kart) else None


def _kart_gosterilir(c):
    hepsi = " ".join(([c["baslik"]] if c["baslik"] else []) + c["cumleler"])
    if turkce_harf_var(hepsi):
        return False
    if c["baslik"] is None and len(sozcukler(" ".join(c["cumleler"]))) < 6:
        return False
    if c["baslik"] is None and c["box"][0] > 0.6 and c["box"][1] < 0.32:
        return False
    if c["box"][1] < 0.1:
        return False
    return True


def kart_anahtari(c):
    return anahtar(" ".join(([c["baslik"]] if c["baslik"] else []) + c["cumleler"]))


def mekan_adi(baslik):
    l = baslik.lower()
    return any(re.search(rf"\b{p}\b", l) for p in _PLACE)


def tr_buyuk(s):
    return s.replace("i", "İ").replace("ı", "I").upper()


def kart_duzelt(t):
    for a, b in _FIXES:
        t = t.replace(a, b)
    return t


def kart_yeri(kart, satir, ust_cerceve=None, alt_cerceve=None):
    lh = min(max((kart[3] - kart[1]) / max(1, satir), 0.02), 0.05)
    gerek = lh * (satir + 1)
    alti = (alt_cerceve if alt_cerceve is not None else kart[3]) + 0.008
    ustu = (ust_cerceve if ust_cerceve is not None else kart[1]) - 0.008
    if alti + gerek <= 0.98:
        return (kart[0], alti, kart[2], alti + gerek), lh
    if ustu - gerek >= 0.02:
        return (kart[0], ustu - gerek, kart[2], ustu), lh
    yer = max(0.98 - alti, ustu - 0.02)
    kucuk = max(yer / (satir + 1), 0.012)
    if 0.98 - alti >= ustu - 0.02:
        return (kart[0], alti, kart[2], 0.98), kucuk
    return (kart[0], 0.02, kart[2], ustu), kucuk


def kart_cercevesi(kirpma_gri, bolge, kart):
    """Kartın koyu çerçevesinin kareye göre (üst, alt) kenarı; koyu değilse o yan None."""
    b = kareden_bolgeye(bolge, kart)
    h, w = kirpma_gri.shape[:2]
    x0 = min(max(int(b[0] * w), 0), w - 1)
    x1 = min(max(int(b[2] * w), x0), w - 1)
    xs = np.arange(x0, x1 + 1, 2)

    def yuru(bas, adim):
        y = bas
        if not 0 <= y < h:
            return None
        ref = int(np.sort(kirpma_gri[y, xs])[len(xs) // 2])

        def koyu(yy):
            v = kirpma_gri[yy, xs].astype(np.int16)
            return ((v < 130) & (np.abs(v - ref) <= 20)).sum() >= len(xs) * 0.6
        if not koyu(y):
            return None
        while 0 <= y + adim < h and koyu(y + adim):
            y += adim
        return y

    t, bt, _, _ = bolge
    ust = yuru(int(b[1] * h) - 2, -1)
    alt = yuru(int(b[3] * h) + 2, 1)
    return (None if ust is None else t + ust / h * (bt - t),
            None if alt is None else t + (alt + 1) / h * (bt - t))


class HaritaDurumu:
    def __init__(self):
        self.gorulme = -10 ** 12

    def goruldu(self, simdi):
        self.gorulme = simdi

    def acik(self, simdi):
        return simdi - self.gorulme <= 5000

    def telefon_engelli(self, simdi):
        return simdi - self.gorulme <= 5000 + 8000

    def kart_araligi(self, simdi):
        return 1500 if simdi - self.gorulme <= 5000 + 10000 else 2000


# ================================================================ altyazı kuralları
class AltyaziKurallari:
    """GTA 6'da altyazıdan atılanlar: telefonda yakın zamanda görülen mesajlar ve uygulama satırları."""

    def __init__(self):
        self._kilit = threading.Lock()
        self.telefon = None
        self.telefon_zaman = -10 ** 12
        self.son_mesajlar = []

    def telefon_goruldu(self, box, simdi):
        if box is not None:
            with self._kilit:
                self.telefon, self.telefon_zaman = box, simdi

    def mesajlar(self, texts, simdi):
        with self._kilit:
            self.son_mesajlar += [(anahtar(t), simdi) for t in texts]
            del self.son_mesajlar[:-200]

    def telefon_etkin(self, simdi):
        return self.telefon is not None and simdi - self.telefon_zaman <= 5000

    def karartma(self, simdi):
        """Altyazı okunmadan önce siyaha boyanacak telefon kısmı."""
        with self._kilit:
            if not self.telefon_etkin(simdi):
                return None
            p = self.telefon
            return (p[0], p[1], p[2], max(p[3], min(p[3] + 0.15, 0.84)))

    def telefonun_icinde(self, box, simdi):
        p = self.karartma(simdi)
        if p is None:
            return False
        return box[0] >= p[0] - 0.02 and box[2] <= p[2] + 0.02 and box[1] >= p[1] - 0.02 and box[3] <= p[3] + 0.02

    def at(self, text, simdi):
        """True: altyazı satırı aslında telefondaki bir mesaj ya da uygulama yazısı."""
        if tam_uygulama_satiri(text) or uygulama_yazisi_mi(text):
            return True
        if len(sozcukler(text)) >= 3:
            k = anahtar(text)
            with self._kilit:
                self.son_mesajlar = [(m, z) for m, z in self.son_mesajlar if simdi - z <= 30000]
                return bool(k) and any(k in m or m in k for m, _ in self.son_mesajlar if len(m) >= 8)
        return False


# ================================================================ sabit sözlük ve hafıza
_SABIT = {
    "book ryde": "Ryde çağır", "change destination": "Hedefi değiştir", "your ryde is on the way": "Ryde'ın yolda",
    "your ryde has arrived": "Ryde'ın geldi", "cancel ryde": "Ryde'ı iptal et", "steps today": "Bugünkü adımlar",
    "calories": "Kalori", "workout": "Antrenman", "distance": "Mesafe", "daily goal": "Günlük hedef",
    "new message": "Yeni mesaj", "balance": "Bakiye", "send money": "Para gönder", "request money": "Para iste",
}


def sabit_turkce(text):
    k = re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", re.sub(r"\(.*?\)", "", text.lower()))).strip()
    return _SABIT.get(k)


class MesajHafizasi:
    """Telefon mesajlarının kalıcı çeviri hafızası (en çok 5000)."""

    def __init__(self, dosya):
        self.dosya = dosya
        self._kilit = threading.Lock()
        self._m = None

    def _yukle(self):
        if self._m is None:
            try:
                with open(self.dosya, encoding="utf-8") as f:
                    self._m = {k: v for k, v in json.load(f).items() if isinstance(v, str)}
            except Exception:
                self._m = {}
        return self._m

    def al(self, text):
        with self._kilit:
            return self._yukle().get(anahtar(text))

    def koy(self, text, tr):
        with self._kilit:
            m = self._yukle()
            if len(m) >= 5000:
                m.clear()
            m[anahtar(text)] = tr
            try:
                os.makedirs(os.path.dirname(self.dosya), exist_ok=True)
                tmp = self.dosya + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(m, f, ensure_ascii=False)
                os.replace(tmp, self.dosya)
            except Exception:
                pass


class KartHafizasi:
    def __init__(self):
        self.m = {}

    def al(self, c):
        k = kart_anahtari(c)
        if k in self.m:
            return self.m[k]
        if len(k) >= 12:
            for kk, v in self.m.items():
                if kk.startswith(k):
                    return v
        return None

    def koy(self, c, tr):
        k = kart_anahtari(c)
        if any(kk != k and kk.startswith(k) for kk in self.m):
            return
        self.m.pop(k, None)
        self.m[k] = tr
        while len(self.m) > 200:
            self.m.pop(next(iter(self.m)))


# ================================================================ okuyucu
class GtaOkuyucu:
    """Kareleri alır; telefon ve harita kartı çevirilerini ekran öğeleri olarak yayınlar.

    okuyucu.satirlar(bgr) -> [(metin, kutu)]  (kutu kırpmaya göre 0-1)
    cevir(metin) -> Türkçe ya da None
    yayinla(öğeler)  -> TV ve bilgisayar katmanı
    """
    LOCATE_MS = 300
    READ_EMPTY_MS = 600
    READ_SHOWN_MS = 1000

    def __init__(self, okuyucu, cevir, yayinla, hafiza_dosyasi):
        self.okuyucu, self.cevir_fn, self.yayinla_fn = okuyucu, cevir, yayinla
        self.kurallar = AltyaziKurallari()
        self.harita = HaritaDurumu()
        self.bulucu = TelefonBulucu()
        self.tahta = EkranTahtasi()
        self.panel = SohbetPaneli()
        self.hareket = TelefonHareketi()
        self.hafiza = MesajHafizasi(hafiza_dosyasi)
        self.kart_hafiza = KartHafizasi()
        self.oturum = {}
        self._son_bulma = self._son_okuma = self._son_harita = -10 ** 12
        self.telefon = None
        self.gta_goruldu = False
        self._son_liste = None

    # ------------------------------------------------------------ durum
    @property
    def durum(self):
        simdi = _ms()
        if self.telefon is not None:
            return f"Oyundaki telefon görüldü · {len(self.panel.gosterilen)} mesaj"
        if self.harita.acik(simdi):
            return "Harita açık"
        return "Oyundaki telefon aranıyor"

    def altyazi_bastir(self):
        return self.harita.acik(_ms())

    def sifirla(self):
        self.panel.sifirla()
        self.hareket.sifirla()
        self.tahta.sifirla()
        self.telefon = None
        self._yayinla()

    # ------------------------------------------------------------ kare
    def kare(self, bgr):
        simdi = _ms()
        # Harita ya da menü açık: telefon aranmaz, panel hemen kalkar
        if self.harita.telefon_engelli(simdi):
            self.telefon = None
            if self._telefonu_birak():
                self._yayinla()
            self._harita_bak(bgr, simdi)
            return
        if simdi - self._son_bulma < self.LOCATE_MS:
            self._harita_bak(bgr, simdi)
            return
        self._son_bulma = simdi
        rgb = RgbResim.kareden(bgr)
        p = self.bulucu.bul_veya_tut(rgb, simdi)
        self.telefon = p
        self.kurallar.telefon_goruldu(p["box"] if p else None, simdi)
        # Telefonun yeri bilindikten sonra: telefondaki yazılar harita kartı sanılmaz
        self._harita_bak(bgr, simdi)
        if self.harita.telefon_engelli(simdi):
            return
        if p is None:
            self._telefon_yok(bgr, simdi)
            return
        self.hareket.telefon(p["box"])
        aralik = self.READ_EMPTY_MS if not self.panel.gosterilen else self.READ_SHOWN_MS
        if simdi - self._son_okuma < aralik:
            return
        self._son_okuma = simdi
        b = p["box"]
        r = kirp((b[1], b[3], b[0], b[2]), bgr.shape[1], bgr.shape[0])
        if r is None:
            return
        x, y, w, h = r
        kirpma = bgr[y:y + h, x:x + w]
        self._telefonu_oku(p, kirpma, rgb, simdi)

    def _telefonu_birak(self):
        self.panel.sifirla()
        self.hareket.sifirla()
        return self.tahta.birak("telefon")

    def _telefon_yok(self, bgr, simdi):
        alan = self.tahta.tut["telefon"].alan
        if alan is None or simdi - self._son_okuma < self.READ_SHOWN_MS:
            return
        self._son_okuma = simdi
        r = kirp((alan[1], alan[3], alan[0], alan[2]), bgr.shape[1], bgr.shape[0])
        izi = iz(gri(bgr[r[1]:r[1] + r[3], r[0]:r[0] + r[2]])) if r else None
        if self.tahta.kayip("telefon", izi, simdi):
            self.panel.sifirla()
            self.hareket.sifirla()
            self._yayinla()

    def _telefonu_oku(self, p, kirpma, rgb, simdi):
        satirlar = self.okuyucu.satirlar(kirpma, buyut_en=640)
        if satirlar is None:
            return
        izi = iz(gri(kirpma))
        tel = p["box"]
        ekran = telefon_ekrani(satirlar, lambda b: rgb.balon(telefondan_kareye(tel, b)))
        tur = ekran[0]
        if tur in ("chat", "list", "app"):
            self.gta_goruldu = True
        if tur == "map":
            self.harita.goruldu(simdi)
            self._telefonu_birak()
            self._yayinla()
        elif tur == "list":
            if self._telefonu_birak():
                self._yayinla()
        elif tur == "none":
            if self.tahta.kayip("telefon", izi, simdi):
                self.panel.sifirla()
                self.hareket.sifirla()
                self._yayinla()
        elif tur == "app":
            satir = ekran[2]
            tr = self.hepsini_cevir([m["text"] for m in satir])
            self.kurallar.mesajlar([m["text"] for m in satir], simdi)
            ogeler = uygulama_ogeleri(tel, [(m, t) for m, t in zip(satir, tr) if t])
            self._telefon_ogeleri(tel, izi, ogeler)
            self._yayinla()
        else:
            self.kurallar.mesajlar([m["text"] for m in ekran[2]], simdi)
            adim = self.panel.sohbet(ekran)
            if adim[0] == "temizle":
                self.tahta.birak("telefon")
                self._yayinla()
            elif adim[0] == "goster":
                self._sohbeti_goster(tel, izi, adim[1], adim[2])
            else:
                gosteriliyor = bool(self.tahta.ogeler.get("telefon"))
                if gosteriliyor:
                    self.tahta.goruldu("telefon", tel, izi)
                    if not self.hareket.panel_yerinde:
                        self._sohbeti_goster(tel, izi, self.panel.baslik or "", self.panel.gosterilen)

    def _telefon_ogeleri(self, tel, izi, ogeler):
        if ogeler:
            self.tahta.goruldu("telefon", tel, izi, ogeler)
        else:
            self.tahta.birak("telefon")

    def _sohbeti_goster(self, tel, izi, baslik, msgs):
        tr = self.hepsini_cevir([m["text"] for m in msgs])
        ciftler = [(m, t) for m, t in zip(msgs, tr) if t]
        self._telefon_ogeleri(tel, izi, sohbet_ogeleri(tel, baslik, ciftler, self.hareket.ox, self.hareket.oy))
        self._yayinla()

    # ------------------------------------------------------------ çeviri
    def hepsini_cevir(self, texts):
        out = [self._bilinen(t) for t in texts]
        bilinmeyen = [i for i, v in enumerate(out) if v is None]
        if not bilinmeyen:
            return out
        sonuc = {}

        def is_(i):
            try:
                tr = self.cevir_fn(texts[i])
            except Exception:
                tr = None
            if tr:
                sonuc[i] = tr

        isler = [threading.Thread(target=is_, args=(i,), daemon=True) for i in bilinmeyen]
        # Aynı anda en çok 2 çeviri
        for k in range(0, len(isler), 2):
            for t in isler[k:k + 2]:
                t.start()
            for t in isler[k:k + 2]:
                t.join(20)
        for i, tr in sonuc.items():
            out[i] = tr
            self.oturum[texts[i]] = tr
            self.hafiza.koy(texts[i], tr)
        return out

    def _bilinen(self, t):
        return sabit_turkce(t) or self.hafiza.al(t) or self.oturum.get(t)

    # ------------------------------------------------------------ harita kartı
    def _harita_bak(self, bgr, simdi):
        if simdi - self._son_harita < self.harita.kart_araligi(simdi):
            return
        self._son_harita = simdi
        H, W = bgr.shape[:2]
        r = kirp(_sinirla(HARITA_BOLGESI), W, H)
        if r is None:
            return
        x, y, w, h = r
        kirpma = bgr[y:y + h, x:x + w]
        bolge = (y / H, (y + h) / H, x / W, (x + w) / W)
        satirlar = self.okuyucu.satirlar(kirpma)
        if satirlar is None:
            return
        hepsi = [(t, bolgeden_kareye(bolge, b) if b else None) for t, b in satirlar]
        texts = [t for t, _ in hepsi]
        if harita_ekrani_mi(texts):
            self.harita.goruldu(simdi)
            self.gta_goruldu = True
        kare_satirlari = [(t, b) for t, b in hepsi if not (b and self.kurallar.telefonun_icinde(b, simdi))]
        kart = kart_bul(kare_satirlari)
        kirpma_gri = gri(kirpma)
        if kart is None:
            alan = self.tahta.tut["harita"].alan
            if alan is not None:
                if self.tahta.kayip("harita", self._kart_izi(kirpma_gri, bolge, alan), simdi):
                    self._yayinla()
            return
        self.tahta.goruldu("harita", kart["box"], self._kart_izi(kirpma_gri, bolge, kart["box"]))
        tr = self.kart_hafiza.al(kart)
        if tr is None:
            tr = self._karti_cevir(kart)
            if tr is None:
                return
            self.kart_hafiza.koy(kart, tr)
        ust, alt = kart_cercevesi(kirpma_gri, bolge, kart["box"])
        satir = len(kart["cumleler"]) + (1 if kart["baslik"] else 0)
        box, lh = kart_yeri(kart["box"], satir, ust, alt)
        self.tahta.goster("harita", [{"text": tr, "box": kutu_dict(box), "line": lh, "card": True,
                                      "paragraphs": True}])
        self._yayinla()

    @staticmethod
    def _kart_izi(kirpma_gri, bolge, box):
        b = kareden_bolgeye(bolge, box)
        h, w = kirpma_gri.shape[:2]
        r = kirp((b[1], b[3], b[0], b[2]), w, h)
        return iz(kirpma_gri, r) if r else None

    def _karti_cevir(self, c):
        baslik = c["baslik"]
        parcalar = ([baslik] if baslik and not mekan_adi(baslik) else []) + c["cumleler"]
        gelen = self.hepsini_cevir(parcalar)
        if any(g is None for g in gelen):
            return None
        i = 0
        baslik_tr = None
        if baslik:
            if mekan_adi(baslik):
                baslik_tr = baslik
            else:
                baslik_tr = tr_buyuk(gelen[0])
                i = 1
        govde = " ".join(kart_duzelt(g) for g in gelen[i:])
        return "\n".join(x for x in (baslik_tr, govde) if x)

    # ------------------------------------------------------------ yayın
    def _yayinla(self):
        liste = self.tahta.liste()
        if liste != self._son_liste:
            self._son_liste = liste
            self.yayinla_fn(liste)


def _ms():
    return int(time.monotonic() * 1000)
