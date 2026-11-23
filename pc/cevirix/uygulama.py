"""Çevirix PC: ana pencere, altyazı katmanı ve alan seçici."""
import glob
import os
import queue
import subprocess
import sys
import tkinter as tk
import webbrowser
from tkinter import messagebox

from . import ayarlar, ekran
from .motor import Motor
from .sozluk import Sozluk

SURUM = "1.0"

ARKA = "#0b0d18"
KART = "#151a2e"
KENAR = "#262d4a"
YAZI = "#e9ecff"
SOLUK = "#8a93b8"
CAMGOBEGI = "#00e5ff"
PEMBE = "#ff2bd6"
YESIL = "#2ee59d"
KIRMIZI = "#ff5470"


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


# ---------------------------------------------------------------- katman
class Katman:
    """Oyunun üstünde duran, tıklamayı geçiren Türkçe altyazı."""

    def __init__(self, kok, ayar, motor):
        self.ayar, self.motor = ayar, motor
        self.pen = tk.Toplevel(kok)
        self.pen.overrideredirect(True)
        self.pen.attributes("-topmost", True)
        self.pen.attributes("-alpha", 0.92)
        self.pen.configure(bg="#000000")
        self.etiket = tk.Label(self.pen, text="", fg="#ffffff", bg="#000000", justify="center",
                               padx=22, pady=10)
        self.etiket.pack()
        self.pen.withdraw()
        self.gizli = False       # F9 ile kullanıcı gizledi mi
        self.metin = ""
        self._hazir = False
        self._sabitle()

    def _sabitle(self):
        if self.pen.winfo_viewable():
            ekran.en_ustte(ekran.tk_hwnd(self.pen))
        self.pen.after(1500, self._sabitle)

    def goster(self, tr):
        self.metin = tr
        if self.gizli or not tr:
            return
        (x, y, w, h), _ = self.motor.altyazi_alani()
        (hx, hy, hw, hh), _ = self.motor.hedef()
        boyut = int(self.ayar.get("yazi_boyutu", 30))
        self.etiket.configure(text=tr, font=("Segoe UI Semibold", boyut),
                              wraplength=max(300, int(hw * 0.8)))
        self.pen.update_idletasks()
        kw, kh = self.etiket.winfo_reqwidth(), self.etiket.winfo_reqheight()
        kx = hx + (hw - kw) // 2
        if self.ayar.get("konum") == "ust":
            ky = hy + int(hh * 0.04)
        else:
            # İngilizce altyazının tam üstüne, alt kenarına hizalı
            ky = min(y + h - kh, hy + hh - kh - 4)
            ky = max(hy, ky)
        self.pen.geometry(f"{kw}x{kh}+{kx}+{ky}")
        self.pen.deiconify()
        if not self._hazir:
            self.pen.update_idletasks()
            ekran.katman_yap(ekran.tk_hwnd(self.pen))
            self._hazir = True
        ekran.en_ustte(ekran.tk_hwnd(self.pen))

    def temizle(self):
        self.metin = ""
        self.pen.withdraw()

    def gizle_goster(self):
        self.gizli = not self.gizli
        if self.gizli:
            self.pen.withdraw()
        elif self.metin:
            self.goster(self.metin)
        return self.gizli


# ---------------------------------------------------------------- alan seçici
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


