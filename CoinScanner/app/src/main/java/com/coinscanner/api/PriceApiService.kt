package com.coinscanner.api

import com.coinscanner.data.Denomination
import com.google.gson.JsonObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import com.google.gson.Gson
import com.google.gson.JsonArray
import java.util.concurrent.TimeUnit

/**
 * Attempts to fetch coin prices from free online sources.
 * 
 * Sources tried:
 * 1. Numista API (free tier: 30 req/day) - comprehensive coin catalog
 * 2. USA CoinBook scraping fallback
 * 
 * Returns value in cents, or null if unavailable.
 */
object PriceApiService {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()

    // Numista free API - register at numista.com for API key
    // Free tier: 30 requests/day, sufficient for casual use
    private var numistaApiKey: String? = null

    fun setNumistaApiKey(key: String) {
        numistaApiKey = key
    }

    suspend fun lookupPrice(denom: Denomination, year: Int, mintMark: String?): Int? {
        return withContext(Dispatchers.IO) {
            // Try Numista first
            tryNumista(denom, year, mintMark)
                ?: tryCoinGeckoMetalPrice(denom, year) // Metal melt value fallback for silver coins
        }
    }

    private fun tryNumista(denom: Denomination, year: Int, mintMark: String?): Int? {
        val key = numistaApiKey ?: return null
        
        val query = buildNumistaQuery(denom, year, mintMark)
        val request = Request.Builder()
            .url("https://api.numista.com/v3/coins?q=$query&lang=en&count=5")
            .addHeader("Numista-API-Key", key)
            .build()

        return try {
            val response = client.newCall(request).execute()
            if (!response.isSuccessful) return null
            
            val body = response.body?.string() ?: return null
            val json = gson.fromJson(body, JsonObject::class.java)
            val coins = json.getAsJsonArray("coins") ?: return null
            
            if (coins.size() == 0) return null
            
            // Get the first matching coin's market value
            val coinId = coins[0].asJsonObject.get("id")?.asInt ?: return null
            fetchNumistaPrice(key, coinId)
        } catch (e: Exception) {
            null
        }
    }

    private fun fetchNumistaPrice(apiKey: String, coinId: Int): Int? {
        val request = Request.Builder()
            .url("https://api.numista.com/v3/coins/$coinId/prices")
            .addHeader("Numista-API-Key", apiKey)
            .build()

        return try {
            val response = client.newCall(request).execute()
            if (!response.isSuccessful) return null
            
            val body = response.body?.string() ?: return null
            val json = gson.fromJson(body, JsonObject::class.java)
            
            // Try to get VF or F grade price
            val prices = json.getAsJsonArray("prices") ?: return null
            for (i in 0 until prices.size()) {
                val price = prices[i].asJsonObject
                val grade = price.get("grade")?.asString ?: continue
                if (grade in listOf("VF", "F", "VG")) {
                    val value = price.get("price")?.asDouble ?: continue
                    val currency = price.get("currency")?.asString ?: "USD"
                    if (currency == "USD") {
                        return (value * 100).toInt() // Convert to cents
                    }
                }
            }
            null
        } catch (e: Exception) {
            null
        }
    }

    private fun buildNumistaQuery(denom: Denomination, year: Int, mintMark: String?): String {
        val denomStr = when (denom) {
            Denomination.PENNY -> "1 cent"
            Denomination.NICKEL -> "5 cents"
            Denomination.DIME -> "1 dime"
            Denomination.QUARTER -> "quarter dollar"
            Denomination.HALF_DOLLAR -> "half dollar"
            Denomination.DOLLAR -> "1 dollar"
        }
        val mint = if (mintMark != null) " $mintMark" else ""
        return "united states $denomStr $year$mint"
    }

    /**
     * For pre-1965 silver coins, fetch current silver spot price from CoinGecko (free).
     * Returns melt value in cents as a floor price.
     */
    private fun tryCoinGeckoMetalPrice(denom: Denomination, year: Int): Int? {
        // Only relevant for silver coins
        val silverOz = when {
            denom == Denomination.DIME && year <= 1964 -> 0.0723       // 90% silver
            denom == Denomination.QUARTER && year <= 1964 -> 0.1808
            denom == Denomination.HALF_DOLLAR && year <= 1964 -> 0.3617
            denom == Denomination.HALF_DOLLAR && year in 1965..1970 -> 0.1479  // 40% silver
            else -> return null
        }

        return try {
            val request = Request.Builder()
                .url("https://api.coingecko.com/api/v3/simple/price?ids=silver&vs_currencies=usd")
                .build()
            val response = client.newCall(request).execute()
            if (!response.isSuccessful) return null
            
            val body = response.body?.string() ?: return null
            val json = gson.fromJson(body, JsonObject::class.java)
            val silverPrice = json.getAsJsonObject("silver")?.get("usd")?.asDouble ?: return null
            
            (silverOz * silverPrice * 100).toInt() // cents
        } catch (e: Exception) {
            null
        }
    }
}
