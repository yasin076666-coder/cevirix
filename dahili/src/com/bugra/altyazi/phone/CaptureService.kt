package com.bugra.altyazi.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.PowerManager
import android.util.DisplayMetrics
import android.view.Display
import androidx.core.app.NotificationCompat
import com.metallic.chiaki.R
import kotlin.math.max
import kotlin.math.min

/**
 * Ön plan servisi: ekranı yakalar → altyazıyı okur → çevirir → TV'ye yollar → (isteğe bağlı) seslendirir.
 */
class CaptureService : Service() {

    companion object {
        const val ACTION_START = "com.bugra.altyazi.START"
        const val ACTION_STOP = "com.bugra.altyazi.STOP"
        const val EXTRA_CODE = "code"
        const val EXTRA_DATA = "data"
        private const val NOTIF_ID = 42
        private const val CHANNEL = "altyazi_kanal"
        private const val MAX_SIDE = 3200 // tam çözünürlük: küçük altyazılar da okunsun

        @Volatile
        var instance: CaptureService? = null
            private set
    }

    private var engineAcquired = false

    private lateinit var thread: HandlerThread
    private lateinit var handler: Handler

    private var projection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var reader: ImageReader? = null
    private var analyzer: FrameAnalyzer? = null
    private var displayListener: DisplayManager.DisplayListener? = null
    private var capW = 0
    private var capH = 0

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null


    @Volatile private var started = false
    @Volatile private var stopping = false
    @Volatile private var lastStartId = 0

    private val imageListener = ImageReader.OnImageAvailableListener { r ->
        val img = try { r.acquireLatestImage() } catch (e: Exception) { null }
        if (img != null) {
            val a = analyzer
            if (a != null) a.onImage(img) else try { img.close() } catch (e: Exception) { }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Prefs.init(this)
        instance = this
        thread = HandlerThread("ekran-yakalama").apply { start() }
        handler = Handler(thread.looper)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        lastStartId = startId
        // startForegroundService ile başlatıldığı için her durumda önce ön plana geç
        startForegroundCompat()
        when (intent?.action) {
            ACTION_STOP -> stopEverything()
            ACTION_START -> if (!started || stopping) {
                val code = intent.getIntExtra(EXTRA_CODE, 0)
                @Suppress("DEPRECATION")
                val data: Intent? = intent.getParcelableExtra(EXTRA_DATA)
                if (data == null) stopEverything() else begin(code, data)
            }
            else -> if (!started) stopEverything() // izin anahtarı olmadan yeniden başlatıldı
        }
        return START_NOT_STICKY
    }

    private fun begin(code: Int, data: Intent) {
        stopping = false
        try {
            val mpm = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            val mp = mpm.getMediaProjection(code, data) ?: throw IllegalStateException("Ekran izni alınamadı")
            projection = mp
            mp.registerCallback(object : MediaProjection.Callback() {
                override fun onStop() {
                    handler.post {
                        if (!stopping) {
                            notice("Ekran paylaşımı sonlandırıldı")
                            stopEverything()
                        }
                    }
                }
            }, handler)

            acquireLocks()
            CevirixEngine.acquire(this, "Ekran okuma")
            engineAcquired = true
            analyzer = FrameAnalyzer(
                onText = { t -> CevirixEngine.onSubtitleText(t) },
                onCleared = { CevirixEngine.sendClear() },
                onNotice = { msg -> notice(msg) }
            )
            createCapture()
            registerDisplayListener()
            started = true

            notice("Çalışıyor – şimdi PS Remote Play'e geçin")
        } catch (e: Exception) {
            notice("Başlatılamadı: ${e.message}")
            stopEverything()
        }
    }

    // ---------------------------------------------------------------- yakalama

    private data class CapSize(val w: Int, val h: Int, val dpi: Int)

    private fun captureSize(): CapSize {
        val dm = DisplayMetrics()
        val display = (getSystemService(Context.DISPLAY_SERVICE) as DisplayManager).getDisplay(Display.DEFAULT_DISPLAY)
        @Suppress("DEPRECATION")
        display.getRealMetrics(dm)
        val scale = min(1f, MAX_SIDE.toFloat() / max(dm.widthPixels, dm.heightPixels))
        val w = max(2, ((dm.widthPixels * scale).toInt() / 2) * 2)
        val h = max(2, ((dm.heightPixels * scale).toInt() / 2) * 2)
        return CapSize(w, h, dm.densityDpi)
    }

    private fun createCapture() {
        val size = captureSize()
        val r = ImageReader.newInstance(size.w, size.h, PixelFormat.RGBA_8888, 2)
        r.setOnImageAvailableListener(imageListener, handler)
        reader = r
        capW = size.w
        capH = size.h
        virtualDisplay = projection?.createVirtualDisplay(
            "AltyaziYakalama",
            size.w, size.h, size.dpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            r.surface, null, handler
        ) ?: throw IllegalStateException("Sanal ekran oluşturulamadı")
    }

    /** Telefon döndürülünce (dikey ↔ yatay) yakalama boyutunu günceller. */
    private fun onRotation() {
        val vd = virtualDisplay ?: return
        try {
            val size = captureSize()
            if (size.w == capW && size.h == capH) return
            val old = reader
            val r = ImageReader.newInstance(size.w, size.h, PixelFormat.RGBA_8888, 2)
            r.setOnImageAvailableListener(imageListener, handler)
            vd.resize(size.w, size.h, size.dpi)
            vd.surface = r.surface
            reader = r
            capW = size.w
            capH = size.h
            old?.setOnImageAvailableListener(null, null)
            old?.close()
        } catch (e: Exception) {
            notice("Ekran döndürme işlenemedi: ${e.message}")
        }
    }

    private fun registerDisplayListener() {
        val dm = getSystemService(Context.DISPLAY_SERVICE) as DisplayManager
        val l = object : DisplayManager.DisplayListener {
            override fun onDisplayAdded(displayId: Int) {}
            override fun onDisplayRemoved(displayId: Int) {}
            override fun onDisplayChanged(displayId: Int) {
                if (displayId == Display.DEFAULT_DISPLAY) onRotation()
            }
        }
        dm.registerDisplayListener(l, handler)
        displayListener = l
    }

    // ---------------------------------------------------------------- yardımcılar

    private fun notice(msg: String) {
        CevirixEngine.notice(msg)
    }

    private fun acquireLocks() {
        try {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "altyazi:yakalama").apply {
                setReferenceCounted(false)
                acquire(6 * 60 * 60 * 1000L)
            }
        } catch (e: Exception) { }
        try {
            val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            @Suppress("DEPRECATION")
            val mode = if (Build.VERSION.SDK_INT >= 29) WifiManager.WIFI_MODE_FULL_LOW_LATENCY else WifiManager.WIFI_MODE_FULL_HIGH_PERF
            wifiLock = wm.createWifiLock(mode, "altyazi:wifi").apply {
                setReferenceCounted(false)
                acquire()
            }
        } catch (e: Exception) { }
    }

