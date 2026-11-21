package com.bugra.altyazi.tv

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings

/** TV açıldığında altyazı servisini kendiliğinden başlatır (ayar açıksa). */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val prefs = context.getSharedPreferences(SubtitleOverlayService.PREFS, Context.MODE_PRIVATE)
        if (!prefs.getBoolean("auto_start", true)) return
        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(context)) return
        val svc = Intent(context, SubtitleOverlayService::class.java)
        try {
            if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(svc) else context.startService(svc)
        } catch (e: Exception) {
            // bazı TV'ler açılışta servis başlatmaya izin vermez; uygulama açılınca başlar
        }
    }
}
