package com.bugra.altyazi.phone

/** PS5'ten gelen oyun sesini telefonda açıp kapatır (bağlantı kesilmez). */
object PsAudio {
    private val loaded: Boolean = try {
        System.loadLibrary("chiaki-jni")
        true
    } catch (e: Throwable) {
        false
    }

    @JvmStatic
    private external fun nativeSetMuted(muted: Boolean)

    fun apply() {
        if (!loaded) return
        try { nativeSetMuted(Prefs.psMuted) } catch (e: Throwable) { }
    }

    fun set(muted: Boolean) {
        Prefs.psMuted = muted
        apply()
    }
}
