package com.coinscanner.analysis

import com.coinscanner.data.CoinError
import com.coinscanner.data.CoinScanResult
import com.coinscanner.data.Denomination
import com.coinscanner.data.ErrorSeverity
import com.coinscanner.data.ErrorType

/**
 * Parses OCR text from both sides of a coin to extract structured data.
 * Handles common OCR misreads on coin surfaces (worn text, curved text, reflections).
 */
object CoinTextParser {

    private val YEAR_REGEX = Regex("""\b(1[789]\d{2}|20[0-2]\d)\b""")
    private val MINT_MARK_REGEX = Regex("""\b([PDSW])\b""")

    fun parse(obverseText: String, reverseText: String): CoinScanResult {
        val allText = "$obverseText $reverseText"
        val cleanObverse = cleanOcrText(obverseText)
        val cleanReverse = cleanOcrText(reverseText)
        val cleanAll = "$cleanObverse $cleanReverse"

        val year = extractYear(cleanAll)
        val mintMark = extractMintMark(cleanObverse, year)
        val denomination = Denomination.fromText(cleanReverse) ?: Denomination.fromText(cleanAll)
        val designType = detectDesignType(cleanAll, denomination, year)
        val errors = detectVisualErrors(cleanObverse, cleanReverse, year, denomination)

        return CoinScanResult(
            year = year,
            mintMark = mintMark,
            denomination = denomination,
            obverseText = cleanObverse,
            reverseText = cleanReverse,
            detectedErrors = errors,
            designType = designType
        )
    }

    private fun cleanOcrText(raw: String): String {
        return raw
            .replace(Regex("[|]"), "I")       // Common OCR misread
            .replace("0NE", "ONE")
            .replace("LFBERTY", "LIBERTY")
            .replace("LIBERT Y", "LIBERTY")
            .replace("L1BERTY", "LIBERTY")
            .replace("TRVST", "TRUST")        // Older coins actually use V for U
            .replace("VNUM", "UNUM")
            .replace("PIURIBUS", "PLURIBUS")
            .replace("AMERJCA", "AMERICA")
            .replace("AMERCA", "AMERICA")
            .replace("UN1TED", "UNITED")
            .replace("STAT ES", "STATES")
            .trim()
    }

    private fun extractYear(text: String): Int? {
        val matches = YEAR_REGEX.findAll(text).toList()
        if (matches.isEmpty()) return null
        // Prefer 4-digit year that looks reasonable for a US coin
        return matches
            .map { it.value.toInt() }
            .filter { it in 1793..2026 }
            .maxOrNull() // Take the most recent plausible year
    }

    private fun extractMintMark(obverse: String, year: Int?): String? {
        // Mint marks: P (Philadelphia), D (Denver), S (San Francisco), W (West Point)
        // On modern coins, mint mark is on obverse near date
        // P wasn't used on most coins before 1980 (except war nickels 1942-45)
        
        val text = obverse.uppercase()
        
        // Look for isolated single letter that's a valid mint mark
        // Typically near the date on obverse
        val candidates = mutableListOf<String>()
        
        // Check for explicit mint mark patterns
        for (mark in listOf("S", "D", "W")) {
            // Look for the letter appearing as isolated character
            if (Regex("""(?<![A-Z])${mark}(?![A-Z])""").containsMatchIn(text)) {
                candidates.add(mark)
            }
        }
        
        // P is tricky - only used after 1980 on most denominations
        if (year != null && year >= 1980) {
            if (Regex("""(?<![A-Z])P(?![A-Z])""").containsMatchIn(text)) {
                candidates.add("P")
            }
        }
        
        // If we find exactly one plausible mint mark, use it
        // Filter out letters that are likely part of words
        return candidates.firstOrNull()
    }

    private fun detectDesignType(text: String, denom: Denomination?, year: Int?): String? {
        if (year == null) return null
        
        return when (denom) {
            Denomination.PENNY -> when {
                text.contains("VDB") && year == 1909 -> "Lincoln Wheat VDB"
                year in 1909..1958 -> "Lincoln Wheat"
                year in 1959..2008 -> "Lincoln Memorial"
                year == 2009 -> "Lincoln Bicentennial"
                year >= 2010 -> "Lincoln Shield"
                else -> "Lincoln"
            }
            Denomination.NICKEL -> when {
                year < 1938 -> "Buffalo"
                year in 1942..1945 && (text.contains("P") || text.contains("S")) -> "Jefferson War Silver"
                year >= 1938 -> "Jefferson"
                else -> null
            }
            Denomination.DIME -> when {
                year < 1946 -> "Mercury"
                year <= 1964 -> "Roosevelt Silver"
                else -> "Roosevelt"
            }
            Denomination.QUARTER -> when {
                year <= 1964 -> "Washington Silver"
                year in 1999..2008 -> "State Quarter"
                year in 2010..2021 -> "ATB Quarter"
                year >= 2022 -> "American Quarter"
                else -> "Washington"
            }
            Denomination.HALF_DOLLAR -> when {
                year == 1964 -> "Kennedy Silver 90%"
                year in 1965..1970 -> "Kennedy Silver 40%"
                else -> "Kennedy"
            }
            Denomination.DOLLAR -> when {
                text.contains("SACAGAWEA") || text.contains("LIBERTY") && year in 2000..2008 -> "Sacagawea"
                year in 2007..2020 -> "Presidential"
                else -> "Dollar"
            }
            null -> null
        }
    }

