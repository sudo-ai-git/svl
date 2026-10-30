package com.coinscanner.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.coinscanner.data.CoinErrorEntity

@Dao
interface CoinErrorDao {
    @Query("""
        SELECT * FROM coin_errors 
        WHERE denomination = :denomination AND year = :year 
        AND (mintMark = :mintMark OR (:mintMark IS NULL AND mintMark IS NULL))
    """)
    suspend fun findErrors(denomination: String, year: Int, mintMark: String?): List<CoinErrorEntity>

    @Query("""
        SELECT * FROM coin_errors 
        WHERE denomination = :denomination AND year = :year
    """)
    suspend fun findErrorsAnyMint(denomination: String, year: Int): List<CoinErrorEntity>

    @Query("SELECT * FROM coin_errors WHERE errorType = :errorType")
    suspend fun findByErrorType(errorType: String): List<CoinErrorEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(errors: List<CoinErrorEntity>)
}
