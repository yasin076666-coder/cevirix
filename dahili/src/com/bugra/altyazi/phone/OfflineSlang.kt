package com.bugra.altyazi.phone

import android.content.Context
import org.json.JSONObject
import java.util.Locale

/**
 * Çevrimdışı sokak dili katmanı (assets/sokak_sozlugu.json):
 * 1) Hazır kalıplar: oyunlarda sık geçen cümleler doğrudan sokak ağzıyla eşleşir.
 * 2) İngilizce sokak ağzı düzeltme: gonna/wanna/ain't/cops... çeviriden önce düz İngilizceye çevrilir.
 * 3) Türkçe sokak ağzı: çeviri çıktısındaki resmî dil (Siz, -misiniz, dostum, Kahretsin...) samimileşir.
 * 4) Hitaplar: "bro, man, dude" cümleden ayrılır, Türkçeye "kanka, lan, abi" olarak geri eklenir.
 */
object OfflineSlang {

    private val TR = Locale("tr", "TR")

    @Volatile private var loaded = false
    private var phrases: Map<String, String> = emptyMap()
    private var pre: List<Pair<Regex, String>> = emptyList()
    private var post: List<Pair<Regex, String>> = emptyList()
    private var vocatives: Map<String, String> = emptyMap()
    private var leadingVoc: Regex? = null
    private var trailingVoc: Regex? = null

    private val gDrop = Regex("\\b([A-Za-z]+)in'(?![A-Za-z])")
    private val speakerRx = Regex("^([A-Z][A-Za-z0-9 .'\\-]{0,24}):\\s+(.+)$")
    private val sentenceSplit = Regex("(?<=[.!?])\\s+")

    val size: Int get() = phrases.size

    @Synchronized
    fun load(context: Context) {
        if (loaded) return
        try {
            val text = context.assets.open("sokak_sozlugu.json").bufferedReader(Charsets.UTF_8).use { it.readText() }
            val root = JSONObject(text)

            val p = root.getJSONObject("phrases")
            val map = HashMap<String, String>(p.length() * 2)
            val it = p.keys()
            while (it.hasNext()) {
                val k = it.next()
                map[k] = p.getString(k)
            }
            phrases = map

            val preArr = root.getJSONArray("pre")
            pre = (0 until preArr.length()).mapNotNull { i ->
                val pair = preArr.getJSONArray(i)
                runCatching { Regex(pair.getString(0), RegexOption.IGNORE_CASE) to pair.getString(1) }.getOrNull()
            }

            val postArr = root.getJSONArray("post")
            post = (0 until postArr.length()).mapNotNull { i ->
                val pair = postArr.getJSONArray(i)
                runCatching { Regex(pair.getString(0)) to pair.getString(1) }.getOrNull()
            }

            val v = root.getJSONObject("vocatives")
            val vm = HashMap<String, String>()
            val vi = v.keys()
            while (vi.hasNext()) {
                val k = vi.next()
                vm[k] = v.getString(k)
            }
            vocatives = vm
            val alt = vm.keys.sortedByDescending { it.length }.joinToString("|") { Regex.escape(it) }
            leadingVoc = Regex("^($alt)[,!]?\\s+(.+)$", RegexOption.IGNORE_CASE)
            trailingVoc = Regex("^(.+?),\\s*($alt)([.!?]*)$", RegexOption.IGNORE_CASE)
            loaded = true
        } catch (e: Exception) {
            loaded = false
        }
    }

    // ---------------------------------------------------------------- İngilizce tarafı

    /** Anahtar için: küçük harf, sokak ağzı düzeltilmiş, kısaltmalar açılmış, noktalamasız. */
    private fun normalizeEn(s: String): String {
        var t = s.lowercase(Locale.ROOT).replace('’', '\'').replace('‘', '\'')
        for ((rx, rep) in pre) t = rx.replace(t, rep)
        t = gDrop.replace(t) { m -> m.groupValues[1] + "ing" }
        t = expandContractions(t)
        return t
    }

    private fun expandContractions(s: String): String {
        var t = s
        t = Regex("\\b([Cc])an't\\b").replace(t) { m -> m.groupValues[1] + "annot" }
        t = Regex("\\b([Ww])on't\\b").replace(t) { m -> m.groupValues[1] + "ill not" }
        t = Regex("n't\\b", RegexOption.IGNORE_CASE).replace(t, " not")
        t = Regex("'re\\b", RegexOption.IGNORE_CASE).replace(t, " are")
        t = Regex("'m\\b", RegexOption.IGNORE_CASE).replace(t, " am")
        t = Regex("'ll\\b", RegexOption.IGNORE_CASE).replace(t, " will")
        t = Regex("'ve\\b", RegexOption.IGNORE_CASE).replace(t, " have")
        t = Regex("'d\\b", RegexOption.IGNORE_CASE).replace(t, " would")
        return t
    }

    private fun key(s: String): String {
        val q = if (s.trim().endsWith("?")) "?" else ""
        val n = normalizeEn(s).replace("'", "")
        val k = n.replace(Regex("[^a-z0-9 ]"), " ").replace(Regex("\\s+"), " ").trim()
        return if (k.isEmpty()) "" else k + q
    }

    private fun lookup(sentence: String): String? {
        val k = key(sentence)
        if (k.isEmpty()) return null
        return phrases[k] ?: if (k.endsWith("?")) phrases[k.dropLast(1)] else null
    }

