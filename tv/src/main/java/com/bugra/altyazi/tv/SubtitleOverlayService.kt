package com.bugra.altyazi.tv

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.ConnectivityManager
import android.net.Network
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlin.math.min

/**
 * HDMI görüntüsünün üstüne Türkçe altyazı çizen servis.
 * - Telefonu ağda kendisi bulur (IP yazmak zorunlu değil).
 * - Bağlantı koparsa 1-5 sn aralıklarla durmadan yeniden bağlanır.
 * - Eski bağlantılardan gelen geç olaylar yok sayılır (çift bağlantı/çakışma olmaz).
 * - Wi-Fi geri gelince beklemeden hemen bağlanır.
 */
class SubtitleOverlayService : Service() {

    companion object {
        const val ACTION_STATUS = "com.bugra.altyazi.tv.STATUS"
        const val EXTRA_STATUS_TEXT = "status_text"
        const val EXTRA_CONNECTED = "connected"
        const val ACTION_TEST = "com.bugra.altyazi.tv.TEST"
        const val ACTION_RECONNECT = "com.bugra.altyazi.tv.RECONNECT"
        const val PREFS = "ayarlar"
        const val NSD_TYPE = "_altyazitr._tcp"
        const val PORT = 8765

        @Volatile var isRunning = false
        @Volatile var lastStatus = "Başlatılmadı"
        @Volatile var lastConnected = false
    }

    private val main = Handler(Looper.getMainLooper())
    private lateinit var prefs: SharedPreferences

    // altyazı katmanı
    private var wm: WindowManager? = null
    private var container: LinearLayout? = null
    private var trView: TextView? = null
    private var enView: TextView? = null
    private var lp: WindowManager.LayoutParams? = null

    // görünüm
    private var fontSize = 30
    private var yOffset = 70
    private var bgAlpha = 170
    private var showEn = false

    // bağlantı
    private val client = OkHttpClient.Builder()
        .pingInterval(5, TimeUnit.SECONDS)
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .retryOnConnectionFailure(true)
        .build()
    private var ws: WebSocket? = null
    private var generation = 0
    private var backoffMs = 1000L
    private var attempt = 0
    private var discoveredHost: String? = null
    private var stopped = true

    private var nsd: NsdManager? = null
    private var discoveryListener: NsdManager.DiscoveryListener? = null
    private var resolving = false
    private var netCallback: ConnectivityManager.NetworkCallback? = null
    private var wifiLock: WifiManager.WifiLock? = null

