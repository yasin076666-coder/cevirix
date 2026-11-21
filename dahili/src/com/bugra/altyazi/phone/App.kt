package com.bugra.altyazi.phone

import android.app.Application
import android.content.Context
import android.os.Build
import java.io.PrintWriter
import java.io.StringWriter

class App : Application() {
    override fun onCreate() {
        super.onCreate()
        Thread { OfflineSlang.load(this) }.start()
        Prefs.init(this)
        OfflineTranslator.checkDownloaded()
        installCrashCatcher()
        startLogRecorder()
    }

    /** Kendi işlemimizin kayıtlarını dosyaya yazar (C tarafındaki çökmeleri de görebilmek için). */
    private fun startLogRecorder() {
        try {
            val cur = java.io.File(filesDir, "kayit.txt")
            val old = java.io.File(filesDir, "onceki_kayit.txt")
            if (cur.exists()) {
                old.delete()
                cur.renameTo(old)
            }
            val pid = android.os.Process.myPid()
            Thread {
                try {
                    val proc = Runtime.getRuntime().exec(arrayOf("logcat", "-v", "time", "--pid=$pid"))
                    cur.outputStream().buffered().use { out ->
                        proc.inputStream.copyTo(out, 1024)
                    }
                } catch (e: Throwable) {
                }
            }.apply { isDaemon = true; name = "cevirix-kayit" }.start()
        } catch (e: Throwable) {
        }
    }

    /** Çökme olursa ayrıntısını saklar; Çevirix bir sonraki açılışta ekranda gösterir. */
    private fun installCrashCatcher() {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            try {
                val sw = StringWriter()
                error.printStackTrace(PrintWriter(sw))
                val text = "Çevirix ${Build.MODEL} Android ${Build.VERSION.RELEASE}\n" +
                    "Thread: ${thread.name}\n" + sw.toString().take(6000)
                getSharedPreferences("hata", Context.MODE_PRIVATE).edit().putString("son_hata", text).commit()
            } catch (e: Throwable) {
            }
            previous?.uncaughtException(thread, error)
        }
    }

    companion object {
        /** PS5 ekranı açılırken işaret koyar; işlem çökerse bir sonraki açılışta anlaşılır. */
        fun markPs5Opening(context: Context) {
            context.getSharedPreferences("hata", Context.MODE_PRIVATE).edit()
                .putInt("ps5_pid", android.os.Process.myPid()).commit()
        }

        /** Önceki işlem PS5 ekranında çöktüyse son kayıt satırlarını döndürür. */
        fun takeNativeCrash(context: Context): String? {
            val sp = context.getSharedPreferences("hata", Context.MODE_PRIVATE)
            val pid = sp.getInt("ps5_pid", -1)
            if (pid == -1) return null
            if (pid == android.os.Process.myPid()) return null // aynı işlem: çökme yok
            sp.edit().remove("ps5_pid").apply()
            val f = java.io.File(context.filesDir, "onceki_kayit.txt")
            if (!f.exists()) return "PS5 ekranı açılırken uygulama kapandı ama kayıt bulunamadı."
            val lines = f.readLines()
            val important = lines.filter {
                it.contains(" E/") || it.contains(" F/") || it.contains("Fatal") ||
                    it.contains("chiaki", true) || it.contains("Exception") || it.contains("at ")
            }
            val pick = (if (important.size > 10) important else lines).takeLast(80)
            return "PS5 ekranında kapanma (son kayıtlar):\n" + pick.joinToString("\n").take(7000)
        }

        fun takeLastCrash(context: Context): String? {
            val sp = context.getSharedPreferences("hata", Context.MODE_PRIVATE)
            val t = sp.getString("son_hata", null) ?: return null
            sp.edit().remove("son_hata").remove("ps5_pid").apply()
            return t
        }
    }
}
