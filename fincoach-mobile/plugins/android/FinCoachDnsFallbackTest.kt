package __ANDROID_PACKAGE__

import java.net.InetAddress
import java.net.UnknownHostException
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.util.Base64
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLPeerUnverifiedException
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.RecordedRequest
import okhttp3.mockwebserver.SocketPolicy
import okio.Buffer
import okhttp3.tls.HandshakeCertificates
import okhttp3.tls.HeldCertificate
import org.junit.Assert.*
import org.junit.Test
import org.junit.Rule
import org.junit.rules.TemporaryFolder
import com.facebook.react.modules.network.OkHttpClientProvider
import com.facebook.react.modules.network.CookieJarContainer

class FinCoachDnsFallbackTest {
  @get:Rule val temporaryFolder = TemporaryFolder()
  private val api = "api.example.org"
  private val v4 = InetAddress.getByAddress(byteArrayOf(127, 0, 0, 1))
  private val v6 = InetAddress.getByAddress(ByteArray(16).also { it[15] = 1 })
  private fun dns(resolve: (String) -> List<InetAddress>) = object : Dns {
    override fun lookup(hostname: String): List<InetAddress> = resolve(hostname)
  }
  private val missing = dns { host -> throw UnknownHostException(host) }

  @Test fun systemSuccessKeepsTheOriginalAddresses() {
    val resolver = FinCoachDnsFallback(api, dns { listOf(v4) }, dns { throw AssertionError("DoH should not run") })
    assertEquals(listOf(v4), resolver.lookup(api))
  }

  @Test fun systemFailureRecoversOnlyTheAllowedApiHost() {
    val resolver = FinCoachDnsFallback(api, missing, dns { host ->
      assertEquals(api, host)
      listOf(v4, v6)
    })
    assertEquals(listOf(v4, v6), resolver.lookup(api))
  }

  @Test fun unrelatedHostDoesNotUsePublicFallback() {
    val original = UnknownHostException("unrelated")
    val resolver = FinCoachDnsFallback(api, dns { throw original }, dns { throw AssertionError("DoH leaked an unrelated hostname") })
    try { resolver.lookup("project.supabase.co"); fail("Expected resolution failure") }
    catch (error: UnknownHostException) { assertSame(original, error) }
  }

  @Test fun hostnameScopeIsCaseInsensitiveButNotASuffixMatch() {
    val resolver = FinCoachDnsFallback(api, missing, dns { listOf(v4) })
    assertEquals(listOf(v4), resolver.lookup("API.EXAMPLE.ORG"))
    try { resolver.lookup("other.api.example.org"); fail("Subdomains must not be allowed implicitly") }
    catch (_: UnknownHostException) { }
  }

  @Test fun failedFallbackIsStillAResolutionFailure() {
    val resolver = FinCoachDnsFallback(api, missing, missing)
    try { resolver.lookup(api); fail("Expected resolution failure") }
    catch (_: UnknownHostException) { }
  }

  @Test fun emptyFallbackCannotBecomeSuccessfulResolution() {
    val resolver = FinCoachDnsFallback(api, missing, dns { emptyList() })
    try { resolver.lookup(api); fail("Empty DNS answers must fail") }
    catch (_: UnknownHostException) { }
  }

  @Test fun dnsRecoverySendsOneOriginalPostAndPreservesHostAndAuthorization() {
    val server = MockWebServer()
    server.enqueue(MockResponse().setBody("ok"))
    server.start()
    val client = OkHttpClient.Builder().dns(FinCoachDnsFallback(api, missing, dns { listOf(v4) })).build()
    try {
      val url = server.url("/coach/messages").newBuilder().host(api).build()
      val body = "{}".toRequestBody("application/json".toMediaType())
      val request = Request.Builder().url(url).header("Authorization", "Bearer test-token").post(body).build()
      client.newCall(request).execute().use { assertEquals("ok", it.body!!.string()) }
      val observed = server.takeRequest(1, TimeUnit.SECONDS)!!
      assertEquals("POST", observed.method)
      assertEquals("/coach/messages", observed.path)
      assertEquals("$api:${server.port}", observed.getHeader("Host"))
      assertEquals("Bearer test-token", observed.getHeader("Authorization"))
      assertEquals(1, server.requestCount)
    } finally {
      client.connectionPool.evictAll()
      client.dispatcher.executorService.shutdown()
      server.shutdown()
    }
  }

  @Test fun dnsRecoveryDoesNotDisableTlsHostnameVerification() {
    val certificate = HeldCertificate.Builder().addSubjectAlternativeName("localhost").build()
    val serverTls = HandshakeCertificates.Builder().heldCertificate(certificate).build()
    val clientTls = HandshakeCertificates.Builder().addTrustedCertificate(certificate.certificate).build()
    val server = MockWebServer()
    server.useHttps(serverTls.sslSocketFactory(), false)
    server.start()
    val client = OkHttpClient.Builder()
      .dns(FinCoachDnsFallback(api, missing, dns { listOf(v4) }))
      .sslSocketFactory(clientTls.sslSocketFactory(), clientTls.trustManager)
      .build()
    try {
      val url = server.url("/").newBuilder().host(api).build()
      try { client.newCall(Request.Builder().url(url).build()).execute().close(); fail("Wrong certificate hostname must fail") }
      catch (_: SSLPeerUnverifiedException) { }
      assertEquals(0, server.requestCount)
    } finally {
      client.connectionPool.evictAll()
      client.dispatcher.executorService.shutdown()
      server.shutdown()
    }
  }

