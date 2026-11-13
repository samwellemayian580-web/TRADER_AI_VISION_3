plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.traderai.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.traderai.app"
        minSdk = 24
        targetSdk = 35
        versionCode = 4
        versionName = "3.1"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

chaquopy {
    defaultConfig {
        version = "3.11"

        pip {
            install("flask==3.0.3")
            install("numpy==1.26.2")
            install("pandas==2.1.3")
        }
    }

    sourceSets {
        getByName("main") {
            srcDir("../../")
        }
    }
}
