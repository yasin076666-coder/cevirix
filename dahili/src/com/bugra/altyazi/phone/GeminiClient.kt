package com.bugra.altyazi.phone

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.Collections
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/** Gemini API ile GTA 6 sokak diline uygun çeviri (engelleyici çağrı, IO thread'inde kullanın). */
object GeminiClient {

    class GeminiError(val code: Int, message: String) : Exception(message)

    private val JSON = "application/json; charset=utf-8".toMediaType()

    private val http = OkHttpClient.Builder()
        .connectTimeout(4, TimeUnit.SECONDS)
        .writeTimeout(4, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .callTimeout(9, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    /** "Düşünme" ayarını desteklemeyen modeller (bir kez hata verince hatırlanır). */
    private val noThinking: MutableSet<String> = Collections.newSetFromMap(ConcurrentHashMap())

    private const val SYSTEM_PROMPT = """Sen GTA 6 için çalışan, sokak kültürünü çok iyi bilen profesyonel bir Türkçe oyun yerelleştirme uzmanısın.
Görevin: Ekrandan yazı tanıma (OCR) ile okunmuş İngilizce oyun altyazısını, karakterlerin ağzından çıkmış gibi doğal ve akıcı Türkçe sokak diliyle çevirmek.

Kurallar:
- Sadece Türkçe çeviriyi yaz. Açıklama, tırnak işareti, not veya alternatif yazma.
- Kitap dili kullanma. Samimi, canlı, sokak ağzı kullan: "bro/dude/man" için bağlama göre "kanka, birader, abi, lan"; "cops" için "aynasızlar, polisler"; "let's go/bounce" için "kaçalım, toz olalım" gibi. Abartma, her cümleye argo sıkıştırma; Türk bir oyuncunun doğal bulacağı şekilde yaz.
- Küfür ve sert ifadeleri yumuşatma ve sansürleme; Türkçedeki doğal karşılığıyla çevir.
- Kişi, şehir, mekan, marka ve araç adlarını (Lucia, Jason, Vice City, Leonida, Port Gellhorn vb.) çevirme.
- Satırın başında konuşmacı adı varsa (ör. "LUCIA: ...") adı aynen koru ve sadece konuşmayı çevir.
- OCR hatası varsa (eksik harf, bozuk kelime, birleşik kelimeler) cümlenin anlamını tahmin edip düzgün çevir.
- Metin bir diyalog değilse (menü, sayı, para, harita, anlamsız harfler) hiçbir şey yazma, boş yanıt ver.
- Çeviri altyazı gibi kısa ve hızlı okunur olsun."""

    fun translate(apiKey: String, model: String, english: String, context: List<Pair<String, String>>): String {
        val m = model.trim()
        return try {
            call(apiKey, m, english, context, !noThinking.contains(m))
        } catch (e: GeminiError) {
            val thinkingProblem = e.code == 400 && (e.message ?: "").contains("thinking", ignoreCase = true)
            if (thinkingProblem && !noThinking.contains(m)) {
                noThinking.add(m)
                call(apiKey, m, english, context, false)
            } else {
                throw e
            }
        }
    }

    private fun call(
        apiKey: String,
        model: String,
        english: String,
        context: List<Pair<String, String>>,
        useThinking: Boolean
    ): String {
        val userText = buildString {
            if (context.isNotEmpty()) {
                append("Önceki altyazılar (sadece bağlam için, bunları tekrar çevirme):\n")
                for ((en, tr) in context) {
                    append("EN: ").append(en).append('\n')
                    append("TR: ").append(tr).append('\n')
                }
                append('\n')
            }
            Glossary.noteFor(english)?.let { append(it).append("\n\n") }
            append("Şimdi bu altyazıyı çevir:\n").append(english)
        }

        val generation = JSONObject()
            .put("temperature", 0.5)
            .put("maxOutputTokens", 300)
        if (useThinking) {
            thinkingConfigFor(model)?.let { generation.put("thinkingConfig", it) }
        }

        val safety = JSONArray()
        listOf(
            "HARM_CATEGORY_HARASSMENT",
            "HARM_CATEGORY_HATE_SPEECH",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "HARM_CATEGORY_DANGEROUS_CONTENT"
        ).forEach { safety.put(JSONObject().put("category", it).put("threshold", "BLOCK_NONE")) }

        val body = JSONObject()
            .put(
                "system_instruction",
                JSONObject().put("parts", JSONArray().put(JSONObject().put("text", SYSTEM_PROMPT)))
            )
            .put(
                "contents",
                JSONArray().put(
                    JSONObject()
                        .put("role", "user")
                        .put("parts", JSONArray().put(JSONObject().put("text", userText)))
                )
            )
            .put("generationConfig", generation)
            .put("safetySettings", safety)

        val request = Request.Builder()
            .url("https://generativelanguage.googleapis.com/v1beta/models/$model:generateContent")
            .header("x-goog-api-key", apiKey.trim())
            .post(body.toString().toRequestBody(JSON))
            .build()

        val (code, raw) = http.newCall(request).execute().use { resp ->
            resp.code to resp.body?.string().orEmpty()
        }
        if (code !in 200..299) throw GeminiError(code, extractError(raw))
        return parse(raw)
    }

    private fun thinkingConfigFor(model: String): JSONObject? = when {
        model.startsWith("gemini-2.5") ->
            if (model.contains("pro")) null else JSONObject().put("thinkingBudget", 0)
        model.startsWith("gemini-3") || model.startsWith("gemini-4") ->
            JSONObject().put("thinkingLevel", "minimal")
        else -> null
    }

    private fun parse(raw: String): String {
        val root = JSONObject(raw)
        val candidates = root.optJSONArray("candidates")
        if (candidates == null || candidates.length() == 0) throw GeminiError(0, "Gemini boş yanıt verdi")
        val parts = candidates.getJSONObject(0).optJSONObject("content")?.optJSONArray("parts")
            ?: return "" // içerik yoksa (ör. diyalog değil) boş kabul et
        val sb = StringBuilder()
        for (i in 0 until parts.length()) {
            val p = parts.getJSONObject(i)
            if (p.optBoolean("thought", false)) continue
            sb.append(p.optString("text", ""))
        }
        return sb.toString().trim().trim('"', '“', '”', '«', '»').trim()
    }

    private fun extractError(raw: String): String = try {
        JSONObject(raw).getJSONObject("error").optString("message", raw.take(200))
    } catch (e: Exception) {
        raw.take(200)
    }
}
