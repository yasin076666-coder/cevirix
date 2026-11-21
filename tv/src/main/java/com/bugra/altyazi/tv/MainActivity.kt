package com.bugra.altyazi.tv

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

/** TV kumandasıyla kullanılan ayar ekranı. */
class MainActivity : Activity() {

    private lateinit var permissionBadge: TextView
    private lateinit var statusLabel: TextView
    private lateinit var ipInput: EditText
    private lateinit var autoBtn: Button

    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val text = intent?.getStringExtra(SubtitleOverlayService.EXTRA_STATUS_TEXT) ?: return
            val connected = intent.getBooleanExtra(SubtitleOverlayService.EXTRA_CONNECTED, false)
            showStatus(text, connected)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = getSharedPreferences(SubtitleOverlayService.PREFS, MODE_PRIVATE)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setBackgroundColor(Color.parseColor("#040A1A"))
            setPadding(96, 28, 96, 40)
        }

        val title = ImageView(this).apply {
            setImageResource(R.drawable.logo)
            adjustViewBounds = true
            scaleType = ImageView.ScaleType.FIT_CENTER
            contentDescription = getString(R.string.app_name)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                (resources.displayMetrics.heightPixels * 0.26f).toInt()
            )
        }
        val subtitle = TextView(this).apply {
            text = "PS5 oyunlarının Türkçe altyazısı, HDMI görüntüsünün üstünde"
            textSize = 16f
            setTextColor(Color.parseColor("#FF8A3D"))
            setPadding(0, 6, 0, 24)
        }

        permissionBadge = TextView(this).apply {
            textSize = 17f
            setPadding(28, 12, 28, 12)
        }

        statusLabel = TextView(this).apply {
            textSize = 19f
            setPadding(0, 22, 0, 24)
        }

        val ipCaption = TextView(this).apply {
            text = "Telefon IP adresi (boş bırakın, otomatik bulunur):"
            textSize = 16f
            setTextColor(Color.parseColor("#C8D0E0"))
            setPadding(0, 0, 0, 10)
        }

        ipInput = EditText(this).apply {
            hint = "Otomatik"
            setText(prefs.getString("phone_ip", ""))
            textSize = 22f
            inputType = InputType.TYPE_CLASS_TEXT
            setSingleLine(true)
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
            setPadding(28, 18, 28, 18)
            background = card("#1C2436", "#FF2E88")
            layoutParams = LinearLayout.LayoutParams(700, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = 28
            }
        }

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }

        val startBtn = tvButton("Başlat", "#E11D74") {
            if (!hasOverlayPermission()) {
                Toast.makeText(this, "Önce ekran üstü izni verilmeli (kurulum rehberi, TV adımı).", Toast.LENGTH_LONG).show()
                openOverlaySettings()
                return@tvButton
            }
            prefs.edit().putString("phone_ip", ipInput.text.toString().trim()).apply()
            startOverlayService(SubtitleOverlayService.ACTION_RECONNECT)
            Toast.makeText(this, "Hazır! Şimdi PS5'in HDMI girişine geçebilirsiniz.", Toast.LENGTH_LONG).show()
        }
        val testBtn = tvButton("Test yazısı", "#2563EB") {
            if (!hasOverlayPermission()) {
                Toast.makeText(this, "Ekran üstü izni yok.", Toast.LENGTH_LONG).show()
                return@tvButton
            }
            startOverlayService(SubtitleOverlayService.ACTION_TEST)
        }
        val stopBtn = tvButton("Durdur", "#334155") {
            stopService(Intent(this, SubtitleOverlayService::class.java))
            showStatus("Durduruldu", false)
        }
        row.addView(startBtn)
        row.addView(testBtn)
        row.addView(stopBtn)

        autoBtn = tvButton("", "#1C2436") {
            val now = !prefs.getBoolean("auto_start", true)
            prefs.edit().putBoolean("auto_start", now).apply()
            updateAutoBtn(now)
        }.apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = 26 }
        }
        updateAutoBtn(prefs.getBoolean("auto_start", true))

        val hint = TextView(this).apply {
            text = "Telefon ve TV aynı Wi-Fi ağında olmalı. Başlat'tan sonra kumandayla PS5'in HDMI girişine geçin; altyazılar oyunun üstünde belirir. Bağlantı koparsa kendiliğinden yeniden bağlanır."
            textSize = 15f
            gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#8E9AB3"))
            setPadding(40, 30, 40, 0)
        }

        root.addView(title)
        root.addView(subtitle)
        root.addView(permissionBadge)
        root.addView(statusLabel)
        root.addView(ipCaption)
        root.addView(ipInput)
        root.addView(row)
        root.addView(autoBtn)
        root.addView(hint)
        setContentView(root)
        startBtn.requestFocus()
    }

    override fun onResume() {
        super.onResume()
        updatePermissionBadge()
        showStatus(SubtitleOverlayService.lastStatus, SubtitleOverlayService.lastConnected)
        val filter = IntentFilter(SubtitleOverlayService.ACTION_STATUS)
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(statusReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(statusReceiver, filter)
        }
        // İzin varsa ve servis çalışmıyorsa kendiliğinden başlat
        val prefs = getSharedPreferences(SubtitleOverlayService.PREFS, MODE_PRIVATE)
        if (hasOverlayPermission() && !SubtitleOverlayService.isRunning && prefs.getBoolean("auto_start", true)) {
            startOverlayService(null)
        }
    }

    override fun onPause() {
        try { unregisterReceiver(statusReceiver) } catch (e: Exception) { }
        super.onPause()
    }

    private fun startOverlayService(action: String?) {
        val i = Intent(this, SubtitleOverlayService::class.java)
        if (action != null) i.action = action
        try {
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(i) else startService(i)
        } catch (e: Exception) {
            Toast.makeText(this, "Servis başlatılamadı: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun hasOverlayPermission(): Boolean =
        Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(this)

    private fun openOverlaySettings() {
        try {
            startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
        } catch (e: Exception) {
            // Android TV'lerin çoğunda bu ekran yok; ADB komutu gerekir
        }
    }

    private fun showStatus(text: String, connected: Boolean) {
        statusLabel.text = "Durum: $text"
        statusLabel.setTextColor(Color.parseColor(if (connected) "#34D399" else "#FBBF24"))
    }

    private fun updatePermissionBadge() {
        val ok = hasOverlayPermission()
        permissionBadge.text = if (ok) "Ekran üstü izni: VAR ✓" else "Ekran üstü izni: YOK (kurulum rehberine bakın)"
        permissionBadge.setTextColor(Color.WHITE)
        permissionBadge.background = card(if (ok) "#14532D" else "#7F1D1D", if (ok) "#22C55E" else "#EF4444")
    }

    private fun updateAutoBtn(on: Boolean) {
        autoBtn.text = if (on) "TV açılınca otomatik başlat: AÇIK" else "TV açılınca otomatik başlat: KAPALI"
    }

    private fun tvButton(label: String, bgHex: String, onClick: () -> Unit): Button =
        Button(this).apply {
            text = label
            textSize = 18f
            isAllCaps = false
            setTextColor(Color.WHITE)
            setPadding(40, 20, 40, 20)
            background = card(bgHex, "#334155")
            isFocusable = true
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { setMargins(14, 0, 14, 0) }
            setOnFocusChangeListener { v: View, hasFocus: Boolean ->
                v.background = card(bgHex, if (hasFocus) "#FFFFFF" else "#334155")
                v.scaleX = if (hasFocus) 1.07f else 1f
                v.scaleY = if (hasFocus) 1.07f else 1f
            }
            setOnClickListener { onClick() }
        }

    private fun card(fill: String, stroke: String) = GradientDrawable().apply {
        shape = GradientDrawable.RECTANGLE
        cornerRadius = 16f
        setColor(Color.parseColor(fill))
        setStroke(3, Color.parseColor(stroke))
    }
}
