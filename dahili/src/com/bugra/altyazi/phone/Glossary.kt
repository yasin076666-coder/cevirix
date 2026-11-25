package com.bugra.altyazi.phone

import com.ninotranslator.core.translation.Term
import com.ninotranslator.core.translation.TermProtector

/**
 * Terim sözlüğü: çevrilmeyecek adlar ve sabit karşılıklar.
 * Satır biçimi: "Lucia" (aynen kalsın) ya da "wanted level = aranma seviyesi".
 * Gemini'ye talimat olarak gider; internetsiz çeviride yer tutucuyla korunur (Nino'nun TermProtector'ı).
 */
object Glossary {

    const val DEFAULT = """Lucia
Jason
Vice City
Leonida
Leonida Keys
Port Gellhorn
Grassrivers
Ambrosia
Mount Kalaga
Vice-Dale
VCPD
Ammu-Nation
Weazel News
Cal Hampton
Boobie Ike
Dre'Quan
Raul Bautista
Brian Heder
Real Dimez"""

    @Volatile private var cachedText: String? = null
    @Volatile private var cachedTerms: List<Term> = emptyList()

    fun terms(): List<Term> {
        val text = Prefs.glossary + "\n" + GameProfile.current.terms
        if (text == cachedText) return cachedTerms
        val list = text.lines().mapNotNull { raw ->
            val l = raw.trim()
            if (l.isEmpty() || l.startsWith("#")) return@mapNotNull null
            val i = l.indexOf('=')
            if (i > 0) {
                val src = l.substring(0, i).trim()
                val dst = l.substring(i + 1).trim()
                if (src.isEmpty()) null else Term(src, dst.ifEmpty { null })
            } else Term(l, null)
        }
        cachedText = text
        cachedTerms = list
        return list
    }

    /** Gemini'ye eklenen not: oyun bilgisi ve cümlede geçen terimler. */
    fun noteFor(english: String): String? {
        val game = GameProfile.current.note
        val found = terms().filter { english.contains(it.source, ignoreCase = true) }
        if (found.isEmpty()) return game.ifBlank { null }
        val keep = found.filter { it.target == null }.joinToString(", ") { it.source }
        val fixed = found.filter { it.target != null }.joinToString("; ") { "${it.source} → ${it.target}" }
        return buildString {
            if (game.isNotBlank()) append(game).append("\n")
            append("Terim sözlüğü:")
            if (keep.isNotEmpty()) append(" şu adları çevirme, aynen yaz: ").append(keep).append('.')
            if (fixed.isNotEmpty()) append(" Şu karşılıkları kullan: ").append(fixed).append('.')
        }
    }

    /** İnternetsiz çeviri: terimleri koruyarak çevir. Yer tutucu kaybolursa korumasız çeviriye döner. */
    suspend fun translateProtected(text: String, machine: suspend (String) -> String?): String? {
        val t = terms()
        if (t.isEmpty() || t.none { text.contains(it.source, ignoreCase = true) }) return machine(text)
        val p = TermProtector(t)
        val prot = p.protect(text)
        if (prot.replacements.isEmpty()) return machine(text)
        val out = machine(prot.text) ?: return null
        return p.restore(out, prot) ?: machine(text)
    }
}
