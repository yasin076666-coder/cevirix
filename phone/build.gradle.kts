plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val buildNo = (project.findProperty("buildNo") as String?)?.toIntOrNull() ?: 1

android {
    namespace = "com.bugra.altyazi.phone"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.bugra.altyazi.phone"
        minSdk = 26
        targetSdk = 34
        versionCode = buildNo
        versionName = "1.0.$buildNo"

        // Galaxy S8+ ve tüm güncel telefonlar 64-bit ARM: diğer işlemci kütüphaneleri çıkarılır
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }
    }

    // Sabit imza: yeni sürüm eski sürümün üstüne sorunsuz kurulur
    signingConfigs {
        create("ortak") {
            storeFile = rootProject.file("keystore/altyazi.jks")
            storePassword = "altyazi123"
            keyAlias = "altyazi"
            keyPassword = "altyazi123"
        }
    }

    buildTypes {
        getByName("debug") {
            signingConfig = signingConfigs.getByName("ortak")
        }
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("ortak")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }

    packaging {
        resources {
            excludes += setOf(
                "META-INF/versions/9/OSGI-INF/MANIFEST.MF",
                "META-INF/DEPENDENCIES",
                "META-INF/LICENSE*",
                "META-INF/NOTICE*"
            )
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

    // Cihaz içi yazı okuma (OCR) ve çevrimdışı çeviri
    implementation("com.google.mlkit:text-recognition:16.0.1")
    implementation("com.google.mlkit:translate:17.0.3")

    // TV'ye altyazı yayını ve Gemini istekleri
    implementation("org.java-websocket:Java-WebSocket:1.5.7")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