    /** Çeviri modeline gidecek metin: büyük/küçük harf korunur, sokak ağzı düzeltilir. */
    private fun prepareForTranslation(s: String): String {
        var t = s.replace('’', '\'').replace('‘', '\'')
        for ((rx, rep) in pre) t = rx.replace(t, rep)
        t = gDrop.replace(t) { m -> m.groupValues[1] + "ing" }
        return expandContractions(t)
    }

    // ---------------------------------------------------------------- Türkçe tarafı

    private fun applyPost(s: String): String {
        var t = s
        for ((rx, rep) in post) t = rx.replace(t, rep)
        t = t.replace(Regex("\\s+"), " ").replace(Regex("\\s+([,.!?])"), "$1").trim()
        return capitalizeFirst(t)
    }

    private fun capitalizeFirst(s: String): String =
        if (s.isEmpty()) s else s.substring(0, 1).uppercase(TR) + s.substring(1)

    private fun lowerFirst(s: String): String =
        if (s.isEmpty()) s else s.substring(0, 1).lowercase(TR) + s.substring(1)

    // ---------------------------------------------------------------- çeviri

    /**
     * Bir altyazıyı sokak diliyle çevirir. [machine]: bilinmeyen cümleler için çevrimdışı çeviri.
     * Kalıp sözlüğünde olmayan bir cümle çevrilemezse null döner.
     */
    suspend fun translate(en: String, machine: suspend (String) -> String?): String? {
        if (!loaded) return machine(en)?.let { it }
        val trimmed = en.trim()
        val sm = speakerRx.find(trimmed)
        val speaker = sm?.groupValues?.get(1)
        val body = sm?.groupValues?.get(2) ?: trimmed

        val sentences = sentenceSplit.split(body).map { it.trim() }.filter { it.isNotEmpty() }
        if (sentences.isEmpty()) return null
        val parts = ArrayList<String>(sentences.size)
        for (s in sentences) {
            parts += translateSentence(s, machine) ?: return null
        }
        val joined = parts.joinToString(" ")
        return if (speaker != null) "$speaker: $joined" else joined
    }

    /** Sadece kalıp sözlüğüyle (çeviri modeli olmadan) çevrilebiliyorsa döndürür. */
    fun translateFromPhrasesOnly(en: String): String? {
        if (!loaded) return null
        val trimmed = en.trim()
        val sm = speakerRx.find(trimmed)
        val speaker = sm?.groupValues?.get(1)
        val body = sm?.groupValues?.get(2) ?: trimmed
        val sentences = sentenceSplit.split(body).map { it.trim() }.filter { it.isNotEmpty() }
        if (sentences.isEmpty()) return null
        val parts = sentences.map { s -> phraseWithVocative(s) ?: return null }
        val joined = parts.joinToString(" ")
        return if (speaker != null) "$speaker: $joined" else joined
    }

    private fun phraseWithVocative(s: String): String? {
        lookup(s)?.let { return it }
        val v = splitVocative(s) ?: return null
        val hit = lookup(v.core) ?: return null
        return attachVocative(hit, v)
    }

    private suspend fun translateSentence(s: String, machine: suspend (String) -> String?): String? {
        lookup(s)?.let { return it }
        val v = splitVocative(s)
        if (v != null) {
            lookup(v.core)?.let { return attachVocative(it, v) }
            val tr = machine(prepareForTranslation(v.core)) ?: return null
            return attachVocative(applyPost(tr), v)
        }
        val tr = machine(prepareForTranslation(s)) ?: return null
        return applyPost(tr)
    }

    private data class Vocative(val core: String, val word: String, val leading: Boolean, val punct: String)

    private fun splitVocative(s: String): Vocative? {
        leadingVoc?.find(s)?.let { m ->
            val core = m.groupValues[2].trim()
            if (core.length >= 2) {
                val tr = vocatives[m.groupValues[1].lowercase(Locale.ROOT)] ?: return@let
                return Vocative(core, tr, leading = true, punct = "")
            }
        }
        trailingVoc?.find(s)?.let { m ->
            val core = m.groupValues[1].trim()
            if (core.length >= 2) {
                val tr = vocatives[m.groupValues[2].lowercase(Locale.ROOT)] ?: return@let
                val punct = m.groupValues[3].ifEmpty { "." }
                return Vocative(core + punct.take(1), tr, leading = false, punct = punct)
            }
        }
        return null
    }

    private fun attachVocative(tr: String, v: Vocative): String {
        if (v.word.isBlank()) return tr
        return if (v.leading) {
            capitalizeFirst(v.word) + ", " + lowerFirstUnlessName(tr)
        } else {
            val end = tr.takeLastWhile { it == '.' || it == '!' || it == '?' }
            val bodyTr = tr.dropLast(end.length).trimEnd(',', ' ')
            "$bodyTr ${v.word}${end.ifEmpty { v.punct }}"
        }
    }

    /** Cümle bir özel isimle başlamıyorsa ilk harfi küçült (ör. "Kanka, hadi gidelim"). */
    private fun lowerFirstUnlessName(s: String): String {
        val first = s.substringBefore(' ')
        val names = setOf("Lucia", "Jason", "Vice", "Leonida", "Port", "Kirk", "Allah'ım")
        return if (first.trimEnd(',', '!', '?', '.') in names) s else lowerFirst(s)
    }
}
