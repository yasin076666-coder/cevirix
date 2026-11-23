package com.bugra.altyazi.phone

import android.content.Context
import android.media.AudioAttributes
import android.speech.tts.TextToSpeech
import java.util.Locale

/** Türkçe canlı dublaj (metin okuma). */
class Speaker(context: Context) : TextToSpeech.OnInitListener {

    private val tts = TextToSpeech(context.applicationContext, this)

    @Volatile private var ready = false
    @Volatile private var problem: String? = "Ses motoru hazırlanıyor, birkaç saniye sonra tekrar dene."
    private val appContext = context.applicationContext
    var onNotice: ((String) -> Unit)? = null

    override fun onInit(status: Int) {
        if (status != TextToSpeech.SUCCESS) {
            problem = "Telefonun metin okuma motoru başlatılamadı. Ayarlar › Genel yönetim › Dil ve giriş › Metin okuma'dan Google motorunu seç."
            onNotice?.invoke("Sesli okuma motoru başlatılamadı")
            return
        }
        var r = tts.setLanguage(Locale("tr", "TR"))
        if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) r = tts.setLanguage(Locale("tr"))
        ready = r != TextToSpeech.LANG_MISSING_DATA && r != TextToSpeech.LANG_NOT_SUPPORTED
        problem = if (ready) null else "Telefonda Türkçe ses paketi yok. Ayarlar › Genel yönetim › Dil ve giriş › Metin okuma › Google › Ses verilerini yükle › Türkçe."
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

    /** Deneme cümlesi okur; çalmazsa nedenini döndürür. */
    fun test(text: String): String? {
        problem?.let { return it }
        val am = appContext.getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
        val stream = if (Prefs.voiceOnNotification) android.media.AudioManager.STREAM_NOTIFICATION else android.media.AudioManager.STREAM_MUSIC
        val vol = am.getStreamVolume(stream)
        speak(text)
        if (vol == 0) {
            return if (Prefs.voiceOnNotification)
                "Bildirim sesi kapalı (0). Telefonun bildirim sesini aç ya da sesli okumayı \"Medya sesi\"ne al."
            else "Medya sesi kapalı (0). Telefonun ses tuşuyla medya sesini aç."
        }
        if (Prefs.voiceOnNotification && am.ringerMode != android.media.AudioManager.RINGER_MODE_NORMAL)
            return "Telefon sessiz ya da titreşimde; bildirim sesi çalmaz. Sesi aç ya da \"Medya sesi\"ni seç."
        return null
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
