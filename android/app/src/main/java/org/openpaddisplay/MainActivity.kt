package org.openpaddisplay

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.WindowManager
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.FrameLayout
import kotlin.math.min
import kotlin.math.abs

class MainActivity : Activity(), SurfaceHolder.Callback {
    private lateinit var canvas: FrameLayout
    private lateinit var video: SurfaceView
    private var client: StreamClient? = null
    private var active = false
    private var generation = 0
    private var streamWidth = 1920
    private var streamHeight = 1280

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setDecorFitsSystemWindows(false)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        canvas = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        canvas.setOnApplyWindowInsetsListener { view, insets ->
            val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            fitVideo()
            insets
        }
        video = SurfaceView(this).also { it.holder.addCallback(this) }
        canvas.addView(video, FrameLayout.LayoutParams(-1, -1, Gravity.CENTER))
        canvas.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> fitVideo() }
        setContentView(canvas)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) {
            window.insetsController?.apply {
                systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                hide(WindowInsets.Type.systemBars())
            }
        }
    }

    private fun fitVideo() {
        if (canvas.width == 0 || canvas.height == 0) return
        val availableWidth = canvas.width - canvas.paddingLeft - canvas.paddingRight
        val availableHeight = canvas.height - canvas.paddingTop - canvas.paddingBottom
        val scale = min(availableWidth.toFloat() / streamWidth, availableHeight.toFloat() / streamHeight)
        val width = (streamWidth * scale).toInt().coerceAtLeast(1)
        val height = (streamHeight * scale).toInt().coerceAtLeast(1)
        if (video.layoutParams.width != width || video.layoutParams.height != height) {
            video.layoutParams = FrameLayout.LayoutParams(width, height, Gravity.CENTER)
        }
    }

    private fun connect() {
        if (!active || !video.holder.surface.isValid || client != null) return
        val id = ++generation
        client = StreamClient(video.holder.surface, { header ->
            runOnUiThread {
                if (id == generation) {
                    streamWidth = header.width
                    streamHeight = header.height
                    fitVideo()
                    requestDisplayMode(header.fps)
                }
            }
        }, { message ->
            runOnUiThread {
                if (id == generation) {
                    val diagnostics = "$message\nPanel: ${video.display?.refreshRate ?: 0f} Hz"
                    Log.i("OpenPadDisplay", diagnostics.replace('\n', ' '))
                }
            }
        }).also { it.start() }
    }

    private fun disconnect() {
        generation++
        client?.stop()
        client = null
    }

    private fun requestDisplayMode(fps: Int) {
        val display = video.display ?: return
        val current = display.mode
        val mode = display.supportedModes.firstOrNull {
            it.physicalWidth == current.physicalWidth && it.physicalHeight == current.physicalHeight &&
                abs(it.refreshRate - fps) < 0.5f
        }
        window.attributes = window.attributes.apply { preferredDisplayModeId = mode?.modeId ?: 0 }
    }

    override fun onResume() { super.onResume(); active = true; connect() }
    override fun onPause() { active = false; disconnect(); super.onPause() }
    override fun surfaceCreated(holder: SurfaceHolder) { connect() }
    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) { }
    override fun surfaceDestroyed(holder: SurfaceHolder) { disconnect() }
}
