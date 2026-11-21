#!/usr/bin/env python3
"""
chiaki-ng Android uygulamasını Çevirix'e dönüştürür.
Kullanım: python3 dahili/hazirla.py <chiaki-ng klasörü> <cevirix depo klasörü>
Her değişiklik kontrol edilir; beklenen metin bulunamazsa derleme hemen durur.
"""
import os
import re
import shutil
import sys

chiaki = os.path.abspath(sys.argv[1])
repo = os.path.abspath(sys.argv[2])
dahili = os.path.join(repo, "dahili")
app = os.path.join(chiaki, "android", "app")
main = os.path.join(app, "src", "main")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


def replace_once(s, old, new, what):
    if old not in s:
        sys.exit(f"HATA: '{what}' için beklenen metin bulunamadı")
    return s.replace(old, new, 1)


def copy_tree(src, dst):
    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for fn in files:
            shutil.copy2(os.path.join(root, fn), os.path.join(target, fn))


# 1) Kaynak kodlar ve kaynaklar
copy_tree(os.path.join(dahili, "src"), os.path.join(main, "java"))
copy_tree(os.path.join(dahili, "res"), os.path.join(main, "res"))
shutil.copy2(os.path.join(dahili, "strings_tr.xml"), os.path.join(main, "res", "values", "strings.xml"))
shutil.copy2(os.path.join(repo, "keystore", "altyazi.jks"), os.path.join(app, "cevirix.jks"))
print("kaynaklar kopyalandı")

# 2) build.gradle
p = os.path.join(app, "build.gradle")
s = read(p)
s = replace_once(s, 'applicationId "com.metallic.chiaki"', 'applicationId "com.bugra.cevirix"', "applicationId")
s = replace_once(
    s,
    "versionCode 12",
    'versionCode((project.findProperty("buildNo") ?: "1").toString().toInteger())',
    "versionCode",
)
s = replace_once(
    s,
    "        targetSdk 35\n",
    '        targetSdk 35\n        ndk {\n            abiFilters "arm64-v8a"\n        }\n',
    "abiFilters",
)
s = replace_once(
    s,
    "    signingConfigs {\n        release\n    }\n",
    "    signingConfigs {\n        release {\n"
    '            storeFile file("cevirix.jks")\n'
    '            storePassword "altyazi123"\n'
    '            keyAlias "altyazi"\n'
    '            keyPassword "altyazi123"\n'
    "        }\n    }\n",
    "signingConfigs",
)
s = replace_once(
    s,
    "            minifyEnabled true\n",
    "            minifyEnabled false\n            signingConfig signingConfigs.release\n",
    "minifyEnabled",
)
s = replace_once(
    s,
    "    buildFeatures {\n",
    "    packagingOptions {\n        resources {\n"
    "            excludes += ['META-INF/versions/9/OSGI-INF/MANIFEST.MF', 'META-INF/DEPENDENCIES', "
    "'META-INF/LICENSE*', 'META-INF/NOTICE*']\n"
    "        }\n    }\n\n"
    "    lint {\n        abortOnError false\n        checkReleaseBuilds false\n    }\n\n"
    "    buildFeatures {\n",
    "packagingOptions",
)
s = replace_once(
    s,
    "    implementation libs.oboe\n",
    "    implementation libs.oboe\n\n"
    "    // Çevirix: yazı okuma, çeviri, TV bağlantısı\n"
    "    implementation 'com.google.mlkit:text-recognition:16.0.1'\n"
    "    implementation 'com.google.mlkit:translate:17.0.3'\n"
    "    implementation 'org.java-websocket:Java-WebSocket:1.5.7'\n"
    "    implementation 'com.squareup.okhttp3:okhttp:4.12.0'\n"
    "    implementation 'androidx.lifecycle:lifecycle-runtime-ktx:2.8.7'\n",
    "dependencies",
)
write(p, s)
print("build.gradle güncellendi")

