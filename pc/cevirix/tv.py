"""Çevirix TV bağlantısı (telefondaki SubtitleServer'ın karşılığı).

Philips / Android TV'deki Çevirix TV uygulaması bu bilgisayarı ağda kendisi bulur
(_altyazitr._tcp) ve 8765 numaralı porta WebSocket ile bağlanır. Mesaj biçimi telefonla aynı:
hello / sub / clear / style.
- Sunucu düşerse 2 sn sonra kendini yeniden kurar.
- TV yeniden bağlanınca görünüm ayarlarını ve son 6 sn içindeki altyazıyı tekrar yollar.
"""
import asyncio
import json
import socket
import threading
import time

PORT = 8765
NSD_TUR = "_altyazitr._tcp.local."
YENIDEN_GONDER_SN = 6.0


def yerel_ip():
    """Bu bilgisayarın ağdaki adresi (dışarıya veri gönderilmez, yalnız yönlendirme sorulur)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class TvSunucusu:
    def __init__(self, ayar, bildir):
        self.ayar = ayar
        self.bildir = bildir            # bildir(tur, deger): arayüze olay
        self._istemciler = set()
        self._dongu = None
        self._dur_olayi = None
        self.son_hata = None
        self._calisiyor = False
        self._son_sub = None
        self._son_sub_zaman = 0.0
        self._zc = None
        self._zc_bilgi = None
        self.ip = yerel_ip()

    # ------------------------------------------------------------ yaşam döngüsü
    def baslat(self):
        if self._calisiyor:
            return
        self._calisiyor = True
        threading.Thread(target=self._calistir, daemon=True, name="cevirix-tv").start()
        threading.Thread(target=self._duyur, daemon=True, name="cevirix-mdns").start()

    def durdur(self):
        self._calisiyor = False
        d, olay = self._dongu, self._dur_olayi
        if d and olay:
            try:
                d.call_soon_threadsafe(olay.set)
            except RuntimeError:
                pass
        self._duyuruyu_kaldir()
        self._istemciler = set()
        self.bildir("tv", 0)

    @property
    def istemci_sayisi(self):
        return len(self._istemciler)

    async def _sunucu(self):
        import websockets
        self._dur_olayi = asyncio.Event()
        if not self._calisiyor:
            return
        async with websockets.serve(self._baglanti, "0.0.0.0", PORT, ping_interval=8, ping_timeout=8):
            self.son_hata = None
            self.bildir("durum_tv", f"TV bağlantısı bekleniyor ({self.ip})")
            await self._dur_olayi.wait()

    def _calistir(self):
        while self._calisiyor:
            dongu = asyncio.new_event_loop()
            self._dongu = dongu
            asyncio.set_event_loop(dongu)
            try:
                dongu.run_until_complete(self._sunucu())
            except OSError as e:
                self.son_hata = repr(e)
                self.bildir("durum_tv", f"TV portu ({PORT}) açılamadı: {e.strerror or e}. Yeniden deneniyor…")
            except Exception as e:
                self.son_hata = repr(e)
                self.bildir("durum_tv", f"TV sunucusu hatası: {e}. Yeniden deneniyor…")
            finally:
                self._dongu = None
                self._dur_olayi = None
                try:
                    dongu.close()
                except Exception:
                    pass
            if self._calisiyor:
                time.sleep(2)

    async def _baglanti(self, ws, *_):
        self._istemciler.add(ws)
        self.bildir("tv", len(self._istemciler))
        try:
            await ws.send(json.dumps(self._stil("hello"), ensure_ascii=False))
            if self._son_sub and time.time() - self._son_sub_zaman < YENIDEN_GONDER_SN:
                await ws.send(self._son_sub)
            async for mesaj in ws:
                if mesaj == "ping":
                    await ws.send('{"type":"pong"}')
        except Exception:
            pass
        finally:
            self._istemciler.discard(ws)
            self.bildir("tv", len(self._istemciler))

    # ------------------------------------------------------------ ağda duyurma (mDNS)
    def _duyur(self):
        try:
            from zeroconf import ServiceInfo, Zeroconf
            ip = self.ip
            bilgi = ServiceInfo(NSD_TUR, f"CevirixPC-{socket.gethostname()[:20]}.{NSD_TUR}",
                                addresses=[socket.inet_aton(ip)], port=PORT,
                                server=f"cevirix-{socket.gethostname()[:20].lower()}.local.")
            zc = Zeroconf()
            zc.register_service(bilgi, allow_name_change=True)
            self._zc, self._zc_bilgi = zc, bilgi
            if not self._calisiyor:
                self._duyuruyu_kaldir()
        except Exception as e:
            self.bildir("durum_tv", f"Ağda duyurulamadı ({e}). TV'de bu adresi elle yazın: {self.ip}")

    def _duyuruyu_kaldir(self):
        zc, bilgi = self._zc, self._zc_bilgi
        self._zc = self._zc_bilgi = None
        if zc:
            try:
                zc.unregister_service(bilgi)
                zc.close()
            except Exception:
                pass

    # ------------------------------------------------------------ gönderme
    def _stil(self, tur):
        a = self.ayar
        return {"type": tur, "fontSize": int(a["yazi_boyutu"]), "yOffset": int(a["alt_yukseklik"]),
                "bgAlpha": int(a["arka_koyuluk"]), "showEn": bool(a["ingilizce_goster"])}

    def _yayinla(self, metin):
        d = self._dongu
        if not d or not self._istemciler:
            return

        async def gonder():
            for ws in list(self._istemciler):
                try:
                    await ws.send(metin)
                except Exception:
                    pass

        try:
            asyncio.run_coroutine_threadsafe(gonder(), d)
        except Exception:
            pass

    def goster(self, tr, en, sira, kesin=True):
        if not self.ayar.get("tv_gonder", True):
            return
        o = self._stil("sub")
        o.update({"tr": tr, "en": en, "seq": sira})
        metin = json.dumps(o, ensure_ascii=False)
        self._son_sub, self._son_sub_zaman = metin, time.time()
        self._yayinla(metin)

    def kesinlesti(self, tr, sira):
        pass

    def temizle(self):
        self._son_sub = None
        self._yayinla('{"type":"clear"}')

    def stil_gonder(self, ornek=True):
        """Görünüm ayarlarını TV'ye yollar; ornek=True ise TV örnek bir altyazı gösterir."""
        if not self._istemciler:
            return False
        o = self._stil("style")
        o["preview"] = ornek
        self._yayinla(json.dumps(o, ensure_ascii=False))
        return True