# ---------------------------------------------------------------- ana pencere
class Uygulama:
    def __init__(self):
        ekran.dpi_farkinda()
        self.ayar = ayarlar.yukle()
        self.olaylar = queue.Queue()
        self.sozluk = Sozluk(kaynak("sokak_sozlugu.json"))
        self.motor = Motor(self.ayar, self.olaylar, self.sozluk)
        self.chiaki = None

        self.kok = tk.Tk()
        self.kok.title("Çevirix PC – Oyun Çevirici")
        self.kok.configure(bg=ARKA)
        self.kok.minsize(560, 700)
        try:
            self.kok.iconbitmap(kaynak("cevirix.ico"))
        except Exception:
            pass
        self.kok.protocol("WM_DELETE_WINDOW", self.kapat)
        self._arayuz()
        self.katman = Katman(self.kok, self.ayar, self.motor)
        ekran.KisayolTuslari(lambda kid: self.olaylar.put(("tus", kid)))
        self.kok.after(50, self._olaylari_isle)
        if not self.ayar.get("gemini_anahtar"):
            self._durum("Önce aşağıya Gemini anahtarınızı yazın", PEMBE)

    # ---------------------------------------------- arayüz
    def _dugme(self, ust, metin, komut, renk=CAMGOBEGI, buyuk=False):
        b = tk.Button(ust, text=metin, command=komut, bg=renk, fg="#05060c", activebackground=YAZI,
                      relief="flat", bd=0, cursor="hand2",
                      font=("Segoe UI Semibold", 14 if buyuk else 11), padx=14, pady=10 if buyuk else 6)
        return b

    def _kart(self, baslik):
        f = tk.Frame(self.icerik, bg=KART, highlightbackground=KENAR, highlightthickness=1)
        f.pack(fill="x", padx=18, pady=7)
        tk.Label(f, text=baslik, bg=KART, fg=SOLUK, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        return f

    def _arayuz(self):
        ust = tk.Frame(self.kok, bg=ARKA)
        ust.pack(fill="x", padx=18, pady=(14, 4))
        try:
            img = tk.PhotoImage(file=kaynak("logo.png"))
            oran = max(1, img.width() // 90)
            self._logo = img.subsample(oran, oran)
            tk.Label(ust, image=self._logo, bg=ARKA).pack(side="left")
        except Exception:
            pass
        ad = tk.Frame(ust, bg=ARKA)
        ad.pack(side="left", padx=12)
        tk.Label(ad, text="ÇEVİRİX PC", bg=ARKA, fg=CAMGOBEGI, font=("Segoe UI Black", 22)).pack(anchor="w")
        tk.Label(ad, text="PS5 oyunlarını Türkçe altyazıyla oyna", bg=ARKA, fg=SOLUK,
                 font=("Segoe UI", 10)).pack(anchor="w")

        self.icerik = tk.Frame(self.kok, bg=ARKA)
        self.icerik.pack(fill="both", expand=True)

        k1 = self._kart("1 · PS5'E BAĞLAN")
        tk.Label(k1, text="PS5 görüntüsü bu bilgisayara gelir. İlk seferde PS5'i eşleştirmeniz gerekir.",
                 bg=KART, fg=YAZI, font=("Segoe UI", 10), wraplength=500, justify="left").pack(anchor="w", padx=14)
        self._dugme(k1, "▶  PS5'e Bağlan", self.chiaki_ac).pack(anchor="w", padx=14, pady=10)

        k2 = self._kart("2 · ÇEVİRİ")
        satir = tk.Frame(k2, bg=KART)
        satir.pack(fill="x", padx=14, pady=(2, 10))
        self.baslat_btn = self._dugme(satir, "Çeviriyi Başlat  (F8)", self.ac_kapat, YESIL, buyuk=True)
        self.baslat_btn.pack(side="left")
        self._dugme(satir, "Altyazı Alanını Seç", self.alan_sec, KENAR).pack(side="left", padx=10)
        self.durum = tk.Label(k2, text="Hazır", bg=KART, fg=SOLUK, font=("Segoe UI", 10), anchor="w")
        self.durum.pack(fill="x", padx=14)
        self.son_en = tk.Label(k2, text="", bg=KART, fg=SOLUK, font=("Segoe UI", 10, "italic"),
                               wraplength=500, justify="left", anchor="w")
        self.son_en.pack(fill="x", padx=14, pady=(6, 0))
        self.son_tr = tk.Label(k2, text="Çeviriler burada da görünür", bg=KART, fg=YAZI,
                               font=("Segoe UI Semibold", 14), wraplength=500, justify="left", anchor="w")
        self.son_tr.pack(fill="x", padx=14, pady=(2, 12))

        k3 = self._kart("3 · AYARLAR")
        g = tk.Frame(k3, bg=KART)
        g.pack(fill="x", padx=14, pady=(0, 12))
        g.columnconfigure(1, weight=1)

        def etiket(r, t):
            tk.Label(g, text=t, bg=KART, fg=YAZI, font=("Segoe UI", 10)).grid(row=r, column=0, sticky="w", pady=5)

        etiket(0, "Gemini anahtarı")
        self.anahtar = tk.StringVar(value=self.ayar.get("gemini_anahtar", ""))
        tk.Entry(g, textvariable=self.anahtar, show="•", bg=ARKA, fg=YAZI, insertbackground=YAZI,
                 relief="flat").grid(row=0, column=1, sticky="ew", padx=8, ipady=4)
        tk.Button(g, text="Anahtar al", command=lambda: webbrowser.open("https://aistudio.google.com/apikey"),
                  bg=KART, fg=CAMGOBEGI, relief="flat", cursor="hand2", bd=0).grid(row=0, column=2)

        etiket(1, "Model")
        self.model = tk.StringVar(value=self.ayar.get("gemini_model", ""))
        tk.Entry(g, textvariable=self.model, bg=ARKA, fg=YAZI, insertbackground=YAZI,
                 relief="flat").grid(row=1, column=1, sticky="ew", padx=8, ipady=4)

        etiket(2, "Yazı boyutu")
        self.boyut = tk.IntVar(value=int(self.ayar.get("yazi_boyutu", 30)))
        tk.Scale(g, from_=16, to=60, orient="horizontal", variable=self.boyut, bg=KART, fg=YAZI,
                 troughcolor=ARKA, highlightthickness=0, command=lambda _: self._kaydet()
                 ).grid(row=2, column=1, sticky="ew", padx=8)

        etiket(3, "Türkçe altyazı")
        self.konum = tk.StringVar(value=self.ayar.get("konum", "kapat"))
        kf = tk.Frame(g, bg=KART)
        kf.grid(row=3, column=1, columnspan=2, sticky="w", padx=4)
        for deger, metin in (("kapat", "İngilizcenin üstüne"), ("ust", "Ekranın üstüne")):
            tk.Radiobutton(kf, text=metin, value=deger, variable=self.konum, command=self._kaydet,
                           bg=KART, fg=YAZI, selectcolor=ARKA, activebackground=KART).pack(side="left", padx=4)

        alt = tk.Frame(k3, bg=KART)
        alt.pack(fill="x", padx=14, pady=(0, 12))
        self._dugme(alt, "Kaydet", self._kaydet_bildir).pack(side="left")
        self._dugme(alt, "Terim Sözlüğü", self.terimler, KENAR).pack(side="left", padx=10)

        tk.Label(self.kok, text=f"F8: çeviriyi başlat/durdur   •   F9: altyazıyı gizle/göster   •   "
                                f"Sokak sözlüğü: {self.sozluk.boyut} kalıp   •   v{SURUM}",
                 bg=ARKA, fg=SOLUK, font=("Segoe UI", 9)).pack(pady=(4, 10))

    # ---------------------------------------------- işlemler
    def _durum(self, t, renk=SOLUK):
        self.durum.configure(text=t, fg=renk)

    def _kaydet(self):
        self.ayar["gemini_anahtar"] = self.anahtar.get().strip()
        self.ayar["gemini_model"] = self.model.get().strip() or ayarlar.VARSAYILAN["gemini_model"]
        self.ayar["yazi_boyutu"] = int(self.boyut.get())
        self.ayar["konum"] = self.konum.get()
        ayarlar.kaydet(self.ayar)
        katman = getattr(self, "katman", None)
        if katman and katman.metin:
            self.katman.goster(self.katman.metin)

    def _kaydet_bildir(self):
        self._kaydet()
        self._durum("Ayarlar kaydedildi", YESIL)

    def chiaki_ac(self):
        if ekran.pencere_bul(pid=self.motor.chiaki_pid):
            self._durum("PS5 bağlantı penceresi zaten açık", YESIL)
            return
        yol = chiaki_bul(self.ayar)
        if not yol:
            messagebox.showerror("Çevirix", "PS5 bağlantı programı (chiaki-ng) bulunamadı.\n"
                                            "Çevirix'i kurulum dosyasıyla yeniden kurun.")
            return
        try:
            self.chiaki = subprocess.Popen([yol], cwd=os.path.dirname(yol))
            self.motor.chiaki_pid = self.chiaki.pid
            self._durum("PS5 bağlantı penceresi açılıyor…", CAMGOBEGI)
        except Exception as e:
            messagebox.showerror("Çevirix", f"Açılamadı: {e}")

    def ac_kapat(self):
        self._kaydet()
        if self.motor.calisiyor:
            self.motor.durdur()
            self.katman.temizle()
            self.baslat_btn.configure(text="Çeviriyi Başlat  (F8)", bg=YESIL)
        else:
            self.motor.baslat()
            self.baslat_btn.configure(text="Çeviriyi Durdur  (F8)", bg=KIRMIZI)

    def alan_sec(self):
        self.katman.temizle()

        def bitti(alan):
            if alan:
                self.ayar["alan"] = [round(v, 4) for v in alan]
                ayarlar.kaydet(self.ayar)
                self._durum("Altyazı alanı kaydedildi", YESIL)

        AlanSecici(self.kok, self.motor, bitti)

    def terimler(self):
        p = tk.Toplevel(self.kok)
        p.title("Terim Sözlüğü")
        p.configure(bg=ARKA)
        tk.Label(p, text="Her satıra bir ad: çevrilmeden aynen kalır.\n"
                         "Sabit karşılık için:  wanted level = aranma seviyesi",
                 bg=ARKA, fg=SOLUK, justify="left").pack(anchor="w", padx=12, pady=8)
        t = tk.Text(p, width=50, height=20, bg=KART, fg=YAZI, insertbackground=YAZI, relief="flat")
        t.pack(padx=12, fill="both", expand=True)
        t.insert("1.0", self.ayar.get("terimler", ""))

        def kaydet():
            self.ayar["terimler"] = t.get("1.0", "end").strip()
            ayarlar.kaydet(self.ayar)
            p.destroy()

        self._dugme(p, "Kaydet", kaydet).pack(pady=10)

    # ---------------------------------------------- olaylar
    def _olaylari_isle(self):
        try:
            while True:
                o = self.olaylar.get_nowait()
                tur = o[0]
                if tur == "altyazi":
                    self.katman.goster(o[1])
                    self.son_tr.configure(text=o[1])
                    self.son_en.configure(text=o[2])
                elif tur == "temizle":
                    self.katman.temizle()
                elif tur == "durum":
                    self._durum(o[1], CAMGOBEGI if self.motor.calisiyor else SOLUK)
                elif tur == "hata":
                    self._durum(o[1], KIRMIZI)
                    if not self.motor.calisiyor:
                        self.baslat_btn.configure(text="Çeviriyi Başlat  (F8)", bg=YESIL)
                elif tur == "model":
                    self.model.set(o[1])
                    ayarlar.kaydet(self.ayar)
                elif tur == "sizinti":
                    self.konum.set("ust")
                    self._kaydet()
                    self._durum("Türkçe yazı ekranın üstüne alındı (bu bilgisayarda gerekli)", PEMBE)
                elif tur == "tus":
                    if o[1] == 1:
                        self.ac_kapat()
                    elif o[1] == 2:
                        gizli = self.katman.gizle_goster()
                        self._durum("Altyazı gizlendi (F9)" if gizli else "Altyazı gösteriliyor", PEMBE)
        except queue.Empty:
            pass
        self.kok.after(50, self._olaylari_isle)

    def kapat(self):
        self._kaydet()
        self.motor.calisiyor = False
        self.kok.destroy()

    def calistir(self):
        self.kok.mainloop()


def main():
    Uygulama().calistir()
