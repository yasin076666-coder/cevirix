package com.bugra.altyazi.phone

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.SystemClock
import org.java_websocket.WebSocket
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.server.WebSocketServer
import org.json.JSONObject
import java.net.InetSocketAddress
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Telefonda çalışan WebSocket sunucusu. Philips TV bu sunucuya bağlanır.
 * - Port kapalı kalırsa / hata olursa kendini otomatik yeniden başlatır.
 * - Ağda kendini duyurur (NSD), TV telefonu IP yazmadan bulur.
 * - TV yeniden bağlandığında görünüm ayarlarını ve son altyazıyı tekrar yollar.
 */
class SubtitleServer(private val context: Context) {

    companion object {
        const val PORT = 8765
        const val NSD_TYPE = "_altyazitr._tcp"
        private const val RESEND_WINDOW_MS = 6000L
    }

    var onClientsChanged: ((Int) -> Unit)? = null
    var onNotice: ((String) -> Unit)? = null

    private val exec = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var server: Server? = null
    @Volatile private var running = false
    @Volatile private var lastSub: String? = null
    @Volatile private var lastSubAt = 0L
    private var nsdListener: NsdManager.RegistrationListener? = null

    fun start() {
        if (running) return
        running = true
        exec.execute { bindServer() }
        registerNsd()
    }

    fun stop() {
        running = false
        unregisterNsd()
        val s = server
        server = null
        try {
            exec.execute {
                try { s?.stop(500) } catch (e: Exception) { }
            }
            exec.shutdown()
        } catch (e: Exception) { }
    }

    private fun bindServer() {
        if (!running) return
        try {
            val s = Server(InetSocketAddress(PORT))
            s.setReuseAddr(true)
            s.setTcpNoDelay(true)
            s.setConnectionLostTimeout(8)
            server = s
            s.start()
        } catch (e: Exception) {
            scheduleRebind()
        }
    }

    private fun scheduleRebind() {
        if (!running) return
        try {
            exec.schedule(Runnable {
                if (running) {
                    val old = server
                    server = null
                    try { old?.stop(200) } catch (e: Exception) { }
                    bindServer()
                }
            }, 2, TimeUnit.SECONDS)
        } catch (e: Exception) { }
    }

    private fun styleJson(type: String): JSONObject = JSONObject()
        .put("type", type)
        .put("fontSize", Prefs.tvFontSize)
        .put("yOffset", Prefs.tvYOffset)
        .put("bgAlpha", Prefs.tvBgAlpha)
        .put("showEn", Prefs.tvShowEn)

    private fun broadcast(json: String) {
        try { server?.broadcast(json) } catch (e: Exception) { }
    }

    fun sendSubtitle(tr: String, en: String, seq: Long) {
        val json = styleJson("sub").put("tr", tr).put("en", en).put("seq", seq).toString()
        lastSub = json
        lastSubAt = SystemClock.elapsedRealtime()
        broadcast(json)
    }

    fun sendClear() {
        lastSub = null
        broadcast(JSONObject().put("type", "clear").toString())
    }

    fun sendStyle(preview: Boolean) {
        broadcast(styleJson("style").put("preview", preview).toString())
    }

    fun clientCount(): Int = try { server?.connections?.size ?: 0 } catch (e: Exception) { 0 }

    private inner class Server(addr: InetSocketAddress) : WebSocketServer(addr) {
        override fun onOpen(conn: WebSocket?, handshake: ClientHandshake?) {
            try {
                conn?.send(styleJson("hello").toString())
                val sub = lastSub
                if (sub != null && SystemClock.elapsedRealtime() - lastSubAt < RESEND_WINDOW_MS) conn?.send(sub)
            } catch (e: Exception) { }
            onClientsChanged?.invoke(connections.size)
        }

        override fun onClose(conn: WebSocket?, code: Int, reason: String?, remote: Boolean) {
            onClientsChanged?.invoke(connections.size)
        }

        override fun onMessage(conn: WebSocket?, message: String?) {
            if (message == "ping") {
                try { conn?.send("{\"type\":\"pong\"}") } catch (e: Exception) { }
            }
        }

        override fun onError(conn: WebSocket?, ex: Exception?) {
            if (conn == null && running) {
                // Sunucu soketi düştü (ör. port meşgul): kendini yeniden kur
                onNotice?.invoke("Bağlantı sunucusu yeniden başlatılıyor…")
                scheduleRebind()
            }
        }

        override fun onStart() {
            onNotice?.invoke("Çalışıyor – TV bağlantısı bekleniyor")
        }
    }

    private fun registerNsd() {
        try {
            val nsd = context.getSystemService(Context.NSD_SERVICE) as NsdManager
            val info = NsdServiceInfo().apply {
                serviceName = "AltyaziTelefon"
                serviceType = NSD_TYPE
                port = PORT
            }
            val listener = object : NsdManager.RegistrationListener {
                override fun onServiceRegistered(serviceInfo: NsdServiceInfo?) {}
                override fun onRegistrationFailed(serviceInfo: NsdServiceInfo?, errorCode: Int) {}
                override fun onServiceUnregistered(serviceInfo: NsdServiceInfo?) {}
                override fun onUnregistrationFailed(serviceInfo: NsdServiceInfo?, errorCode: Int) {}
            }
            nsd.registerService(info, NsdManager.PROTOCOL_DNS_SD, listener)
            nsdListener = listener
        } catch (e: Exception) { }
    }

    private fun unregisterNsd() {
        val l = nsdListener ?: return
        nsdListener = null
        try {
            (context.getSystemService(Context.NSD_SERVICE) as NsdManager).unregisterService(l)
        } catch (e: Exception) { }
    }
}