    /**
     * Detect potential minting errors from OCR text analysis.
     * This checks for text anomalies that indicate known error types.
     */
    fun detectVisualErrors(
        obverse: String, reverse: String, year: Int?, denom: Denomination?
    ): List<CoinError> {
        val errors = mutableListOf<CoinError>()
        val ob = obverse.uppercase()
        val rev = reverse.uppercase()

        // ── Doubled Die Detection ──
        // Look for repeated/overlapping text fragments
        if (hasDoubledText(ob) || hasDoubledText(rev)) {
            errors.add(CoinError(
                ErrorType.DOUBLED_DIE,
                "Possible doubled die detected - text appears duplicated/overlapping",
                ErrorSeverity.MAJOR
            ))
        }

        // ── Missing Letters ──
        if (ob.contains("LIBERTY")) {
            val idx = ob.indexOf("LIBERTY")
            val chunk = ob.substring(idx, minOf(idx + 7, ob.length))
            if (chunk.length < 7) {
                errors.add(CoinError(ErrorType.MISSING_LETTERS, "LIBERTY appears incomplete", ErrorSeverity.MINOR))
            }
        }
        
        if (ob.contains("IN GOD WE TRUST") || ob.contains("IN GOD WE RUST")) {
            if (ob.contains("RUST")) {
                errors.add(CoinError(
                    ErrorType.DIE_CRACK,
                    "Possible 'In God We Rust' die fill/grease error - T filled in TRUST",
                    ErrorSeverity.MODERATE
                ))
            }
        }

        // ── Missing text that should be present ──
        if (!ob.contains("LIBERTY") && !ob.contains("LIBERT")) {
            errors.add(CoinError(ErrorType.MISSING_LETTERS, "LIBERTY not detected on obverse - possible weak strike or error", ErrorSeverity.MINOR))
        }
        if (!ob.contains("GOD") && !ob.contains("TRUST")) {
            errors.add(CoinError(ErrorType.MISSING_LETTERS, "IN GOD WE TRUST not detected - possible filled die or error", ErrorSeverity.MINOR))
        }
        if (!rev.contains("UNITED") && !rev.contains("STATES") && !rev.contains("AMERICA") && denom != null) {
            errors.add(CoinError(ErrorType.MISSING_LETTERS, "UNITED STATES OF AMERICA not detected on reverse", ErrorSeverity.MINOR))
        }
        if (!rev.contains("PLURIBUS") && !rev.contains("UNUM")) {
            errors.add(CoinError(ErrorType.MISSING_LETTERS, "E PLURIBUS UNUM not detected", ErrorSeverity.MINOR))
        }

        // ── Wrong metal detection (very rare but worth flagging) ──
        // 1943 copper / 1944 steel - can't detect from text alone, but note it
        if (year == 1943 && denom == Denomination.PENNY) {
            errors.add(CoinError(
                ErrorType.WRONG_PLANCHET,
                "⚠️ Check metal: 1943 cents should be STEEL (silver-gray). If copper/brown, this is extremely valuable!",
                ErrorSeverity.RARE
            ))
        }
        if (year == 1944 && denom == Denomination.PENNY) {
            errors.add(CoinError(
                ErrorType.WRONG_PLANCHET,
                "⚠️ Check metal: 1944 cents should be COPPER (brown). If steel/silver-gray, this is extremely valuable!",
                ErrorSeverity.RARE
            ))
        }

        return errors
    }

    /**
     * Simple heuristic: if OCR picks up the same word fragment twice in close proximity,
     * it may indicate doubled die (text struck twice at slightly different positions).
     */
    private fun hasDoubledText(text: String): Boolean {
        val words = text.split(Regex("\\s+")).filter { it.length >= 3 }
        val seen = mutableMapOf<String, Int>()
        for ((i, word) in words.withIndex()) {
            val prev = seen[word]
            if (prev != null && i - prev <= 3) {
                return true // Same word appears very close together
            }
            seen[word] = i
        }
        return false
    }
}
