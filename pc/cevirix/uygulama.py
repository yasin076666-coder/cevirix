"""Çevirix PC: ana pencere (telefon sürümüyle aynı sekmeler ve ayarlar), altyazı katmanı, alan seçici."""
import glob
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import ayarlar, ekran
from .gecmis import Gecmis
from .gemini import MODEL_SECENEKLERI, VARSAYILAN_TERIMLER
from .motor import Motor
from .ses import Ses
from .sozluk import Sozluk
from .tv import TvSunucusu, yerel_ip
from .web import PORT as WEB_PORT
from .web import WebSayfasi

SURUM = "2.0"

ARKA = "#0b0d18"
KART = "#151a2e"
KART2 = "#1c2340"
KENAR = "#262d4a"
YAZI = "#e9ecff"
SOLUK = "#8a93b8"
CAMGOBEGI = "#00e5ff"
PEMBE = "#ff2bd6"
TURUNCU = "#ff8a3d"
YESIL = "#2ee59d"
SARI = "#ffc94d"
KIRMIZI = "#ff5470"
ANAHTAR_RENK = "#010101"   # katmanda saydam sayılan renk

HATA_DOSYASI = os.path.join(ayarlar.KLASOR, "son_hata.txt")


def uygulama_klasoru():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def kaynak(ad):
    taban = getattr(sys, "_MEIPASS", os.path.join(uygulama_klasoru(), "veri"))
    return os.path.join(taban, ad)


def chiaki_bul(ayar):
    yol = (ayar.get("chiaki_yolu") or "").strip()
    if yol and os.path.isfile(yol):
        return yol
    for ad in ("chiaki.exe", "chiaki-ng.exe"):
        bulunan = glob.glob(os.path.join(uygulama_klasoru(), "chiaki-ng", "**", ad), recursive=True)
        if bulunan:
            return bulunan[0]
    return None


def hata_yaz(metin):
    try:
        os.makedirs(ayarlar.KLASOR, exist_ok=True)
        with open(HATA_DOSYASI, "w", encoding="utf-8") as f:
            f.write(time.strftime("%d.%m.%Y %H:%M:%S") + f"  ·  Çevirix PC v{SURUM}\n\n" + metin)
    except Exception:
        pass


