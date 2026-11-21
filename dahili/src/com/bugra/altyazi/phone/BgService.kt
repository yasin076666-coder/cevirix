package com.bugra.altyazi.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import com.metallic.chiaki.R

/**
 * Çevirix arka planda çeviri yaparken çalışan bildirim servisi.
 * Telefonun uygulamayı kapatmasını, Wi-Fi'nin uyumasını engeller.
 */
class BgService : Service() {

    companion object {
        const val ACTION_STOP = "com.bugra.cevirix.BG_STOP"
        private const val CHANNEL = "cevirix_arka_plan"
        private const val NOTIF_ID = 77

        /** Bildirimdeki "Durdur" basılınca akış ekranını kapatır. */
        @Volatile var onStopRequested: (() -> Unit)? = null

        fun start(ctx: Context) {
            try {
                val i = Intent(ctx, BgService::class.java)
                if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
            } catch (e: Exception) { }
        }

        fun stop(ctx: Context) {
            try { ctx.stopService(Intent(ctx, BgService::class.java)) } catch (e: Exception) { }
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForegroundCompat()
        if (intent?.action == ACTION_STOP) {
            onStopRequested?.invoke()
            stopSelf()
            return START_NOT_STICKY
        }
        acquireLocks()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        releaseLocks()
        super.onDestroy()
    }

    private fun acquireLocks() {
        try {
            if (wakeLock == null) {
                val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
                wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "cevirix:arkaplan").apply {
                    setReferenceCounted(false)
                    acquire(6 * 60 * 60 * 1000L)
                }
            }
            if (wifiLock == null) {
                val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
                @Suppress("DEPRECATION")
                wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "cevirix:arkaplan").apply {
                    setReferenceCounted(false)
                    acquire()
                }
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
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Arka planda çeviri", NotificationManager.IMPORTANCE_LOW)
            )
        }
        val flags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        val stopPi = PendingIntent.getService(
            this, 11, Intent(this, BgService::class.java).setAction(ACTION_STOP), flags
        )
        // Bildirime basınca oyun ekranına geri dön
        val openIntent = Intent(this, com.metallic.chiaki.stream.StreamActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_NEW_TASK)
        val openPi = PendingIntent.getActivity(this, 12, openIntent, flags)
        val n: Notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.cx_ic_stat)
            .setContentTitle("Çevirix arka planda çeviriyor")
            .setContentText("Telefonu rahatça kullanabilirsin. Altyazılar TV'ye gitmeye devam ediyor.")
            .setOngoing(true)
            .setContentIntent(openPi)
            .addAction(0, "Durdur", stopPi)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIF_ID, n)
        }
    }
}
