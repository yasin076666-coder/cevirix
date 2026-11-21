package com.bugra.altyazi.phone

import android.graphics.Bitmap
import android.graphics.SurfaceTexture
import android.opengl.EGL14
import android.opengl.EGLConfig
import android.opengl.EGLContext
import android.opengl.EGLDisplay
import android.opengl.EGLSurface
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.os.Handler
import android.os.HandlerThread
import android.view.Surface
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Arka plan görüntü alıcısı.
 * Uygulama arka plana geçince PS5 görüntüsü ekrandaki yüzey yerine buradaki
 * görünmez yüzeye (SurfaceTexture) akar; kareler GPU'da okunup altyazı aranır.
 * Böylece telefon başka işler için kullanılırken çeviri devam eder.
 */
object BgFrames {

    /** Kod çözücü şu an bu görünmez yüzeye mi yazıyor? */
    @Volatile var inUse = false
    @Volatile var frames = 0L
        private set

    @Volatile private var ready = false
    val isReady: Boolean get() = ready
    private var thread: HandlerThread? = null
    private var handler: Handler? = null

    private var display: EGLDisplay = EGL14.EGL_NO_DISPLAY
    private var context: EGLContext = EGL14.EGL_NO_CONTEXT
    private var pbuffer: EGLSurface = EGL14.EGL_NO_SURFACE
    private var oesTex = 0
    private var program = 0
    private var fbo = 0
    private var fboTex = 0
    private var fboW = 0
    private var fboH = 0
    private var st: SurfaceTexture? = null
    private var surface: Surface? = null
    @Volatile private var hasFrame = false
    private val mtx = FloatArray(16)
    private var readBuf: ByteBuffer? = null

    private val quad: FloatBuffer = floatArrayOf(
        // x, y, u, v  (v ters: okunan satır 0 = resmin üstü)
        -1f, -1f, 0f, 1f,
        1f, -1f, 1f, 1f,
        -1f, 1f, 0f, 0f,
        1f, 1f, 1f, 0f
    ).let {
        ByteBuffer.allocateDirect(it.size * 4).order(ByteOrder.nativeOrder()).asFloatBuffer().apply { put(it); position(0) }
    }

    private val VS = """
        attribute vec4 aPos;
        attribute vec4 aTex;
        uniform mat4 uTex;
        varying vec2 vTex;
        void main() {
            gl_Position = aPos;
            vTex = (uTex * aTex).xy;
        }
    """.trimIndent()
    private val FS = """
        #extension GL_OES_EGL_image_external : require
        precision mediump float;
        varying vec2 vTex;
        uniform samplerExternalOES sTex;
        void main() {
            gl_FragColor = vec4(texture2D(sTex, vTex).rgb, 1.0);
        }
    """.trimIndent()

    /** Görünmez yüzeyi hazırla (akış başlarken bir kez). */
    @Synchronized
    fun prepare(): Boolean {
        if (ready) return true
        val t = HandlerThread("cevirix-gl").apply { start() }
        val h = Handler(t.looper)
        val latch = CountDownLatch(1)
        var ok = false
        h.post {
            ok = try { initGl(h) } catch (e: Throwable) { false }
            latch.countDown()
        }
        latch.await(3, TimeUnit.SECONDS)
        if (!ok) {
            h.post { try { releaseGl() } catch (e: Throwable) { } }
            t.quitSafely()
            return false
        }
        thread = t
        handler = h
        ready = true
        return true
    }

    /** Ekrandaki yüzey kapanırken çağrılır: arka plan açıksa görüntüyü buraya al. */
    fun takeoverSurface(): Surface? {
        if (!ready || !Prefs.backgroundStream || !keepAliveWanted) return null
        val s = surface ?: return null
        inUse = true
        hasFrame = false
        return s
    }

    /** Akış ekranı kapanmıyorsa (sadece arka plana geçiyorsa) true. */
    @Volatile var keepAliveWanted = false

