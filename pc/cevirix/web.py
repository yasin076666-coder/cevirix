"""Tarayıcı altyazı sayfası (telefondaki WebSubtitlePage'in karşılığı).

iPhone, iPad, tablet ya da başka bir bilgisayarda http://<bu bilgisayar>:8790 açılınca
Türkçe altyazılar canlı görünür. Sayfa altyazıları aynı porttaki /events akışından (SSE) alır.
"""
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8790

MANIFEST = ('{"name":"Çevirix Altyazı","short_name":"Çevirix","display":"fullscreen","orientation":"landscape",'
            '"background_color":"#050C20","theme_color":"#050C20","start_url":"/"}')

SAYFA = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Çevirix">
<meta name="theme-color" content="#050C20">
<link rel="manifest" href="/manifest.json">
<title>Çevirix Altyazı</title>
<style>
html,body{margin:0;height:100%;background:#050C20;color:#EEF4FF;font-family:-apple-system,"Segoe UI",Roboto,sans-serif;overflow:hidden;-webkit-user-select:none;user-select:none}
#stage{position:fixed;inset:0;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;padding:0 5vw calc(env(safe-area-inset-bottom) + 9vh)}
#sub{max-width:92vw;text-align:center;font-weight:600;line-height:1.3;background:rgba(0,0,0,.72);border-radius:12px;padding:.25em .6em;font-size:var(--fs,6vh);transition:opacity .15s}
#en{max-width:92vw;text-align:center;color:#C9D3EA;font-size:calc(var(--fs,6vh)*.55);margin-top:.3em}
.empty{opacity:0}
#top{position:fixed;top:calc(env(safe-area-inset-top) + 10px);left:12px;right:12px;display:flex;justify-content:space-between;align-items:center;font-size:14px;color:#8C9CC0}
#dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#FFC94D;margin-right:7px;vertical-align:1px}
#dot.ok{background:#3EE0F0}
button{background:#15233F;color:#EEF4FF;border:1px solid #1F3157;border-radius:12px;font-size:16px;min-width:46px;height:40px;margin-left:6px}
#hint{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;padding:0 10vw;color:#8C9CC0;font-size:17px;line-height:1.5;pointer-events:none}
</style>
</head>
<body>
<div id="top"><span><span id="dot"></span><span id="state">Bağlanıyor…</span></span>
<span><button id="dn" aria-label="Yazıyı küçült">A−</button><button id="up" aria-label="Yazıyı büyüt">A+</button><button id="fs" aria-label="Tam ekran">⛶</button></span></div>
<div id="hint">Çevirix PC'de çeviri başlayınca Türkçe altyazılar burada görünür.<br>iPhone'da Paylaş › Ana Ekrana Ekle ile uygulama gibi kullanabilirsin.</div>
<div id="stage"><div id="sub" class="empty"></div><div id="en" class="empty"></div></div>
<script>
(function(){
  var sub=document.getElementById('sub'),en=document.getElementById('en'),dot=document.getElementById('dot'),state=document.getElementById('state'),hint=document.getElementById('hint');
  var fs=6; try{fs=parseFloat(localStorage.getItem('cx_fs'))||6}catch(e){}
  function applyFs(){document.documentElement.style.setProperty('--fs',fs+'vh');try{localStorage.setItem('cx_fs',fs)}catch(e){}}
  applyFs();
  document.getElementById('up').onclick=function(){fs=Math.min(14,fs+0.5);applyFs()};
  document.getElementById('dn').onclick=function(){fs=Math.max(3,fs-0.5);applyFs()};
  document.getElementById('fs').onclick=function(){var d=document.documentElement;(d.requestFullscreen||d.webkitRequestFullscreen||function(){}).call(d)};
  var timer=null;
  function show(o){sub.textContent=o.tr||'';sub.className='';en.textContent=o.en||'';en.className=(o.showEn&&o.en)?'':'empty';hint.style.display='none';clearTimeout(timer);timer=setTimeout(clear,15000)}
  function clear(){sub.className='empty';en.className='empty'}
  var lock=null;
  function wake(){try{if(navigator.wakeLock&&!lock)navigator.wakeLock.request('screen').then(function(l){lock=l;l.addEventListener('release',function(){lock=null})}).catch(function(){})}catch(e){}}
  document.addEventListener('visibilitychange',function(){if(!document.hidden)wake()});
  document.addEventListener('click',wake);
  wake();
  var es=null;
  function connect(){
    try{es&&es.close()}catch(e){}
    es=new EventSource('/events');
    es.onopen=function(){dot.className='ok';state.textContent='Bağlı'};
    es.onerror=function(){dot.className='';state.textContent='Bilgisayar bekleniyor…'};
    es.addEventListener('subtitle',function(e){try{show(JSON.parse(e.data))}catch(x){}});
    es.addEventListener('clear',function(){clear()});
  }
  connect();
})();
</script>
</body>
</html>"""


class WebSayfasi:
    def __init__(self, ayar, bildir):
        self.ayar = ayar
        self.bildir = bildir
        self._sunucu = None
        self._dinleyiciler = set()
        self._kilit = threading.Lock()
        self._son = None

    @property
    def calisiyor(self):
        return self._sunucu is not None

    @property
    def izleyici_sayisi(self):
        return len(self._dinleyiciler)

    def baslat(self):
        if self._sunucu:
            return
        sahip = self

        class Isleyici(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                yol = self.path.split("?", 1)[0]
                if yol == "/events":
                    return self._akis()
                if yol == "/manifest.json":
                    govde, tur = MANIFEST.encode("utf-8"), "application/manifest+json"
                else:
                    govde, tur = SAYFA.encode("utf-8"), "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", tur)
                self.send_header("Content-Length", str(len(govde)))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(govde)
                self.close_connection = True

            def _akis(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                q = queue.Queue(maxsize=50)
                with sahip._kilit:
                    sahip._dinleyiciler.add(q)
                    if sahip._son:
                        q.put_nowait(sahip._son)
                sahip.bildir("web", len(sahip._dinleyiciler))
                try:
                    self.wfile.write(b"retry: 2000\n\n")
                    self.wfile.flush()
                    while sahip._sunucu is not None:
                        try:
                            olay = q.get(timeout=15)
                        except queue.Empty:
                            olay = ": canli\n\n"
                        self.wfile.write(olay.encode("utf-8"))
                        self.wfile.flush()
                except Exception:
                    pass
                finally:
                    with sahip._kilit:
                        sahip._dinleyiciler.discard(q)
                    sahip.bildir("web", len(sahip._dinleyiciler))
                    self.close_connection = True

        try:
            s = ThreadingHTTPServer(("0.0.0.0", PORT), Isleyici)
            s.daemon_threads = True
        except OSError as e:
            self.bildir("durum_web", f"Tarayıcı sayfası açılamadı (port {PORT}): {e.strerror or e}")
            return
        self._sunucu = s
        threading.Thread(target=s.serve_forever, daemon=True, name="cevirix-web").start()

    def durdur(self):
        s = self._sunucu
        self._sunucu = None
        if s:
            threading.Thread(target=lambda: (s.shutdown(), s.server_close()), daemon=True).start()
        self.bildir("web", 0)

    def _yay(self, olay, sakla=False):
        with self._kilit:
            self._son = olay if sakla else None
            for q in list(self._dinleyiciler):
                try:
                    q.put_nowait(olay)
                except queue.Full:
                    pass

    def goster(self, tr, en, sira, kesin=True):
        veri = json.dumps({"tr": tr, "en": en, "showEn": bool(self.ayar.get("ingilizce_goster"))},
                          ensure_ascii=False)
        self._yay(f"event: subtitle\ndata: {veri}\n\n", sakla=True)

    def kesinlesti(self, tr, sira):
        pass

    def temizle(self):
        self._yay("event: clear\ndata: {}\n\n")
