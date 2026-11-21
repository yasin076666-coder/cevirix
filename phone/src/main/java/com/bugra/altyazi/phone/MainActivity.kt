package com.bugra.altyazi.phone

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.google.android.material.button.MaterialButton
import com.google.android.material.button.MaterialButtonToggleGroup
import com.google.android.material.chip.Chip
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.android.material.slider.RangeSlider
import com.google.android.material.slider.Slider
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.roundToInt

class MainActivity : AppCompatActivity() {

    private lateinit var statusDot: View
    private lateinit var statusText: TextView
    private lateinit var tvChip: TextView
    private lateinit var ipChip: TextView
    private lateinit var latencyChip: TextView
    private lateinit var lastTr: TextView
    private lateinit var lastEn: TextView
    private lateinit var startBtn: MaterialButton
    private lateinit var keyResult: TextView
    private lateinit var offlineText: TextView
    private lateinit var offlineBtn: MaterialButton
    private lateinit var modelInput: TextInputEditText
    private lateinit var chips: List<Chip>
    private lateinit var previewImage: ImageView
    private lateinit var rawText: TextView

    private val ui = Handler(Looper.getMainLooper())
    private val styleRunnable = Runnable { CaptureService.instance?.pushStyle() }

    private val projectionLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { res ->
            val data = res.data
            if (res.resultCode == Activity.RESULT_OK && data != null) {
                val i = Intent(this, CaptureService::class.java)
                    .setAction(CaptureService.ACTION_START)
                    .putExtra(CaptureService.EXTRA_CODE, res.resultCode)
                    .putExtra(CaptureService.EXTRA_DATA, data)
                ContextCompat.startForegroundService(this, i)
            } else {
                toast("Ekran izni verilmedi")
            }
        }

    private val notifLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Prefs.init(this)
        setContentView(R.layout.activity_main)

        statusDot = findViewById(R.id.statusDot)
        statusText = findViewById(R.id.statusText)
        tvChip = findViewById(R.id.tvChip)
        ipChip = findViewById(R.id.ipChip)
        latencyChip = findViewById(R.id.latencyChip)
        lastTr = findViewById(R.id.lastTr)
        lastEn = findViewById(R.id.lastEn)
        startBtn = findViewById(R.id.startBtn)
        keyResult = findViewById(R.id.keyResult)
        offlineText = findViewById(R.id.offlineText)
        offlineBtn = findViewById(R.id.offlineBtn)
        modelInput = findViewById(R.id.modelInput)
        previewImage = findViewById(R.id.previewImage)
        rawText = findViewById(R.id.rawText)

