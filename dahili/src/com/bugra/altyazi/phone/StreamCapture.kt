package com.bugra.altyazi.phone

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Rect
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.SystemClock
import android.util.TypedValue
import android.view.Gravity
import android.view.PixelCopy
import android.view.SurfaceView
import android.view.View
import android.widget.FrameLayout
import android.widget.TextView
import kotlin.math.max
import kotlin.math.min

/**
 * Dahili Remote Play: PS5 görüntüsünün gösterildiği yüzeyden altyazı şeridini
 * düzenli aralıklarla kopyalar (PixelCopy) ve Çevirix motoruna verir.
 * Oyun sırasında ekranın üstünde küçük bir canlı teşhis satırı gösterir.
 */
class StreamCapture(private val activity: Activity, private val surfaceView: SurfaceView) {

    companion object {
        private const val INTERVAL_MS = 200L
        private const val BG_W = 1280
        private const val BG_H = 720
        private const val BG_INTERVAL_MS = 140L
        private const val LIVE_W = 640
        private const val LIVE_H = 360

        /** Açık olan akış (ana ekrandan tam ekrana geçmek/kapatmak için). */
        @Volatile var current: StreamCapture? = null
            private set
    }

    private var autoMinimized = false
    private val liveBufs = arrayOfNulls<Bitmap>(3)
    private var liveIdx = 0
    private val livePaint = android.graphics.Paint(android.graphics.Paint.FILTER_BITMAP_FLAG)

    private val tickThread = HandlerThread("cevirix-tick").apply { start() }
    private val tickHandler = Handler(tickThread.looper)
    private val copyThread = HandlerThread("cevirix-pixelcopy").apply { start() }
    private val copyHandler = Handler(copyThread.looper)
    private val ui = Handler(Looper.getMainLooper())

