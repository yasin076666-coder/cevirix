package com.bugra.altyazi.phone

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/** Çeviri geçmişi: en yenisi başta, en çok 300 satır (files/gecmis.json). */
object HistoryStore {
    data class Entry(val en: String, val tr: String, val engine: String, val at: Long)

    private const val MAX = 300
    private val items = ArrayList<Entry>()
    private var file: File? = null
    private var loaded = false
    @Volatile private var dirty = false

    @Synchronized
    fun init(ctx: Context) {
        if (loaded) return
        file = File(ctx.filesDir, "gecmis.json")
        try {
            val f = file
            if (f != null && f.exists()) {
                val a = JSONObject(f.readText()).optJSONArray("entries") ?: JSONArray()
                for (i in 0 until a.length()) {
                    val o = a.optJSONObject(i) ?: continue
                    items += Entry(o.optString("en"), o.optString("tr"), o.optString("engine"), o.optLong("at"))
                }
            }
        } catch (e: Exception) {
            items.clear()
        }
        loaded = true
    }

    @Synchronized
    fun add(en: String, tr: String, engine: String) {
        if (tr.isBlank() || engine == "Test") return
        val first = items.firstOrNull()
        if (first != null && first.en == en) {
            items[0] = Entry(en, tr, engine, System.currentTimeMillis())
        } else {
            items.add(0, Entry(en.take(500), tr.take(500), engine, System.currentTimeMillis()))
            while (items.size > MAX) items.removeAt(items.size - 1)
        }
        dirty = true
    }

    @Synchronized
    fun list(): List<Entry> = ArrayList(items)

    @Synchronized
    fun clear() {
        items.clear()
        dirty = true
        flush()
    }

    /** Diske yaz (değiştiyse). */
    @Synchronized
    fun flush() {
        if (!dirty) return
        val f = file ?: return
        try {
            val a = JSONArray()
            for (e in items) a.put(JSONObject().put("en", e.en).put("tr", e.tr).put("engine", e.engine).put("at", e.at))
            val tmp = File(f.parentFile, f.name + ".tmp")
            tmp.writeText(JSONObject().put("version", 1).put("entries", a).toString())
            tmp.renameTo(f)
            dirty = false
        } catch (e: Exception) {
        }
    }
}
