package com.coinscanner.data

import androidx.room.Entity
import androidx.room.PrimaryKey

/** Parsed data extracted from OCR of both coin sides */
data class CoinScanResult(
    val year: Int?,
    val mintMark: String?,          // P, D, S, W, or null (Philadelphia pre-1980)
    val denomination: Denomination?,
    val obverseText: String,
    val reverseText: String,
    val detectedErrors: List<CoinError>,
    val designType: String?         // e.g. "Lincoln Memorial", "Washington Eagle"
)

enum class Denomination(val label: String, val faceValueCents: Int) {
    PENNY("Penny", 1),
    NICKEL("Nickel", 5),
    DIME("Dime", 10),
    QUARTER("Quarter", 25),
    HALF_DOLLAR("Half Dollar", 50),
    DOLLAR("Dollar", 100);

    companion object {
        fun fromText(text: String): Denomination? {
            val t = text.uppercase()
            return when {
                t.contains("ONE CENT") || t.contains("1 CENT") || t.contains("ONE¢") -> PENNY
                t.contains("FIVE CENTS") || t.contains("5 CENTS") -> NICKEL
                t.contains("ONE DIME") || t.contains("10 CENTS") -> DIME
                t.contains("QUARTER DOLLAR") || t.contains("25 CENTS") -> QUARTER
                t.contains("HALF DOLLAR") || t.contains("50 CENTS") -> HALF_DOLLAR
                t.contains("ONE DOLLAR") || t.contains("$1") -> DOLLAR
                else -> null
            }
        }
    }
}

data class CoinError(
    val errorType: ErrorType,
    val description: String,
    val severity: ErrorSeverity = ErrorSeverity.MINOR
)

enum class ErrorSeverity { MINOR, MODERATE, MAJOR, RARE }

enum class ErrorType(val label: String) {
    DOUBLED_DIE("Doubled Die"),
    OFF_CENTER("Off-Center Strike"),
    WRONG_PLANCHET("Wrong Planchet"),
    DIE_CRACK("Die Crack / Cud"),
    CLIPPED_PLANCHET("Clipped Planchet"),
    BROADSTRIKE("Broadstrike"),
    DIE_CLASH("Die Clash"),
    REPUNCHED_MINTMARK("Repunched Mint Mark"),
    REPUNCHED_DATE("Repunched Date"),
    MISSING_EDGE_LETTERING("Missing Edge Lettering"),
    WRONG_DESIGN("Wrong Design / Mule"),
    ROTATED_DIE("Rotated Die"),
    PARTIAL_COLLAR("Partial Collar Strike"),
    LAMINATION("Lamination Error"),
    STRIKE_THROUGH("Strike Through"),
    DOUBLE_STRUCK("Double Struck"),
    BLANK_PLANCHET("Blank Planchet"),
    MISSING_LETTERS("Missing Letters/Digits"),
    EXTRA_METAL("Extra Metal / Die Break"),
    OTHER("Other Error");
}

/** Pricing result */
data class CoinValuation(
    val coinDescription: String,
    val faceValueCents: Int,
    val estimatedValueCents: Int?,
    val priceSource: String,        // "API", "Local Database", "No data"
    val errors: List<CoinError>,
    val errorPremiumCents: Int,
    val aboveFaceValue: Boolean,
    val notes: String
)

// ── Room Entities ──

@Entity(tableName = "coin_values")
data class CoinValueEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val denomination: String,       // PENNY, NICKEL, etc.
    val year: Int,
    val mintMark: String?,          // P, D, S, W, null
    val designType: String?,
    val gradeVG: Int?,              // value in cents at VG grade
    val gradeFine: Int?,
    val gradeVF: Int?,
    val gradeEF: Int?,
    val gradeAU: Int?,
    val gradeUNC: Int?,
    val notes: String? = null
)

@Entity(tableName = "coin_errors")
data class CoinErrorEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val denomination: String,
    val year: Int,
    val mintMark: String?,
    val errorType: String,          // ErrorType.name
    val description: String,
    val severity: String,           // ErrorSeverity.name
    val estimatedPremiumCents: Int, // additional value above base
    val rarity: String?             // "Common", "Scarce", "Rare", "Very Rare", "Unique"
)