  @Test fun clientIntegrationPreservesReactNativeCookiesAndTimeouts() {
    val resolver = FinCoachDnsFallback(api, missing, dns { listOf(v4) })
    val client = FinCoachNetwork.createNetworkClient(OkHttpClientProvider.createClientBuilder(), resolver)
    assertSame(resolver, client.dns)
    assertTrue(client.cookieJar is CookieJarContainer)
    assertEquals(0, client.readTimeoutMillis)
    assertEquals(0, client.connectTimeoutMillis)
  }

  // These responses exercise the real DoH wire decoder, bootstrap DNS and HTTP cache.
  // The fake server returns RFC 1035 A/AAAA packets, not mocked library results.
  private fun answer(query: ByteArray): ByteArray {
    val type = ((query[query.size - 4].toInt() and 255) shl 8) or (query[query.size - 3].toInt() and 255)
    val address = if (type == 28) v6.address else v4.address
    val stream = ByteArrayOutputStream()
    val header = query.copyOfRange(0, 12)
    header[2] = 0x81.toByte(); header[3] = 0x80.toByte()
    header[6] = 0; header[7] = 1
    stream.write(header)
    stream.write(query, 12, query.size - 12)
    DataOutputStream(stream).apply {
      writeShort(0xc00c); writeShort(type); writeShort(1); writeInt(120)
      writeShort(address.size); write(address)
    }
    return stream.toByteArray()
  }

  @Test fun realDohBootstrapsBothAddressFamiliesAndCachesWithoutCredentials() {
    val server = MockWebServer()
    server.dispatcher = object : Dispatcher() {
      override fun dispatch(request: RecordedRequest): MockResponse {
        val packet = Base64.getUrlDecoder().decode(request.requestUrl!!.queryParameter("dns"))
        return MockResponse().setHeader("Content-Type", "application/dns-message")
          .setHeader("Cache-Control", "public, max-age=120")
          .setBody(Buffer().write(answer(packet)))
      }
    }
    server.start()
    val endpoint = server.url("/dns-query").newBuilder().host("bootstrap.example.org").build()
    val resolver = FinCoachNetwork.createDohResolver(temporaryFolder.newFolder(), endpoint, listOf(v4))
    try {
      assertEquals(setOf(v4, v6), resolver.lookup(api).toSet())
      assertEquals(setOf(v4, v6), resolver.lookup(api).toSet())
      assertEquals(2, server.requestCount)
      repeat(2) {
        val query = server.takeRequest(1, TimeUnit.SECONDS)!!
        assertNull(query.getHeader("Authorization"))
        assertNull(query.getHeader("Cookie"))
        assertEquals("/dns-query", query.requestUrl!!.encodedPath)
      }
    } finally {
      resolver.client.cache?.close()
      resolver.client.connectionPool.evictAll()
      resolver.client.dispatcher.executorService.shutdown()
      server.shutdown()
    }
  }

  @Test fun dohHttpFailureRemainsADnsFailure() {
    val server = MockWebServer()
    server.enqueue(MockResponse().setResponseCode(503))
    server.enqueue(MockResponse().setResponseCode(503))
    server.start()
    val resolver = FinCoachNetwork.createDohResolver(temporaryFolder.newFolder(), server.url("/dns-query"), listOf(v4))
    try {
      try { resolver.lookup(api); fail("HTTP failure must not produce addresses") }
      catch (_: UnknownHostException) { }
      assertEquals(2, server.requestCount)
    } finally {
      resolver.client.cache?.close()
      resolver.client.connectionPool.evictAll()
      resolver.client.dispatcher.executorService.shutdown()
      server.shutdown()
    }
  }

  @Test fun unavailableDohFailsWithinItsBoundedTimeout() {
    val server = MockWebServer()
    server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
    server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
    server.start()
    val resolver = FinCoachNetwork.createDohResolver(temporaryFolder.newFolder(), server.url("/dns-query"), listOf(v4))
    val started = System.nanoTime()
    try {
      try { resolver.lookup(api); fail("Unavailable DoH must fail") }
      catch (_: UnknownHostException) { }
      val elapsedMillis = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started)
      assertTrue("DoH was not bounded: ${elapsedMillis}ms", elapsedMillis < 6500)
    } finally {
      resolver.client.cache?.close()
      resolver.client.connectionPool.evictAll()
      resolver.client.dispatcher.executorService.shutdown()
      server.shutdown()
    }
  }
}
