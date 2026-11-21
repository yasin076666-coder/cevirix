package com.bugra.altyazi.phone

import java.net.Inet4Address
import java.net.NetworkInterface
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

object TextTools {
    private val spaces = Regex("\\s+")

    fun clean(s: String): String = s.replace('|', 'I').replace(spaces, " ").trim()

    fun normalize(s: String): String = s.lowercase().filter { it.isLetterOrDigit() }

    /** Oyun arayüzündeki sayı/para/simge satırlarını ayıklar. */
    fun isDialogLine(line: String): Boolean {
        val letters = line.count { it.isLetter() }
        if (letters < 2) return false
        val nonSpace = line.count { !it.isWhitespace() }
        return letters >= nonSpace * 0.5
    }

    /** OCR titremelerinde aynı cümleyi tekrar göndermemek için benzerlik ölçer. */
    fun similar(a: String, b: String, threshold: Double = 0.85): Boolean {
        if (a == b) return true
        if (a.isEmpty() || b.isEmpty()) return false
        val maxLen = max(a.length, b.length)
        if (abs(a.length - b.length) > maxLen * 0.2) return false
        val d = levenshtein(a, b)
        return 1.0 - d.toDouble() / maxLen >= threshold
    }

    private fun levenshtein(a: String, b: String): Int {
        var prev = IntArray(b.length + 1) { it }
        var cur = IntArray(b.length + 1)
        for (i in 1..a.length) {
            cur[0] = i
            for (j in 1..b.length) {
                val cost = if (a[i - 1] == b[j - 1]) 0 else 1
                cur[j] = min(min(cur[j - 1] + 1, prev[j] + 1), prev[j - 1] + cost)
            }
            val t = prev; prev = cur; cur = t
        }
        return prev[b.length]
    }
}

object NetUtil {
    /** Telefonun yerel Wi-Fi IPv4 adresi. */
    fun localIp(): String {
        try {
            val all = NetworkInterface.getNetworkInterfaces()?.toList() ?: return "-"
            val ordered = all.sortedBy { if (it.name.startsWith("wlan")) 0 else 1 }
            for (ni in ordered) {
                if (!ni.isUp || ni.isLoopback) continue
                for (addr in ni.inetAddresses.toList()) {
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        val host = addr.hostAddress
                        if (!host.isNullOrBlank()) return host
                    }
                }
            }
        } catch (e: Exception) {
            // yoksay
        }
        return "-"
    }
}
