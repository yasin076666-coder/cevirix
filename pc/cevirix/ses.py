"""Türkçe canlı dublaj (Windows'un metin okuma sesleri, telefondaki Speaker'ın karşılığı).

Hem klasik SAPI seslerini hem de Windows 10/11'in yeni (OneCore) seslerini listeler;
Türkçe ses varsa ("Microsoft Tolga") onu kendiliğinden seçer.
"""
import queue
import threading

ONECORE = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices"
SVSF_ASYNC = 1
SVSF_PURGE = 2


def _turkce_mu(token):
    try:
        dil = (token.GetAttribute("Language") or "").lower()
        if "41f" in dil.split(";"):
            return True
    except Exception:
        pass
    ad = (token.GetDescription() or "").lower()
    return "turk" in ad or "türk" in ad or "tolga" in ad


class Ses:
    def __init__(self, ayar, bildir):
        self.ayar = ayar
        self.bildir = bildir
        self._kuyruk = queue.Queue()
        self._hazir = threading.Event()
        self.sesler = []                # [(ad, türkçe mi)]
        self.sorun = "Ses motoru hazırlanıyor…"
        threading.Thread(target=self._dongu, daemon=True, name="cevirix-ses").start()

    # ------------------------------------------------------------ çıkış arayüzü (motor çağırır)
    def goster(self, tr, en, sira, kesin=True):
        if kesin and self.ayar.get("sesli_okuma"):
            self.oku(tr)

    def kesinlesti(self, tr, sira):
        if self.ayar.get("sesli_okuma"):
            self.oku(tr)

    def temizle(self):
        pass

    # ------------------------------------------------------------ dış arayüz
    def oku(self, metin):
        if metin and metin.strip():
            self._kuyruk.put(("oku", metin))

    def ayar_degisti(self):
        self._kuyruk.put(("ayar", None))

    def dene(self, metin="Sesli okuma çalışıyor kanka."):
        """Deneme cümlesi okur; sorun varsa açıklamasını döndürür."""
        self._hazir.wait(5)
        if self.sorun:
            return self.sorun
        self.oku(metin)
        return None

    # ------------------------------------------------------------ ses iş parçacığı
    def _dongu(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            self._ses = win32com.client.Dispatch("SAPI.SpVoice")
            self._jetonlar = self._listele(win32com.client)
            self.sesler = [(ad, tr) for ad, tr, _ in self._jetonlar]
            self._uygula()
        except Exception as e:
            self.sorun = f"Windows ses motoru açılamadı: {e}"
            self._hazir.set()
            self.bildir("ses", self.sorun)
            return
        self._hazir.set()
        self.bildir("ses", self.sorun or "")
        while True:
            is_, veri = self._kuyruk.get()
            try:
                if is_ == "ayar":
                    self._uygula()
                    self.bildir("ses", self.sorun or "")
                elif is_ == "oku" and not self.sorun:
                    self._ses.Rate = self._hiz()
                    self._ses.Speak(veri, SVSF_ASYNC | SVSF_PURGE)
            except Exception as e:
                self.bildir("ses", f"Sesli okuma hatası: {e}")

    def _listele(self, w32):
        bulunan, goruldu = [], set()

        def ekle(jetonlar):
            for i in range(jetonlar.Count):
                t = jetonlar.Item(i)
                ad = t.GetDescription()
                if ad and ad not in goruldu:
                    goruldu.add(ad)
                    bulunan.append((ad, _turkce_mu(t), t))

        try:
            ekle(self._ses.GetVoices())
        except Exception:
            pass
        try:
            kat = w32.Dispatch("SAPI.SpObjectTokenCategory")
            kat.SetId(ONECORE, False)
            ekle(kat.EnumerateTokens())
        except Exception:
            pass
        bulunan.sort(key=lambda x: (not x[1], x[0]))
        return bulunan

    def _uygula(self):
        istenen = (self.ayar.get("ses_adi") or "").strip()
        # Sıra: kullanıcının seçtiği, sonra Türkçe sesler, sonra diğerleri (liste zaten böyle sıralı)
        adaylar = sorted(self._jetonlar, key=lambda x: not (istenen and x[0] == istenen))
        if not adaylar:
            self.sorun = "Bu bilgisayarda hiç metin okuma sesi yok."
            return
        secilen, son_hata = None, None
        for aday in adaylar:
            try:
                self._ses.Voice = aday[2]
                secilen = aday
                break
            except Exception as e:  # bazı yeni (OneCore) sesler eski motorla açılmaz
                son_hata = e
        if secilen is None:
            self.sorun = f"Ses seçilemedi: {son_hata}"
            return
        self.sorun = None
        self.secili = secilen[0]
        if not secilen[1]:
            self.bildir("ses_uyari", "Türkçe ses yüklü değil; Türkçe metin yabancı sesle okunur. "
                                     "Ayarlar › Zaman ve dil › Konuşma › Ses ekle › Türkçe.")

    def _hiz(self):
        yuzde = int(self.ayar.get("konusma_hizi", 110))
        return max(-10, min(10, round((yuzde - 100) / 6)))