    private val hideRunnable = Runnable { container?.visibility = View.GONE }
    private val reconnectRunnable = Runnable { connect() }
    private val resolveTimeout = Runnable { resolving = false }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startAsForeground()
        if (!isRunning) {
            isRunning = true
            stopped = false
            ensureOverlay()
            acquireWifiLock()
            registerNetworkCallback()
            startDiscovery()
            backoffMs = 1000
            connectSoon(0)
        }
        when (intent?.action) {
            ACTION_TEST -> {
                ensureOverlay()
                showSubtitle("Altyazı katmanı hazır! Abi bu iş tamam.", "Overlay ready", 6000)
            }
            ACTION_RECONNECT -> {
                backoffMs = 1000
                connectSoon(0)
            }
        }
        return START_STICKY
    }

    // ---------------------------------------------------------------- bağlantı

    private fun manualHost(): String? = prefs.getString("phone_ip", "")
        ?.trim()
        ?.removePrefix("ws://")
        ?.substringBefore(":")
        ?.substringBefore("/")
        ?.takeIf { it.isNotEmpty() }

    private fun pickHost(): String? {
        val options = listOfNotNull(discoveredHost, manualHost(), prefs.getString("last_ok_ip", null))
            .filter { it.isNotBlank() }
            .distinct()
        if (options.isEmpty()) return null
        val h = options[attempt % options.size]
        attempt++
        return h
    }

    private fun connectSoon(delayMs: Long) {
        main.removeCallbacks(reconnectRunnable)
        main.postDelayed(reconnectRunnable, delayMs)
    }

    private fun connect() {
        if (stopped) return
        main.removeCallbacks(reconnectRunnable)
        val host = pickHost()
        if (host == null) {
            status("Telefon aranıyor… (telefonda Başlat'a basın)", false)
            scheduleReconnect()
            return
        }
        val gen = ++generation
        try { ws?.cancel() } catch (e: Exception) { }
        ws = null
        status("Bağlanıyor: $host", false)

        val request = try {
            Request.Builder().url("ws://$host:$PORT").build()
        } catch (e: Exception) {
            status("Geçersiz adres: $host", false)
            scheduleReconnect()
            return
        }

        ws = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                main.post {
                    if (gen != generation || stopped) {
                        webSocket.cancel()
                        return@post
                    }
                    backoffMs = 1000
                    attempt = 0
                    prefs.edit().putString("last_ok_ip", host).apply()
                    status("Telefona bağlı ($host)", true)
                }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                main.post { if (gen == generation) handleMessage(text) }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                try { webSocket.close(1000, null) } catch (e: Exception) { }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                main.post { if (gen == generation) connectionLost("Bağlantı kapandı, yeniden bağlanılıyor…") }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                main.post { if (gen == generation) connectionLost("Telefon bekleniyor… ($host)") }
            }
        })
    }

    private fun connectionLost(msg: String) {
        ws = null
        status(msg, false)
        scheduleReconnect()
    }

    private fun scheduleReconnect() {
        if (stopped) return
        connectSoon(backoffMs)
        backoffMs = min(backoffMs * 2, 5000L)
    }

    private fun handleMessage(text: String) {
        val o = try { JSONObject(text) } catch (e: Exception) { return }
        when (o.optString("type", "sub")) {
            "hello" -> applyStyle(o)
            "style" -> {
                applyStyle(o)
                if (o.optBoolean("preview", false)) {
                    showSubtitle("Örnek altyazı: Kanka bu iş çok temiz!", "Sample subtitle", 3500)
                }
            }
            "clear" -> {
                main.removeCallbacks(hideRunnable)
                container?.visibility = View.GONE
            }
            "pong" -> Unit
            "screen" -> showScreen(o.optJSONArray("items"), o.optLong("durationMs", 120000L))
            "screen-clear" -> clearScreen()
            else -> {
                applyStyle(o)
                showSubtitle(o.optString("tr", ""), o.optString("en", ""), 9000)
            }
        }
    }

    private fun applyStyle(o: JSONObject) {
        if (o.has("fontSize")) fontSize = o.optInt("fontSize", fontSize).coerceIn(14, 60)
        if (o.has("yOffset")) yOffset = o.optInt("yOffset", yOffset).coerceIn(0, 400)
        if (o.has("bgAlpha")) bgAlpha = o.optInt("bgAlpha", bgAlpha).coerceIn(0, 255)
        if (o.has("showEn")) showEn = o.optBoolean("showEn", showEn)
    }

    // ---------------------------------------------------------------- ağda telefonu bulma (NSD)

    private fun startDiscovery() {
        try {
            val m = getSystemService(Context.NSD_SERVICE) as NsdManager
            nsd = m
            val l = object : NsdManager.DiscoveryListener {
                override fun onDiscoveryStarted(serviceType: String?) {}
                override fun onDiscoveryStopped(serviceType: String?) {}
                override fun onStartDiscoveryFailed(serviceType: String?, errorCode: Int) {
                    main.post { discoveryListener = null }
                    main.postDelayed({ if (!stopped && discoveryListener == null) startDiscovery() }, 15000)
                }
                override fun onStopDiscoveryFailed(serviceType: String?, errorCode: Int) {}
                override fun onServiceFound(serviceInfo: NsdServiceInfo?) {
                    if (serviceInfo != null) main.post { resolve(serviceInfo, 0) }
                }
                override fun onServiceLost(serviceInfo: NsdServiceInfo?) {}
            }
            discoveryListener = l
            m.discoverServices(NSD_TYPE, NsdManager.PROTOCOL_DNS_SD, l)
        } catch (e: Exception) {
            discoveryListener = null
        }
    }

    private fun stopDiscovery() {
        val l = discoveryListener ?: return
        discoveryListener = null
        try { nsd?.stopServiceDiscovery(l) } catch (e: Exception) { }
    }

    private fun resolve(info: NsdServiceInfo, tries: Int) {
        if (stopped || tries > 6) return
        if (resolving) {
            main.postDelayed({ resolve(info, tries + 1) }, 800)
            return
        }
        resolving = true
        main.postDelayed(resolveTimeout, 6000)
        try {
            nsd?.resolveService(info, object : NsdManager.ResolveListener {
                override fun onResolveFailed(serviceInfo: NsdServiceInfo?, errorCode: Int) {
                    main.post {
                        main.removeCallbacks(resolveTimeout)
                        resolving = false
                    }
                }

                override fun onServiceResolved(serviceInfo: NsdServiceInfo?) {
                    @Suppress("DEPRECATION")
                    val host = serviceInfo?.host?.hostAddress
                    main.post {
                        main.removeCallbacks(resolveTimeout)
                        resolving = false
                        if (host != null && host.contains('.')) {
                            val changed = host != discoveredHost
                            discoveredHost = host
                            if (changed && !lastConnected) {
                                attempt = 0
                                backoffMs = 1000
                                connectSoon(0)
                            }
                        }
                    }
                }
            })
        } catch (e: Exception) {
            main.removeCallbacks(resolveTimeout)
            resolving = false
        }
    }

    private fun registerNetworkCallback() {
        try {
            val cm = getSystemService(ConnectivityManager::class.java)
            val cb = object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    main.post {
                        if (!stopped && !lastConnected) {
                            backoffMs = 1000
                            connectSoon(500)
                        }
                    }
                }
            }
            cm.registerDefaultNetworkCallback(cb)
            netCallback = cb
        } catch (e: Exception) { }
    }

    private fun acquireWifiLock() {
        try {
            val w = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            @Suppress("DEPRECATION")
            val mode = if (Build.VERSION.SDK_INT >= 29) WifiManager.WIFI_MODE_FULL_LOW_LATENCY else WifiManager.WIFI_MODE_FULL_HIGH_PERF
            wifiLock = w.createWifiLock(mode, "altyazi:tv").apply {
                setReferenceCounted(false)
                acquire()
            }
        } catch (e: Exception) { }
    }

    // ---------------------------------------------------------------- altyazı katmanı

    private fun ensureOverlay(): Boolean {
        if (container != null) return true
        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(this)) {
            status("Ekran üstü gösterme izni yok – kurulum rehberindeki izin adımını yapın", lastConnected)
            return false
        }
        return try {
            val manager = getSystemService(WINDOW_SERVICE) as WindowManager
            val maxW = (resources.displayMetrics.widthPixels * 0.84f).toInt()

            val box = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER_HORIZONTAL
                setPadding(44, 18, 44, 20)
                background = pill(bgAlpha)
                visibility = View.GONE
            }
            val tr = TextView(this).apply {
                setTextColor(Color.WHITE)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, fontSize.toFloat())
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
                maxWidth = maxW
                setShadowLayer(6f, 2f, 2f, Color.BLACK)
            }
            val en = TextView(this).apply {
                setTextColor(Color.parseColor("#C8D0E0"))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                gravity = Gravity.CENTER
                maxWidth = maxW
                setShadowLayer(4f, 1f, 1f, Color.BLACK)
                visibility = View.GONE
                setPadding(0, 6, 0, 0)
            }
            box.addView(tr)
            box.addView(en)

            @Suppress("DEPRECATION")
            val type = if (Build.VERSION.SDK_INT >= 26) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                WindowManager.LayoutParams.TYPE_SYSTEM_ALERT
            }
            val params = WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                type,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT
            ).apply {
                gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
                y = yOffset
            }
            manager.addView(box, params)
            wm = manager
            container = box
            trView = tr
            enView = en
            lp = params
            true
        } catch (e: Exception) {
            container = null
            status("Altyazı katmanı açılamadı: ${e.message}", lastConnected)
            false
        }
    }

    // ---------------------------------------------------------------- ekran örtüleri (GTA 6 telefon / harita kartı)

    private var screenLayer: android.widget.FrameLayout? = null
    private val clearScreenRunnable = Runnable { clearScreen() }

    private fun ensureScreenLayer(): android.widget.FrameLayout? {
        screenLayer?.let { return it }
        return try {
            val manager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
            val layer = android.widget.FrameLayout(this)
            @Suppress("DEPRECATION")
            val type = if (Build.VERSION.SDK_INT >= 26) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            else WindowManager.LayoutParams.TYPE_SYSTEM_ALERT
            val params = WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                type,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT
            ).apply { gravity = Gravity.TOP or Gravity.START }
            manager.addView(layer, params)
            screenLayer = layer
            layer
        } catch (e: Exception) {
            null
        }
    }

    private fun parseColor(hex: String?, fallback: Int): Int =
        try { if (hex.isNullOrBlank()) fallback else Color.parseColor(hex) } catch (e: Exception) { fallback }

    /** Öğeler: box (0–1), text, line (satır yüksekliği oranı), fill/ink (#rrggbb), alpha, card, backdrop, plain. */
    private fun showScreen(items: org.json.JSONArray?, durationMs: Long) {
        main.removeCallbacks(clearScreenRunnable)
        if (items == null || items.length() == 0) { clearScreen(); return }
        val layer = ensureScreenLayer() ?: return
        layer.post {
            layer.removeAllViews()
            val w = layer.width.takeIf { it > 0 } ?: resources.displayMetrics.widthPixels
            val h = layer.height.takeIf { it > 0 } ?: resources.displayMetrics.heightPixels
            for (i in 0 until items.length()) {
                val it = items.optJSONObject(i) ?: continue
                val b = it.optJSONObject("box") ?: continue
                val left = (b.optDouble("left", 0.0) * w).toInt()
                val top = (b.optDouble("top", 0.0) * h).toInt()
                val right = (b.optDouble("right", 0.0) * w).toInt()
                val bottom = (b.optDouble("bottom", 0.0) * h).toInt()
                if (right - left < 4 || bottom - top < 4) continue
                val alpha = it.optDouble("alpha", if (it.optBoolean("card")) 1.0 else 0.85).coerceIn(0.0, 1.0)
                val backdrop = it.optBoolean("backdrop")
                val plain = it.optBoolean("plain")
                val fill = parseColor(it.optString("fill", ""), if (it.optBoolean("card")) Color.parseColor("#1B1B22") else Color.BLACK)
                val ink = parseColor(it.optString("ink", ""), Color.WHITE)
                val text = it.optString("text", "")
                    .replace("⟦", "").replace("⟧", "")
                val v = TextView(this).apply {
                    this.text = text
                    setTextColor(ink)
                    val line = it.optDouble("line", 0.03)
                    setTextSize(TypedValue.COMPLEX_UNIT_PX, (line * h * 0.78).toFloat().coerceIn(12f, 80f))
                    gravity = if (plain) Gravity.START or Gravity.CENTER_VERTICAL else Gravity.START or Gravity.TOP
                    setPadding(10, 4, 10, 4)
                    if (!plain || backdrop) {
                        background = GradientDrawable().apply {
                            cornerRadius = if (it.optBoolean("side")) 22f else 10f
                            setColor(Color.argb((alpha * 255).toInt(), Color.red(fill), Color.green(fill), Color.blue(fill)))
                        }
                    }
                    if (plain) setShadowLayer(4f, 1f, 1f, Color.BLACK)
                }
                val lpItem = android.widget.FrameLayout.LayoutParams(right - left, bottom - top)
                lpItem.leftMargin = left
                lpItem.topMargin = top
                layer.addView(v, lpItem)
            }
            layer.visibility = View.VISIBLE
        }
        if (durationMs > 0) main.postDelayed(clearScreenRunnable, durationMs)
    }

    private fun clearScreen() {
        main.removeCallbacks(clearScreenRunnable)
        screenLayer?.let {
            it.removeAllViews()
            it.visibility = View.GONE
        }
    }

    private fun pill(alpha: Int) = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        cornerRadius = 20f
        setColor(Color.argb(alpha.coerceIn(0, 255), 8, 10, 16))
    }

    private fun showSubtitle(tr: String, en: String, hideAfterMs: Long) {
        if (!ensureOverlay()) return
        val box = container ?: return
        main.removeCallbacks(hideRunnable)
        if (tr.isBlank()) {
            box.visibility = View.GONE
            return
        }
        trView?.setTextSize(TypedValue.COMPLEX_UNIT_SP, fontSize.toFloat())
        trView?.text = tr
        enView?.let {
            if (showEn && en.isNotBlank()) {
                it.text = en
                it.visibility = View.VISIBLE
            } else {
                it.visibility = View.GONE
            }
        }
        box.background = pill(bgAlpha)
        val params = lp
        if (params != null && params.y != yOffset) {
            params.y = yOffset
            try { wm?.updateViewLayout(box, params) } catch (e: Exception) { }
        }
        box.visibility = View.VISIBLE
        main.postDelayed(hideRunnable, hideAfterMs)
    }

    // ---------------------------------------------------------------- durum / bildirim

    private fun status(text: String, connected: Boolean) {
        lastStatus = text
        lastConnected = connected
        try {
            sendBroadcast(Intent(ACTION_STATUS).apply {
                setPackage(packageName)
                putExtra(EXTRA_STATUS_TEXT, text)
                putExtra(EXTRA_CONNECTED, connected)
            })
        } catch (e: Exception) { }
    }

    private fun startAsForeground() {
        val channelId = "altyazi_tv"
        if (Build.VERSION.SDK_INT >= 26) {
            getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(channelId, "Türkçe altyazı", NotificationManager.IMPORTANCE_LOW)
            )
        }
        val builder = if (Build.VERSION.SDK_INT >= 26) {
            Notification.Builder(this, channelId)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        val n = builder
            .setContentTitle(getString(R.string.app_name))
            .setContentText("Altyazı katmanı çalışıyor")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .build()
        try {
            if (Build.VERSION.SDK_INT >= 34) {
                startForeground(101, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
            } else {
                startForeground(101, n)
            }
        } catch (e: Exception) { }
    }

    override fun onDestroy() {
        stopped = true
        isRunning = false
        main.removeCallbacksAndMessages(null)
        try { ws?.close(1000, "kapatildi") } catch (e: Exception) { }
        ws = null
        stopDiscovery()
        try {
            netCallback?.let { getSystemService(ConnectivityManager::class.java).unregisterNetworkCallback(it) }
        } catch (e: Exception) { }
        netCallback = null
        try { if (wifiLock?.isHeld == true) wifiLock?.release() } catch (e: Exception) { }
        container?.let { c -> try { wm?.removeView(c) } catch (e: Exception) { } }
        screenLayer?.let { l -> try { (getSystemService(Context.WINDOW_SERVICE) as WindowManager).removeView(l) } catch (e: Exception) { } }
        screenLayer = null
        container = null
        status("Durduruldu", false)
        super.onDestroy()
    }
}
