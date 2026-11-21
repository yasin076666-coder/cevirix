package com.bugra.altyazi.phone

import android.graphics.Bitmap
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update

/** Servis ile ekran arasında paylaşılan canlı durum. */
object AppState {
    data class Status(
        val running: Boolean = false,
        val message: String = "Hazır. Başlat'a basın.",
        val tvClients: Int = 0,
        val phoneIp: String = "-",
        val lastEn: String = "",
        val lastTr: String = "",
        val latencyMs: Long = 0,
        val engine: String = "",
        val lineCount: Int = 0
    )

    val status = MutableStateFlow(Status())
    val preview = MutableStateFlow<Bitmap?>(null)

    fun update(block: (Status) -> Status) {
        status.update(block)
    }
}
