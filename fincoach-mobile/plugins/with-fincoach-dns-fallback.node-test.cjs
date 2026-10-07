const assert = require('node:assert/strict');
const { test } = require('node:test'); // Run separately from Vitest's *.test.* discovery.
const plugin = require('./with-fincoach-dns-fallback');

test('derives the exact allowed hostname from the build API URL', () => {
  assert.deepEqual(plugin.resolveOptions('https://api.chisquaredv10.dpdns.org/'), {
    enabled: true, apiHost: 'api.chisquaredv10.dpdns.org',
  });
  assert.equal(plugin.resolveOptions('https://API.EXAMPLE.ORG:8443/v1').apiHost, 'api.example.org');
});
test('disabled builds need no public API configuration', () => {
  assert.deepEqual(plugin.resolveOptions(undefined, { enabled: false }), { enabled: false, apiHost: '' });
});
test('public config evaluation does not require prebuild-only environment values', () => {
  const original = process.env.EXPO_PUBLIC_FINCOACH_API_URL;
  delete process.env.EXPO_PUBLIC_FINCOACH_API_URL;
  try {
    const config = plugin({ android: { package: 'com.fincoach.app' } });
    assert.ok(config.mods.android.mainApplication);
  } finally {
    if (original === undefined) delete process.env.EXPO_PUBLIC_FINCOACH_API_URL;
    else process.env.EXPO_PUBLIC_FINCOACH_API_URL = original;
  }
});
test('rejects missing, malformed, and credential-bearing API URLs', () => {
  for (const url of [undefined, '', 'not-a-url', 'https://user:password@api.example.org']) {
    assert.throws(() => plugin.resolveOptions(url), /EXPO_PUBLIC_FINCOACH_API_URL/);
  }
});
test('local and plain HTTP development builds keep system DNS', () => {
  for (const url of ['http://192.168.1.100:8000', 'http://localhost:8000', 'https://127.0.0.1', 'https://[::1]', 'http://api.example.org', 'https://backend']) {
    assert.equal(plugin.resolveOptions(url).enabled, false, url);
  }
});
test('local and reserved names stay private even with a trailing root dot', () => {
  for (const host of ['backend.local.', 'backend.localhost.', 'backend.localdomain.', 'backend.home.arpa', 'backend.test', 'backend.invalid', 'localhost.', 'home.arpa']) {
    assert.equal(plugin.resolveOptions(`https://${host}`).enabled, false, host);
  }
  assert.deepEqual(plugin.resolveOptions('https://api.example.org.'), { enabled: true, apiHost: 'api.example.org.' });
});
test('registers before React Native and remains idempotent', () => {
  const original = 'class MainApplication {\n  override fun onCreate() {\n    super.onCreate()\n    loadReactNative(this)\n  }\n}\n';
  const once = plugin.updateMainApplication(original);
  assert.equal(plugin.updateMainApplication(once), once);
  assert.equal(once.match(/FinCoachNetwork\.install\(this\)/g).length, 1);
  assert.ok(once.indexOf('FinCoachNetwork.install(this)') < once.indexOf('loadReactNative(this)'));
});
test('fails clearly for unsupported startup code', () => {
  assert.throws(() => plugin.updateMainApplication('class UnsupportedApplication {}'), /onCreate/);
});
test('dependency injection is repeatable and updates the selected version', () => {
  const original = 'dependencies {\n    implementation("com.facebook.react:react-android")\n}\n';
  const once = plugin.updateAppBuildGradle(original, '4.12.0');
  assert.equal(plugin.updateAppBuildGradle(once, '4.12.0'), once);
  assert.equal(once.match(/okhttp-dnsoverhttps:4\.12\.0/g).length, 1);
  const updated = plugin.updateAppBuildGradle(once, '4.9.2');
  assert.ok(updated.includes('okhttp-dnsoverhttps:4.9.2'));
  assert.ok(!updated.includes('okhttp-dnsoverhttps:4.12.0'));
});
test('renders build constants and rejects invalid Android packages', () => {
  const template = 'package __ANDROID_PACKAGE__\nconst val ENABLED = __DNS_ENABLED__\nconst val API = __API_HOST__\n';
  assert.equal(plugin.renderKotlin(template, 'com.fincoach.app', { enabled: true, apiHost: 'api.example.org' }),
    'package com.fincoach.app\nconst val ENABLED = true\nconst val API = "api.example.org"\n');
  assert.throws(() => plugin.renderKotlin(template, 'com.bad;injection', { enabled: false, apiHost: '' }), /package/);
});
