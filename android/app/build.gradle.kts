plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}

android {
    namespace = "org.openpaddisplay"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.openpaddisplay"
        minSdk = 30
        targetSdk = 35
        versionCode = 7
        versionName = "1.0.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
