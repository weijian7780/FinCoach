package __ANDROID_PACKAGE__

import android.content.Context
import android.util.Log
import java.io.File
import java.net.InetAddress
import java.net.UnknownHostException
import java.util.Locale
import java.util.concurrent.TimeUnit
import com.facebook.react.modules.network.OkHttpClientFactory
import com.facebook.react.modules.network.OkHttpClientProvider
import okhttp3.Cache
import okhttp3.Dns
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.dnsoverhttps.DnsOverHttps
import okhttp3.HttpUrl.Companion.toHttpUrl

/** Resolve only the configured API through public DoH after system lookup fails. */
internal class FinCoachDnsFallback(
  private val apiHost: String,
  private val systemDns: Dns,
  private val fallbackDns: Dns,
  private val onEvent: (String, String) -> Unit = { _, _ -> },
) : Dns {
  override fun lookup(hostname: String): List<InetAddress> {
    try {
      val addresses = systemDns.lookup(hostname)
      if (addresses.isEmpty()) throw UnknownHostException(hostname)
      if (hostname.equals(apiHost, ignoreCase = true)) onEvent("system_success", apiHost)
      return addresses
    } catch (systemFailure: UnknownHostException) {
      // The factory is shared by RN/Expo: this boundary keeps unrelated hosts private.
      if (!hostname.equals(apiHost, ignoreCase = true)) throw systemFailure
      onEvent("fallback_started", apiHost)
      try {
        val addresses = fallbackDns.lookup(hostname.lowercase(Locale.ROOT))
        if (addresses.isEmpty()) throw UnknownHostException(apiHost)
        onEvent("fallback_success", apiHost)
        return addresses
      } catch (fallbackFailure: UnknownHostException) {
        onEvent("fallback_failed", apiHost)
        if (fallbackFailure !== systemFailure) fallbackFailure.addSuppressed(systemFailure)
        throw fallbackFailure
      }
    }
  }
}

internal object FinCoachNetwork {
  private const val ENABLED = __DNS_ENABLED__
  private const val API_HOST = __API_HOST__
  fun install(context: Context) {
    if (!ENABLED || API_HOST.isEmpty()) return
    val application = context.applicationContext
    // The shared DoH client is credential-free and is never used for API HTTP requests.
    // Numeric resolver bootstrap addresses do not require the failing system resolver.
    val doh = createDohResolver(
      application.cacheDir,
      "https://dns.google/dns-query".toHttpUrl(),
      listOf("8.8.8.8", "8.8.4.4", "2001:4860:4860::8888", "2001:4860:4860::8844")
        .map { InetAddress.getByName(it) },
    )
    val events: (String, String) -> Unit = { event, host ->
      if (BuildConfig.DEBUG) Log.i("FinCoachDns", "$event host=$host")
    }
    val resolver = FinCoachDnsFallback(API_HOST, Dns.SYSTEM, doh, events)
    OkHttpClientProvider.setOkHttpClientFactory(OkHttpClientFactory {
      // Preserve RN's cookies/cache/default timeouts; Expo Fetch also uses this factory.
      createNetworkClient(OkHttpClientProvider.createClientBuilder(application), resolver)
    })
  }

  fun createNetworkClient(builder: OkHttpClient.Builder, resolver: Dns): OkHttpClient =
    builder.dns(resolver).build()

  fun createDohResolver(cacheDir: File, endpoint: HttpUrl, bootstrapHosts: List<InetAddress>): DnsOverHttps {
    val client = OkHttpClient.Builder()
      .connectTimeout(2, TimeUnit.SECONDS)
      .readTimeout(3, TimeUnit.SECONDS)
      .callTimeout(4, TimeUnit.SECONDS)
      .cache(Cache(File(cacheDir, "fincoach-doh"), 512L * 1024L))
      .build()
    return DnsOverHttps.Builder()
      .client(client)
      .url(endpoint)
      .bootstrapDnsHosts(*bootstrapHosts.toTypedArray())
      .includeIPv6(true)
      .build()
  }
}
