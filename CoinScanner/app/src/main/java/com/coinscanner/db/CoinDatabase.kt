package com.coinscanner.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.sqlite.db.SupportSQLiteDatabase
import com.coinscanner.data.CoinErrorEntity
import com.coinscanner.data.CoinValueEntity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

@Database(entities = [CoinValueEntity::class, CoinErrorEntity::class], version = 1)
abstract class CoinDatabase : RoomDatabase() {
    abstract fun coinValueDao(): CoinValueDao
    abstract fun coinErrorDao(): CoinErrorDao

    companion object {
        @Volatile private var INSTANCE: CoinDatabase? = null

        fun getInstance(context: Context): CoinDatabase =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    CoinDatabase::class.java,
                    "coin_scanner.db"
                )
                .addCallback(SeedCallback())
                .build().also { INSTANCE = it }
            }
    }

    private class SeedCallback : Callback() {
        override fun onCreate(db: SupportSQLiteDatabase) {
            super.onCreate(db)
            INSTANCE?.let { database ->
                CoroutineScope(Dispatchers.IO).launch {
                    DatabaseSeeder.seed(database)
                }
            }
        }
    }
}