        setupStatus()
        setupTranslation()
        setupDubbing()
        setupRoi()
        setupTv()

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { AppState.status.collect { render(it) } }
                launch { AppState.preview.collect { bmp -> if (bmp != null) previewImage.setImageBitmap(bmp) } }
                launch { OfflineTranslator.state.collect { renderOffline(it) } }
            }
        }

        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            notifLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    override fun onResume() {
        super.onResume()
        AppState.update { it.copy(phoneIp = NetUtil.localIp()) }
        OfflineTranslator.checkDownloaded()
    }

    // ---------------------------------------------------------------- durum

    private fun setupStatus() {
        startBtn.setOnClickListener {
            if (AppState.status.value.running) stopCapture() else startCapture()
        }
        findViewById<MaterialButton>(R.id.testBtn).setOnClickListener {
            val s = CaptureService.instance
            if (s == null || !AppState.status.value.running) toast("Önce Başlat'a basın") else s.sendTest()
        }
    }

    private fun startCapture() {
        val geminiReady = Prefs.geminiEnabled && Prefs.geminiKey.isNotBlank()
        if (!geminiReady && OfflineTranslator.state.value != OfflineTranslator.ModelState.READY) {
            OfflineTranslator.download()
            toast("Gemini anahtarı yok: çevrimdışı Türkçe paketi indiriliyor")
        }
        try {
            val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            projectionLauncher.launch(mpm.createScreenCaptureIntent())
        } catch (e: Exception) {
            toast("Ekran yakalama başlatılamadı: ${e.message}")
        }
    }

    private fun stopCapture() {
        try {
            startService(Intent(this, CaptureService::class.java).setAction(CaptureService.ACTION_STOP))
        } catch (e: Exception) {
            CaptureService.instance?.stopSelf()
        }
    }

    private fun render(s: AppState.Status) {
        statusText.text = s.message
        val dotColor = when {
            !s.running -> R.color.muted
            s.tvClients > 0 -> R.color.green
            else -> R.color.yellow
        }
        statusDot.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, dotColor))
        tvChip.text = if (s.tvClients > 0) "📺 TV bağlı" else "📺 TV bekleniyor"
        ipChip.text = "📱 ${s.phoneIp}"
        latencyChip.text = if (s.latencyMs > 0) "⚡ ${s.latencyMs} ms · ${s.engine}" else "⚡ —"
        lastTr.text = s.lastTr.ifBlank { "Henüz altyazı yok" }
        lastEn.text = s.lastEn
        lastEn.visibility = if (s.lastEn.isBlank()) View.GONE else View.VISIBLE
        rawText.text = if (!s.running) {
            "Teşhis: çalışmıyor"
        } else {
            "Teşhis: ${s.frames} kare yakalandı · ${s.ocrRuns} kez okundu\nSon okunan yazı: " +
                s.rawText.ifBlank { "(henüz yazı bulunamadı)" }
        }

        startBtn.text = if (s.running) "Durdur" else "Başlat"
        val btnColor = if (s.running) R.color.surface2 else R.color.pink
        startBtn.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, btnColor))
    }

    // ---------------------------------------------------------------- çeviri

    private fun setupTranslation() {
        val geminiSwitch = findViewById<MaterialSwitch>(R.id.geminiSwitch)
        val keyInput = findViewById<TextInputEditText>(R.id.keyInput)

        geminiSwitch.isChecked = Prefs.geminiEnabled
        geminiSwitch.setOnCheckedChangeListener { _, checked -> Prefs.geminiEnabled = checked }

        keyInput.setText(Prefs.geminiKey)
        keyInput.doAfterTextChanged { Prefs.geminiKey = it?.toString().orEmpty() }

        chips = listOf(
            findViewById<Chip>(R.id.chipFast),
            findViewById<Chip>(R.id.chipSmart),
            findViewById<Chip>(R.id.chipBackup)
        )
        modelInput.setText(Prefs.geminiModel)
        syncChips(Prefs.geminiModel)
        modelInput.doAfterTextChanged {
            val m = it?.toString()?.trim().orEmpty()
            Prefs.geminiModel = m
            syncChips(m)
        }
        for (c in chips) {
            c.setOnClickListener {
                val model = c.tag as String
                modelInput.setText(model)
                modelInput.setSelection(model.length)
            }
        }

        findViewById<MaterialButton>(R.id.testKeyBtn).setOnClickListener {
            val key = Prefs.geminiKey
            if (key.isBlank()) {
                keyResult.text = "Önce anahtarı yapıştırın."
                return@setOnClickListener
            }
            keyResult.text = "Deneniyor…"
            lifecycleScope.launch {
                val r = withContext(Dispatchers.IO) {
                    runCatching {
                        GeminiClient.translate(
                            key, Prefs.geminiModel,
                            "Yo bro, the cops are right behind us, we gotta bounce!",
                            emptyList()
                        )
                    }
                }
                keyResult.text = r.fold(
                    onSuccess = { "✓ Çalışıyor: $it" },
                    onFailure = { "✗ ${Translator.explain(it)}" }
                )
            }
        }

        findViewById<MaterialButton>(R.id.getKeyBtn).setOnClickListener {
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://aistudio.google.com/apikey")))
            } catch (e: Exception) {
                toast("Tarayıcı açılamadı")
            }
        }

        offlineBtn.setOnClickListener { OfflineTranslator.download() }
    }

    private fun syncChips(model: String) {
        for (c in chips) {
            val match = c.tag == model
            if (c.isChecked != match) c.isChecked = match
        }
    }

    private fun renderOffline(state: OfflineTranslator.ModelState) {
        val (text, showBtn) = when (state) {
            OfflineTranslator.ModelState.READY -> "Çevrimdışı Türkçe paketi: hazır ✓" to false
            OfflineTranslator.ModelState.DOWNLOADING -> "Çevrimdışı Türkçe paketi indiriliyor…" to false
            OfflineTranslator.ModelState.FAILED -> "Paket indirilemedi. İnterneti kontrol edip tekrar deneyin." to true
            else -> "Çevrimdışı Türkçe paketi (yedek, ~30 MB) yüklü değil" to true
        }
        offlineText.text = text
        offlineBtn.visibility = if (showBtn) View.VISIBLE else View.GONE
    }

    // ---------------------------------------------------------------- dublaj

    private fun setupDubbing() {
        val dubSwitch = findViewById<MaterialSwitch>(R.id.dubSwitch)
        dubSwitch.isChecked = Prefs.dubbing
        dubSwitch.setOnCheckedChangeListener { _, checked -> Prefs.dubbing = checked }

        val rateLabel = findViewById<TextView>(R.id.rateLabel)
        val rateSlider = findViewById<Slider>(R.id.rateSlider)
        rateSlider.value = snap(Prefs.speechRate, 70, 160, 5).toFloat()
        rateLabel.text = "Konuşma hızı: %${rateSlider.value.toInt()}"
        rateSlider.addOnChangeListener { _, value, fromUser ->
            rateLabel.text = "Konuşma hızı: %${value.toInt()}"
            if (fromUser) Prefs.speechRate = value.toInt()
        }

        val toggle = findViewById<MaterialButtonToggleGroup>(R.id.voiceToggle)
        toggle.check(if (Prefs.voiceOnNotification) R.id.btnVoiceNotif else R.id.btnVoiceMedia)
        toggle.addOnButtonCheckedListener { _, id, isChecked ->
            if (isChecked) Prefs.voiceOnNotification = id == R.id.btnVoiceNotif
        }
    }

    // ---------------------------------------------------------------- altyazı bölgesi

    private fun setupRoi() {
        val label = findViewById<TextView>(R.id.roiLabel)
        val slider = findViewById<RangeSlider>(R.id.roiSlider)
        var top = snap(Prefs.roiTop, 30, 96, 1)
        var bottom = snap(Prefs.roiBottom, 34, 100, 1)
        if (bottom - top < 4) {
            bottom = (top + 10).coerceAtMost(100)
            top = (bottom - 10).coerceAtLeast(30)
        }
        slider.setMinSeparationValue(4f)
        slider.values = listOf(top.toFloat(), bottom.toFloat())
        label.text = roiText(top, bottom)
        slider.addOnChangeListener { s, _, fromUser ->
            val v = s.values
            if (v.size >= 2) {
                val t = v[0].roundToInt()
                val b = v[1].roundToInt()
                label.text = roiText(t, b)
                if (fromUser) {
                    Prefs.roiTop = t
                    Prefs.roiBottom = b
                }
            }
        }
    }

    private fun roiText(top: Int, bottom: Int) = "Okunan şerit: ekranın %$top – %$bottom arası (yukarıdan)"

    // ---------------------------------------------------------------- TV görünümü

    private fun setupTv() {
        bindSlider(R.id.fontSlider, R.id.fontLabel, 18, 48, 2, Prefs.tvFontSize, { "Yazı boyutu: $it" }) {
            Prefs.tvFontSize = it
        }
        bindSlider(R.id.ySlider, R.id.yLabel, 10, 250, 5, Prefs.tvYOffset, { "Alttan yükseklik: $it" }) {
            Prefs.tvYOffset = it
        }
        bindSlider(R.id.alphaSlider, R.id.alphaLabel, 0, 255, 5, Prefs.tvBgAlpha, { "Arka plan koyuluğu: %${it * 100 / 255}" }) {
            Prefs.tvBgAlpha = it
        }

        val enSwitch = findViewById<MaterialSwitch>(R.id.enSwitch)
        enSwitch.isChecked = Prefs.tvShowEn
        enSwitch.setOnCheckedChangeListener { _, checked ->
            Prefs.tvShowEn = checked
            scheduleStylePush()
        }

        findViewById<MaterialButton>(R.id.tvPreviewBtn).setOnClickListener {
            val s = CaptureService.instance
            if (s == null || !AppState.status.value.running) toast("Önce Başlat'a basın") else s.pushStyle()
        }
    }

    private fun bindSlider(
        sliderId: Int,
        labelId: Int,
        from: Int,
        to: Int,
        step: Int,
        current: Int,
        format: (Int) -> String,
        save: (Int) -> Unit
    ) {
        val slider = findViewById<Slider>(sliderId)
        val label = findViewById<TextView>(labelId)
        val v = snap(current, from, to, step)
        slider.value = v.toFloat()
        label.text = format(v)
        slider.addOnChangeListener { _, value, fromUser ->
            val iv = value.roundToInt()
            label.text = format(iv)
            if (fromUser) {
                save(iv)
                scheduleStylePush()
            }
        }
    }

    private fun scheduleStylePush() {
        ui.removeCallbacks(styleRunnable)
        ui.postDelayed(styleRunnable, 300)
    }

    // ---------------------------------------------------------------- yardımcılar

    private fun snap(value: Int, from: Int, to: Int, step: Int): Int {
        val c = value.coerceIn(from, to)
        val snapped = from + ((c - from) / step) * step
        return snapped.coerceIn(from, to)
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()

    override fun onDestroy() {
        ui.removeCallbacks(styleRunnable)
        super.onDestroy()
    }
}