    private var ocr: SubtitleOcr? = null
    @Volatile private var running = false
    @Volatile private var inFlight = false
    @Volatile private var inFlightSince = 0L
    private var acquired = false
    @Volatile private var copyOk = 0L
    @Volatile private var copyFail = 0L
    @Volatile private var lastErr = 0
    private var hud: TextView? = null
    private var hudImage: android.widget.ImageView? = null
    private var shownPreview: Bitmap? = null

    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            capture()
            tickHandler.postDelayed(this, if (BgFrames.inUse) BG_INTERVAL_MS else INTERVAL_MS)
        }
    }

    private val hudUpdater = object : Runnable {
        override fun run() {
            if (!running) return
            renderHud()
            ui.postDelayed(this, 500)
        }
    }

    fun start() {
        Prefs.init(activity)
        if (!Prefs.streamTranslate || Build.VERSION.SDK_INT < 24) return

        // Eski ekran okuma modu açık kaldıysa kapat: iki mod aynı anda çalışmasın
        if (CaptureService.instance != null) {
            try {
                activity.startService(Intent(activity, CaptureService::class.java).setAction(CaptureService.ACTION_STOP))
            } catch (e: Exception) { }
        }

        CevirixEngine.acquire(activity, "Dahili Remote Play")
        acquired = true
        ocr = SubtitleOcr(
            source = "Dahili Remote Play",
            onText = { CevirixEngine.onSubtitleText(it) },
            onCleared = { CevirixEngine.sendClear() },
            onNotice = { CevirixEngine.notice(it) }
        )
        running = true
        AppState.update {
            it.copy(frames = 0, ocrRuns = 0, copyOk = 0, copyFail = 0, copyErr = 0, rawText = "", source = "Dahili Remote Play")
        }
        current = this
        AppState.streaming.value = true
        com.bugra.altyazi.phone.gta.GtaBridge.start(activity.applicationContext)
        PsAudio.apply()
        addHud()
        BgService.onStopRequested = { ui.post { try { activity.finish() } catch (e: Exception) { } } }
        // Arka plan için görünmez yüzeyi önceden hazırla
        tickHandler.post { if (Prefs.backgroundStream) BgFrames.prepare() }
        tickHandler.postDelayed(tick, 1500)
        ui.post(hudUpdater)
    }

    /**
     * Akış ekranı duraklarken çağrılır. true: bağlantı açık kalsın (arka plan modu).
     * Ekran kapanıyorsa (geri tuşu) veya arka plan modu kapalıysa false.
     */
    fun keepAliveOnPause(finishing: Boolean): Boolean {
        val keep = running && !finishing && Prefs.backgroundStream && BgFrames.isReady
        BgFrames.keepAliveWanted = keep
        return keep
    }

    /** Ekran tamamen görünmez oldu: arka plan servisini başlat. */
    fun onActivityStopped(finishing: Boolean) {
        if (BgFrames.keepAliveWanted && !finishing) {
            BgService.start(activity)
            CevirixEngine.notice("Arka planda çeviriye devam ediliyor")
        }
    }

    /** Ekran geri geldi: servis gerekmez. */
    fun onActivityStarted() {
        BgFrames.keepAliveWanted = false
        BgService.stop(activity)
    }

    /** Oyunu Çevirix ana ekranındaki küçük pencereye al. */
    fun minimize() {
        ui.post {
            try {
                activity.startActivity(
                    Intent(activity, CevirixActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
                )
            } catch (e: Exception) { }
        }
    }

    /** Bağlantıyı kapat. */
    fun finishStream() {
        ui.post { try { activity.finish() } catch (e: Exception) { } }
    }

    fun stop() {
        running = false
        if (current === this) current = null
        com.bugra.altyazi.phone.gta.GtaBridge.stop()
        CevirixEngine.sendScreenClear()
        AppState.streaming.value = false
        AppState.liveFrame.value = null
        BgFrames.keepAliveWanted = false
        BgService.onStopRequested = null
        BgService.stop(activity)
        tickHandler.removeCallbacksAndMessages(null)
        copyHandler.removeCallbacksAndMessages(null)
        ui.removeCallbacksAndMessages(null)
        ocr?.close()
        ocr = null
        if (acquired) {
            acquired = false
            CevirixEngine.release()
        }
        tickHandler.post { BgFrames.release() }
        try { tickThread.quitSafely() } catch (e: Exception) { }
        try { copyThread.quitSafely() } catch (e: Exception) { }
    }

    private fun capture() {
        if (inFlight) {
            if (SystemClock.uptimeMillis() - inFlightSince < 2000) return
            // yanıt gelmedi: hata say ve devam et
            inFlight = false
            copyFail++
            lastErr = -2
            publishCopyStats()
        }
        if (BgFrames.inUse) {
            captureBackground()
            return
        }
        val w = surfaceView.width
        val h = surfaceView.height
        if (w < 32 || h < 32) return
        if (!surfaceView.holder.surface.isValid) return

        // Tüm kareyi sabit boyutlu bir resme kopyala (video çözünürlüğünden bağımsız),
        // altyazı şeridini sonra kes. srcRect video tamponu koordinatı istediği için kullanılmıyor.
        val fw = min(1920, max(640, w))
        val fh = fw * 9 / 16 // video tamponu 16:9 (oranlar bozulmasın: oyun içi telefon bulma şekle bakar)
        val full = obtainFull(fw, fh)

        try {
            inFlight = true
            inFlightSince = SystemClock.uptimeMillis()
            PixelCopy.request(surfaceView, full, { result ->
                if (result == PixelCopy.SUCCESS) {
                    com.bugra.altyazi.phone.gta.GtaBridge.offer(full)
                    val crop = cropSubtitle(full)
                    onCopied(result, crop)
                } else {
                    onCopied(result, null)
                }
            }, copyHandler)
        } catch (e: Exception) {
            inFlight = false
            copyFail++
            lastErr = -1
            publishCopyStats()
        } catch (e: OutOfMemoryError) {
            inFlight = false
        }
    }

    /** Arka planda: görüntüyü görünmez yüzeyden GPU ile oku. */
    private fun captureBackground() {
        try {
            val full = obtainFull(BG_W, BG_H)
            if (!BgFrames.grab(full)) return // henüz kare yok
            publishLive(full)
            com.bugra.altyazi.phone.gta.GtaBridge.offer(full)
            val crop = cropSubtitle(full)
            onCopied(if (crop != null) PixelCopy.SUCCESS else -3, crop)
        } catch (e: Throwable) {
            copyFail++
            lastErr = -4
        }
    }

    /** Küçük pencere için kareyi küçültüp yayınla (üçlü tampon: gösterilen kare ezilmesin). */
    private fun publishLive(full: Bitmap) {
        try {
            liveIdx = (liveIdx + 1) % liveBufs.size
            val b = liveBufs[liveIdx] ?: Bitmap.createBitmap(LIVE_W, LIVE_H, Bitmap.Config.ARGB_8888).also { liveBufs[liveIdx] = it }
            val c = android.graphics.Canvas(b)
            c.drawBitmap(full, null, Rect(0, 0, LIVE_W, LIVE_H), livePaint)
            AppState.liveFrame.value = b
        } catch (e: Throwable) { }
    }

    private var fullBmp: Bitmap? = null

    private fun obtainFull(w: Int, h: Int): Bitmap {
        val b = fullBmp
        if (b != null && !b.isRecycled && b.width == w && b.height == h) return b
        val nb = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        fullBmp = nb
        return nb
    }

    private fun cropSubtitle(full: Bitmap): Bitmap? = try {
        val w = full.width
        val h = full.height
        val top = (h * Prefs.roiTop / 100).coerceIn(0, h - 8)
        val bottom = (h * Prefs.roiBottom / 100).coerceIn(top + 8, h)
        val left = (w * Roi.LEFT).toInt()
        val right = max(left + 16, (w * Roi.RIGHT).toInt()).coerceAtMost(w)
        Bitmap.createBitmap(full, left, top, right - left, bottom - top)
    } catch (e: Throwable) {
        null
    }

    private fun onCopied(result: Int, bmp: Bitmap?) {
        inFlight = false
        if (result == PixelCopy.SUCCESS && bmp != null) {
            copyOk++
            // Görüntü geldi: oyunu ana ekrandaki küçük pencereye al (oturum başına bir kez)
            if (!autoMinimized && !BgFrames.inUse && copyOk >= 10 &&
                Prefs.miniView && Prefs.backgroundStream && BgFrames.isReady
            ) {
                autoMinimized = true
                minimize()
            }
            if (running) ocr?.submit(bmp)
        } else {
            copyFail++
            lastErr = result
        }
        if ((copyOk + copyFail) % 5 == 0L) publishCopyStats()
    }

    private fun publishCopyStats() {
        val ok = copyOk
        val fail = copyFail
        val err = lastErr
        AppState.update { it.copy(copyOk = ok, copyFail = fail, copyErr = err) }
    }

    // ---------------------------------------------------------------- canlı teşhis satırı

    private fun addHud() {
        ui.post {
            try {
                val box = android.widget.LinearLayout(activity).apply {
                    orientation = android.widget.LinearLayout.VERTICAL
                    setBackgroundColor(Color.argb(150, 0, 0, 0))
                    setPadding(12, 6, 12, 6)
                    isClickable = true
                    isFocusable = false
                    setOnClickListener { minimize() }
                }
                val tv = TextView(activity).apply {
                    setTextColor(Color.WHITE)
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f)
                    maxLines = 4
                    importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                }
                val img = android.widget.ImageView(activity).apply {
                    adjustViewBounds = true
                    maxHeight = (activity.resources.displayMetrics.density * 48).toInt()
                    scaleType = android.widget.ImageView.ScaleType.FIT_START
                }
                box.addView(tv)
                box.addView(img)
                activity.addContentView(
                    box,
                    FrameLayout.LayoutParams(
                        (activity.resources.displayMetrics.widthPixels * 0.5f).toInt(),
                        FrameLayout.LayoutParams.WRAP_CONTENT,
                        Gravity.TOP or Gravity.CENTER_HORIZONTAL
                    )
                )
                hud = tv
                hudImage = img
            } catch (e: Exception) { }
        }
    }

    private fun renderHud() {
        val tv = hud ?: return
        val s = AppState.status.value
        val tvState = if (s.tvClients > 0) "TV ✓" else "TV ✗"
        val errText = if (s.copyFail > 0) " hata ${s.copyFail} (kod ${s.copyErr})" else ""
        val raw = s.rawText.take(60)
        val tr = s.lastTr.take(70)
        val pv = AppState.preview.value
        if (pv != null && pv !== shownPreview) {
            shownPreview = pv
            hudImage?.setImageBitmap(pv)
        }
        tv.text = "Çevirix · $tvState · kopya ${s.copyOk}$errText · okuma ${s.ocrRuns}\n" +
            "EN: ${raw.ifBlank { "—" }}\nTR: ${tr.ifBlank { "—" }}\nKüçük pencereye almak için dokun"
    }
}
