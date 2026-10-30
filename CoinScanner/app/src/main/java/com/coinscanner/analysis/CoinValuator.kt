package com.coinscanner.analysis

import com.coinscanner.api.PriceApiService
import com.coinscanner.data.*
import com.coinscanner.db.CoinDatabase

/**
 * Determines the value of a scanned coin using:
 * 1. Free online API (if available)
 * 2. Local comprehensive database (fallback)
 * 
 * Only outputs a premium value if the coin is worth more than face value.
 */
class CoinValuator(private val db: CoinDatabase) {

    suspend fun valuate(scan: CoinScanResult): CoinValuation {
        val denom = scan.denomination
        val year = scan.year
        val faceValue = denom?.faceValueCents ?: 1

        val description = buildDescription(scan)

        // No year or denomination = can't price
        if (denom == null || year == null) {
            return CoinValuation(
                coinDescription = description,
                faceValueCents = faceValue,
                estimatedValueCents = null,
                priceSource = "Unable to identify",
                errors = scan.detectedErrors,
                errorPremiumCents = 0,
                aboveFaceValue = false,
                notes = "Could not determine year or denomination from scan. Try re-scanning with better lighting."
            )
        }

        // ── Step 1: Try free API ──
        val apiValue = tryApiLookup(denom, year, scan.mintMark)
        
        // ── Step 2: Local database lookup ──
        val dbValue = tryDatabaseLookup(denom, year, scan.mintMark)

        // ── Step 3: Error premium from database ──
        val errorPremium = calculateErrorPremium(scan, denom, year)

        // Use API value if available, otherwise database
        val baseValueCents = apiValue ?: dbValue
        val source = when {
            apiValue != null -> "Online API (Numista)"
            dbValue != null -> "Local Database"
            else -> "No data available"
        }

        val totalValue = if (baseValueCents != null) {
            baseValueCents + errorPremium
        } else {
            if (errorPremium > 0) faceValue + errorPremium else null
        }

        val aboveFace = totalValue != null && totalValue > faceValue

        return CoinValuation(
            coinDescription = description,
            faceValueCents = faceValue,
            estimatedValueCents = totalValue,
            priceSource = source,
            errors = scan.detectedErrors,
            errorPremiumCents = errorPremium,
            aboveFaceValue = aboveFace,
            notes = buildNotes(scan, baseValueCents, errorPremium, aboveFace)
        )
    }

    private suspend fun tryApiLookup(denom: Denomination, year: Int, mintMark: String?): Int? {
        return try {
            PriceApiService.lookupPrice(denom, year, mintMark)
        } catch (e: Exception) {
            null // Silently fall back to local DB
        }
    }

    private suspend fun tryDatabaseLookup(denom: Denomination, year: Int, mintMark: String?): Int? {
        val dao = db.coinValueDao()
        // Try exact match first
        val exact = dao.find(denom.name, year, mintMark)
        if (exact != null) {
            // Return VF grade as reasonable "average circulated" value
            return exact.gradeVF ?: exact.gradeFine ?: exact.gradeVG
        }
        // Try any mint mark for that year
        val any = dao.findAnyMint(denom.name, year)
        return any?.gradeVF ?: any?.gradeFine ?: any?.gradeVG
    }

    private suspend fun calculateErrorPremium(scan: CoinScanResult, denom: Denomination, year: Int): Int {
        val dao = db.coinErrorDao()
        var premium = 0

        // Check for known errors matching this coin
        val knownErrors = dao.findErrors(denom.name, year, scan.mintMark)
            .ifEmpty { dao.findErrorsAnyMint(denom.name, year) }

        for (detected in scan.detectedErrors) {
            // Find matching known error
            val match = knownErrors.find { it.errorType == detected.errorType.name }
            if (match != null) {
                premium += match.estimatedPremiumCents
            } else {
                // Generic premium for detected but unlisted errors
                premium += when (detected.severity) {
                    ErrorSeverity.MINOR -> 50       // $0.50
                    ErrorSeverity.MODERATE -> 500    // $5.00
                    ErrorSeverity.MAJOR -> 2000      // $20.00
                    ErrorSeverity.RARE -> 10000      // $100.00
                }
            }
        }
        return premium
    }

    private fun buildDescription(scan: CoinScanResult): String {
        val parts = mutableListOf<String>()
        scan.year?.let { parts.add(it.toString()) }
        scan.mintMark?.let { parts.add("${it}-mint") }
        scan.denomination?.let { parts.add(it.label) }
        scan.designType?.let { parts.add("($it)") }
        return if (parts.isEmpty()) "Unknown Coin" else parts.joinToString(" ")
    }

    private fun buildNotes(scan: CoinScanResult, baseValue: Int?, errorPremium: Int, aboveFace: Boolean): String {
        val sb = StringBuilder()

        if (aboveFace) {
            val totalCents = (baseValue ?: scan.denomination?.faceValueCents ?: 0) + errorPremium
            sb.appendLine("💰 This coin may be worth \$${String.format("%.2f", totalCents / 100.0)}!")
        }

        if (scan.detectedErrors.isNotEmpty()) {
            sb.appendLine("\n⚠️ Potential errors detected:")
            for (err in scan.detectedErrors) {
                sb.appendLine("  • ${err.errorType.label}: ${err.description}")
            }
            if (errorPremium > 0) {
                sb.appendLine("  Error premium: +\$${String.format("%.2f", errorPremium / 100.0)}")
            }
        }

        if (baseValue == null && errorPremium == 0) {
            sb.appendLine("ℹ️ No premium data found. Coin is likely worth face value.")
            sb.appendLine("Tip: Ensure good lighting, flat angle, and clean coin surface for better OCR.")
        }

        // Silver content note
        val year = scan.year
        if (year != null) {
            when {
                scan.denomination == Denomination.DIME && year <= 1964 ->
                    sb.appendLine("\n🪙 Pre-1965 silver dime - contains 90% silver (melt value ~\$1.50+)")
                scan.denomination == Denomination.QUARTER && year <= 1964 ->
                    sb.appendLine("\n🪙 Pre-1965 silver quarter - contains 90% silver (melt value ~\$3.75+)")
                scan.denomination == Denomination.HALF_DOLLAR && year <= 1964 ->
                    sb.appendLine("\n🪙 1964 silver half - contains 90% silver (melt value ~\$7.50+)")
                scan.denomination == Denomination.HALF_DOLLAR && year in 1965..1970 ->
                    sb.appendLine("\n🪙 40% silver half dollar (melt value ~\$3.00+)")
            }
        }

        return sb.toString().trim()
    }
}
