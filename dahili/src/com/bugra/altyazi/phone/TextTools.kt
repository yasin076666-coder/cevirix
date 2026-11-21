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

    // GTA araç markaları ve sık görülen tabela/model yazıları (tek başına görülünce diyalog sayılmaz)
    private val BRANDS = setOf(
        "albany", "annis", "benefactor", "bf", "bollokan", "bravado", "brute", "buckingham", "canis",
        "chariot", "cheval", "coil", "declasse", "dewbauchee", "dinka", "dundreary", "emperor", "enus",
        "fathom", "gallivanter", "grotti", "hijak", "hvy", "imponte", "invetero", "jacksheepe", "jobuilt",
        "karin", "lampadati", "lcc", "maibatsu", "mammoth", "maxwell", "mtl", "nagasaki", "obey", "ocelot",
        "overflod", "pegassi", "pfister", "principe", "progen", "rune", "schyster", "shitzu", "stanley",
        "truffade", "ubermacht", "vapid", "vulcar", "vysser", "weeny", "western", "willard", "zirconium",
        "sentinel", "oracle", "felon", "zion", "tailgater", "buffalo", "dominator", "gauntlet", "banshee",
        "infernus", "adder", "zentorno", "comet", "sultan", "elegy", "kuruma", "faggio", "sanchez",
        "leonida", "vice", "city", "taxi", "police", "sheriff", "vcpd", "lspd", "ammunation", "ammu",
        "nation", "cluckin", "bell", "burger", "shot", "bean", "machine", "pisswasser", "sprunk", "ecola",
        "lsc", "customs", "los", "santos", "motel", "gas", "station", "open", "closed", "exit", "stop",
        "one", "way", "only", "keep", "right", "left", "speed", "limit", "mph", "sale", "for", "rent"
    )
    private val endPunct = Regex("[!?.…]$")

    /**
     * Plaka, marka, tabela gibi diyalog olmayan yazıları ayıklar.
     * Ör. "z G03-821", "6ABC123", "Ubermacht", "Grotti Turismo", "Bean Machine".
     */
    fun isNoiseLine(line: String): Boolean {
        val tokens = line.split(spaces).filter { it.isNotBlank() }
        if (tokens.isEmpty()) return true
        var realWords = 0
        var mixed = 0
        var digitTokens = 0
        val words = ArrayList<String>()
        for (t in tokens) {
            val letters = t.count { it.isLetter() }
            val digits = t.count { it.isDigit() }
            when {
                letters > 0 && digits > 0 -> mixed++          // G03-821, 6ABC123
                digits > 0 -> digitTokens++                   // 821, 2026
                letters >= 2 -> { realWords++; words += t.lowercase().filter { it.isLetter() } }
            }
        }
        // Plaka: harf-rakam karışık parçalar ağırlıkta
        if (realWords == 0) return true
        if (mixed > 0 && mixed + digitTokens >= realWords) return true

        val hasPunct = endPunct.containsMatchIn(line.trim())
        if (!hasPunct && realWords <= 3) {
            // Tamamen marka/tabela kelimeleri
            if (words.all { it in BRANDS }) return true
            // Tek kelime, noktalama yok, sözlükte de yok: büyük ihtimalle model adı veya tabela
            if (realWords == 1 && OfflineSlang.translateFromPhrasesOnly(line) == null) return true
            // Küçük harf hiç yok (tabela: "BEAN MACHINE")
            if (line.none { it.isLowerCase() } && OfflineSlang.translateFromPhrasesOnly(line) == null) return true
        }
        return false
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
