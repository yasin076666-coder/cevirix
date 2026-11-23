package com.bugra.altyazi.phone

import android.content.pm.ActivityInfo
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.launch

/** TV yokken altyazıyı bu telefonda tam ekran gösterir (yatay, ekran kapanmaz). */
class PhoneSubtitleActivity : ComponentActivity() {

    private lateinit var tr: TextView
    private lateinit var en: TextView
    private var size = 34f

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        size = getSharedPreferences("phone_sub", MODE_PRIVATE).getFloat("size", 34f)

        val root = FrameLayout(this).apply { setBackgroundColor(Color.parseColor("#050C20")) }
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(48, 24, 48, 24)
        }
        tr = TextView(this).apply {
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            typeface = android.graphics.Typeface.DEFAULT_BOLD
            setLineSpacing(0f, 1.15f)
        }
        en = TextView(this).apply {
            setTextColor(Color.parseColor("#8C9CC0"))
            gravity = Gravity.CENTER
            setPadding(0, 18, 0, 0)
        }
        col.addView(tr)
        col.addView(en)
        root.addView(col, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))

        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(16, 16, 16, 16)
        }
        fun btn(label: String, desc: String, onClick: () -> Unit) = TextView(this).apply {
            text = label
            contentDescription = desc
            setTextColor(Color.parseColor("#EEF4FF"))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            gravity = Gravity.CENTER
            minWidth = 120
            minHeight = 110
            background = GradientDrawable().apply {
                cornerRadius = 28f
                setColor(Color.parseColor("#15233F"))
            }
            setOnClickListener { onClick() }
        }
        val gap = { View(this).apply { layoutParams = LinearLayout.LayoutParams(16, 1) } }
        bar.addView(btn("A−", "Yazıyı küçült") { setSize(size - 3f) })
        bar.addView(gap())
        bar.addView(btn("A+", "Yazıyı büyüt") { setSize(size + 3f) })
        bar.addView(gap())
        bar.addView(btn("✕", "Kapat") { finish() })
        root.addView(bar, FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.TOP or Gravity.END))
        setContentView(root)
        applySize()

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                AppState.status.collect { s ->
                    tr.text = s.lastTr.ifBlank { "Oyunu açınca Türkçe altyazılar burada görünür." }
                    en.text = s.lastEn
                    en.visibility = if (s.lastEn.isBlank()) View.GONE else View.VISIBLE
                }
            }
        }
    }

    private fun setSize(v: Float) {
        size = v.coerceIn(18f, 72f)
        getSharedPreferences("phone_sub", MODE_PRIVATE).edit().putFloat("size", size).apply()
        applySize()
    }

    private fun applySize() {
        tr.setTextSize(TypedValue.COMPLEX_UNIT_SP, size)
        en.setTextSize(TypedValue.COMPLEX_UNIT_SP, size * 0.5f)
    }
}
