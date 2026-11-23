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
import com.metallic.chiaki.R
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

class CevirixActivity : AppCompatActivity() {

    companion object {
        private const val REMOTE_PLAY_PACKAGE = "com.playstation.remoteplay"
    }

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
    private val styleRunnable = Runnable { CevirixEngine.pushStyle() }

    private val projectionLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { res ->
            val data = res.data
            if (res.resultCode == Activity.RESULT_OK && data != null) {
                val i = Intent(this, CaptureService::class.java)
                    .setAction(CaptureService.ACTION_START)
                    .putExtra(CaptureService.EXTRA_CODE, res.resultCode)
                    .putExtra(CaptureService.EXTRA_DATA, data)
                ContextCompat.startForegroundService(this, i)
                // Servis başlasın, ardından PS Remote Play'i otomatik aç
                ui.postDelayed({ openRemotePlay() }, 900)
            } else {
                toast("Ekran izni verilmedi")
            }
        }

    private val notifLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Prefs.init(this)
        setContentView(R.layout.cx_main)

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

        setupPs5()
        setupStatus()
        // Sade ekran: eski "ekran okuma" ve "PS Remote Play'e geç" kaldırıldı
        startBtn.visibility = View.GONE
        findViewById<MaterialButton>(R.id.openRpBtn).visibility = View.GONE
        if (CaptureService.instance != null) stopCapture()
        // Çevirix açıldığı anda TV bağlansın (test düğmesi de hemen çalışır)
        CevirixEngine.acquire(this, "Hazır")
        engineHeld = true
        setupTranslation()
        setupDubbing()
        setupRoi()
        setupTv()
        setupNav()
        setupSteps()
        setupLive()
        setupNino()
        setupGta()

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch { AppState.status.collect { render(it) } }
                launch { AppState.preview.collect { bmp -> if (bmp != null) previewImage.setImageBitmap(bmp) } }
                launch { OfflineTranslator.state.collect { renderOffline(it) } }
                launch { AppState.liveFrame.collect { renderLive(it) } }
                launch { AppState.streaming.collect { renderStreaming(it) } }
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
        renderPsn()
        showLastCrash()
        AppState.update { it.copy(phoneIp = NetUtil.localIp()) }
        OfflineTranslator.checkDownloaded()
    }

    // ---------------------------------------------------------------- hata raporu

    private fun showLastCrash() {
        val text = App.takeLastCrash(this) ?: App.takeNativeCrash(this) ?: return
        val tv = TextView(this).apply {
            this.text = text
            textSize = 11f
            setTextIsSelectable(true)
            setPadding(40, 24, 40, 24)
        }
        val scroll = android.widget.ScrollView(this).apply { addView(tv) }
        com.google.android.material.dialog.MaterialAlertDialogBuilder(this)
            .setTitle("Son çökmenin ayrıntısı")
            .setMessage("Bu ekranın görüntüsünü gönderin, sorunu buna göre düzelteceğim.")
            .setView(scroll)
            .setPositiveButton("Kopyala") { _, _ ->
                val cm = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
                cm.setPrimaryClip(android.content.ClipData.newPlainText("cevirix-hata", text))
                toast("Hata metni kopyalandı")
            }
            .setNegativeButton("Kapat", null)
            .show()
    }

    // ---------------------------------------------------------------- dahili Remote Play

    private lateinit var psnStatus: TextView
    private lateinit var psnLoginBtn: MaterialButton

    private fun setupPs5() {
        psnStatus = findViewById(R.id.psnStatus)
        psnLoginBtn = findViewById(R.id.psnLoginBtn)
        psnLoginBtn.setOnClickListener {
            startActivity(Intent(this, PsnLoginActivity::class.java))
        }
        findViewById<MaterialButton>(R.id.ps5Btn).setOnClickListener {
            if (StreamCapture.current != null) {
                openFullScreen()
                return@setOnClickListener
            }
            if (CaptureService.instance != null) stopCapture()
            try {
                App.markPs5Opening(this)
                startActivity(Intent(this, com.metallic.chiaki.main.MainActivity::class.java))
            } catch (e: Exception) {
                toast("PS5 ekranı açılamadı: ${e.message}")
            }
        }
        val sw = findViewById<MaterialSwitch>(R.id.streamTranslateSwitch)
        sw.isChecked = Prefs.streamTranslate
        sw.setOnCheckedChangeListener { _, checked -> Prefs.streamTranslate = checked }
        val bg = findViewById<MaterialSwitch>(R.id.backgroundSwitch)
        bg.isChecked = Prefs.backgroundStream
        bg.setOnCheckedChangeListener { _, checked -> Prefs.backgroundStream = checked }
        renderPsn()
    }

    private fun renderPsn() {
        if (!::psnStatus.isInitialized) return
        val id = Prefs.psnAccountId
        if (id.isBlank()) {
            psnStatus.text = "Henüz giriş yapılmadı."
            psnLoginBtn.text = "PlayStation ile giriş yap"
        } else {
            psnStatus.text = "Giriş yapıldı. Hesap kimliği: $id"
            psnLoginBtn.text = "Hesabı değiştir"
        }
        renderSteps(AppState.status.value)
    }

    // ---------------------------------------------------------------- sekmeler

    private lateinit var pages: Map<Int, View>

    private fun setupNav() {
        pages = mapOf(
            R.id.navPlay to findViewById(R.id.pagePlay),
            R.id.navTranslate to findViewById(R.id.pageTranslate),
            R.id.navTv to findViewById(R.id.pageTv),
            R.id.navMore to findViewById(R.id.pageMore)
        )
        val nav = findViewById<com.google.android.material.bottomnavigation.BottomNavigationView>(R.id.bottomNav)
        nav.setOnItemSelectedListener { item ->
            showPage(item.itemId)
            true
        }
        nav.setOnItemReselectedListener { item ->
            (pages[item.itemId] as? androidx.core.widget.NestedScrollView)?.smoothScrollTo(0, 0)
        }
    }

    private fun showPage(id: Int) {
        for ((k, v) in pages) {
            if (k == id) {
                if (v.visibility != View.VISIBLE) {
                    v.alpha = 0f
                    v.visibility = View.VISIBLE
                    v.animate().alpha(1f).setDuration(160).start()
                }
            } else {
                v.visibility = View.GONE
            }
        }
    }

    private fun goTo(navId: Int) {
        findViewById<com.google.android.material.bottomnavigation.BottomNavigationView>(R.id.bottomNav).selectedItemId = navId
    }

    // ---------------------------------------------------------------- bağlantı adımları

    private fun setupSteps() {
        findViewById<View>(R.id.stepAccount).setOnClickListener {
            startActivity(Intent(this, PsnLoginActivity::class.java))
        }
        findViewById<View>(R.id.stepPs5).setOnClickListener {
            findViewById<MaterialButton>(R.id.ps5Btn).performClick()
        }
        findViewById<View>(R.id.stepTv).setOnClickListener {
            if (AppState.status.value.tvClients > 0) {
                if (!CevirixEngine.sendTest()) toast("Test altyazısı gönderilemedi")
                else toast("TV'ye test altyazısı gönderildi")
            } else {
                toast("TV'de Çevirix TV uygulamasını aç. Telefon ve TV aynı Wi-Fi'de olmalı.")
            }
        }
        renderSteps(AppState.status.value)
    }

    private fun renderSteps(s: AppState.Status) {
        if (!::psnStatus.isInitialized) return
        val accountOk = Prefs.psnAccountId.isNotBlank()
        val ps5Ok = s.copyOk > 0 && s.source.contains("Remote")
        val tvOk = s.tvClients > 0
        paintStep(R.id.stepAccountIcon, R.id.stepAccountState, accountOk, "Bağlı", "Giriş yap")
        paintStep(R.id.stepPs5Icon, R.id.stepPs5State, ps5Ok, "Okunuyor", "Bağlan")
        paintStep(R.id.stepTvIcon, R.id.stepTvState, tvOk, "Bağlı", "Bekleniyor")
    }

    private fun paintStep(iconId: Int, stateId: Int, ok: Boolean, okText: String, waitText: String) {
        val icon = findViewById<ImageView>(iconId)
        val state = findViewById<TextView>(stateId)
        val color = ContextCompat.getColor(this, if (ok) R.color.cx_cyan else R.color.cx_muted)
        icon.imageTintList = ColorStateList.valueOf(color)
        state.text = if (ok) "✓ $okText" else waitText
        state.setTextColor(color)
    }

    // ---------------------------------------------------------------- durum

    private fun setupStatus() {
        startBtn.setOnClickListener {
            if (CaptureService.instance != null) stopCapture() else startCapture()
        }
        findViewById<MaterialButton>(R.id.openRpBtn).setOnClickListener { openRemotePlay() }
        findViewById<MaterialButton>(R.id.testBtn).setOnClickListener {
            if (!CevirixEngine.sendTest()) toast("Önce PS5'e bağlanın veya ekran okuma modunu başlatın")
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

    private fun openRemotePlay() {
        val launch = packageManager.getLaunchIntentForPackage(REMOTE_PLAY_PACKAGE)
        if (launch == null) {
            toast("PS Remote Play yüklü değil. Önce onu kurun.")
            return
        }
        try {
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(launch)
        } catch (e: Exception) {
            toast("PS Remote Play açılamadı: ${e.message}")
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
            !s.running -> R.color.cx_muted
            s.tvClients > 0 -> R.color.cx_green
            else -> R.color.cx_yellow
        }
        statusDot.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, dotColor))
        tvChip.text = if (s.tvClients > 0) "TV bağlı" else "TV bekleniyor"
        ipChip.text = "Telefon: ${s.phoneIp}"
        latencyChip.text = if (s.latencyMs > 0) "%.1f sn · %s".format(java.util.Locale("tr"), s.latencyMs / 1000.0, s.engine) else ""
        lastTr.text = s.lastTr
        lastTr.visibility = if (s.lastTr.isBlank()) View.GONE else View.VISIBLE
        renderSteps(s)
        renderNino()
        lastEn.text = s.lastEn
        lastEn.visibility = if (s.lastEn.isBlank() || !Prefs.tvShowEn || s.lastTr.isBlank()) View.GONE else View.VISIBLE
        rawText.text = if (s.frames == 0L && s.copyOk == 0L && s.copyFail == 0L) {
            "Teşhis: henüz okuma yapılmadı (PS5'e bağlanıp oyunu açın)"
        } else {
            val copy = if (s.copyOk + s.copyFail > 0) " · görüntü kopyalama: ${s.copyOk} başarılı, ${s.copyFail} hata" +
                (if (s.copyFail > 0) " (kod ${s.copyErr})" else "") else ""
            "Teşhis (${s.source.ifBlank { "-" }}): ${s.frames} kare · ${s.ocrRuns} kez okundu$copy\nSon okunan yazı: " +
                s.rawText.ifBlank { "(henüz yazı bulunamadı)" }
        }

        val capturing = CaptureService.instance != null && s.running
        startBtn.text = if (capturing) "Ekran okumayı durdur" else "Ekran okuma modunu başlat"
        val btnColor = if (capturing) R.color.cx_surface2 else R.color.cx_surface2
        startBtn.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, btnColor))
    }

    // ---------------------------------------------------------------- çeviri

    private fun setupTranslation() {
        val geminiSwitch = findViewById<MaterialSwitch>(R.id.geminiSwitch)
        val keyInput = findViewById<TextInputEditText>(R.id.keyInput)

        geminiSwitch.isChecked = Prefs.geminiEnabled
        geminiSwitch.setOnCheckedChangeListener { _, checked -> Prefs.geminiEnabled = checked }
        val instantSwitch = findViewById<MaterialSwitch>(R.id.instantSwitch)
        instantSwitch.isChecked = Prefs.instantTranslate
        instantSwitch.setOnCheckedChangeListener { _, checked -> Prefs.instantTranslate = checked }

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
        val slang = OfflineSlang.size
        offlineText.text = if (slang > 0) "$text\nSokak sözlüğü: $slang kalıp ✓" else text
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
            updateTvSample()
            scheduleStylePush()
        }

        updateTvSample()

        findViewById<MaterialButton>(R.id.tvPreviewBtn).setOnClickListener {
            if (!CevirixEngine.pushStyle()) toast("Önce PS5'e bağlanın veya ekran okuma modunu başlatın")
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
                updateTvSample()
                scheduleStylePush()
            }
        }
    }

    /** TV sekmesindeki örnek ekranı ve ana ekrandaki canlı pencereyi ayarlara göre günceller. */
    private fun updateTvSample() {
        styleSubtitle(
            findViewById(R.id.tvSampleBox), findViewById(R.id.tvSampleGroup),
            findViewById(R.id.tvSample), findViewById(R.id.tvSampleEn), alwaysShowEn = false
        )
        styleSubtitle(findViewById(R.id.liveBox), findViewById(R.id.liveSubGroup), lastTr, lastEn, alwaysShowEn = null)
    }

    /**
     * Altyazıyı TV'deki oranlarla küçültüp kutuya yerleştirir.
     * TV ekranı ~540dp (1080 piksel) yüksekliğinde kabul edilir.
     */
    private fun styleSubtitle(box: View, group: View, tr: TextView, en: TextView, alwaysShowEn: Boolean?) {
        val bg = android.graphics.drawable.GradientDrawable().apply {
            cornerRadius = 6f * resources.displayMetrics.density
            setColor(android.graphics.Color.argb(Prefs.tvBgAlpha.coerceIn(0, 255), 0, 0, 0))
        }
        tr.background = bg
        if (alwaysShowEn != null) en.visibility = if (Prefs.tvShowEn) View.VISIBLE else View.GONE
        box.post {
            // Kutuyu 16:9 yap (TV gibi)
            val w = box.width
            if (w > 0) {
                val want = w * 9 / 16
                val blp = box.layoutParams
                if (blp.height != want) {
                    blp.height = want
                    box.layoutParams = blp
                }
            }
            val h = (if (w > 0) w * 9 / 16 else box.height).toFloat()
            if (h <= 0f) return@post
            tr.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX, Prefs.tvFontSize * h / 540f)
            en.setTextSize(android.util.TypedValue.COMPLEX_UNIT_PX, Prefs.tvFontSize * 0.55f * h / 540f)
            val lp = group.layoutParams as android.widget.FrameLayout.LayoutParams
            lp.bottomMargin = (Prefs.tvYOffset * h / 1080f).toInt().coerceIn(0, (h * 0.8f).toInt())
            group.layoutParams = lp
        }
    }

    // ---------------------------------------------------------------- canlı pencere

    private lateinit var liveFrameView: ImageView
    private lateinit var liveHint: TextView

    private fun setupLive() {
        val box = findViewById<View>(R.id.liveBox)
        box.clipToOutline = true
        liveFrameView = findViewById(R.id.liveFrame)
        liveHint = findViewById(R.id.liveHint)
        box.setOnClickListener {
            if (StreamCapture.current != null) openFullScreen()
            else findViewById<MaterialButton>(R.id.ps5Btn).performClick()
        }
        findViewById<MaterialButton>(R.id.stopStreamBtn).setOnClickListener {
            StreamCapture.current?.finishStream()
        }
        val muteBtn = findViewById<MaterialButton>(R.id.muteBtn)
        val muteSwitch = findViewById<MaterialSwitch>(R.id.muteSwitch)
        muteSwitch.isChecked = Prefs.psMuted
        renderMute(muteBtn)
        muteBtn.setOnClickListener {
            PsAudio.set(!Prefs.psMuted)
            muteSwitch.isChecked = Prefs.psMuted
            renderMute(muteBtn)
            toast(if (Prefs.psMuted) "PS5 sesi kapatıldı" else "PS5 sesi açıldı")
        }
        muteSwitch.setOnCheckedChangeListener { _, checked ->
            if (checked != Prefs.psMuted) {
                PsAudio.set(checked)
                renderMute(muteBtn)
            }
        }
        findViewById<MaterialButton>(R.id.fontDownBtn).setOnClickListener { nudgeFont(-2) }
        findViewById<MaterialButton>(R.id.fontUpBtn).setOnClickListener { nudgeFont(+2) }
        findViewById<MaterialButton>(R.id.posDownBtn).setOnClickListener { nudgeY(-10) }
        findViewById<MaterialButton>(R.id.posUpBtn).setOnClickListener { nudgeY(+10) }
        updateTvSample()
    }

    private fun setupGta() {
        val sw = findViewById<MaterialSwitch>(R.id.gtaSwitch)
        sw.isChecked = Prefs.gtaExtras
        sw.setOnCheckedChangeListener { _, checked ->
            Prefs.gtaExtras = checked
            if (checked) {
                if (StreamCapture.current != null) com.bugra.altyazi.phone.gta.GtaBridge.start(this)
            } else {
                com.bugra.altyazi.phone.gta.GtaBridge.stop()
                CevirixEngine.sendScreenClear()
            }
        }
    }

    private fun setupNino() {
        val sw = findViewById<MaterialSwitch>(R.id.ninoSwitch)
        sw.isChecked = Prefs.ninoTv
        sw.setOnCheckedChangeListener { _, checked ->
            Prefs.ninoTv = checked
            if (checked) NinoBridge.start(this) else NinoBridge.stop()
            renderNino()
        }
        renderNino()
    }

    private fun renderNino() {
        val t = findViewById<TextView>(R.id.ninoStatus) ?: return
        val names = NinoBridge.displayNames
        val tv = when {
            names.isEmpty() -> "Nino TV bekleniyor. TV'de Nino TV'yi aç; telefon ve TV aynı Wi-Fi'de olsun."
            else -> "Bağlı Nino TV: " + names.joinToString(", ")
        }
        t.text = if (!Prefs.ninoTv) "" else
            "$tv\n\niPhone, iPad ya da Windows'ta altyazı: tarayıcıda ${WebSubtitlePage.url} adresini aç."
    }

    private fun renderMute(btn: MaterialButton) {
        btn.setIconResource(if (Prefs.psMuted) R.drawable.cx_i_vol_off else R.drawable.cx_i_vol_on)
        btn.backgroundTintList = ColorStateList.valueOf(
            if (Prefs.psMuted) ContextCompat.getColor(this, R.color.cx_pink) else android.graphics.Color.argb(179, 0, 0, 0)
        )
    }

    private fun nudgeFont(d: Int) {
        val v = (Prefs.tvFontSize + d).coerceIn(18, 48)
        Prefs.tvFontSize = v
        findViewById<Slider>(R.id.fontSlider).value = snap(v, 18, 48, 2).toFloat()
        updateTvSample()
        scheduleStylePush()
    }

    private fun nudgeY(d: Int) {
        val v = (Prefs.tvYOffset + d).coerceIn(10, 250)
        Prefs.tvYOffset = v
        findViewById<Slider>(R.id.ySlider).value = snap(v, 10, 250, 5).toFloat()
        updateTvSample()
        scheduleStylePush()
    }

    private fun renderLive(bmp: android.graphics.Bitmap?) {
        if (!::liveFrameView.isInitialized) return
        liveFrameView.setImageBitmap(bmp)
        liveHint.visibility = if (bmp == null) View.VISIBLE else View.GONE
    }

    private fun renderStreaming(on: Boolean) {
        val btn = findViewById<MaterialButton>(R.id.ps5Btn)
        btn.text = if (on) "Tam ekrana geç" else "Oyna"
        findViewById<TextView>(R.id.playHint).text = if (on)
            "Oyun açık. Telefonda kumanda kullanacaksan tam ekrana geç."
        else
            "PS5'e bağlanır, altyazıyı okuyup TV'ye Türkçe gönderir."
        findViewById<View>(R.id.stopStreamBtn).visibility = if (on) View.VISIBLE else View.GONE
        if (!on) liveHint.text = "Oyna'ya bas. Oyun görüntüsü burada, TV'deki gibi görünecek."
        else if (AppState.liveFrame.value == null) liveHint.text = "Oyun ekranı açık. Küçük pencereye almak için oradaki üst kutuya dokun."
    }

    private fun openFullScreen() {
        try {
            startActivity(
                Intent(this, com.metallic.chiaki.stream.StreamActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
            )
        } catch (e: Exception) {
            toast("Oyun ekranı açılamadı")
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

    private var engineHeld = false

    override fun onDestroy() {
        if (engineHeld) {
            engineHeld = false
            CevirixEngine.release()
        }
        ui.removeCallbacks(styleRunnable)
        super.onDestroy()
    }
}
