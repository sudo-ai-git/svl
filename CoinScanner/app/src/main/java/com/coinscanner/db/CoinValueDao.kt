package com.coinscanner.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.coinscanner.data.CoinValueEntity

@Dao
interface CoinValueDao {
    @Query("""
        SELECT * FROM coin_values 
        WHERE denomination = :denomination AND year = :year 
        AND (mintMark = :mintMark OR (:mintMark IS NULL AND mintMark IS NULL))
        LIMIT 1
    """)
    suspend fun find(denomination: String, year: Int, mintMark: String?): CoinValueEntity?

    @Query("""
        SELECT * FROM coin_values 
        WHERE denomination = :denomination AND year = :year 
        LIMIT 1
    """)
    suspend fun findAnyMint(denomination: String, year: Int): CoinValueEntity?

    @Query("SELECT * FROM coin_values WHERE denomination = :denomination ORDER BY year")
    suspend fun allForDenomination(denomination: String): List<CoinValueEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(values: List<CoinValueEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(value: CoinValueEntity)
}
