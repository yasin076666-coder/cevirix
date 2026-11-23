package com.bugra.altyazi.phone

import android.content.Context
import android.content.SharedPreferences

/** Tüm ayarlar telefonda kalıcı olarak saklanır. */
object Prefs {
    const val DEFAULT_MODEL = "gemini-3.5-flash-lite"

    private lateinit var sp: SharedPreferences

    fun init(context: Context) {
        if (!::sp.isInitialized) {
            sp = context.applicationContext.getSharedPreferences("ayarlar", Context.MODE_PRIVATE)
        }
    }

    var geminiEnabled: Boolean
        get() = sp.getBoolean("gemini_on", true)
        set(v) = sp.edit().putBoolean("gemini_on", v).apply()

    var geminiKey: String
        get() = sp.getString("gemini_key", "") ?: ""
        set(v) = sp.edit().putString("gemini_key", v.trim()).apply()

    var geminiModel: String
        get() = (sp.getString("gemini_model", DEFAULT_MODEL) ?: DEFAULT_MODEL).ifBlank { DEFAULT_MODEL }
        set(v) = sp.edit().putString("gemini_model", v.trim()).apply()

    var dubbing: Boolean
        get() = sp.getBoolean("dubbing", false)
        set(v) = sp.edit().putBoolean("dubbing", v).apply()

    /** Yüzde olarak konuşma hızı (100 = normal). */
    var speechRate: Int
        get() = sp.getInt("speech_rate", 110)
        set(v) = sp.edit().putInt("speech_rate", v).apply()

    /** true: bildirim ses kanalı (Remote Play sesi kapatılabilir), false: medya. */
    var voiceOnNotification: Boolean
        get() = sp.getBoolean("voice_notif", true)
        set(v) = sp.edit().putBoolean("voice_notif", v).apply()

    /** Altyazı bandının ekrandaki üst ve alt sınırı (yüzde). */
    var roiTop: Int
        get() = sp.getInt("roi_top", 72)
        set(v) = sp.edit().putInt("roi_top", v).apply()

    var roiBottom: Int
        get() = sp.getInt("roi_bottom", 96)
        set(v) = sp.edit().putInt("roi_bottom", v).apply()

    var tvFontSize: Int
        get() = sp.getInt("tv_font", 30)
        set(v) = sp.edit().putInt("tv_font", v).apply()

    var tvYOffset: Int
        get() = sp.getInt("tv_y", 70)
        set(v) = sp.edit().putInt("tv_y", v).apply()

    var tvBgAlpha: Int
        get() = sp.getInt("tv_alpha", 170)
        set(v) = sp.edit().putInt("tv_alpha", v).apply()

    /** PlayStation girişinden alınan hesap kimliği (8 bayt, Base64). */
    var psnAccountId: String
        get() = sp.getString("psn_account_id", "") ?: ""
        set(v) = sp.edit().putString("psn_account_id", v.trim()).apply()

    /** Anında çeviri: önce çevrimdışı hızlı çeviri, Gemini gelince yerine geçer. */
    var instantTranslate: Boolean
        get() = sp.getBoolean("instant_translate", true)
        set(v) = sp.edit().putBoolean("instant_translate", v).apply()

    /** Dahili Remote Play açıkken altyazıyı çevir. */
    var streamTranslate: Boolean
        get() = sp.getBoolean("stream_translate", true)
        set(v) = sp.edit().putBoolean("stream_translate", v).apply()

    /** Telefon başka işte kullanılırken (uygulama arka plandayken) çeviriye devam et. */
    var backgroundStream: Boolean
        get() = sp.getBoolean("background_stream", true)
        set(v) = sp.edit().putBoolean("background_stream", v).apply()

    /** Bağlanınca oyunu ana ekrandaki küçük pencereye al. */
    var miniView: Boolean
        get() = sp.getBoolean("mini_view", true)
        set(v) = sp.edit().putBoolean("mini_view", v).apply()

    /** PS5'ten telefona gelen oyun sesi kapalı mı? */
    var psMuted: Boolean
        get() = sp.getBoolean("ps_muted", true)
        set(v) = sp.edit().putBoolean("ps_muted", v).apply()

    /** Nino TV uygulamalarına da gönder (Samsung, LG, Android TV). */
    var ninoTv: Boolean
        get() = sp.getBoolean("nino_tv", true)
        set(v) = sp.edit().putBoolean("nino_tv", v).apply()

    /** GTA 6: oyun içi telefon mesajları ve harita kartı çevirisi. */
    var gtaExtras: Boolean
        get() = sp.getBoolean("gta_extras", true)
        set(v) = sp.edit().putBoolean("gta_extras", v).apply()

    /** Terim sözlüğü (satır satır: "Ad" ya da "kelime = karşılık"). */
    var glossary: String
        get() = sp.getString("glossary", null) ?: Glossary.DEFAULT
        set(v) = sp.edit().putString("glossary", v).apply()

    var tvShowEn: Boolean
        get() = sp.getBoolean("tv_en", false)
        set(v) = sp.edit().putBoolean("tv_en", v).apply()
}
