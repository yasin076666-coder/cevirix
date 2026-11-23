package com.bugra.altyazi.phone

import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.ServerSocket
import java.net.Socket
import kotlin.concurrent.thread

/**
 * iPhone, iPad, Windows bilgisayar ya da herhangi bir tarayıcı için altyazı sayfası.
 * Adres: http://<telefon>:8790 — sayfa altyazıları 8787'deki olay akışından (SSE) alır.
 */
object WebSubtitlePage {
    const val PORT = 8790
    @Volatile private var server: ServerSocket? = null

    val url: String get() = "http://${NetUtil.localIp()}:$PORT"

    @Synchronized
    fun start() {
        if (server != null) return
        val s = try {
            ServerSocket(PORT).apply { reuseAddress = true }
        } catch (e: Exception) {
            return
        }
        server = s
        thread(name = "cevirix-web", isDaemon = true) {
            while (!s.isClosed) {
                val c = try { s.accept() } catch (e: Exception) { break }
                thread(isDaemon = true) { serve(c) }
            }
        }
    }

    @Synchronized
    fun stop() {
        runCatching { server?.close() }
        server = null
    }

    private fun serve(c: Socket) {
        c.use { sock ->
            try {
                sock.soTimeout = 5000
                val r = BufferedReader(InputStreamReader(sock.getInputStream()))
                val first = r.readLine() ?: return
                while (true) {
                    val l = r.readLine() ?: break
                    if (l.isEmpty()) break
                }
                val path = first.split(' ').getOrNull(1) ?: "/"
                val (type, body) = when {
                    path.startsWith("/manifest.json") -> "application/manifest+json" to MANIFEST
                    else -> "text/html; charset=utf-8" to PAGE
                }
                val bytes = body.toByteArray(Charsets.UTF_8)
                val head = "HTTP/1.1 200 OK\r\nContent-Type: $type\r\nContent-Length: ${bytes.size}\r\n" +
                    "Cache-Control: no-cache\r\nConnection: close\r\n\r\n"
                val out = sock.getOutputStream()
                out.write(head.toByteArray(Charsets.US_ASCII))
                out.write(bytes)
                out.flush()
            } catch (e: Exception) {
            }
        }
    }

    private const val MANIFEST = """{"name":"Çevirix Altyazı","short_name":"Çevirix","display":"fullscreen","orientation":"landscape","background_color":"#050C20","theme_color":"#050C20","start_url":"/"}"""

    private val PAGE = """<!DOCTYPE html>
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
#sub.empty{opacity:0}
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
<div id="hint">Çevirix'te oyunu açınca Türkçe altyazılar burada görünür.<br>iPhone'da Paylaş › Ana Ekrana Ekle ile uygulama gibi kullanabilirsin.</div>
<div id="stage"><div id="sub" class="empty"></div></div>
<script>
(function(){
  var sub=document.getElementById('sub'),dot=document.getElementById('dot'),state=document.getElementById('state'),hint=document.getElementById('hint');
  var fs=6; try{fs=parseFloat(localStorage.getItem('cx_fs'))||6}catch(e){}
  function applyFs(){document.documentElement.style.setProperty('--fs',fs+'vh');try{localStorage.setItem('cx_fs',fs)}catch(e){}}
  applyFs();
  document.getElementById('up').onclick=function(){fs=Math.min(14,fs+0.5);applyFs()};
  document.getElementById('dn').onclick=function(){fs=Math.max(3,fs-0.5);applyFs()};
  document.getElementById('fs').onclick=function(){var d=document.documentElement;(d.requestFullscreen||d.webkitRequestFullscreen||function(){}).call(d)};
  var timer=null;
  function show(t,ms){sub.textContent=t;sub.className='';hint.style.display='none';clearTimeout(timer);if(ms>0)timer=setTimeout(clear,ms)}
  function clear(){sub.className='empty'}
  var lock=null;
  function wake(){try{if(navigator.wakeLock&&!lock)navigator.wakeLock.request('screen').then(function(l){lock=l;l.addEventListener('release',function(){lock=null})}).catch(function(){})}catch(e){}}
  document.addEventListener('visibilitychange',function(){if(!document.hidden)wake()});
  document.addEventListener('click',wake);
  wake();
  var es=null;
  function connect(){
    try{es&&es.close()}catch(e){}
    es=new EventSource('http://'+location.hostname+':8787/events?viewer=obs');
    es.onopen=function(){dot.className='ok';state.textContent='Bağlı'};
    es.onerror=function(){dot.className='';state.textContent='Telefon bekleniyor…'};
    es.addEventListener('subtitle',function(e){try{var o=JSON.parse(e.data);show(o.text||'',o.duration||15000)}catch(x){}});
    es.addEventListener('clear',function(){clear()});
    es.addEventListener('stopped',function(){clear()});
  }
  connect();
})();
</script>
</body>
</html>"""
}