def _karistir(renk1, renk2, oran):
    """renk1'i renk2'nin üstüne 'oran' (0-1) saydamlıkla koyar."""
    a = [int(renk1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(renk2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * oran + y * (1 - oran)):02x}" for x, y in zip(a, b))


# ================================================================ küçük bileşenler
class Anahtar(tk.Canvas):
    """Açma/kapama düğmesi (telefondaki MaterialSwitch gibi)."""

    def __init__(self, ust, deger, komut=None, bg=KART):
        super().__init__(ust, width=46, height=24, bg=bg, highlightthickness=0, cursor="hand2")
        self.deger, self.komut = deger, komut
        self.bind("<Button-1>", self._tikla)
        self.ciz()

    def _tikla(self, _):
        self.deger.set(not self.deger.get())
        self.ciz()
        if self.komut:
            self.komut()

    def ciz(self):
        self.delete("all")
        acik = bool(self.deger.get())
        renk = CAMGOBEGI if acik else KENAR
        self.create_oval(0, 0, 24, 24, fill=renk, outline=renk)
        self.create_oval(22, 0, 46, 24, fill=renk, outline=renk)
        self.create_rectangle(12, 0, 34, 24, fill=renk, outline=renk)
        x = 25 if acik else 3
        self.create_oval(x, 3, x + 18, 21, fill="#05060c" if acik else SOLUK, outline="")


class KaydirmaliSayfa(tk.Frame):
    """Dikey kaydırılabilen sekme sayfası."""

    def __init__(self, ust):
        super().__init__(ust, bg=ARKA)
        self.tuval = tk.Canvas(self, bg=ARKA, highlightthickness=0, bd=0)
        cubuk = ttk.Scrollbar(self, orient="vertical", command=self.tuval.yview)
        self.ic = tk.Frame(self.tuval, bg=ARKA)
        self._pencere = self.tuval.create_window(0, 0, anchor="nw", window=self.ic)
        self.tuval.configure(yscrollcommand=cubuk.set)
        self.tuval.pack(side="left", fill="both", expand=True)
        cubuk.pack(side="right", fill="y")
        self.ic.bind("<Configure>", lambda e: self.tuval.configure(scrollregion=self.tuval.bbox("all")))
        self.tuval.bind("<Configure>", lambda e: self.tuval.itemconfigure(self._pencere, width=e.width))
        self.tuval.bind("<Enter>", lambda e: self.tuval.bind_all("<MouseWheel>", self._tekerlek))
        self.tuval.bind("<Leave>", lambda e: self.tuval.unbind_all("<MouseWheel>"))

    def _tekerlek(self, e):
        if self.ic.winfo_height() > self.tuval.winfo_height():
            self.tuval.yview_scroll(int(-e.delta / 120), "units")

    def basa(self):
        self.tuval.yview_moveto(0)


# ================================================================ altyazı katmanı
class Katman:
    """Oyunun üstünde duran, tıklamayı geçiren Türkçe altyazı.

    İki pencere: arkada ayarlanabilir koyulukta siyah kutu, önde saydam zeminli yazı.
    İkisi de ekran yakalamaya girmez (kendi yazımızı tekrar okumayalım diye).
    """

    def __init__(self, kok, ayar, motor):
        self.ayar, self.motor = ayar, motor
        self.kutu = self._pencere(kok)
        self.kutu.configure(bg="#000000")
        self.pen = self._pencere(kok)
        self.pen.configure(bg=ANAHTAR_RENK)
        self.pen.attributes("-transparentcolor", ANAHTAR_RENK)
        cer = tk.Frame(self.pen, bg=ANAHTAR_RENK)
        cer.pack(padx=22, pady=8)
        self.tr = tk.Label(cer, text="", fg="#ffffff", bg=ANAHTAR_RENK, justify="center")
        self.tr.pack()
        self.en = tk.Label(cer, text="", fg="#d6dcf0", bg=ANAHTAR_RENK, justify="center")
        self.gizli = False       # F9 ile kullanıcı gizledi mi
        self.metin = ("", "")
        self._hazir = False
        self._sabitle()

    @staticmethod
    def _pencere(kok):
        p = tk.Toplevel(kok)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.withdraw()
        return p

    def _sabitle(self):
        if self.pen.winfo_viewable():
            if self.kutu.winfo_viewable():
                ekran.en_ustte(ekran.tk_hwnd(self.kutu))
            ekran.en_ustte(ekran.tk_hwnd(self.pen))
        self.pen.after(1500, self._sabitle)

    def goster(self, tr, en=""):
        self.metin = (tr, en)
        if self.gizli or not tr or not self.ayar.get("pc_katman", True):
            self._gizle()
            return
        (x, y, w, h), _ = self.motor.altyazi_alani()
        (hx, hy, hw, hh), _ = self.motor.hedef()
        boyut = int(self.ayar.get("yazi_boyutu", 30))
        sarma = max(300, int(hw * 0.8))
        self.tr.configure(text=tr, font=("Segoe UI Semibold", boyut), wraplength=sarma)
        if self.ayar.get("ingilizce_goster") and en:
            self.en.configure(text=en, font=("Segoe UI", max(10, int(boyut * 0.55))), wraplength=sarma)
            self.en.pack(pady=(2, 0))
        else:
            self.en.pack_forget()
        self.pen.update_idletasks()
        kw, kh = self.pen.winfo_reqwidth(), self.pen.winfo_reqheight()
        kx = hx + (hw - kw) // 2
        konum = self.ayar.get("konum", "kapat")
        if konum == "ust":
            ky = hy + int(hh * 0.04)
        elif konum == "alt":
            ky = hy + hh - kh - int(int(self.ayar.get("alt_yukseklik", 70)) * hh / 1080)
        else:
            # İngilizce altyazının tam üstüne, alt kenarına hizalı
            ky = min(y + h - kh, hy + hh - kh - 4)
        ky = max(hy, ky)
        geo = f"{kw}x{kh}+{kx}+{ky}"
        koyuluk = int(self.ayar.get("arka_koyuluk", 170))
        if koyuluk > 0:
            self.kutu.attributes("-alpha", max(0.05, koyuluk / 255))
            self.kutu.geometry(geo)
            self.kutu.deiconify()
        else:
            self.kutu.withdraw()
        self.pen.geometry(geo)
        self.pen.deiconify()
        if not self._hazir:
            self.pen.update_idletasks()
            self.kutu.update_idletasks()
            ekran.katman_yap(ekran.tk_hwnd(self.kutu))
            ekran.katman_yap(ekran.tk_hwnd(self.pen))
            self._hazir = True
        if koyuluk > 0:
            ekran.en_ustte(ekran.tk_hwnd(self.kutu))
        ekran.en_ustte(ekran.tk_hwnd(self.pen))

    def yenile(self):
        if self.metin[0]:
            self.goster(*self.metin)

    def _gizle(self):
        self.pen.withdraw()
        self.kutu.withdraw()

    def temizle(self):
        self.metin = ("", "")
        self._gizle()

    def gizle_goster(self):
        self.gizli = not self.gizli
        if self.gizli:
            self._gizle()
        else:
            self.yenile()
        return self.gizli


# ================================================================ ayrı altyazı penceresi
class AltyaziPenceresi:
    """İkinci ekran ya da yan pencere için büyük altyazı (telefondaki tam ekran altyazının karşılığı)."""

    def __init__(self, kok, ayar, kapaninca):
        self.ayar, self.kapaninca = ayar, kapaninca
        self.pen = tk.Toplevel(kok)
        self.pen.title("Çevirix – Altyazı")
        self.pen.configure(bg="#050C20")
        self.pen.geometry("900x260")
        try:
            self.pen.iconbitmap(kaynak("cevirix.ico"))
        except Exception:
            pass
        self.boyut = int(ayar.get("yazi_boyutu", 30))
        ust = tk.Frame(self.pen, bg="#050C20")
        ust.pack(fill="x", padx=10, pady=6)
        tk.Label(ust, text="F11: tam ekran  •  Esc: çık", bg="#050C20", fg=SOLUK,
                 font=("Segoe UI", 9)).pack(side="left")
        for metin, d in (("A+", 2), ("A−", -2)):
            tk.Button(ust, text=metin, command=lambda d=d: self._boyut(d), bg=KART, fg=YAZI, relief="flat",
                      bd=0, padx=10, cursor="hand2").pack(side="right", padx=3)
        self.tr = tk.Label(self.pen, text="Türkçe altyazılar burada görünür", bg="#050C20", fg=YAZI,
                           justify="center", font=("Segoe UI Semibold", self.boyut))
        self.tr.pack(expand=True, fill="both", padx=20)
        self.en = tk.Label(self.pen, text="", bg="#050C20", fg=SOLUK, justify="center")
        self.en.pack(fill="x", padx=20, pady=(0, 16))
        self.pen.bind("<Configure>", lambda e: self._sar())
        self.pen.bind("<F11>", lambda e: self.pen.attributes("-fullscreen", not self.pen.attributes("-fullscreen")))
        self.pen.bind("<Escape>", lambda e: self.pen.attributes("-fullscreen", False))
        self.pen.protocol("WM_DELETE_WINDOW", self.kapat)

    def _sar(self):
        g = max(200, self.pen.winfo_width() - 60)
        self.tr.configure(wraplength=g)
        self.en.configure(wraplength=g)

    def _boyut(self, d):
        self.boyut = max(14, min(90, self.boyut + d))
        self.tr.configure(font=("Segoe UI Semibold", self.boyut))
        self.en.configure(font=("Segoe UI", max(10, int(self.boyut * 0.5))))

    def goster(self, tr, en):
        self.tr.configure(text=tr)
        goster_en = self.ayar.get("ingilizce_goster") and en
        self.en.configure(text=en if goster_en else "", font=("Segoe UI", max(10, int(self.boyut * 0.5))))

    def temizle(self):
        self.tr.configure(text="")
        self.en.configure(text="")

    def kapat(self):
        self.pen.destroy()
        self.kapaninca()


# ================================================================ alan seçici
class AlanSecici:
    def __init__(self, kok, motor, bitti):
        self.motor, self.bitti = motor, bitti
        (self.hx, self.hy, self.hw, self.hh), _ = motor.hedef()
        self.pen = tk.Toplevel(kok)
        self.pen.overrideredirect(True)
        self.pen.attributes("-topmost", True)
        self.pen.attributes("-alpha", 0.45)
        self.pen.geometry(f"{self.hw}x{self.hh}+{self.hx}+{self.hy}")
        self.tuval = tk.Canvas(self.pen, bg="#000000", highlightthickness=0, cursor="crosshair")
        self.tuval.pack(fill="both", expand=True)
        self.tuval.create_text(self.hw // 2, 60, fill="#ffffff", font=("Segoe UI Semibold", 22),
                               text="Fareyle İngilizce altyazının çıktığı alanı çizin\n"
                                    "Bitince bırakın  •  Vazgeçmek için Esc",
                               justify="center")
        sl, su, sg, sy = motor.ayar["alan"]
        self.kutu = self.tuval.create_rectangle(sl * self.hw, su * self.hh, (sl + sg) * self.hw,
                                                (su + sy) * self.hh, outline=CAMGOBEGI, width=4)
        self.bas = None
        self.tuval.bind("<ButtonPress-1>", self._bas)
        self.tuval.bind("<B1-Motion>", self._surukle)
        self.tuval.bind("<ButtonRelease-1>", self._birak)
        self.pen.bind("<Escape>", lambda e: self._kapat(None))
        self.pen.focus_force()

    def _bas(self, e):
        self.bas = (e.x, e.y)

    def _surukle(self, e):
        if self.bas:
            self.tuval.coords(self.kutu, self.bas[0], self.bas[1], e.x, e.y)

    def _birak(self, e):
        if not self.bas:
            return
        x1, y1 = min(self.bas[0], e.x), min(self.bas[1], e.y)
        x2, y2 = max(self.bas[0], e.x), max(self.bas[1], e.y)
        if x2 - x1 < 40 or y2 - y1 < 15:
            self.bas = None
            return
        self._kapat([x1 / self.hw, y1 / self.hh, (x2 - x1) / self.hw, (y2 - y1) / self.hh])

    def _kapat(self, alan):
        self.pen.destroy()
        self.bitti(alan)


# ================================================================ ana pencere
class Uygulama:
    def __init__(self):
        ekran.dpi_farkinda()
        self.ayar = ayarlar.yukle()
        self.olaylar = queue.Queue()
        bildir = lambda tur, deger: self.olaylar.put((tur, deger))  # noqa: E731
        self.sozluk = Sozluk(kaynak("sokak_sozlugu.json"))
        self.gecmis = Gecmis()
        self.motor = Motor(self.ayar, self.olaylar, self.sozluk, self.gecmis)
        self.tv = TvSunucusu(self.ayar, bildir)
        self.web = WebSayfasi(self.ayar, bildir)
        self.ses = Ses(self.ayar, bildir)
        self.motor.cikislar = [self.tv, self.web, self.ses]
        self.chiaki = None
        self.tv_sayisi = 0
        self.web_sayisi = 0
        self.altyazi_penceresi = None
        self._kayit_bekliyor = None
        self._stil_bekliyor = None
        self.anahtarlar = {}
        self.tv_mesaj = ""
        self.ip = yerel_ip()

        self.kok = tk.Tk()
        self.kok.title("Çevirix PC – Oyun Çevirici")
        self.kok.configure(bg=ARKA)
        # Ekran ölçeği (%125, %150...): yazılar büyüyünce pencere de büyüsün
        try:
            self.o = max(1.0, self.kok.winfo_fpixels("1i") / 96.0)
        except Exception:
            self.o = 1.0
        yuk = int(min(820 * self.o, self.kok.winfo_screenheight() * 0.9))
        self.kok.minsize(int(620 * self.o), int(min(640 * self.o, yuk)))
        self.kok.geometry(f"{int(680 * self.o)}x{yuk}")
        self.kok.report_callback_exception = self._arayuz_hatasi
        try:
            self.kok.iconbitmap(kaynak("cevirix.ico"))
        except Exception:
            pass
        self.kok.protocol("WM_DELETE_WINDOW", self.kapat)
        self._stiller()
        self._arayuz()
        self.katman = Katman(self.kok, self.ayar, self.motor)
        ekran.KisayolTuslari(lambda kid: self.olaylar.put(("tus", kid)))
        if self.ayar.get("tv_gonder", True):
            self.tv.baslat()
        if self.ayar.get("web_sayfa", True):
            self.web.baslat()
        self.kok.after(50, self._olaylari_isle)
        self.kok.after(500, self._yenile)
        self.kok.after(30000, self._gecmisi_yaz)
        self.kok.after(400, self._son_hatayi_goster)
        if not self.ayar.get("gemini_anahtar"):
            self._durum("Gemini anahtarı yok: hızlı çeviri kullanılacak (Çeviri sekmesinden ekleyin)", PEMBE)

    # ------------------------------------------------------------ yardımcılar
    def _stiller(self):
        s = ttk.Style(self.kok)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("TCombobox", fieldbackground=ARKA, background=KART2, foreground=YAZI, arrowcolor=YAZI,
                    bordercolor=KENAR, lightcolor=KENAR, darkcolor=KENAR)
        s.map("TCombobox", fieldbackground=[("readonly", ARKA)], foreground=[("readonly", YAZI)])
        s.configure("Vertical.TScrollbar", background=KART2, troughcolor=ARKA, bordercolor=ARKA,
                    arrowcolor=SOLUK, lightcolor=KART2, darkcolor=KART2)
        self.kok.option_add("*TCombobox*Listbox.background", KART)
        self.kok.option_add("*TCombobox*Listbox.foreground", YAZI)
        self.kok.option_add("*TCombobox*Listbox.selectBackground", KENAR)

    def _dugme(self, ust, metin, komut, renk=CAMGOBEGI, buyuk=False, yazi="#05060c"):
        return tk.Button(ust, text=metin, command=komut, bg=renk, fg=yazi, activebackground=YAZI,
                         activeforeground="#05060c", relief="flat", bd=0, cursor="hand2",
                         font=("Segoe UI Semibold", 13 if buyuk else 10), padx=14, pady=9 if buyuk else 5)

    def _ikincil(self, ust, metin, komut):
        return self._dugme(ust, metin, komut, KART2, yazi=YAZI)

    def _kart(self, sayfa, baslik, aciklama=None):
        f = tk.Frame(sayfa.ic, bg=KART, highlightbackground=KENAR, highlightthickness=1)
        f.pack(fill="x", padx=16, pady=6)
        tk.Label(f, text=baslik, bg=KART, fg=SOLUK, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14,
                                                                                      pady=(10, 2))
        if aciklama:
            self._aciklama(f, aciklama)
        return f

    def _aciklama(self, ust, metin, renk=SOLUK):
        e = tk.Label(ust, text=metin, bg=KART, fg=renk, font=("Segoe UI", 9), wraplength=int(560 * self.o),
                     justify="left", anchor="w")
        e.pack(fill="x", padx=14, pady=(0, 6))
        return e

    def _bool(self, anahtar):
        return tk.BooleanVar(value=bool(self.ayar.get(anahtar)))

    def _anahtar_satiri(self, kart, baslik, anahtar, aciklama=None, sonra=None):
        satir = tk.Frame(kart, bg=KART)
        satir.pack(fill="x", padx=14, pady=4)
        sol = tk.Frame(satir, bg=KART)
        sol.pack(side="left", fill="x", expand=True)
        tk.Label(sol, text=baslik, bg=KART, fg=YAZI, font=("Segoe UI Semibold", 10), anchor="w",
                 justify="left").pack(fill="x")
        if aciklama:
            tk.Label(sol, text=aciklama, bg=KART, fg=SOLUK, font=("Segoe UI", 9), anchor="w", justify="left",
                     wraplength=int(470 * self.o)).pack(fill="x")
        deg = self._bool(anahtar)

        def degisti():
            self.ayar[anahtar] = bool(deg.get())
            self._kaydet()
            if sonra:
                sonra()

        a = Anahtar(satir, deg, degisti)
        a.pack(side="right", padx=(10, 0))
        self.anahtarlar[anahtar] = (deg, a)
        return deg, a

    def _kaydirici(self, kart, bicim, alt, ust, adim, anahtar, sonra=None, ondalik=False):
        etiket = tk.Label(kart, bg=KART, fg=YAZI, font=("Segoe UI", 10), anchor="w")
        etiket.pack(fill="x", padx=14, pady=(4, 0))
        deg = tk.DoubleVar(value=float(self.ayar.get(anahtar)))

        def degisti(_=None):
            v = round(float(deg.get()) / adim) * adim
            v = round(v, 2) if ondalik else int(round(v))
            etiket.configure(text=bicim(v))
            if self.ayar.get(anahtar) != v:
                self.ayar[anahtar] = v
                self._kaydet()
                if sonra:
                    sonra()

        sk = tk.Scale(kart, from_=alt, to=ust, resolution=adim, orient="horizontal", variable=deg,
                      showvalue=0, bg=KART, fg=YAZI, troughcolor=ARKA, activebackground=CAMGOBEGI,
                      highlightthickness=0, bd=0, sliderrelief="flat", command=degisti)
        sk.pack(fill="x", padx=14, pady=(0, 6))
        etiket.configure(text=bicim(self.ayar.get(anahtar)))
        return deg, etiket

    def _kaydet(self):
        """Ayarları kısa bir gecikmeyle diske yazar (kaydırıcı sürüklenirken yüzlerce kez yazmamak için)."""
        if self._kayit_bekliyor:
            self.kok.after_cancel(self._kayit_bekliyor)
        self._kayit_bekliyor = self.kok.after(400, self._kaydet_simdi)

    def _kaydet_simdi(self):
        self._kayit_bekliyor = None
        ayarlar.kaydet(self.ayar)

    def _durum(self, t, renk=SOLUK):
        self.durum.configure(text=t, fg=renk)

    # ------------------------------------------------------------ arayüz
    def _arayuz(self):
        ust = tk.Frame(self.kok, bg=ARKA)
        ust.pack(fill="x", padx=16, pady=(12, 4))
        try:
            img = tk.PhotoImage(file=kaynak("logo.png"))
            oran = max(1, img.width() // 70)
            self._logo = img.subsample(oran, oran)
            tk.Label(ust, image=self._logo, bg=ARKA).pack(side="left")
        except Exception:
            pass
        ad = tk.Frame(ust, bg=ARKA)
        ad.pack(side="left", padx=12)
        tk.Label(ad, text="ÇEVİRİX PC", bg=ARKA, fg=CAMGOBEGI, font=("Segoe UI Black", 20)).pack(anchor="w")
        tk.Label(ad, text="PS5 oyunlarını Türkçe altyazıyla oyna", bg=ARKA, fg=SOLUK,
                 font=("Segoe UI", 10)).pack(anchor="w")

        durum_satiri = tk.Frame(self.kok, bg=ARKA)
        durum_satiri.pack(fill="x", padx=18, pady=(2, 6))
        self.nokta = tk.Canvas(durum_satiri, width=12, height=12, bg=ARKA, highlightthickness=0)
        self.nokta.pack(side="left", padx=(0, 8))
        self.durum = tk.Label(durum_satiri, text="Hazır", bg=ARKA, fg=SOLUK, font=("Segoe UI", 10), anchor="w")
        self.durum.pack(side="left", fill="x", expand=True)

        # Sekmeler (telefondaki alt menü gibi)
        nav = tk.Frame(self.kok, bg=ARKA)
        nav.pack(fill="x", padx=16, pady=(0, 4))
        self.govde = tk.Frame(self.kok, bg=ARKA)
        self.govde.pack(fill="both", expand=True)
        self.sayfalar, self.sekme_dugmeleri = {}, {}
        for ad_, baslik, kur in (("oyna", "▶  Oyna", self._sayfa_oyna),
                                 ("ceviri", "Çeviri", self._sayfa_ceviri),
                                 ("tv", "Altyazı & TV", self._sayfa_tv),
                                 ("daha", "Daha fazla", self._sayfa_daha)):
            sayfa = KaydirmaliSayfa(self.govde)
            self.sayfalar[ad_] = sayfa
            kur(sayfa)
            b = tk.Button(nav, text=baslik, relief="flat", bd=0, cursor="hand2", font=("Segoe UI Semibold", 10),
                          padx=10, pady=7, command=lambda a=ad_: self.sekme(a))
            b.pack(side="left", expand=True, fill="x", padx=2)
            self.sekme_dugmeleri[ad_] = b
        self.sekme("oyna")

        self.alt_bilgi = tk.Label(self.kok, text="", bg=ARKA, fg=SOLUK, font=("Segoe UI", 9))
        self.alt_bilgi.pack(pady=(2, 8))
        self._alt_bilgi_yaz()

    def sekme(self, ad):
        for a, s in self.sayfalar.items():
            if a == ad:
                s.pack(fill="both", expand=True)
            else:
                s.pack_forget()
        for a, b in self.sekme_dugmeleri.items():
            secili = a == ad
            b.configure(bg=KART2 if secili else ARKA, fg=CAMGOBEGI if secili else SOLUK,
                        activebackground=KART2, activeforeground=CAMGOBEGI)
        if ad == "ceviri":
            self._gecmis_bilgisi()
        self.sayfalar[ad].basa()

    def _alt_bilgi_yaz(self):
        self.alt_bilgi.configure(text=f"F8: çeviriyi başlat/durdur   •   F9: altyazıyı gizle/göster   •   "
                                      f"Sokak sözlüğü: {self.sozluk.boyut} kalıp   •   v{SURUM}")

    # ---------------------------------------------- 1) Oyna
    def _sayfa_oyna(self, s):
        k = self._kart(s, "BAĞLANTI ADIMLARI")
        self.adimlar = {}
        for anahtar, baslik, dugme, komut in (
                ("ps5", "PS5 görüntüsü", "PS5'e Bağlan", self.chiaki_ac),
                ("ceviri", "Altyazı okuma ve çeviri", "Başlat", self.ac_kapat),
                ("tv", "Philips / Android TV", "Test yazısı", self.test_yazisi)):
            satir = tk.Frame(k, bg=KART)
            satir.pack(fill="x", padx=14, pady=4)
            simge = tk.Canvas(satir, width=14, height=14, bg=KART, highlightthickness=0)
            simge.pack(side="left", padx=(0, 10))
            tk.Label(satir, text=baslik, bg=KART, fg=YAZI, font=("Segoe UI Semibold", 10)).pack(side="left")
            b = self._ikincil(satir, dugme, komut)
            b.pack(side="right")
            durum = tk.Label(satir, text="", bg=KART, fg=SOLUK, font=("Segoe UI", 9))
            durum.pack(side="right", padx=10)
            self.adimlar[anahtar] = (simge, durum)
        tk.Frame(k, bg=KART, height=6).pack()

        k = self._kart(s, "ÇEVİRİ")
        satir = tk.Frame(k, bg=KART)
        satir.pack(fill="x", padx=14, pady=(4, 8))
        self.baslat_btn = self._dugme(satir, "Çeviriyi Başlat  (F8)", self.ac_kapat, YESIL, buyuk=True)
        self.baslat_btn.pack(side="left")
        self._ikincil(satir, "Altyazı Alanını Seç", self.alan_sec).pack(side="left", padx=8)
        self._ikincil(satir, "PS5'e Bağlan", self.chiaki_ac).pack(side="left")

        cipler = tk.Frame(k, bg=KART)
        cipler.pack(fill="x", padx=14, pady=(0, 6))
        self.cip_tv = tk.Label(cipler, bg=KART2, fg=SOLUK, font=("Segoe UI", 9), padx=10, pady=3)
        self.cip_tv.pack(side="left", padx=(0, 6))
        self.cip_ip = tk.Label(cipler, bg=KART2, fg=SOLUK, font=("Segoe UI", 9), padx=10, pady=3,
                               text=f"Bilgisayar: {self.ip}")
        self.cip_ip.pack(side="left", padx=(0, 6))
        self.cip_sure = tk.Label(cipler, bg=KART2, fg=SOLUK, font=("Segoe UI", 9), padx=10, pady=3)

        canli = tk.Frame(k, bg="#050C20", highlightbackground=KENAR, highlightthickness=1)
        canli.pack(fill="x", padx=14, pady=(4, 6))
        self.son_tr = tk.Label(canli, text="Çeviriler burada da görünür", bg="#050C20", fg=YAZI,
                               font=("Segoe UI Semibold", 15), wraplength=int(540 * self.o), justify="center")
        self.son_tr.pack(fill="x", padx=10, pady=(14, 2))
        self.son_en = tk.Label(canli, text="", bg="#050C20", fg=SOLUK, font=("Segoe UI", 10, "italic"),
                               wraplength=int(540 * self.o), justify="center")
        self.son_en.pack(fill="x", padx=10, pady=(0, 12))

        hizli = tk.Frame(k, bg=KART)
        hizli.pack(fill="x", padx=14, pady=(0, 8))
        tk.Label(hizli, text="Yazı", bg=KART, fg=SOLUK, font=("Segoe UI", 9)).pack(side="left")
        self._ikincil(hizli, "A−", lambda: self._it("yazi_boyutu", -2, 16, 60)).pack(side="left", padx=3)
        self._ikincil(hizli, "A+", lambda: self._it("yazi_boyutu", 2, 16, 60)).pack(side="left", padx=3)
        tk.Label(hizli, text="   Yükseklik", bg=KART, fg=SOLUK, font=("Segoe UI", 9)).pack(side="left")
        self._ikincil(hizli, "↓", lambda: self._it("alt_yukseklik", -10, 10, 250)).pack(side="left", padx=3)
        self._ikincil(hizli, "↑", lambda: self._it("alt_yukseklik", 10, 10, 250)).pack(side="left", padx=3)
        self._ikincil(hizli, "Gizle / Göster (F9)", self.gizle_goster).pack(side="right")

        k = self._kart(s, "TEŞHİS")
        self.teshis = self._aciklama(k, "Henüz okuma yapılmadı (PS5'e bağlanıp çeviriyi başlatın)")

    # ---------------------------------------------- 2) Çeviri
    def _sayfa_ceviri(self, s):
        k = self._kart(s, "GEMINI · SOKAK DİLİ ÇEVİRİSİ")
        self._anahtar_satiri(k, "Gemini ile çevir", "gemini_acik",
                             "Kapalıyken yalnız hızlı çeviri ve sokak sözlüğü kullanılır.")
        g = tk.Frame(k, bg=KART)
        g.pack(fill="x", padx=14, pady=(6, 2))
        g.columnconfigure(0, weight=1)
        self.anahtar = tk.StringVar(value=self.ayar.get("gemini_anahtar", ""))
        self.anahtar_giris = tk.Entry(g, textvariable=self.anahtar, show="•", bg=ARKA, fg=YAZI,
                                      insertbackground=YAZI, relief="flat", font=("Segoe UI", 10))
        self.anahtar_giris.grid(row=0, column=0, sticky="ew", ipady=6)
        goster = tk.BooleanVar(value=False)
        tk.Checkbutton(g, text="Göster", variable=goster, bg=KART, fg=SOLUK, selectcolor=ARKA,
                       activebackground=KART, activeforeground=YAZI,
                       command=lambda: self.anahtar_giris.configure(show="" if goster.get() else "•")
                       ).grid(row=0, column=1, padx=(8, 0))
        self.anahtar.trace_add("write", lambda *_: self._metin_ayari("gemini_anahtar", self.anahtar.get().strip()))
        d = tk.Frame(k, bg=KART)
        d.pack(fill="x", padx=14, pady=6)
        self._dugme(d, "Anahtarı dene", self.anahtari_dene).pack(side="left")
        self._ikincil(d, "Ücretsiz anahtar al", lambda: webbrowser.open("https://aistudio.google.com/apikey")
                      ).pack(side="left", padx=8)
        self.anahtar_sonuc = self._aciklama(k, "")

        tk.Label(k, text="Model", bg=KART, fg=SOLUK, font=("Segoe UI", 9)).pack(anchor="w", padx=14, pady=(6, 2))
        m = tk.Frame(k, bg=KART)
        m.pack(fill="x", padx=14)
        self.model_dugmeleri = {}
        for etiket, model in MODEL_SECENEKLERI:
            b = tk.Button(m, text=etiket, relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 9), padx=10,
                          pady=4, command=lambda mo=model: self.model.set(mo))
            b.pack(side="left", padx=(0, 6))
            self.model_dugmeleri[model] = b
        self.model = tk.StringVar(value=self.ayar.get("gemini_model", ""))
        tk.Entry(k, textvariable=self.model, bg=ARKA, fg=YAZI, insertbackground=YAZI, relief="flat",
                 font=("Segoe UI", 10)).pack(fill="x", padx=14, pady=(6, 12), ipady=5)
        self.model.trace_add("write", lambda *_: self._model_degisti())
        self._model_dugmelerini_boya()

        k = self._kart(s, "ANINDA ÇEVİRİ")
        self._anahtar_satiri(k, "Önce hızlı çeviri göster", "aninda_ceviri",
                             "Altyazı anında hızlı çeviriyle çıkar, Gemini'nin sokak dili çevirisi gelince "
                             "aynı satırın yerine geçer.")
        self._aciklama(k, f"Hızlı çeviri: Google Çeviri (anahtarsız, internet gerekir) + sokak sözlüğü "
                          f"({self.sozluk.boyut} kalıp ✓). Gemini kotası dolarsa ya da hata verirse "
                          f"kendiliğinden buna geçer, kısa süre sonra Gemini'yi tekrar dener.")

        k = self._kart(s, "SESLİ OKUMA (CANLI DUBLAJ)")
        self._anahtar_satiri(k, "Türkçe çeviriyi sesli oku", "sesli_okuma",
                             "Her yeni altyazı Windows'un metin okuma sesiyle okunur.")
        self._kaydirici(k, lambda v: f"Konuşma hızı: %{v}", 70, 160, 5, "konusma_hizi")
        tk.Label(k, text="Ses", bg=KART, fg=SOLUK, font=("Segoe UI", 9)).pack(anchor="w", padx=14, pady=(4, 2))
        self.ses_secimi = tk.StringVar(value=self.ayar.get("ses_adi") or "Otomatik (Türkçe ses)")
        self.ses_kutusu = ttk.Combobox(k, textvariable=self.ses_secimi, state="readonly",
                                       values=["Otomatik (Türkçe ses)"])
        self.ses_kutusu.pack(fill="x", padx=14)
        self.ses_kutusu.bind("<<ComboboxSelected>>", lambda e: self._ses_secildi())
        d = tk.Frame(k, bg=KART)
        d.pack(fill="x", padx=14, pady=8)
        self._dugme(d, "Sesi dene", self.sesi_dene).pack(side="left")
        self.ses_sonuc = self._aciklama(k, "")

        k = self._kart(s, "TERİM SÖZLÜĞÜ",
                       "Her satıra bir ad: çevrilmeden aynen kalır.  Sabit karşılık için:  "
                       "wanted level = aranma seviyesi")
        self.terim_kutusu = tk.Text(k, height=8, bg=ARKA, fg=YAZI, insertbackground=YAZI, relief="flat",
                                    font=("Consolas", 10))
        self.terim_kutusu.pack(fill="x", padx=14)
        self.terim_kutusu.insert("1.0", self.ayar.get("terimler", ""))
        d = tk.Frame(k, bg=KART)
        d.pack(fill="x", padx=14, pady=8)
        self._dugme(d, "Kaydet", self.terimleri_kaydet).pack(side="left")
        self._ikincil(d, "Varsayılan terimler", self.terimleri_sifirla).pack(side="left", padx=8)

        k = self._kart(s, "ÇEVİRİ GEÇMİŞİ")
        self.gecmis_bilgi = self._aciklama(k, "")
        d = tk.Frame(k, bg=KART)
        d.pack(fill="x", padx=14, pady=(0, 10))
        self._dugme(d, "Geçmişi aç", self.gecmisi_ac).pack(side="left")
        tk.Frame(s.ic, bg=ARKA, height=10).pack()

    # ---------------------------------------------- 3) Altyazı & TV
    def _sayfa_tv(self, s):
        k = self._kart(s, "GÖRÜNÜM", "Bu ayarlar hem bu bilgisayardaki altyazıya hem de TV'ye uygulanır.")
        self.onizleme = tk.Canvas(k, height=250, bg="#000000", highlightthickness=0)
        self.onizleme.pack(fill="x", padx=14, pady=(0, 6))
        self.onizleme.bind("<Configure>", lambda e: self._onizleme_ciz())
        self._kaydirici(k, lambda v: f"Yazı boyutu: {v}", 16, 60, 2, "yazi_boyutu", self._stil_degisti)
        self._kaydirici(k, lambda v: f"Alttan yükseklik: {v}", 10, 250, 5, "alt_yukseklik", self._stil_degisti)
        self._kaydirici(k, lambda v: f"Arka plan koyuluğu: %{v * 100 // 255}", 0, 255, 5, "arka_koyuluk",
                        self._stil_degisti)
        self._anahtar_satiri(k, "İngilizcesini de göster", "ingilizce_goster",
                             "Türkçenin altında küçük harflerle orijinal satır.", self._stil_degisti)
        tk.Frame(k, bg=KART, height=6).pack()

        k = self._kart(s, "BU BİLGİSAYARIN EKRANI")
        self._anahtar_satiri(k, "Altyazıyı oyunun üstünde göster", "pc_katman",
                             "Kapatırsan altyazı yalnız TV'de / tarayıcıda görünür.", self.katman_yenile)
        tk.Label(k, text="Türkçe altyazının yeri", bg=KART, fg=SOLUK, font=("Segoe UI", 9)).pack(
            anchor="w", padx=14, pady=(6, 0))
        self.konum = tk.StringVar(value=self.ayar.get("konum", "kapat"))
        for deger, metin in (("kapat", "İngilizce altyazının üstüne (önerilen)"),
                             ("alt", "Alttan, yükseklik ayarına göre"),
                             ("ust", "Ekranın üstüne")):
            tk.Radiobutton(k, text=metin, value=deger, variable=self.konum, command=self._konum_degisti,
                           bg=KART, fg=YAZI, selectcolor=ARKA, activebackground=KART, activeforeground=YAZI,
                           font=("Segoe UI", 10), anchor="w").pack(fill="x", padx=14)
        d = tk.Frame(k, bg=KART)
        d.pack(fill="x", padx=14, pady=10)
        self._ikincil(d, "Ayrı altyazı penceresi aç", self.altyazi_penceresi_ac).pack(side="left")
        self._aciklama(k, "Ayrı pencere ikinci bir ekranda ya da oyunun yanında büyük altyazı için.")

        k = self._kart(s, "PHILIPS / ANDROID TV (ÇEVİRİX TV)")
        self._anahtar_satiri(k, "Altyazıyı TV'ye gönder", "tv_gonder",
                             "TV'deki Çevirix TV uygulaması bu bilgisayarı ağda kendisi bulur.", self._tv_degisti)
        self.tv_durum = self._aciklama(k, "", CAMGOBEGI)
        self._aciklama(k, f"TV'de Çevirix TV'yi açın; bilgisayar ve TV aynı Wi-Fi / modemde olmalı. "
                          f"TV bulamazsa uygulamaya bu adresi yazın: {self.ip}\n"
                          f"Windows ilk açılışta güvenlik duvarı izni sorarsa \"Özel ağlar\"a izin verin.")
        d = tk.Frame(k, bg=KART)
        d.pack(fill="x", padx=14, pady=(0, 10))
        self._dugme(d, "TV'ye örnek altyazı gönder", self.tv_ornek).pack(side="left")
        self._ikincil(d, "Test yazısı", self.test_yazisi).pack(side="left", padx=8)

        k = self._kart(s, "TARAYICI SAYFASI (iPhone, iPad, tablet)")
        self._anahtar_satiri(k, "Altyazı sayfasını aç", "web_sayfa",
                             "Aynı ağdaki herhangi bir cihazın tarayıcısında altyazılar canlı görünür.",
                             self._web_degisti)
        self.web_adres = f"http://{self.ip}:{WEB_PORT}"
        satir = tk.Frame(k, bg=KART)
        satir.pack(fill="x", padx=14, pady=4)
        tk.Label(satir, text=self.web_adres, bg=KART, fg=CAMGOBEGI, font=("Consolas", 11)).pack(side="left")
        self._ikincil(satir, "Kopyala", self.web_kopyala).pack(side="right")
        self._ikincil(satir, "Aç", lambda: webbrowser.open(self.web_adres)).pack(side="right", padx=6)
        self.web_durum = self._aciklama(k, "")
        tk.Frame(s.ic, bg=ARKA, height=10).pack()

    # ---------------------------------------------- 4) Daha fazla
    def _sayfa_daha(self, s):
        k = self._kart(s, "OKUMA")
        self._kaydirici(k, lambda v: f"Okuma aralığı: {v} ms (küçük = daha hızlı, daha çok işlemci)",
                        100, 1000, 50, "okuma_araligi_ms")
        self._kaydirici(k, lambda v: f"Altyazı kaybolunca gizleme süresi: {v} sn",
                        0.5, 5.0, 0.5, "gizleme_sn", ondalik=True)
        self._aciklama(k, "Okunan alanı değiştirmek için Oyna sekmesindeki \"Altyazı Alanını Seç\"i kullanın.")

        k = self._kart(s, "PS5 BAĞLANTI PROGRAMI (chiaki-ng)",
                       "Görüntü kalitesi, çözünürlük (720p önerilir), kare hızı ve PS5 eşleştirme "
                       "chiaki-ng'nin kendi ayarlarındadır.")
        self.chiaki_etiket = self._aciklama(k, "", YAZI)
        d = tk.Frame(k, bg=KART)
        d.pack(fill="x", padx=14, pady=(0, 10))
        self._ikincil(d, "Başka chiaki.exe seç…", self.chiaki_sec).pack(side="left")
        self._ikincil(d, "Varsayılana dön", self.chiaki_sifirla).pack(side="left", padx=8)
        self._chiaki_etiketi()

        k = self._kart(s, "AYARLAR")
        d = tk.Frame(k, bg=KART)
        d.pack(fill="x", padx=14, pady=(4, 6))
        self._ikincil(d, "Dışa aktar…", self.disa_aktar).pack(side="left")
        self._ikincil(d, "İçe aktar…", self.ice_aktar).pack(side="left", padx=8)
        self._ikincil(d, "Varsayılanlara dön", self.varsayilana_don).pack(side="left")
        self._aciklama(k, "Dışa aktarılan dosyada Gemini anahtarı bulunmaz. Ayarlar şu klasörde: "
                          + ayarlar.KLASOR)
        d = tk.Frame(k, bg=KART)
        d.pack(fill="x", padx=14, pady=(0, 10))
        self._ikincil(d, "Ayar klasörünü aç", lambda: os.startfile(ayarlar.KLASOR)
                      if os.path.isdir(ayarlar.KLASOR) else None).pack(side="left")

        k = self._kart(s, "KISAYOLLAR (oyun açıkken de çalışır)")
        self._aciklama(k, "F8 · Çeviriyi başlat / durdur\nF9 · Altyazıyı gizle / göster", YAZI)

        k = self._kart(s, "HAKKINDA")
        self._aciklama(k, f"Çevirix PC v{SURUM}  ·  Sokak sözlüğü: {self.sozluk.boyut} kalıp\n"
                          f"Bir sorun olursa \"Son hata raporu\"nun görüntüsünü gönderin.", YAZI)
        d = tk.Frame(k, bg=KART)
        d.pack(fill="x", padx=14, pady=(0, 10))
        self._ikincil(d, "Son hata raporu", lambda: self._son_hatayi_goster(elle=True)).pack(side="left")
        tk.Frame(s.ic, bg=ARKA, height=10).pack()

    # ------------------------------------------------------------ ayar işleyicileri
    def _metin_ayari(self, anahtar, deger):
        if self.ayar.get(anahtar) != deger:
            self.ayar[anahtar] = deger
            self._kaydet()

    def _model_degisti(self):
        from .gemini import VARSAYILAN_MODEL
        self._metin_ayari("gemini_model", self.model.get().strip() or VARSAYILAN_MODEL)
        self._model_dugmelerini_boya()

    def _model_dugmelerini_boya(self):
        secili = self.model.get().strip()
        for model, b in self.model_dugmeleri.items():
            evet = model == secili
            b.configure(bg=CAMGOBEGI if evet else KART2, fg="#05060c" if evet else YAZI)

    def _it(self, anahtar, d, alt, ust):
        self.ayar[anahtar] = max(alt, min(ust, int(self.ayar.get(anahtar)) + d))
        self._kaydet()
        self._stil_degisti()
        ad = "Yazı boyutu" if anahtar == "yazi_boyutu" else "Alttan yükseklik"
        self._durum(f"{ad}: {self.ayar[anahtar]}  (Altyazı & TV sekmesinde de ayarlanır)", CAMGOBEGI)
        self._kaydiricilari_esitle()

    def _kaydiricilari_esitle(self):
        # Kaydırıcılar DoubleVar'a bağlı; sayfa yeniden açıldığında doğru görünsünler diye yeniden kur
        sayfa = self.sayfalar["tv"]
        for c in sayfa.ic.winfo_children():
            c.destroy()
        self._sayfa_tv(sayfa)

    def _stil_degisti(self):
        self._onizleme_ciz()
        self.katman_yenile()
        if self._stil_bekliyor:
            self.kok.after_cancel(self._stil_bekliyor)
        self._stil_bekliyor = self.kok.after(300, lambda: self.tv.stil_gonder(ornek=True))

    def katman_yenile(self):
        katman = getattr(self, "katman", None)
        if katman is None:
            return
        if not self.ayar.get("pc_katman", True):
            katman.temizle()
        else:
            katman.yenile()

    def _konum_degisti(self):
        self.ayar["konum"] = self.konum.get()
        self._kaydet()
        self.katman_yenile()

    def _tv_degisti(self):
        if self.ayar.get("tv_gonder"):
            self.tv.baslat()
        else:
            self.tv.durdur()

    def _web_degisti(self):
        if self.ayar.get("web_sayfa"):
            self.web.baslat()
        else:
            self.web.durdur()

    def _ses_secildi(self):
        v = self.ses_secimi.get()
        self.ayar["ses_adi"] = "" if v.startswith("Otomatik") else v
        self._kaydet()
        self.ses.ayar_degisti()

    def _onizleme_ciz(self):
        c = self.onizleme
        w = c.winfo_width()
        if w < 50:
            return
        h = w * 9 // 16
        if int(c.cget("height")) != h:
            c.configure(height=h)
        c.delete("all")
        # TV ekranına benzeyen koyu sahne
        for i in range(12):
            renk = _karistir("#2a3c66", "#0a1020", i / 11)
            c.create_rectangle(0, i * h / 12, w, (i + 1) * h / 12 + 1, fill=renk, outline="")
        c.create_text(w / 2, h * 0.35, text="ÖNİZLEME", fill="#3a4c7a", font=("Segoe UI Black", max(8, h // 10)))
        boyut = int(self.ayar["yazi_boyutu"])
        px = max(6, int(boyut * h / 540))
        alt = int(int(self.ayar["alt_yukseklik"]) * h / 1080)
        y = h - alt
        if self.ayar.get("ingilizce_goster"):
            en = c.create_text(w / 2, y, text="Sample subtitle", fill="#d6dcf0", anchor="s",
                               font=("Segoe UI", -max(5, int(px * 0.55))))
            y = c.bbox(en)[1] - 2
        tr = c.create_text(w / 2, y, text="Örnek altyazı: Kanka bu iş çok temiz!", fill="#ffffff", anchor="s",
                           font=("Segoe UI Semibold", -px), width=w * 0.85, justify="center")
        koyuluk = int(self.ayar["arka_koyuluk"])
        if koyuluk > 0:
            x1, y1, x2, y2 = c.bbox(tr)
            c.create_rectangle(x1 - 6, y1 - 2, x2 + 6, y2 + 2, outline="",
                               fill=_karistir("#000000", "#1a2748", koyuluk / 255))
            c.tag_raise(tr)

    def _gecmis_bilgisi(self):
        n = len(self.gecmis.liste())
        self.gecmis_bilgi.configure(
            text="Henüz çeviri yok. Oyunda çevrilen satırlar burada birikir (son 300)." if n == 0
            else f"{n} satır kayıtlı. Kaçırdığın bir repliğe geri dönüp okuyabilirsin.")

    def _chiaki_etiketi(self):
        yol = chiaki_bul(self.ayar)
        self.chiaki_etiket.configure(text=f"Kullanılan: {yol}" if yol else "chiaki-ng bulunamadı.",
                                     fg=YAZI if yol else KIRMIZI)

    # ------------------------------------------------------------ işlemler
    def chiaki_ac(self):
        if ekran.pencere_bul(pid=self.motor.chiaki_pid):
            self._durum("PS5 bağlantı penceresi zaten açık", YESIL)
            return
        yol = chiaki_bul(self.ayar)
        if not yol:
            messagebox.showerror("Çevirix", "PS5 bağlantı programı (chiaki-ng) bulunamadı.\n"
                                            "Çevirix'i kurulum dosyasıyla yeniden kurun ya da "
                                            "Daha fazla › chiaki.exe seç.")
            return
        try:
            self.chiaki = subprocess.Popen([yol], cwd=os.path.dirname(yol))
            self.motor.chiaki_pid = self.chiaki.pid
            self._durum("PS5 bağlantı penceresi açılıyor…", CAMGOBEGI)
        except Exception as e:
            messagebox.showerror("Çevirix", f"Açılamadı: {e}")

    def chiaki_sec(self):
        yol = filedialog.askopenfilename(title="chiaki.exe seç", filetypes=[("Program", "*.exe")])
        if yol:
            self.ayar["chiaki_yolu"] = yol
            self._kaydet()
            self._chiaki_etiketi()

    def chiaki_sifirla(self):
        self.ayar["chiaki_yolu"] = ""
        self._kaydet()
        self._chiaki_etiketi()

    def ac_kapat(self):
        self._kaydet_simdi()
        if self.motor.calisiyor:
            self.motor.durdur()
            self.baslat_btn.configure(text="Çeviriyi Başlat  (F8)", bg=YESIL)
        else:
            self.motor.baslat()
            self.baslat_btn.configure(text="Çeviriyi Durdur  (F8)", bg=KIRMIZI)

    def gizle_goster(self):
        gizli = self.katman.gizle_goster()
        self._durum("Altyazı gizlendi (F9)" if gizli else "Altyazı gösteriliyor", PEMBE)

    def test_yazisi(self):
        self.motor.test_gonder()
        if self.tv_sayisi:
            self._durum("Test altyazısı gönderildi (bu ekran ve TV)", YESIL)
        else:
            self._durum("Test altyazısı gösterildi. TV bağlı değil: TV'de Çevirix TV'yi açın.", SARI)

    def tv_ornek(self):
        if self.tv.stil_gonder(ornek=True):
            self._durum("TV'ye örnek altyazı gönderildi", YESIL)
        else:
            self._durum("TV bağlı değil. TV'de Çevirix TV'yi açın, aynı ağda olsun.", SARI)

    def web_kopyala(self):
        self.kok.clipboard_clear()
        self.kok.clipboard_append(self.web_adres)
        self._durum("Adres kopyalandı", YESIL)

    def alan_sec(self):
        self.katman.temizle()

        def bitti(alan):
            if alan:
                self.ayar["alan"] = [round(v, 4) for v in alan]
                self._kaydet_simdi()
                self._durum("Altyazı alanı kaydedildi", YESIL)

        AlanSecici(self.kok, self.motor, bitti)

    def anahtari_dene(self):
        self.ayar["gemini_anahtar"] = self.anahtar.get().strip()
        self.anahtar_sonuc.configure(text="Deneniyor…", fg=SOLUK)

        def is_():
            ok, msg = self.motor.anahtari_dene()
            self.olaylar.put(("anahtar_sonuc", (ok, msg)))

        threading.Thread(target=is_, daemon=True).start()

    def sesi_dene(self):
        if not self.ayar.get("sesli_okuma"):
            self.ayar["sesli_okuma"] = True
            self._kaydet()
            deg, a = self.anahtarlar["sesli_okuma"]
            deg.set(True)
            a.ciz()
        sorun = self.ses.dene()
        self.ses_sonuc.configure(
            text=sorun or "Bir cümle okundu. Duymadıysan bilgisayarın sesini aç. Oyunda her yeni altyazı böyle okunur.",
            fg=KIRMIZI if sorun else YESIL)

    def _ses_listesi(self):
        self.ses_kutusu.configure(values=["Otomatik (Türkçe ses)"] + [ad for ad, _ in self.ses.sesler])

    def terimleri_kaydet(self):
        self.ayar["terimler"] = self.terim_kutusu.get("1.0", "end").strip()
        self._kaydet_simdi()
        n = len([x for x in self.ayar["terimler"].splitlines() if x.strip() and not x.strip().startswith("#")])
        self._durum(f"Terim sözlüğü kaydedildi ({n} terim)", YESIL)

    def terimleri_sifirla(self):
        self.terim_kutusu.delete("1.0", "end")
        self.terim_kutusu.insert("1.0", VARSAYILAN_TERIMLER)
        self.ayar["terimler"] = VARSAYILAN_TERIMLER
        self._kaydet_simdi()
        self._durum("Varsayılan terimler yüklendi", YESIL)

    def gecmisi_ac(self):
        satirlar = self.gecmis.liste()
        if not satirlar:
            self._durum("Geçmiş boş", SARI)
            return
        p = tk.Toplevel(self.kok)
        p.title("Çeviri geçmişi")
        p.configure(bg=ARKA)
        p.geometry("640x560")
        tk.Label(p, text="Bir satıra çift tıklayınca kopyalanır.", bg=ARKA, fg=SOLUK,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(10, 4))
        cer = tk.Frame(p, bg=ARKA)
        cer.pack(fill="both", expand=True, padx=12)
        liste = tk.Listbox(cer, bg=KART, fg=YAZI, selectbackground=KENAR, relief="flat", font=("Segoe UI", 10),
                           activestyle="none", highlightthickness=0)
        cubuk = ttk.Scrollbar(cer, orient="vertical", command=liste.yview)
        liste.configure(yscrollcommand=cubuk.set)
        liste.pack(side="left", fill="both", expand=True)
        cubuk.pack(side="right", fill="y")
        sira = []
        for e in satirlar:
            saat = time.strftime("%H:%M", time.localtime(e["at"] / 1000))
            liste.insert("end", f"{saat}  {e['tr']}")
            liste.insert("end", f"         {e['en']}")
            liste.itemconfigure("end", fg=SOLUK)
            liste.insert("end", "")
            sira += [e, e, None]

        def kopyala(_):
            sec = liste.curselection()
            if not sec or sira[sec[0]] is None:
                return
            e = sira[sec[0]]
            self.kok.clipboard_clear()
            self.kok.clipboard_append(f"{e['tr']}\n{e['en']}")
            self._durum("Kopyalandı", YESIL)

        liste.bind("<Double-Button-1>", kopyala)
        d = tk.Frame(p, bg=ARKA)
        d.pack(fill="x", padx=12, pady=10)

        def temizle():
            if messagebox.askyesno("Çevirix", "Tüm çeviri geçmişi silinsin mi?", parent=p):
                self.gecmis.temizle()
                self._gecmis_bilgisi()
                p.destroy()

        self._ikincil(d, "Temizle", temizle).pack(side="left")
        self._dugme(d, "Kapat", p.destroy).pack(side="right")

    def altyazi_penceresi_ac(self):
        if self.altyazi_penceresi:
            self.altyazi_penceresi.pen.lift()
            return

        def kapandi():
            self.altyazi_penceresi = None

        self.altyazi_penceresi = AltyaziPenceresi(self.kok, self.ayar, kapandi)
        if self.motor.son["tr"]:
            self.altyazi_penceresi.goster(self.motor.son["tr"], self.motor.son["en"])

    def disa_aktar(self):
        yol = filedialog.asksaveasfilename(title="Ayarları dışa aktar", defaultextension=".json",
                                           initialfile="cevirix-ayarlar.json", filetypes=[("JSON", "*.json")])
        if not yol:
            return
        try:
            self.ayar["terimler"] = self.terim_kutusu.get("1.0", "end").strip()
            ayarlar.disa_aktar(self.ayar, yol)
            self._durum("Ayarlar dışa aktarıldı", YESIL)
        except Exception as e:
            messagebox.showerror("Çevirix", f"Kaydedilemedi: {e}")

    def ice_aktar(self):
        yol = filedialog.askopenfilename(title="Ayarları içe aktar", filetypes=[("JSON", "*.json")])
        if not yol:
            return
        try:
            ayarlar.ice_aktar(self.ayar, yol)
        except Exception as e:
            messagebox.showerror("Çevirix", f"Ayarlar dosyadan alınamadı:\n{e}")
            return
        self._ayarlar_yuklendi("Ayarlar içe aktarıldı")

    def varsayilana_don(self):
        if not messagebox.askyesno("Çevirix", "Tüm ayarlar varsayılana dönsün mü?\n"
                                              "Gemini anahtarınız ve altyazı alanınız korunur."):
            return
        sakla = {k: self.ayar.get(k) for k in ("gemini_anahtar", "alan", "chiaki_yolu")}
        self.ayar.clear()
        self.ayar.update(ayarlar.VARSAYILAN)
        self.ayar.update(sakla)
        self._ayarlar_yuklendi("Ayarlar varsayılana döndü")

    def _ayarlar_yuklendi(self, mesaj):
        self._kaydet_simdi()
        for ad, kur in (("oyna", self._sayfa_oyna), ("ceviri", self._sayfa_ceviri), ("tv", self._sayfa_tv),
                        ("daha", self._sayfa_daha)):
            for c in self.sayfalar[ad].ic.winfo_children():
                c.destroy()
            kur(self.sayfalar[ad])
        self._ses_listesi()
        self._tv_degisti()
        self._web_degisti()
        self.ses.ayar_degisti()
        if self.motor.calisiyor:
            self.baslat_btn.configure(text="Çeviriyi Durdur  (F8)", bg=KIRMIZI)
        self.katman_yenile()
        self._durum(mesaj, YESIL)

    # ------------------------------------------------------------ hata raporu
    def _arayuz_hatasi(self, tur, deger, iz):
        metin = "".join(traceback.format_exception(tur, deger, iz))
        hata_yaz(metin)
        try:
            self._durum(f"Beklenmeyen hata: {deger} (Daha fazla › Son hata raporu)", KIRMIZI)
        except Exception:
            pass

    def _son_hatayi_goster(self, elle=False):
        try:
            with open(HATA_DOSYASI, encoding="utf-8") as f:
                metin = f.read()
        except Exception:
            if elle:
                messagebox.showinfo("Çevirix", "Kayıtlı hata yok.")
            return
        if not elle:
            try:
                os.replace(HATA_DOSYASI, HATA_DOSYASI + ".eski")
            except Exception:
                pass
        p = tk.Toplevel(self.kok)
        p.title("Son hatanın ayrıntısı")
        p.configure(bg=ARKA)
        p.geometry("640x420")
        tk.Label(p, text="Bu ekranın görüntüsünü ya da kopyaladığın metni gönder, sorunu buna göre düzelteceğim.",
                 bg=ARKA, fg=YAZI, wraplength=600, justify="left").pack(anchor="w", padx=12, pady=10)
        t = tk.Text(p, bg=KART, fg=YAZI, relief="flat", font=("Consolas", 9))
        t.pack(fill="both", expand=True, padx=12)
        t.insert("1.0", metin)
        d = tk.Frame(p, bg=ARKA)
        d.pack(fill="x", padx=12, pady=10)

        def kopyala():
            self.kok.clipboard_clear()
            self.kok.clipboard_append(metin)
            self._durum("Hata metni kopyalandı", YESIL)

        self._dugme(d, "Kopyala", kopyala).pack(side="left")
        self._ikincil(d, "Kapat", p.destroy).pack(side="right")

    # ------------------------------------------------------------ olaylar
    def _olaylari_isle(self):
        try:
            while True:
                o = self.olaylar.get_nowait()
                tur = o[0]
                if tur == "altyazi":
                    _, tr, en, motor, ms = o
                    self.katman.goster(tr, en)
                    self.son_tr.configure(text=tr)
                    self.son_en.configure(text=en)
                    self.cip_sure.configure(text=f"{ms / 1000:.1f} sn · {motor}".replace(".", ","))
                    self.cip_sure.pack(side="left")
                    if self.altyazi_penceresi:
                        self.altyazi_penceresi.goster(tr, en)
                elif tur == "temizle":
                    self.katman.temizle()
                    if self.altyazi_penceresi:
                        self.altyazi_penceresi.temizle()
                elif tur == "durum":
                    self._durum(o[1], CAMGOBEGI if self.motor.calisiyor else SOLUK)
                elif tur == "hata":
                    self._durum(o[1], KIRMIZI)
                    if not self.motor.calisiyor:
                        self.baslat_btn.configure(text="Çeviriyi Başlat  (F8)", bg=YESIL)
                elif tur == "model":
                    self.model.set(o[1])
                    self._kaydet()
                elif tur == "sizinti":
                    self.konum.set("ust")
                    self._konum_degisti()
                    self._durum("Türkçe yazı ekranın üstüne alındı (bu bilgisayarda gerekli)", PEMBE)
                elif tur == "anahtar_sonuc":
                    ok, msg = o[1]
                    self.anahtar_sonuc.configure(text=("✓ " if ok else "✗ ") + msg, fg=YESIL if ok else KIRMIZI)
                elif tur == "tv":
                    self.tv_sayisi = o[1]
                elif tur == "web":
                    self.web_sayisi = o[1]
                elif tur == "durum_tv":
                    self.tv_mesaj = o[1]
                    if not self.tv_sayisi:
                        self.tv_durum.configure(text=o[1], fg=SARI)
                elif tur == "durum_web":
                    self.web_durum.configure(text=o[1], fg=KIRMIZI)
                elif tur == "ses":
                    self._ses_listesi()
                    if o[1]:
                        self.ses_sonuc.configure(text=o[1], fg=KIRMIZI)
                elif tur == "ses_uyari":
                    self.ses_sonuc.configure(text=o[1], fg=SARI)
                elif tur == "tus":
                    if o[1] == 1:
                        self.ac_kapat()
                    elif o[1] == 2:
                        self.gizle_goster()
        except queue.Empty:
            pass
        self.kok.after(50, self._olaylari_isle)

    def _adim(self, anahtar, tamam, tamam_metin, bekle_metin):
        simge, durum = self.adimlar[anahtar]
        renk = CAMGOBEGI if tamam else SOLUK
        simge.delete("all")
        simge.create_oval(2, 2, 12, 12, fill=renk if tamam else "", outline=renk, width=2)
        durum.configure(text=("✓ " + tamam_metin) if tamam else bekle_metin, fg=renk)

    def _yenile(self):
        try:
            _, ps5 = self.motor.hedef()
            calisiyor = self.motor.calisiyor
            self._adim("ps5", ps5, "Açık", "Bağlı değil")
            self._adim("ceviri", calisiyor, "Okunuyor", "Kapalı")
            if not self.ayar.get("tv_gonder"):
                self._adim("tv", False, "", "Kapalı")
            else:
                self._adim("tv", self.tv_sayisi > 0, f"{self.tv_sayisi} TV bağlı", "Bekleniyor")
            renk = KENAR if not calisiyor else (YESIL if self.tv_sayisi else SARI)
            self.nokta.delete("all")
            self.nokta.create_oval(1, 1, 11, 11, fill=renk, outline="")
            self.cip_tv.configure(text=f"TV bağlı ({self.tv_sayisi})" if self.tv_sayisi else "TV bekleniyor",
                                  fg=YESIL if self.tv_sayisi else SOLUK)
            if not self.ayar.get("tv_gonder"):
                self.tv_durum.configure(text="TV'ye gönderim kapalı.", fg=SOLUK)
            elif self.tv_sayisi:
                self.tv_durum.configure(text=f"✓ {self.tv_sayisi} TV bağlı", fg=YESIL)
            else:
                self.tv_durum.configure(text=self.tv_mesaj or "TV bekleniyor…", fg=SARI)
            if self.ayar.get("web_sayfa") and self.web.calisiyor:
                self.web_durum.configure(
                    text=f"✓ {self.web_sayisi} cihaz izliyor" if self.web_sayisi
                    else "Sayfa açık. Telefonun ya da tabletin tarayıcısına yukarıdaki adresi yazın.",
                    fg=YESIL if self.web_sayisi else SOLUK)
            elif not self.ayar.get("web_sayfa"):
                self.web_durum.configure(text="Tarayıcı sayfası kapalı.", fg=SOLUK)
            t = self.motor.teshis
            if t["kare"]:
                self.teshis.configure(
                    text=f"Kaynak: {t['kaynak'] or '-'}  ·  {t['kare']} kare  ·  {t['okuma']} kez okundu\n"
                         f"Son okunan yazı: {t['ham'] or '(henüz yazı bulunamadı)'}")
        except Exception:
            pass
        self.kok.after(500, self._yenile)

    def _gecmisi_yaz(self):
        self.gecmis.yaz()
        self.kok.after(30000, self._gecmisi_yaz)

    def kapat(self):
        self._kaydet_simdi()
        self.gecmis.yaz()
        self.motor.calisiyor = False
        try:
            self.tv.durdur()
            self.web.durdur()
        except Exception:
            pass
        self.kok.destroy()

    def calistir(self):
        self.kok.mainloop()


def _hata_kancalari():
    def genel(tur, deger, iz):
        hata_yaz("".join(traceback.format_exception(tur, deger, iz)))

    def is_parcacigi(arg):
        if arg.exc_type is SystemExit:
            return
        hata_yaz(f"İş parçacığı: {arg.thread.name if arg.thread else '-'}\n" +
                 "".join(traceback.format_exception(arg.exc_type, arg.exc_value, arg.exc_traceback)))

    sys.excepthook = genel
    threading.excepthook = is_parcacigi


def main():
    _hata_kancalari()
    try:
        Uygulama().calistir()
    except Exception:
        metin = traceback.format_exc()
        hata_yaz(metin)
        try:
            messagebox.showerror("Çevirix", "Çevirix açılırken hata oluştu:\n\n" + metin[-1500:])
        except Exception:
            pass