    /** Son kareyi [fw]x[fh] boyutunda [into] resmine çizer. Çağıran iş parçacığını bekletir. */
    fun grab(into: Bitmap): Boolean {
        val h = handler ?: return false
        if (!ready || !hasFrame) return false
        val latch = CountDownLatch(1)
        var ok = false
        h.post {
            ok = try { draw(into) } catch (e: Throwable) { false }
            latch.countDown()
        }
        return latch.await(800, TimeUnit.MILLISECONDS) && ok
    }

    @Synchronized
    fun release() {
        ready = false
        inUse = false
        val h = handler
        val t = thread
        handler = null
        thread = null
        if (h != null) {
            val latch = CountDownLatch(1)
            h.post {
                try { releaseGl() } catch (e: Throwable) { }
                latch.countDown()
            }
            latch.await(1, TimeUnit.SECONDS)
        }
        t?.quitSafely()
    }

    // ---------------------------------------------------------------- GL

    private fun initGl(h: Handler): Boolean {
        display = EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY)
        if (display == EGL14.EGL_NO_DISPLAY) return false
        val ver = IntArray(2)
        if (!EGL14.eglInitialize(display, ver, 0, ver, 1)) return false
        val attribs = intArrayOf(
            EGL14.EGL_RED_SIZE, 8, EGL14.EGL_GREEN_SIZE, 8, EGL14.EGL_BLUE_SIZE, 8, EGL14.EGL_ALPHA_SIZE, 8,
            EGL14.EGL_RENDERABLE_TYPE, EGL14.EGL_OPENGL_ES2_BIT,
            EGL14.EGL_SURFACE_TYPE, EGL14.EGL_PBUFFER_BIT,
            EGL14.EGL_NONE
        )
        val configs = arrayOfNulls<EGLConfig>(1)
        val num = IntArray(1)
        if (!EGL14.eglChooseConfig(display, attribs, 0, configs, 0, 1, num, 0) || num[0] == 0) return false
        val cfg = configs[0] ?: return false
        context = EGL14.eglCreateContext(
            display, cfg, EGL14.EGL_NO_CONTEXT,
            intArrayOf(EGL14.EGL_CONTEXT_CLIENT_VERSION, 2, EGL14.EGL_NONE), 0
        )
        if (context == EGL14.EGL_NO_CONTEXT) return false
        pbuffer = EGL14.eglCreatePbufferSurface(display, cfg, intArrayOf(EGL14.EGL_WIDTH, 1, EGL14.EGL_HEIGHT, 1, EGL14.EGL_NONE), 0)
        if (pbuffer == EGL14.EGL_NO_SURFACE) return false
        if (!EGL14.eglMakeCurrent(display, pbuffer, pbuffer, context)) return false

