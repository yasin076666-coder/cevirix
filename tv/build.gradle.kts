plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val buildNo = (project.findProperty("buildNo") as String?)?.toIntOrNull() ?: 1

android {
    namespace = "com.bugra.altyazi.tv"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.bugra.altyazi.tv"
        minSdk = 24
        targetSdk = 34
        versionCode = buildNo
        versionName = "1.0.$buildNo"
    }

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
}

dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
