package com.bugra.altyazi.phone

import android.content.Context
import android.media.AudioAttributes
import android.speech.tts.TextToSpeech
import java.util.Locale

/** Türkçe canlı dublaj (metin okuma). */
class Speaker(context: Context) : TextToSpeech.OnInitListener {

    private val tts = TextToSpeech(context.applicationContext, this)

    @Volatile private var ready = false
    var onNotice: ((String) -> Unit)? = null

    override fun onInit(status: Int) {
        if (status != TextToSpeech.SUCCESS) {
            onNotice?.invoke("Sesli okuma motoru başlatılamadı")
            return
        }
        val r = tts.setLanguage(Locale("tr", "TR"))
        ready = r != TextToSpeech.LANG_MISSING_DATA && r != TextToSpeech.LANG_NOT_SUPPORTED
        if (!ready) onNotice?.invoke("Telefonda Türkçe ses paketi yok (Ayarlar › Metin okuma)")
    }

    fun speak(text: String) {
        if (!ready || text.isBlank()) return
        try {
            val usage = if (Prefs.voiceOnNotification) AudioAttributes.USAGE_NOTIFICATION else AudioAttributes.USAGE_MEDIA
            tts.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(usage)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            tts.setSpeechRate(Prefs.speechRate / 100f)
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "altyazi")
        } catch (e: Exception) {
            // yoksay
        }
    }

    fun stop() {
        try { tts.stop() } catch (e: Exception) { }
    }

    fun shutdown() {
        ready = false
        try {
            tts.stop()
            tts.shutdown()
        } catch (e: Exception) { }
    }
}