        val tex = IntArray(1)
        GLES20.glGenTextures(1, tex, 0)
        oesTex = tex[0]
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, oesTex)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)

        program = buildProgram()
        if (program == 0) return false

        val texture = SurfaceTexture(oesTex)
        texture.setDefaultBufferSize(1920, 1080)
        texture.setOnFrameAvailableListener({
            // Kareyi hemen tüket: tüketilmezse kod çözücü bekler.
            try {
                EGL14.eglMakeCurrent(display, pbuffer, pbuffer, context)
                st?.updateTexImage()
                frames++
                hasFrame = true
            } catch (e: Throwable) { }
        }, h)
        st = texture
        surface = Surface(texture)
        return true
    }

    private fun buildProgram(): Int {
        fun shader(type: Int, src: String): Int {
            val s = GLES20.glCreateShader(type)
            GLES20.glShaderSource(s, src)
            GLES20.glCompileShader(s)
            val st = IntArray(1)
            GLES20.glGetShaderiv(s, GLES20.GL_COMPILE_STATUS, st, 0)
            if (st[0] == 0) { GLES20.glDeleteShader(s); return 0 }
            return s
        }
        val v = shader(GLES20.GL_VERTEX_SHADER, VS)
        val f = shader(GLES20.GL_FRAGMENT_SHADER, FS)
        if (v == 0 || f == 0) return 0
        val p = GLES20.glCreateProgram()
        GLES20.glAttachShader(p, v)
        GLES20.glAttachShader(p, f)
        GLES20.glLinkProgram(p)
        val st = IntArray(1)
        GLES20.glGetProgramiv(p, GLES20.GL_LINK_STATUS, st, 0)
        return if (st[0] == 0) { GLES20.glDeleteProgram(p); 0 } else p
    }

    private fun ensureFbo(w: Int, h: Int) {
        if (fbo != 0 && fboW == w && fboH == h) return
        if (fbo != 0) {
            GLES20.glDeleteFramebuffers(1, intArrayOf(fbo), 0)
            GLES20.glDeleteTextures(1, intArrayOf(fboTex), 0)
        }
        val t = IntArray(1)
        GLES20.glGenTextures(1, t, 0)
        fboTex = t[0]
        GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, fboTex)
        GLES20.glTexImage2D(GLES20.GL_TEXTURE_2D, 0, GLES20.GL_RGBA, w, h, 0, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, null)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        val f = IntArray(1)
        GLES20.glGenFramebuffers(1, f, 0)
        fbo = f[0]
        GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER, fbo)
        GLES20.glFramebufferTexture2D(GLES20.GL_FRAMEBUFFER, GLES20.GL_COLOR_ATTACHMENT0, GLES20.GL_TEXTURE_2D, fboTex, 0)
        fboW = w
        fboH = h
        readBuf = ByteBuffer.allocateDirect(w * h * 4).order(ByteOrder.nativeOrder())
    }

    private fun draw(into: Bitmap): Boolean {
        val texture = st ?: return false
        EGL14.eglMakeCurrent(display, pbuffer, pbuffer, context)
        val w = into.width
        val h = into.height
        ensureFbo(w, h)
        GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER, fbo)
        GLES20.glViewport(0, 0, w, h)
        GLES20.glUseProgram(program)
        texture.getTransformMatrix(mtx)

        val aPos = GLES20.glGetAttribLocation(program, "aPos")
        val aTex = GLES20.glGetAttribLocation(program, "aTex")
        quad.position(0)
        GLES20.glVertexAttribPointer(aPos, 2, GLES20.GL_FLOAT, false, 16, quad)
        GLES20.glEnableVertexAttribArray(aPos)
        quad.position(2)
        GLES20.glVertexAttribPointer(aTex, 2, GLES20.GL_FLOAT, false, 16, quad)
        GLES20.glEnableVertexAttribArray(aTex)
        GLES20.glUniformMatrix4fv(GLES20.glGetUniformLocation(program, "uTex"), 1, false, mtx, 0)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, oesTex)
        GLES20.glUniform1i(GLES20.glGetUniformLocation(program, "sTex"), 0)
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)

        val buf = readBuf ?: return false
        buf.position(0)
        GLES20.glReadPixels(0, 0, w, h, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, buf)
        GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER, 0)
        if (GLES20.glGetError() != GLES20.GL_NO_ERROR) return false
        buf.position(0)
        into.copyPixelsFromBuffer(buf)
        return true
    }

    private fun releaseGl() {
        try { surface?.release() } catch (e: Throwable) { }
        try { st?.release() } catch (e: Throwable) { }
        surface = null
        st = null
        hasFrame = false
        if (display != EGL14.EGL_NO_DISPLAY) {
            EGL14.eglMakeCurrent(display, pbuffer, pbuffer, context)
            if (fbo != 0) GLES20.glDeleteFramebuffers(1, intArrayOf(fbo), 0)
            if (fboTex != 0) GLES20.glDeleteTextures(1, intArrayOf(fboTex), 0)
            if (oesTex != 0) GLES20.glDeleteTextures(1, intArrayOf(oesTex), 0)
            if (program != 0) GLES20.glDeleteProgram(program)
            EGL14.eglMakeCurrent(display, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_CONTEXT)
            if (pbuffer != EGL14.EGL_NO_SURFACE) EGL14.eglDestroySurface(display, pbuffer)
            if (context != EGL14.EGL_NO_CONTEXT) EGL14.eglDestroyContext(display, context)
        }
        fbo = 0; fboTex = 0; oesTex = 0; program = 0; fboW = 0; fboH = 0
        display = EGL14.EGL_NO_DISPLAY
        context = EGL14.EGL_NO_CONTEXT
        pbuffer = EGL14.EGL_NO_SURFACE
        readBuf = null
    }
}