# 3) AndroidManifest.xml
p = os.path.join(main, "AndroidManifest.xml")
s = read(p)
s = replace_once(
    s,
    '    <uses-permission android:name="android.permission.INTERNET" />\n',
    '    <uses-permission android:name="android.permission.INTERNET" />\n'
    '    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />\n'
    '    <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />\n'
    '    <uses-permission android:name="android.permission.WAKE_LOCK" />\n'
    '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />\n'
    '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PROJECTION" />\n'
    '    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />\n\n'
    "    <queries>\n"
    '        <package android:name="com.playstation.remoteplay" />\n'
    "    </queries>\n",
    "izinler",
)
s = replace_once(s, "    <application\n", '    <application\n        android:name="com.bugra.altyazi.phone.App"\n', "Application sınıfı")
s = replace_once(s, 'android:icon="@mipmap/ic_launcher"', 'android:icon="@mipmap/cx_ic_launcher"', "simge")
s = replace_once(s, 'android:roundIcon="@mipmap/ic_launcher_round"', 'android:roundIcon="@mipmap/cx_ic_launcher"', "yuvarlak simge")
s = replace_once(
    s,
    'android:authorities="com.metallic.chiaki.fileprovider"',
    'android:authorities="com.bugra.cevirix.fileprovider"',
    "fileprovider",
)
# chiaki ana ekranı artık başlatıcı değil
launcher_block = re.search(
    r'(<activity android:name="\.main\.MainActivity"[^>]*>)\s*<intent-filter>.*?</intent-filter>',
    s,
    re.S,
)
if not launcher_block:
    sys.exit("HATA: chiaki MainActivity intent-filter bulunamadı")
s = s[: launcher_block.start()] + launcher_block.group(1) + s[launcher_block.end():]
s = replace_once(
    s,
    "    </application>",
    "        <activity\n"
    '            android:name="com.bugra.altyazi.phone.CevirixActivity"\n'
    '            android:exported="true"\n'
    '            android:launchMode="singleTask"\n'
    '            android:screenOrientation="portrait"\n'
    '            android:theme="@style/CxTema"\n'
    '            android:windowSoftInputMode="adjustResize">\n'
    "            <intent-filter>\n"
    '                <action android:name="android.intent.action.MAIN" />\n'
    '                <category android:name="android.intent.category.LAUNCHER" />\n'
    "            </intent-filter>\n"
    "        </activity>\n\n"
    "        <activity\n"
    '            android:name="com.bugra.altyazi.phone.PsnLoginActivity"\n'
    '            android:exported="false"\n'
    '            android:theme="@style/CxTema" />\n\n'
    "        <service\n"
    '            android:name="com.bugra.altyazi.phone.CaptureService"\n'
    '            android:exported="false"\n'
    '            android:foregroundServiceType="mediaProjection" />\n'
    "    </application>",
    "Çevirix ekranları",
)
write(p, s)
print("manifest güncellendi")

# 4) fileprovider sabiti
p = os.path.join(main, "java", "com", "metallic", "chiaki", "common", "LogManager.kt")
s = read(p)
s = replace_once(s, '"com.metallic.chiaki.fileprovider"', '"com.bugra.cevirix.fileprovider"', "LogManager authority")
write(p, s)

# 5) Akış ekranı: PS5 görüntüsünden altyazı okuma
p = os.path.join(main, "java", "com", "metallic", "chiaki", "stream", "StreamActivity.kt")
s = read(p)
s = replace_once(
    s,
    "\tprivate val uiVisibilityHandler = Handler(Looper.getMainLooper())\n",
    "\tprivate val uiVisibilityHandler = Handler(Looper.getMainLooper())\n"
    "\tprivate var cevirixCapture: com.bugra.altyazi.phone.StreamCapture? = null\n",
    "StreamActivity alanı",
)
s = replace_once(
    s,
    "\t\tviewModel.session.attachToSurfaceView(binding.surfaceView)\n",
    "\t\tviewModel.session.attachToSurfaceView(binding.surfaceView)\n"
    "\t\tcevirixCapture = com.bugra.altyazi.phone.StreamCapture(this, binding.surfaceView).also { it.start() }\n",
    "StreamActivity başlatma",
)
s = replace_once(
    s,
    "\t\tcontrolsJob?.cancel()\n",
    "\t\tcontrolsJob?.cancel()\n\t\tcevirixCapture?.stop()\n\t\tcevirixCapture = null\n",
    "StreamActivity durdurma",
)
write(p, s)
print("akış ekranı güncellendi")

# 6) Eşleştirme ekranı: hesap kimliğini otomatik doldur
p = os.path.join(main, "java", "com", "metallic", "chiaki", "regist", "RegistActivity.kt")
s = read(p)
s = replace_once(
    s,
    "\t\tbinding.registButton.setOnClickListener { doRegist() }\n",
    "\t\tbinding.registButton.setOnClickListener { doRegist() }\n"
    "\t\tcom.bugra.altyazi.phone.Prefs.init(this)\n"
    "\t\tval cevirixAccountId = com.bugra.altyazi.phone.Prefs.psnAccountId\n"
    "\t\tif(cevirixAccountId.isNotBlank() && binding.psnIdEditText.text.isNullOrBlank())\n"
    "\t\t\tbinding.psnIdEditText.setText(cevirixAccountId)\n",
    "RegistActivity hesap kimliği",
)
write(p, s)
print("eşleştirme ekranı güncellendi")
print("HAZIR")
