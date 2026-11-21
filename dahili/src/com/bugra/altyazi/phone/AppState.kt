package com.bugra.altyazi.phone

import android.graphics.Bitmap
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update

/** Servis ile ekran arasında paylaşılan canlı durum. */
object AppState {
    data class Status(
        val running: Boolean = false,
        val message: String = "Hazır. PS5'e bağlanıp oyunu açın.",
        val tvClients: Int = 0,
        val phoneIp: String = "-",
        val lastEn: String = "",
        val lastTr: String = "",
        val latencyMs: Long = 0,
        val engine: String = "",
        val lineCount: Int = 0,
        val frames: Long = 0,
        val ocrRuns: Long = 0,
        val rawText: String = "",
        val source: String = "",
        val copyOk: Long = 0,
        val copyFail: Long = 0,
        val copyErr: Int = 0
    )

    val status = MutableStateFlow(Status())
    val preview = MutableStateFlow<Bitmap?>(null)

    /** Arka planda akan oyun görüntüsü (ana ekrandaki küçük pencere için). */
    val liveFrame = MutableStateFlow<Bitmap?>(null)

    /** PS5 bağlantısı açık mı? */
    val streaming = MutableStateFlow(false)

    fun update(block: (Status) -> Status) {
        status.update(block)
    }
}
