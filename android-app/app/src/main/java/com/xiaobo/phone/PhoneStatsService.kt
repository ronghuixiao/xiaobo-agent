package com.xiaobo.phone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.Process
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

/**
 * 前台服务 - 定时采集屏幕使用数据并上报到服务器
 */
class PhoneStatsService : Service() {

    companion object {
        private const val TAG = "PhoneStatsService"
        private const val CHANNEL_ID = "xiaobo_monitor"
        private const val NOTIFICATION_ID = 1001
        private const val SERVER_URL = "http://1.117.61.172:8088/api/phone/stats"
        private const val DEVICE_ID = "vivo_ronghui"
        // 定时间隔：30 分钟
        private const val INTERVAL_MS = 30 * 60 * 1000L

        // 服务运行状态
        var isRunning = false
            private set

        /**
         * 构建 POST 请求体 JSON
         */
        @JvmStatic
        fun buildPostBody(appUsages: List<AppUsageInfo>): String {
            val totalSeconds = appUsages.sumOf { it.duration }

            val json = JSONObject()
            json.put("device_id", DEVICE_ID)
            json.put("screen_time_total", totalSeconds)

            val appsArray = JSONArray()
            appUsages.forEach { app ->
                val appJson = JSONObject()
                appJson.put("package", app.packageName)
                appJson.put("name", app.name)
                appJson.put("duration", app.duration)
                appsArray.put(appJson)
            }
            json.put("app_usages", appsArray)

            return json.toString()
        }

        /**
         * 将数据 POST 到服务器
         */
        @JvmStatic
        fun postToServer(body: String): Boolean {
            var connection: HttpURLConnection? = null
            return try {
                val url = URL(SERVER_URL)
                connection = url.openConnection() as HttpURLConnection
                connection.apply {
                    requestMethod = "POST"
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                    setRequestProperty("Accept", "application/json")
                    connectTimeout = 10_000
                    readTimeout = 10_000
                    doOutput = true
                }

                val writer = OutputStreamWriter(connection.outputStream, Charsets.UTF_8)
                writer.write(body)
                writer.flush()
                writer.close()

                val responseCode = connection.responseCode
                Log.d(TAG, "服务器响应: $responseCode")
                responseCode in 200..299
            } catch (e: Exception) {
                Log.e(TAG, "网络请求失败", e)
                false
            } finally {
                connection?.disconnect()
            }
        }
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var monitorJob: Job? = null

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification())
        startMonitoring()
        Log.d(TAG, "服务已启动")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY  // 被杀后自动重启
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
        monitorJob?.cancel()
        scope.cancel()
        Log.d(TAG, "服务已停止")
    }

    override fun onBind(intent: Intent?): IBinder? = null

    /**
     * 创建通知渠道（Android 8.0+）
     */
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "手机监控",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "小柏手机使用监控服务"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    /**
     * 构建前台服务通知
     */
    private fun buildNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_info_details)
            .setContentTitle("小柏正在监控手机使用")
            .setContentText("每30分钟自动上报使用数据")
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }

    /**
     * 启动定时监控循环
     */
    private fun startMonitoring() {
        monitorJob = scope.launch {
            while (isActive) {
                try {
                    // 首次启动立即上报一次
                    val stats = collectUsageStats()
                    val body = buildPostBody(stats)
                    val success = postToServer(body)
                    Log.d(TAG, if (success) "上报成功" else "上报失败")

                    // 更新通知
                    withContext(Dispatchers.Main) {
                        val mgr = getSystemService(NotificationManager::class.java)
                        mgr.notify(NOTIFICATION_ID, buildNotification())
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "上报异常", e)
                }

                // 等待 30 分钟
                delay(INTERVAL_MS)
            }
        }
    }

    /**
     * 采集今日使用统计数据
     */
    private fun collectUsageStats(): List<AppUsageInfo> {
        val usm = getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val cal = java.util.Calendar.getInstance()
        cal.set(java.util.Calendar.HOUR_OF_DAY, 0)
        cal.set(java.util.Calendar.MINUTE, 0)
        cal.set(java.util.Calendar.SECOND, 0)
        cal.set(java.util.Calendar.MILLISECOND, 0)
        val startTime = cal.timeInMillis
        val endTime = System.currentTimeMillis()

        val stats = usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, startTime, endTime)

        return stats.filter { it.totalTimeInForeground > 0 }
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
}
