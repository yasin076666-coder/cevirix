package com.bugra.altyazi.phone

import android.annotation.SuppressLint
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Credentials
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

/**
 * PlayStation hesabıyla giriş: Sony'nin kendi giriş sayfası açılır (şifre doğrudan Sony'ye gider),
 * dönüşte gelen kodla hesap kimliği (Account ID, Base64) alınır ve kaydedilir.
 * Akış chiaki-ng'nin masaüstü sürümündeki PSN girişinin aynısıdır.
 */
class PsnLoginActivity : AppCompatActivity() {

    companion object {
        private const val CLIENT_ID = "ba495a24-818c-472b-b12d-ff231c1b5745"
        private const val CLIENT_SECRET = "mvaiZkRsAsI1IBkY"
        private const val REDIRECT = "https://remoteplay.dl.playstation.net/remoteplay/redirect"
        private const val TOKEN_URL = "https://auth.api.sonyentertainmentnetwork.com/2.0/oauth/token"
        private val LOGIN_URL =
            "https://auth.api.sonyentertainmentnetwork.com/2.0/oauth/authorize" +
                "?service_entity=urn:service-entity:psn&response_type=code" +
                "&client_id=$CLIENT_ID&redirect_uri=$REDIRECT&scope=psn:clientapp" +
                "&request_locale=tr_TR&ui=pr&service_logo=ps&layout_type=popup&smcid=remoteplay" +
                "&prompt=always&PlatformPrivacyWs1=minimal&"
    }

    private lateinit var webView: WebView
    private lateinit var progress: ProgressBar
    private lateinit var info: TextView
    private var handled = false

    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Prefs.init(this)

        val root = FrameLayout(this).apply { setBackgroundColor(Color.parseColor("#0A0D14")) }
        webView = WebView(this)
        progress = ProgressBar(this).apply { isIndeterminate = true }
        info = TextView(this).apply {
            setTextColor(Color.WHITE)
            textSize = 16f
            gravity = Gravity.CENTER
            setPadding(48, 48, 48, 48)
            visibility = View.GONE
        }
        root.addView(webView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        root.addView(progress, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
        root.addView(info, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
        setContentView(root)
        title = "PlayStation ile giriş"

        // Her girişte temiz oturum
        try {
            CookieManager.getInstance().removeAllCookies(null)
            CookieManager.getInstance().flush()
        } catch (e: Exception) { }

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val url = request?.url?.toString() ?: return false
                return checkRedirect(url)
            }

            @Deprecated("Deprecated in Java")
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                return url != null && checkRedirect(url)
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                progress.visibility = View.VISIBLE
                if (url != null) checkRedirect(url)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                progress.visibility = View.GONE
            }
        }
        webView.loadUrl(LOGIN_URL)
    }

    private fun checkRedirect(url: String): Boolean {
        if (!url.startsWith(REDIRECT)) return false
        if (handled) return true
        handled = true
        val code = Uri.parse(url).getQueryParameter("code")
        if (code.isNullOrBlank()) {
            fail("Giriş tamamlanamadı (kod gelmedi). Tekrar deneyin.")
            return true
        }
        webView.visibility = View.GONE
        progress.visibility = View.VISIBLE
        info.visibility = View.VISIBLE
        info.text = "Hesap kimliği alınıyor…"
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) { runCatching { fetchAccountId(code) } }
            result.fold(
                onSuccess = { id ->
                    Prefs.psnAccountId = id
                    Toast.makeText(this@PsnLoginActivity, "PlayStation hesabı bağlandı ✓", Toast.LENGTH_LONG).show()
                    setResult(RESULT_OK)
                    finish()
                },
                onFailure = { fail("Hesap kimliği alınamadı: ${it.message}") }
            )
        }
        return true
    }

    private fun fetchAccountId(code: String): String {
        val auth = Credentials.basic(CLIENT_ID, CLIENT_SECRET)
        val form = FormBody.Builder()
            .add("grant_type", "authorization_code")
            .add("code", code)
            .add("redirect_uri", REDIRECT)
            .build()
        val tokenReq = Request.Builder().url(TOKEN_URL).header("Authorization", auth).post(form).build()
        val token = http.newCall(tokenReq).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) throw IllegalStateException("token ${resp.code}")
            JSONObject(body).getString("access_token")
        }
        val infoReq = Request.Builder()
            .url(TOKEN_URL + "/" + URLEncoder.encode(token, "UTF-8"))
            .header("Authorization", auth)
            .get()
            .build()
        val userId = http.newCall(infoReq).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) throw IllegalStateException("hesap ${resp.code}")
            JSONObject(body).getString("user_id")
        }
        // user_id (64 bit sayı) → 8 bayt little-endian → Base64
        val value = java.math.BigInteger(userId).toLong()
        val bytes = ByteArray(8) { i -> ((value ushr (8 * i)) and 0xFF).toByte() }
        return Base64.encodeToString(bytes, Base64.NO_WRAP)
    }

    private fun fail(msg: String) {
        progress.visibility = View.GONE
        info.visibility = View.VISIBLE
        info.text = "$msg\n\nGeri tuşuyla çıkıp tekrar deneyebilirsiniz."
    }

    override fun onDestroy() {
        try { webView.destroy() } catch (e: Exception) { }
        super.onDestroy()
    }
}
