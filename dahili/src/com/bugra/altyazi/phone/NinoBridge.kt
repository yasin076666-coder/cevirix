package com.bugra.altyazi.phone

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Build
import com.ninotranslator.core.link.DisplayHub
import com.ninotranslator.core.link.ShowPayload
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.util.ArrayDeque

/**
 * Nino TV uygulamalarıyla konuşma (Nino Bağlantı Protokolü, sürüm 1).
 * - Samsung (Tizen) ve LG (webOS) Nino TV'leri telefona 47800'den bağlanır.
 * - Android TV'deki Nino TV ağda `_nino._tcp` olarak bulunur, telefon ona bağlanır.
 * Kod: Nino Game Translator (AGPL-3.0, github.com/yunusdemirbag/nino-game-translator).
 */
object NinoBridge {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    @Volatile private var hub: DisplayHub? = null
    private var watchJob: Job? = null

    private var nsd: NsdManager? = null
    private var discovery: NsdManager.DiscoveryListener? = null
    private val resolveQueue = ArrayDeque<NsdServiceInfo>()
    private var resolving = false

    /** Bağlı Nino TV sayısı değişti. */
    @Volatile var onCountChanged: ((Int) -> Unit)? = null

    @Volatile var displayNames: List<String> = emptyList()
        private set

    @Synchronized
    fun start(context: Context) {
        if (hub != null) return
        val h = try {
            DisplayHub(
                DisplayHub.Config(
                    deviceName = "Çevirix (${Build.MODEL})",
                    clientVersion = "cevirix-android/1",
                    appVersion = "1"
                )
            ).also { it.start() }
        } catch (e: Throwable) {
            null
        } ?: return
        hub = h
        watchJob = scope.launch {
            h.displays.collect { list ->
                displayNames = list.map { it.name }
                onCountChanged?.invoke(list.size)
            }
        }
        pushStyle()
        scope.launch { runCatching { h.started() } }
        startDiscovery(context.applicationContext)
        WebSubtitlePage.start()
    }

    @Synchronized
    fun stop() {
        stopDiscovery()
        WebSubtitlePage.stop()
        val h = hub ?: return
        hub = null
        watchJob?.cancel()
        watchJob = null
        displayNames = emptyList()
        onCountChanged?.invoke(0)
        scope.launch {
            runCatching { h.stopped() }
            runCatching { h.close() }
        }
    }

    fun show(seq: Long, tr: String, en: String) {
        val h = hub ?: return
        val (speaker, body) = splitSpeaker(tr)
        val extras = HashMap<String, Any?>()
        if (speaker != null) extras["speaker"] = speaker
        val payload = ShowPayload(
            id = (seq and 0x7fffffff).toInt(),
            text = if (speaker != null) body else tr,
            source = if (Prefs.tvShowEn) en else null,
            extras = extras
        )
        scope.launch { runCatching { h.show(payload) } }
    }

    fun clear(seq: Long? = null) {
        val h = hub ?: return
        scope.launch { runCatching { h.clear(seq?.let { (it and 0x7fffffff).toInt() }) } }
    }

    /** Çevirix'in TV ayarlarını Nino'nun görünüm alanlarına çevirir (1080p TV ölçüsü). */
    fun pushStyle() {
        val h = hub ?: return
        val style = mapOf<String, Any?>(
            "fontSize" to Prefs.tvFontSize * 2,
            "bottomPercent" to (Prefs.tvYOffset * 100.0 / 1080.0).coerceIn(0.0, 60.0),
            "background" to (Prefs.tvBgAlpha * 100 / 255).coerceIn(0, 100),
            "placement" to "fixed",
            "autoSize" to false,
            "stackPrevious" to false
        )
        runCatching { h.setStyle(style) }
    }

    private val speakerRx = Regex("^([A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü0-9 .'\\-]{0,24}):\\s+(.+)$", RegexOption.DOT_MATCHES_ALL)

    private fun splitSpeaker(s: String): Pair<String?, String> {
        val m = speakerRx.find(s.trim()) ?: return null to s
        return m.groupValues[1] to m.groupValues[2]
    }

    // ---------------------------------------------------------------- Android TV'deki Nino'yu bulma

    private fun startDiscovery(ctx: Context) {
        try {
            val m = ctx.getSystemService(Context.NSD_SERVICE) as NsdManager
            nsd = m
            val l = object : NsdManager.DiscoveryListener {
                override fun onDiscoveryStarted(serviceType: String) {}
                override fun onDiscoveryStopped(serviceType: String) {}
                override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {}
                override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {}
                override fun onServiceFound(info: NsdServiceInfo) {
                    synchronized(resolveQueue) { resolveQueue.add(info) }
                    resolveNext()
                }
                override fun onServiceLost(info: NsdServiceInfo) {}
            }
            discovery = l
            m.discoverServices("_nino._tcp", NsdManager.PROTOCOL_DNS_SD, l)
        } catch (e: Throwable) {
            discovery = null
        }
    }

    private fun resolveNext() {
        val m = nsd ?: return
        val next = synchronized(resolveQueue) {
            if (resolving) return
            val n = resolveQueue.poll() ?: return
            resolving = true
            n
        }
        try {
            @Suppress("DEPRECATION")
            m.resolveService(next, object : NsdManager.ResolveListener {
                override fun onResolveFailed(info: NsdServiceInfo, errorCode: Int) {
                    synchronized(resolveQueue) { resolving = false }
                    resolveNext()
                }

                override fun onServiceResolved(info: NsdServiceInfo) {
                    synchronized(resolveQueue) { resolving = false }
                    @Suppress("DEPRECATION")
                    val host = info.host?.hostAddress
                    if (host != null && !host.contains(':')) {
                        runCatching { hub?.connectTo(host, if (info.port > 0) info.port else 47800) }
                    }
                    resolveNext()
                }
            })
        } catch (e: Throwable) {
            synchronized(resolveQueue) { resolving = false }
        }
    }

    private fun stopDiscovery() {
        val m = nsd
        val l = discovery
        if (m != null && l != null) runCatching { m.stopServiceDiscovery(l) }
        discovery = null
        nsd = null
        synchronized(resolveQueue) {
            resolveQueue.clear()
            resolving = false
        }
    }
}
