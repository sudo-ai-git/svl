package com.coinscanner

import android.app.Application
import com.coinscanner.db.CoinDatabase

class CoinScannerApp : Application() {
    val database: CoinDatabase by lazy { CoinDatabase.getInstance(this) }
}
