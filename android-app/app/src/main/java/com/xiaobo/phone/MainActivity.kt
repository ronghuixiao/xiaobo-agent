package com.xiaobo.phone

import android.app.AppOpsManager
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Process
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

/**
 * 主界面 - 显示今日屏幕使用时间及应用使用情况
 */
class MainActivity : AppCompatActivity() {

    private lateinit var screenTimeText: TextView
    private lateinit var appsContainer: LinearLayout
    private lateinit var serviceStatusText: TextView
    private lateinit var toggleServiceButton: MaterialButton
    private lateinit var sendNowButton: MaterialButton

    companion object {
        // 服务器地址
        const val SERVER_URL = "http://1.117.61.172:8088/api/phone/stats"
        // 设备标识
        const val DEVICE_ID = "vivo_ronghui"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // 绑定视图
        screenTimeText = findViewById(R.id.screenTimeText)
        appsContainer = findViewById(R.id.appsContainer)
        serviceStatusText = findViewById(R.id.serviceStatusText)
        toggleServiceButton = findViewById(R.id.toggleServiceButton)
        sendNowButton = findViewById(R.id.sendNowButton)

        // 检查使用情况访问权限
        if (!hasUsageStatsPermission()) {
            Toast.makeText(this, "请授予使用情况访问权限", Toast.LENGTH_LONG).show()
            startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
        }

        // 开启/关闭服务按钮
        toggleServiceButton.setOnClickListener {
            val intent = Intent(this, PhoneStatsService::class.java)
            if (PhoneStatsService.isRunning) {
                stopService(intent)
                Toast.makeText(this, "服务已停止", Toast.LENGTH_SHORT).show()
            } else {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(intent)
                } else {
                    startService(intent)
                }
                Toast.makeText(this, "服务已启动", Toast.LENGTH_SHORT).show()
            }
            updateUI()
        }

        // 立即上报按钮
        sendNowButton.setOnClickListener {
            lifecycleScope.launch {
                val stats = fetchUsageStats()
                val data = PhoneStatsService.buildPostBody(stats)
                val success = PhoneStatsService.postToServer(data)
                withContext(Dispatchers.Main) {
                    Toast.makeText(
                        this@MainActivity,
                        if (success) "上报成功 ✓" else "上报失败 ✗",
                        Toast.LENGTH_SHORT
                    ).show()
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        updateUI()
    }

    /**
     * 检查是否已有使用情况访问权限
     */
    private fun hasUsageStatsPermission(): Boolean {
        val appOps = getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            packageName
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    /**
     * 更新界面数据
     */
    private fun updateUI() {
        // 更新服务状态
        serviceStatusText.text = if (PhoneStatsService.isRunning) "● 服务运行中" else "○ 服务已停止"
        toggleServiceButton.text = if (PhoneStatsService.isRunning) "停止监控" else "启动监控"

        // 异步获取使用统计数据
        lifecycleScope.launch {
            val stats = fetchUsageStats()
            withContext(Dispatchers.Main) {
                displayStats(stats)
            }
        }
    }

    /**
     * 从 UsageStatsManager 获取今日使用统计
     */
    private suspend fun fetchUsageStats(): List<AppUsageInfo> = withContext(Dispatchers.IO) {
        val usm = getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val cal = Calendar.getInstance()
        cal.set(Calendar.HOUR_OF_DAY, 0)
        cal.set(Calendar.MINUTE, 0)
        cal.set(Calendar.SECOND, 0)
        cal.set(Calendar.MILLISECOND, 0)
        val startTime = cal.timeInMillis
        val endTime = System.currentTimeMillis()

        val stats = usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, startTime, endTime)

        stats.filter { it.totalTimeInForeground > 0 }
            .map {
                val label = try {
                    packageManager.getApplicationLabel(
                        packageManager.getApplicationInfo(it.packageName, 0)
                    ).toString()
                } catch (e: Exception) {
                    it.packageName
                }
                AppUsageInfo(it.packageName, label, it.totalTimeInForeground / 1000)
            }
            .sortedByDescending { it.duration }
    }

    /**
     * 在界面上显示使用统计数据
     */
    private fun displayStats(appUsages: List<AppUsageInfo>) {
        val totalSeconds = appUsages.sumOf { it.duration }
        val hours = totalSeconds / 3600
        val minutes = (totalSeconds % 3600) / 60
        screenTimeText.text = String.format("%d 小时 %02d 分钟", hours, minutes)

        // 清空并重新填充应用列表
        appsContainer.removeAllViews()
        val topApps = appUsages.take(5)

        if (topApps.isEmpty()) {
            val emptyView = TextView(this).apply {
                text = "暂无数据"
                textSize = 14f
                setPadding(0, 16, 0, 16)
                gravity = Gravity.CENTER
            }
            appsContainer.addView(emptyView)
            return
        }

        topApps.forEachIndexed { index, app ->
            val appHours = app.duration / 3600
            val appMinutes = (app.duration % 3600) / 60
            val appSeconds = app.duration % 60

            val itemLayout = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(16, 12, 16, 12)
                gravity = Gravity.CENTER_VERTICAL
            }

            // 排名
            val rankText = TextView(this).apply {
                text = "${index + 1}"
                textSize = 16f
                setTextColor(getColor(R.color.primary))
                minWidth = 40
                gravity = Gravity.CENTER
            }

            // 应用信息
            val infoLayout = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(16, 0, 0, 0)
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            }

            val nameText = TextView(this).apply {
                text = app.name
                textSize = 15f
                setTextColor(getColor(R.color.text_primary))
            }

            val durationText = TextView(this).apply {
                text = when {
                    appHours > 0 -> "${appHours}小时${appMinutes}分钟"
                    appMinutes > 0 -> "${appMinutes}分钟${appSeconds}秒"
                    else -> "${appSeconds}秒"
                }
                textSize = 13f
                setTextColor(getColor(R.color.text_secondary))
            }

            infoLayout.addView(nameText)
            infoLayout.addView(durationText)

            itemLayout.addView(rankText)
            itemLayout.addView(infoLayout)
            appsContainer.addView(itemLayout)

            // 分隔线
            if (index < topApps.size - 1) {
                val divider = View(this).apply {
                    layoutParams = LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, 1
                    ).apply {
                        marginStart = 56
                    }
                    setBackgroundColor(getColor(R.color.divider))
                }
                appsContainer.addView(divider)
            }
        }
    }
}

/**
 * 应用使用信息数据类
 */
data class AppUsageInfo(
    val packageName: String,
    val name: String,
    val duration: Long  // 秒
)
