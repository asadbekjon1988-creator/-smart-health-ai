package uz.smarthealthai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.ZoneId
import java.time.temporal.ChronoUnit

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { SmartHealthScreen() }
    }
}

@Composable
private fun SmartHealthScreen() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    val permissions = remember {
        setOf(
            HealthPermission.getReadPermission(StepsRecord::class),
            HealthPermission.getReadPermission(SleepSessionRecord::class)
        )
    }
    var server by remember { mutableStateOf("https://smart-health-ai-dmi2.onrender.com") }
    var token by remember { mutableStateOf("") }
    var status by remember { mutableStateOf("Health Connect bilan ulanishga tayyor.") }
    val permissionLauncher = rememberLauncherForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        status = if (granted.containsAll(permissions)) "Ruxsatlar berildi. Endi sinxronlash mumkin." else "Qadam va uyqu ruxsatlari to‘liq berilmadi."
    }

    MaterialTheme {
        Column(Modifier.fillMaxSize().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Smart Health AI", style = MaterialTheme.typography.headlineMedium)
            Text("Health Connect’dan qadam va uyqu ma’lumotlarini xavfsiz yuborish.")
            OutlinedTextField(server, { server = it }, label = { Text("Server manzili") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            OutlinedTextField(token, { token = it }, label = { Text("API token") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
            Button(onClick = {
                if (HealthConnectClient.getSdkStatus(context) != HealthConnectClient.SDK_AVAILABLE) {
                    status = "Health Connect mavjud emas yoki yangilanishi kerak. Play Store'dan tekshiring."
                } else {
                    val client = HealthConnectClient.getOrCreate(context)
                    scope.launch {
                        val granted = client.permissionController.getGrantedPermissions()
                        if (granted.containsAll(permissions)) status = "Ruxsatlar avval berilgan."
                        else permissionLauncher.launch(permissions)
                    }
                }
            }, modifier = Modifier.fillMaxWidth()) { Text("Health Connect ruxsatlarini berish") }
            Button(onClick = {
                if (!server.startsWith("https://") || token.isBlank()) {
                    status = "Server manzili va API tokenni kiriting."
                } else if (HealthConnectClient.getSdkStatus(context) != HealthConnectClient.SDK_AVAILABLE) {
                    status = "Health Connect mavjud emas yoki yangilanishi kerak."
                } else {
                    scope.launch {
                        try {
                            val client = HealthConnectClient.getOrCreate(context)
                            val granted = client.permissionController.getGrantedPermissions()
                            if (!granted.containsAll(permissions)) {
                                status = "Avval Health Connect ruxsatlarini bering."
                                return@launch
                            }
                            status = "Ma'lumotlar olinmoqda..."
                            val end = Instant.now()
                            val start = end.minus(1, ChronoUnit.DAYS)
                            val stepsResult = client.aggregate(
                                AggregateRequest(setOf(StepsRecord.COUNT_TOTAL), TimeRangeFilter.between(start, end))
                            )
                            val steps = stepsResult[StepsRecord.COUNT_TOTAL] ?: 0L
                            val sleeps = client.readRecords(
                                ReadRecordsRequest(SleepSessionRecord::class, TimeRangeFilter.between(start, end))
                            ).records
                            val sleepMinutes = sleeps.sumOf { session ->
                                val from = maxOf(session.startTime, start)
                                val to = minOf(session.endTime, end)
                                if (to.isAfter(from)) ChronoUnit.MINUTES.between(from, to) else 0L
                            }
                            val payload = JSONObject()
                                .put("source", "health_connect")
                                .put("recorded_at", end.atZone(ZoneId.systemDefault()).toOffsetDateTime().toString())
                                .put("metrics", JSONObject().put("steps", steps).put("sleep_duration_minutes", sleepMinutes))
                            val response = postData(server.trim().trimEnd('/'), token, payload.toString())
                            status = "Yuborildi: $steps qadam, $sleepMinutes daqiqa uyqu. Server: $response"
                        } catch (e: Exception) {
                            status = "Xatolik: ${e.message ?: "noma'lum xato"}"
                        }
                    }
                }
            }, modifier = Modifier.fillMaxWidth()) { Text("Hozir sinxronlash") }
            Text(status, style = MaterialTheme.typography.bodyLarge)
            Text("Eslatma: tokenni boshqa odamlarga yubormang. Bu dastlabki sinov versiyasi; avtomatik fon sinxronlash keyingi bosqichda qo‘shiladi.", style = MaterialTheme.typography.bodySmall)
        }
    }
}

private suspend fun postData(baseUrl: String, token: String, body: String): String =
    withContext(Dispatchers.IO) {
        val connection = URL("$baseUrl/api/v1/health-data").openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 20000
            connection.readTimeout = 20000
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val response = stream.bufferedReader().use { it.readText() }
            if (code !in 200..299) error("Server HTTP $code: $response")
            response
        } finally {
            connection.disconnect()
        }
    }
