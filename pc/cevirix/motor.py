"""Okuma + çeviri motoru: ekrandan altyazıyı okur, çevirir, arayüze olay gönderir."""
import collections
import threading
import time

from . import ekran
from .gemini import Gemini, GeminiHatasi
from .metin import Dengeleyici, benzer, diyalog_mu


class Motor:
    def __init__(self, ayar, olaylar, sozluk):
        self.ayar = ayar
        self.olaylar = olaylar          # queue.Queue -> arayüz
        self.sozluk = sozluk
        self.gemini = Gemini()
        self.calisiyor = False
        self.chiaki_pid = None
        self._hwnd = None
        self._hwnd_zaman = 0.0
        self._bekleyen = None
        self._kosul = threading.Condition()
        self._onbellek = collections.OrderedDict()
        self._baglam = collections.deque(maxlen=3)
        self.gosterilen_tr = ""
        self._sizinti = 0
        self._okuyucu = None
        self._kusak = 0
        threading.Thread(target=self._ceviri_dongusu, daemon=True).start()

    # ------------------------------------------------------------ dış arayüz
    def baslat(self):
        if self.calisiyor:
            return
        self.calisiyor = True
        self._kusak += 1
        threading.Thread(target=self._okuma_dongusu, args=(self._kusak,), daemon=True).start()

    def durdur(self):
        self.calisiyor = False
        self._kusak += 1
        self.olaylar.put(("temizle",))
        self.olaylar.put(("durum", "Çeviri durdu"))

    def hedef(self):
        """PS5 görüntüsünün ekrandaki yeri: chiaki-ng penceresi, bulunamazsa tüm ekran."""
        simdi = time.time()
        if simdi - self._hwnd_zaman > 1.0:
            self._hwnd_zaman = simdi
            self._hwnd = ekran.pencere_bul(pid=self.chiaki_pid)
        if self._hwnd:
            alan = ekran.istemci_alani(self._hwnd)
            if alan:
                return alan, True
            self._hwnd = None
        return ekran.birincil_ekran(), False

    def altyazi_alani(self):
        (hx, hy, hw, hh), bulundu = self.hedef()
        sl, su, sg, sy = self.ayar["alan"]
        return (hx + int(sl * hw), hy + int(su * hh), max(40, int(sg * hw)), max(20, int(sy * hh))), bulundu

    # ------------------------------------------------------------ okuma
    def _okuma_dongusu(self, kusak):
        from .okuyucu import Okuyucu, degisti_mi
        try:
            if self._okuyucu is None:
                self.olaylar.put(("durum", "Yazı okuyucu hazırlanıyor…"))
                self._okuyucu = Okuyucu()
            yak = ekran.Yakalayici()
        except Exception as e:
            self.calisiyor = False
            self.olaylar.put(("hata", f"Yazı okuyucu açılamadı: {e}"))
            return

        deng = Dengeleyici()
        onceki_kare = None
        onceki_metin = ""
        son_gorulme = 0.0
        temiz = True
        son_durum = None

        while self.calisiyor and kusak == self._kusak:
            bas = time.time()
            try:
                (x, y, w, h), bulundu = self.altyazi_alani()
                durum = "PS5 görüntüsü okunuyor" if bulundu else "chiaki-ng penceresi yok, tüm ekran okunuyor"
                if durum != son_durum:
                    self.olaylar.put(("durum", durum))
                    son_durum = durum
                kare = yak.al(x, y, w, h)
                if degisti_mi(onceki_kare, kare):
                    metin = self._okuyucu.oku(kare)
                    onceki_kare = kare
                    onceki_metin = metin
                else:
                    metin = onceki_metin

                if metin and not diyalog_mu(metin):
                    metin = ""
                # Kendi Türkçe yazımızı okuyorsak (yakalamadan gizleme çalışmıyorsa) yok say
                if metin and self.gosterilen_tr and benzer(metin, self.gosterilen_tr) > 0.7:
                    self._sizinti += 1
                    if self._sizinti == 3:
                        self.olaylar.put(("sizinti",))
                    metin = ""

                if metin:
                    son_gorulme = time.time()
                    temiz = False
                    yeni = deng.besle(metin)
                    if yeni:
                        self._gonder(yeni)
                elif not temiz and time.time() - son_gorulme > float(self.ayar["gizleme_sn"]):
                    temiz = True
                    deng.sifirla()
                    self.gosterilen_tr = ""
                    self.olaylar.put(("temizle",))
            except Exception as e:
                self.olaylar.put(("durum", f"Okuma hatası: {e}"))
                time.sleep(1.0)
            bekle = int(self.ayar["okuma_araligi_ms"]) / 1000.0 - (time.time() - bas)
            if bekle > 0:
                time.sleep(bekle)

    # ------------------------------------------------------------ çeviri
    def _gonder(self, metin):
        with self._kosul:
            self._bekleyen = metin   # yalnız en yenisi önemli
            self._kosul.notify()

    def _ceviri_dongusu(self):
        while True:
            with self._kosul:
                while self._bekleyen is None:
                    self._kosul.wait()
                en, self._bekleyen = self._bekleyen, None
            tr = self._cevir(en)
            if tr and self.calisiyor:
                self.gosterilen_tr = tr
                self.olaylar.put(("altyazi", tr, en))

    def _cevir(self, en):
        if en in self._onbellek:
            self._onbellek.move_to_end(en)
            return self._onbellek[en]
        tr = self.sozluk.cevir(en)
        kaynak = "sözlük"
        if tr is None:
            anahtar = (self.ayar.get("gemini_anahtar") or "").strip()
            if not anahtar:
                self.olaylar.put(("hata", "Gemini anahtarı girilmemiş. Ayarlar'a anahtarı yazın."))
                return None
            try:
                tr, model = self.gemini.cevir(anahtar, self.ayar.get("gemini_model"), en,
                                              list(self._baglam), self.ayar.get("terimler", ""))
                kaynak = model
                if model != self.ayar.get("gemini_model"):
                    self.ayar["gemini_model"] = model
                    self.olaylar.put(("model", model))
            except GeminiHatasi as e:
                if e.kod == 429:
                    msg = "Gemini kotası doldu, biraz bekleyin (ücretsiz anahtarda dakika sınırı var)."
                elif e.kod in (400, 401, 403) and "key" in str(e).lower():
                    msg = "Gemini anahtarı geçersiz. Ayarlar'dan kontrol edin."
                else:
                    msg = f"Çeviri hatası: {e}"
                self.olaylar.put(("hata", msg))
                return None
        if not tr:
            return None
        self._onbellek[en] = tr
        if len(self._onbellek) > 600:
            self._onbellek.popitem(last=False)
        self._baglam.append((en, tr))
        self.olaylar.put(("durum", f"Çevrildi ({kaynak})"))
        return tr
