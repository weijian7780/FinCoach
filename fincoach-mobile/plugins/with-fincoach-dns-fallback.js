const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const { withMainApplication, withAppBuildGradle, withDangerousMod } = require('expo/config-plugins');

/** Resolve the build's API host, never a second hard-coded copy of its URL. */
function resolveOptions(apiUrl, { enabled = true } = {}) {
  if (!enabled) return { enabled: false, apiHost: '' };
  let url;
  try {
    url = new URL(apiUrl);
    if (url.username || url.password || !['http:', 'https:'].includes(url.protocol)) throw new Error();
  } catch {
    throw new Error('DNS fallback requires a valid, credential-free EXPO_PUBLIC_FINCOACH_API_URL.');
  }
  const host = url.hostname.toLowerCase();
  // Local development names belong to the local resolver, never a public DoH provider.
  // Classify rooted DNS names too, while keeping the actual host for exact request matching.
  const classificationHost = host.replace(/\.$/, '');
  const isLocal = net.isIP(classificationHost.replace(/^\[|\]$/g, '')) !== 0 || !classificationHost.includes('.') ||
    ['local', 'localhost', 'localdomain', 'home.arpa', 'test', 'invalid'].some((suffix) =>
      classificationHost === suffix || classificationHost.endsWith(`.${suffix}`));
  return { enabled: url.protocol === 'https:' && !isLocal, apiHost: host };
}

/** Insert once, before loadReactNative can create the shared network client. */
function updateMainApplication(contents) {
  if (contents.includes('FinCoachNetwork.install(this)')) return contents;
  const anchor = /override fun onCreate\(\)\s*\{\s*\r?\n\s*super\.onCreate\(\)/;
  if (!anchor.test(contents)) throw new Error('DNS fallback cannot find the Kotlin onCreate startup anchor.');
  return contents.replace(anchor, (match) => `${match}\n    FinCoachNetwork.install(this)`);
}

/** A generated block can be replaced without duplicating dependencies on prebuild. */
function updateAppBuildGradle(contents, version) {
  if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Invalid pinned OkHttp version.');
  const marker = /\s*\/\/ @generated begin fincoach-dns-fallback[\s\S]*?\/\/ @generated end fincoach-dns-fallback\n?/g;
  const clean = contents.replace(marker, '\n');
  if (!/^dependencies\s*\{/m.test(clean)) throw new Error('DNS fallback cannot find the app Gradle dependencies block.');
  const block = [
    '    // @generated begin fincoach-dns-fallback',
    `    implementation("com.squareup.okhttp3:okhttp-dnsoverhttps:${version}")`,
    '    testImplementation("junit:junit:4.13.2")',
    `    testImplementation("com.squareup.okhttp3:mockwebserver:${version}")`,
    `    testImplementation("com.squareup.okhttp3:okhttp-tls:${version}")`,
    '    // @generated end fincoach-dns-fallback',
  ].join('\n');
  return clean.replace(/^dependencies\s*\{/m, (match) => `${match}\n${block}`);
}

function renderKotlin(template, packageName, options) {
  if (!/^[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)+$/.test(packageName)) throw new Error('Invalid Android package.');
  return template.replaceAll('__ANDROID_PACKAGE__', packageName)
    .replaceAll('__DNS_ENABLED__', String(options.enabled))
    .replaceAll('__API_HOST__', JSON.stringify(options.apiHost));
}

function inferOkHttpVersion(projectRoot) {
  const reactNativeRoot = path.dirname(require.resolve('react-native/package.json', { paths: [projectRoot] }));
  const catalog = fs.readFileSync(path.join(reactNativeRoot, 'gradle/libs.versions.toml'), 'utf8');
  const match = catalog.match(/^okhttp\s*=\s*"(\d+\.\d+\.\d+)"/m);
  if (!match) throw new Error('DNS fallback cannot determine the React Native OkHttp version.');
  return match[1];
}

function withFinCoachDnsFallback(config, options = {}) {
  const packageName = config.android?.package;
  // EAS reads public config before supplying the selected profile's environment.
  // Validate its URL when native mods execute, not during that early config read.
  renderKotlin('', packageName, { enabled: false, apiHost: '' });
  let resolved;
  const nativeOptions = () => {
    if (!resolved) {
      resolved = resolveOptions(process.env.EXPO_PUBLIC_FINCOACH_API_URL, options);
      if (options.enabled !== false && !resolved.enabled) {
        console.info('[FinCoach DNS] Public DNS fallback is inactive for this development API URL.');
      }
    }
    return resolved;
  };
  config = withMainApplication(config, (mod) => {
    nativeOptions();
    if (mod.modResults.language !== 'kt') throw new Error('FinCoach DNS fallback requires Kotlin MainApplication.');
    mod.modResults.contents = updateMainApplication(mod.modResults.contents);
    return mod;
  });
  config = withAppBuildGradle(config, (mod) => {
    nativeOptions();
    const version = inferOkHttpVersion(mod.modRequest.projectRoot);
    mod.modResults.contents = updateAppBuildGradle(mod.modResults.contents, version);
    return mod;
  });
  return withDangerousMod(config, ['android', async (mod) => {
    const resolved = nativeOptions();
    const root = path.join(mod.modRequest.platformProjectRoot, 'app/src');
    for (const [filename, sourceSet] of [['FinCoachDnsFallback.kt', 'main'], ['FinCoachDnsFallbackTest.kt', 'test']]) {
      const templatePath = path.join(__dirname, 'android', filename);
      if (!fs.existsSync(templatePath)) continue;
      const output = path.join(root, sourceSet, 'java', ...packageName.split('.'), filename);
      fs.mkdirSync(path.dirname(output), { recursive: true });
      fs.writeFileSync(output, renderKotlin(fs.readFileSync(templatePath, 'utf8'), packageName, resolved));
    }
    return mod;
  }]);
}

module.exports = withFinCoachDnsFallback;
Object.assign(module.exports, { resolveOptions, updateMainApplication, updateAppBuildGradle, renderKotlin });