    private fun releaseLocks() {
        try { if (wakeLock?.isHeld == true) wakeLock?.release() } catch (e: Exception) { }
        try { if (wifiLock?.isHeld == true) wifiLock?.release() } catch (e: Exception) { }
        wakeLock = null
        wifiLock = null
    }

    private fun startForegroundCompat() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, "Altyazı çevirisi", NotificationManager.IMPORTANCE_LOW)
        )
        val flags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        val stopPi = PendingIntent.getService(
            this, 1, Intent(this, CaptureService::class.java).setAction(ACTION_STOP), flags
        )
        val openPi = PendingIntent.getActivity(this, 2, Intent(this, CevirixActivity::class.java), flags)
        val n: Notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.cx_ic_stat)
            .setContentTitle(getString(R.string.app_name))
            .setContentText("Çeviri çalışıyor")
            .setOngoing(true)
            .setContentIntent(openPi)
            .addAction(0, "Durdur", stopPi)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
        } else {
            startForeground(NOTIF_ID, n)
        }
    }

    private fun stopEverything() {
        if (stopping) return
        stopping = true
        try {
            displayListener?.let {
                (getSystemService(Context.DISPLAY_SERVICE) as DisplayManager).unregisterDisplayListener(it)
            }
        } catch (e: Exception) { }
        displayListener = null
        analyzer?.close()
        analyzer = null
        try { virtualDisplay?.release() } catch (e: Exception) { }
        virtualDisplay = null
        try {
            reader?.setOnImageAvailableListener(null, null)
            reader?.close()
        } catch (e: Exception) { }
        reader = null
        try { projection?.stop() } catch (e: Exception) { }
        projection = null
        if (engineAcquired) {
            engineAcquired = false
            CevirixEngine.release()
        }
        releaseLocks()
        started = false
        try { stopForeground(STOP_FOREGROUND_REMOVE) } catch (e: Exception) { }
        // Bu arada yeni bir "Başlat" geldiyse servis kapanmaz (yarış durumunu önler)
        stopSelfResult(lastStartId)
    }

    override fun onDestroy() {
        stopEverything()
        try { thread.quitSafely() } catch (e: Exception) { }
        instance = null
        super.onDestroy()
    }
}
