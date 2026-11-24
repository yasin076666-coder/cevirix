"""Okuma + çeviri motoru (telefondaki CevirixEngine + Translator'ın karşılığı).

- Ekrandan altyazıyı okur.
- Önbellekte varsa anında gösterir.
- Anında çeviri açıksa önce hızlı çeviri çıkar, Gemini'nin sokak dili çevirisi gelince yerine geçer.
- Gemini hata verirse bir süre dinlenir, bu sırada hızlı çeviri kullanılır.
- Sonucu bu bilgisayarın ekranına, TV'ye, tarayıcı sayfasına ve sesli okumaya gönderir.
"""
import collections
import concurrent.futures
import re
import threading
import time

from . import ekran
from .gemini import DENEME_CUMLESI, Gemini, GeminiHatasi, acikla
from .hizli import HizliCeviri, terim_listesi
from .metin import Dengeleyici, benzer, diyalog_mu

TEST_TR = "Vice City'ye hoş geldin kanka! Her şey tıkırında."
TEST_EN = "Welcome to Vice City, bro! Everything's running smooth."


def _anahtar(en):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ?!]", " ", en.lower())).strip()


class Motor:
    def __init__(self, ayar, olaylar, sozluk, gecmis):
        self.ayar = ayar
        self.olaylar = olaylar          # queue.Queue -> arayüz
        self.sozluk = sozluk
        self.gecmis = gecmis
        self.gemini = Gemini()
        self.hizli = HizliCeviri()
        self.calisiyor = False
        self.chiaki_pid = None
        self.cikislar = []              # TV, web sayfası, ses: göster(tr, en, sira) / temizle()
        self._hwnd = None
        self._hwnd_zaman = 0.0
        self._pencere_calisiyor = set()
        self.chiaki_acik = False        # arayüz her yarım saniyede günceller
        self.ps5_bagli = False
        self._havuz = concurrent.futures.ThreadPoolExecutor(max_workers=6)
        self._kilit = threading.Lock()
        self._sira = 0
        self._son_gosterilen = 0
        self._son_kesin = True
        self._onbellek = collections.OrderedDict()
        self._baglam = collections.deque(maxlen=3)
        self._hata_serisi = 0
        self._dinlenme = 0.0
        self._son_uyari = 0.0
        self.gosterilen_tr = ""
        self._sizinti = 0
        self._okuyucu = None
        self._kusak = 0
        self.teshis = {"kare": 0, "okuma": 0, "ham": "", "kaynak": ""}
        self.son = {"tr": "", "en": "", "ms": 0, "motor": ""}

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
        self.temizle_her_yerde()
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

    @property
    def gemini_kullanilabilir(self):
        return (bool(self.ayar.get("gemini_acik", True))
                and bool((self.ayar.get("gemini_anahtar") or "").strip())
                and time.time() >= self._dinlenme)

    def test_gonder(self):
        with self._kilit:
            self._sira += 1
            sira = self._sira
            self._son_gosterilen = sira
            self._son_kesin = True
        self._dagit(sira, TEST_EN, TEST_TR, "Test", kesin=True, t0=time.time())

    def anahtari_dene(self):
        """Arayüzdeki 'Anahtarı dene' düğmesi: (başarılı mı, mesaj)."""
        anahtar = (self.ayar.get("gemini_anahtar") or "").strip()
        if not anahtar:
            return False, "Önce anahtarı yapıştırın."
        try:
            tr, model = self.gemini.cevir(anahtar, self.ayar.get("gemini_model"), DENEME_CUMLESI)
            if model != self.ayar.get("gemini_model"):
                self.ayar["gemini_model"] = model
                self.olaylar.put(("model", model))
            self._dinlenme = 0.0
            return True, f"Çalışıyor: {tr}"
        except GeminiHatasi as e:
            return False, acikla(e, self.ayar.get("gemini_model", ""))

    def temizle_her_yerde(self):
        self.gosterilen_tr = ""
        self.olaylar.put(("temizle",))
        for c in list(self.cikislar):
            try:
                c.temizle()
            except Exception:
                pass

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
        self.teshis = {"kare": 0, "okuma": 0, "ham": "", "kaynak": ""}

        while self.calisiyor and kusak == self._kusak:
            bas = time.time()
            try:
                kare, kaynak = self._altyazi_karesi(yak)
                self.teshis["kaynak"] = kaynak
                if kare is None:
                    durum = kaynak
                elif kaynak == "tüm ekran":
                    durum = "chiaki-ng açık değil, tüm ekran okunuyor"
                else:
                    durum = "PS5 görüntüsü okunuyor"
                if durum != son_durum:
                    self.olaylar.put(("durum", durum))
                    son_durum = durum
                if kare is None:
                    onceki_kare, onceki_metin = None, ""
                    if not temiz:
                        temiz = True
                        deng.sifirla()
                        self.temizle_her_yerde()
                    time.sleep(0.5)
                    continue
                self.teshis["kare"] += 1
                if degisti_mi(onceki_kare, kare):
                    metin = self._okuyucu.oku(kare)
                    self.teshis["okuma"] += 1
                    if metin:
                        self.teshis["ham"] = metin
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
                        self.altyazi_geldi(yeni)
                elif not temiz and time.time() - son_gorulme > float(self.ayar["gizleme_sn"]):
                    temiz = True
                    deng.sifirla()
                    self.temizle_her_yerde()
            except Exception as e:
                self.olaylar.put(("durum", f"Okuma hatası: {e}"))
                time.sleep(1.0)
            bekle = int(self.ayar["okuma_araligi_ms"]) / 1000.0 - (time.time() - bas)
            if bekle > 0:
                time.sleep(bekle)

    def _pencere_karesi(self):
        """chiaki-ng penceresinin tamamı (önünde Çevirix penceresi olsa bile). Olmazsa None."""
        hwnd = self._hwnd
        if not hwnd:
            return None
        try:
            kare = ekran.pencere_goruntusu(hwnd)
        except Exception:
            return None
        if kare is None:
            return None
        if hwnd not in self._pencere_calisiyor:
            # Bu pencerede yöntem çalışıyor mu? Görüntü bir kez siyah değilse güvenilir say.
            if float(kare[::16, ::16].mean()) < 3:
                return None
            self._pencere_calisiyor.add(hwnd)
        return kare

    def _altyazi_karesi(self, yak):
        """(altyazı şeridi görüntüsü ya da None, kaynak / bekleme nedeni)"""
        (x, y, w, h), bulundu = self.altyazi_alani()
        if self.chiaki_acik:
            # chiaki-ng açıkken yalnız onun penceresi okunur; asla tüm ekran okunmaz
            if not bulundu:
                return None, "Oyun penceresi simge durumunda. chiaki-ng'yi küçültmeyin (arkada kalabilir)."
            if not self.ps5_bagli:
                return None, "PS5 bağlantısı bekleniyor (chiaki-ng menüsü okunmaz)"
            tam = self._pencere_karesi()
            if tam is not None:
                th, tw = tam.shape[:2]
                sl, su, sg, sy = self.ayar["alan"]
                x1, y1 = int(sl * tw), int(su * th)
                x2, y2 = min(tw, x1 + max(40, int(sg * tw))), min(th, y1 + max(20, int(sy * th)))
                return tam[y1:y2, x1:x2], "chiaki-ng (arkadayken de)"
            # Arkadan okuma bu bilgisayarda çalışmadı: ekrandan oku, ama önde başka pencere varsa okuma
            on = ekran.user32.GetForegroundWindow() if ekran.WIN else None
            if on and on != self._hwnd:
                return None, "Oyun penceresi arkada; bu bilgisayarda yalnız öndeyken okunabiliyor (Oyuna geç)"
            return yak.al(x, y, w, h), "chiaki-ng (ekrandan)"
        return yak.al(x, y, w, h), "tüm ekran"

    def onizleme_karesi(self, en_genislik=480):
        """Oyna sekmesindeki canlı pencere için küçültülmüş oyun görüntüsü (RGB) ya da None."""
        _, bulundu = self.hedef()
        if not bulundu:
            return None
        tam = self._pencere_karesi()
        if tam is None:
            return None
        h, w = tam.shape[:2]
        adim = max(1, w // en_genislik)
        return tam[::adim, ::adim, ::-1]

    # ------------------------------------------------------------ çeviri hattı
    def altyazi_geldi(self, en):
        with self._kilit:
            self._sira += 1
            sira = self._sira
        self._havuz.submit(self._isle, sira, en, time.time())

    def _isle(self, sira, en, t0):
        try:
            onbellek = self._onbellekte(en)
            if onbellek:
                self._goster(sira, en, onbellek, "Önbellek", True, t0)
                return
            gemini_var = self.gemini_kullanilabilir
            hizli_is = None
            if not gemini_var or self.ayar.get("aninda_ceviri", True):
                def hizli():
                    tr = self._hizli_cevir(en)
                    if tr:
                        self._goster(sira, en, tr, "Hızlı", not gemini_var, t0)
                    return tr
                hizli_is = self._havuz.submit(hizli) if gemini_var else None
                if not gemini_var:
                    if hizli() is None:
                        self._uyari("Çeviri yapılamadı (Gemini kapalı ve internet yok)")
                    return

            g = self._gemini_cevir(en)
            if g is None:
                # Gemini kullanılamadı: hızlı çeviri yoksa şimdi yap
                if hizli_is is None:
                    tr = self._hizli_cevir(en)
                    if tr:
                        self._goster(sira, en, tr, "Hızlı", True, t0)
                else:
                    try:
                        hizli_is.result(timeout=6)
                    except Exception:
                        pass
                    self._hizliyi_kesinlestir(sira)
            elif not g:
                # Diyalog değil: hızlı çeviri ekrana çıktıysa kaldır
                with self._kilit:
                    simdiki = sira == self._son_gosterilen
                if simdiki:
                    self.temizle_her_yerde()
            else:
                self._goster(sira, en, g, "Gemini", True, t0)
        except Exception as e:
            self.olaylar.put(("durum", f"Çeviri hatası: {e}"))

    def _onbellekte(self, en):
        k = _anahtar(en)
        with self._kilit:
            if k in self._onbellek:
                self._onbellek.move_to_end(k)
                return self._onbellek[k]
        return None

    def _hatirla(self, en, tr):
        with self._kilit:
            self._onbellek[_anahtar(en)] = tr
            if len(self._onbellek) > 600:
                self._onbellek.popitem(last=False)
            self._baglam.append((en, tr))

    def _hizli_cevir(self, en):
        """Sokak sözlüğü (anında) + hızlı çeviri (Gemini'siz)."""
        tr = self.sozluk.cevir(en)
        if tr:
            return tr
        terimler = terim_listesi(self.ayar.get("terimler", ""))
        return self.sozluk.makine_ile_cevir(en, lambda t: self.hizli.cevir(t, terimler))

    def _gemini_cevir(self, en):
        """None: kullanılamadı (yedek kullanılmalı). Boş metin: diyalog değil."""
        if not self.gemini_kullanilabilir:
            return None
        anahtar = self.ayar["gemini_anahtar"].strip()
        with self._kilit:
            baglam = list(self._baglam)
        try:
            tr, model = self.gemini.cevir(anahtar, self.ayar.get("gemini_model"), en, baglam,
                                          self.ayar.get("terimler", ""))
            self._hata_serisi = 0
            if model != self.ayar.get("gemini_model"):
                self.ayar["gemini_model"] = model
                self.olaylar.put(("model", model))
            if tr:
                self._hatirla(en, tr)
            return tr
        except GeminiHatasi as e:
            self._hata_serisi += 1
            simdi = time.time()
            if e.kod == 429:
                self._dinlenme = simdi + 60
            elif e.anahtar_sorunu or e.kod == 404:
                self._dinlenme = simdi + 30
            elif self._hata_serisi >= 3:
                self._dinlenme = simdi + 20
            self._uyari(f"{acikla(e, self.ayar.get('gemini_model', ''))} – hızlı çeviri kullanılıyor")
            return None

    def _uyari(self, msg):
        simdi = time.time()
        if simdi - self._son_uyari < 3:
            return
        self._son_uyari = simdi
        self.olaylar.put(("hata", msg))

    # ------------------------------------------------------------ gösterme
    def _goster(self, sira, en, tr, motor, kesin, t0):
        with self._kilit:
            if sira < self._son_gosterilen:
                return  # daha yeni bir satır gösteriliyor
            if sira == self._son_gosterilen and self._son_kesin:
                return  # kesin çeviri zaten gösterildi
            self._son_gosterilen = sira
            self._son_kesin = kesin
        if not self.calisiyor:
            return
        self._dagit(sira, en, tr, motor, kesin, t0)

    def _dagit(self, sira, en, tr, motor, kesin, t0):
        ms = int((time.time() - t0) * 1000)
        self.gosterilen_tr = tr
        self.son = {"tr": tr, "en": en, "ms": ms, "motor": motor}
        if kesin:
            self.gecmis.ekle(en, tr, motor)
        self.olaylar.put(("altyazi", tr, en, motor, ms))
        for c in list(self.cikislar):
            try:
                c.goster(tr, en, sira, kesin)
            except Exception:
                pass

    def _hizliyi_kesinlestir(self, sira):
        """Gemini başarısız olduysa hızlı çeviriyi kesin say (geçmiş ve seslendirme için)."""
        with self._kilit:
            olur = sira == self._son_gosterilen and not self._son_kesin
            if olur:
                self._son_kesin = True
        if olur and self.son["tr"]:
            self.gecmis.ekle(self.son["en"], self.son["tr"], self.son["motor"])
            for c in list(self.cikislar):
                try:
                    c.kesinlesti(self.son["tr"], sira)
                except Exception:
                    pass
