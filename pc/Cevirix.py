"""Çevirix PC giriş noktası (PyInstaller bunu derler)."""
import os
import sys


def oz_test(cikti):
    """Derleme sonrası denetim: paketin içinde OCR, sözlük, TV sunucusu, tarayıcı sayfası,
    ses motoru ve arayüz gerçekten çalışıyor mu."""
    import json
    import time
    import traceback
    sonuc = {}

    def dene(ad, is_):
        try:
            sonuc[ad] = is_()
        except Exception:
            sonuc[ad + "_hata"] = traceback.format_exc()

    def ocr():
        import cv2
        import numpy as np
        from cevirix.okuyucu import Okuyucu
        img = np.zeros((120, 900, 3), dtype=np.uint8)
        cv2.putText(img, "We gotta get outta here, bro.", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                    (255, 255, 255), 3, cv2.LINE_AA)
        return Okuyucu().oku(img)

    def sozluk():
        from cevirix.sozluk import Sozluk
        from cevirix.uygulama import kaynak
        s = Sozluk(kaynak("sokak_sozlugu.json"))
        sonuc["sozluk_ornek"] = s.cevir("What's up?")
        sonuc["sokak"] = s.makine_ile_cevir("Yo bro, can you hear me?",
                                            lambda t: "Beni duyabiliyor musunuz?")
        return s.boyut

    def yakalama():
        from cevirix.ekran import Yakalayici
        return list(Yakalayici().al(0, 0, 64, 32).shape)

    def pencere():
        # Arkadaki pencereyi okuma: önce görünür bir pencere aç, üstüne başka pencere koy, yine oku
        import tkinter as tk
        from cevirix import ekran
        from cevirix.baglanti import BAGLI, KAPANDI, BaglantiIzleyici
        kok = tk.Tk()
        kok.geometry("400x300+50+50")
        kok.configure(bg="#ff0000")
        ust = tk.Toplevel(kok)
        ust.geometry("500x400+0+0")
        ust.configure(bg="#0000ff")
        for _ in range(20):
            kok.update()
            time.sleep(0.05)
        kare = ekran.pencere_goruntusu(ekran.tk_hwnd(kok))
        kok.destroy()
        assert kare is not None, "PrintWindow görüntü vermedi"
        kirmizi = float(kare[:, :, 2].mean())
        sonuc["pencere_kirmizi"] = round(kirmizi)
        sonuc["islem"] = ekran.islem_calisiyor(("cevirix.exe",))
        # Bağlantı izleyici: sahte chiaki kaydı
        import tempfile
        kl = tempfile.mkdtemp()
        b = BaglantiIzleyici(kl)
        yol = os.path.join(kl, "chiaki_session_test.log")
        with open(yol, "w", encoding="utf-8") as f:
            f.write("[I] Ctrl received Login message: success\n")
        d1 = b.yokla(True)
        with open(yol, "a", encoding="utf-8") as f:
            f.write("[I] Session has quit\n")
        d2 = b.yokla(True)
        assert (d1, d2) == (BAGLI, KAPANDI), (d1, d2)
        return "tamam" if kirmizi > 200 else f"arkadaki pencere okunamadı (kırmızı={kirmizi:.0f})"

    def gta():
        # Yapay bir oyun karesi: koyu sahnede beyaz ekranlı telefon, üstte ad, altında üç mesaj
        import cv2
        import numpy as np
        from cevirix import gta as g
        from cevirix.okuyucu import Okuyucu
        kare = np.full((720, 1280, 3), 40, dtype=np.uint8)
        cv2.rectangle(kare, (700, 120), (960, 600), (245, 245, 245), -1)
        yaz = lambda t, x, y, s=0.62: cv2.putText(kare, t, (x, y), cv2.FONT_HERSHEY_SIMPLEX, s, (20, 20, 20), 2,  # noqa: E731
                                                  cv2.LINE_AA)
        yaz("Lucia", 795, 160, 0.8)
        yaz("Where are you", 712, 240)
        yaz("right now?", 712, 265)
        yaz("The cops are", 712, 340)
        yaz("all over town.", 712, 365)
        yaz("Meet me at the", 712, 440)
        yaz("docks tonight.", 712, 465)
        gelen = []
        o = g.GtaOkuyucu(Okuyucu(), lambda t: "TR " + t, lambda l: gelen.append(l),
                         os.path.join(tempfile.mkdtemp(), "m.json"))
        img = g.RgbResim.kareden(kare)
        tel = g.TelefonBulucu().bul(img)
        sonuc["gta_telefon"] = [round(v, 3) for v in tel["box"]] if tel else None
        assert tel, "telefon bulunamadı"
        for _ in range(3):
            o._son_bulma = o._son_okuma = -10 ** 12
            o._son_harita = 10 ** 15        # harita kartı bu denemede okunmasın
            o.kare(kare)
        son = gelen[-1] if gelen else []
        balon = [x["text"] for x in son if x.get("side")]
        sonuc["gta_balonlar"] = balon
        sonuc["gta_kart"] = g.kart_bul([("MAKE MONEY", (0.62, 0.40, 0.80, 0.43)),
                                        ("Rob the store on the corner of Ocean Drive.", (0.62, 0.44, 0.95, 0.47))])
        return "tamam" if len(balon) >= 2 else f"balon yok: {son}"

    def tv():
        from websockets.sync.client import connect
        from cevirix import ayarlar
        from cevirix.tv import PORT, TvSunucusu
        t = TvSunucusu(dict(ayarlar.VARSAYILAN), lambda *a: None)
        t.baslat()
        try:
            for _ in range(40):
                try:
                    ws = connect(f"ws://127.0.0.1:{PORT}", open_timeout=2)
                    break
                except Exception:
                    time.sleep(0.25)
            else:
                raise RuntimeError(f"TV sunucusuna bağlanılamadı. Sunucu hatası: {t.son_hata}")
            with ws:
                merhaba = json.loads(ws.recv(timeout=5))
                assert merhaba["type"] == "hello", merhaba
                t.goster("Merhaba kanka", "Hello bro", 1)
                sub = json.loads(ws.recv(timeout=5))
                assert sub["type"] == "sub" and sub["tr"] == "Merhaba kanka", sub
            return "tamam"
        finally:
            t.durdur()

    def web():
        import urllib.request
        from cevirix import ayarlar
        from cevirix.web import PORT, WebSayfasi
        w = WebSayfasi(dict(ayarlar.VARSAYILAN), lambda *a: None)
        w.baslat()
        try:
            govde = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=5).read().decode("utf-8")
            assert "Çevirix" in govde
            return "tamam"
        finally:
            w.durdur()

    def ses():
        from cevirix import ayarlar
        from cevirix.ses import Ses
        s = Ses(dict(ayarlar.VARSAYILAN), lambda *a: None)
        s._hazir.wait(15)
        return {"sesler": [ad for ad, _ in s.sesler], "sorun": s.sorun}

    def arayuz():
        from cevirix.uygulama import Uygulama
        u = Uygulama()
        for ad in ("oyna", "ceviri", "tv", "daha", "oyna"):
            u.sekme(ad)
            u.kok.update()
        u.test_yazisi()
        for _ in range(10):
            u._olaylari_isle()
            u.kok.update()
            time.sleep(0.05)
        u._it("yazi_boyutu", 2, 16, 60)
        u.kok.update()
        u.kapat()
        return "tamam"

    def yaz():
        with open(cikti, "w", encoding="utf-8") as f:
            json.dump(sonuc, f, ensure_ascii=False, indent=2)

    # Her adımdan önce ve sonra yazılır: program bir adımda çökerse hangisi olduğu görülür
    import tempfile
    for ad, is_ in (("ocr", ocr), ("sozluk", sozluk), ("yakalama", yakalama), ("pencere", pencere), ("gta", gta),
                    ("tv", tv), ("web", web),
                    ("ses", ses), ("arayuz", arayuz)):
        sonuc["son_baslayan"] = ad
        yaz()
        dene(ad, is_)
        yaz()
    sonuc["son_baslayan"] = "bitti"
    yaz()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--test":
        oz_test(sys.argv[2])
    else:
        from cevirix.uygulama import main
        main()
