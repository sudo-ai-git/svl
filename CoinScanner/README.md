# 🪙 Coin Scanner

Android app that photographs both sides of a US coin, reads text via OCR, detects minting errors, and estimates value.

## Features

- **Camera capture** with coin-positioning guide circle (CameraX)
- **OCR text extraction** from obverse + reverse (Google ML Kit, on-device, free)
- **Automatic identification**: year, mint mark, denomination, design type
- **Minting error detection**: doubled dies, off-center, wrong planchet, die cracks, missing letters, and 15+ more error types
- **Price valuation pipeline**:
  1. **Numista API** (free tier, 30 req/day) — real-time market data
  2. **CoinGecko** — silver spot price for pre-1965 coins (melt value floor)
  3. **Local Room database** — 400+ coin entries covering key dates, semi-keys, and all major US denominations from 1909–2025
- **Error premium calculation** from database of 60+ famous US coin errors with rarity ratings
- **Only displays value if above face value**

## Architecture

```
ui/
  MainActivity.kt        → Home screen
  CameraActivity.kt      → Two-step camera (front → back)
  ResultActivity.kt      → Valuation display

analysis/
  CoinTextParser.kt      → OCR text → structured CoinScanResult
  CoinValuator.kt        → Scan result → valuation (API + DB)

api/
  PriceApiService.kt     → Numista API + CoinGecko silver price

data/
  CoinModels.kt          → All data classes + Room entities

db/
  CoinDatabase.kt        → Room database setup
  CoinValueDao.kt        → Coin value queries
  CoinErrorDao.kt        → Error queries
  DatabaseSeeder.kt      → Pre-populated coin data (400+ values, 60+ errors)
```

## Setup

1. Open in Android Studio (Hedgehog+)
2. Sync Gradle
3. **(Optional)** Get a free Numista API key at [numista.com](https://en.numista.com/api/) and set it in `PriceApiService.setNumistaApiKey("YOUR_KEY")`
4. Run on device with camera (API 26+)

## Coin Database Coverage

| Denomination | Years | Key Data |
|---|---|---|
| Penny | 1909–2025 | Wheat, Memorial, Shield; VDB, steel, copper errors |
| Nickel | 1938–2025 | Jefferson, war silver (1942-45) |
| Dime | 1942–2025 | Mercury, Roosevelt silver + clad |
| Quarter | 1932–2025 | Washington silver, State, ATB, American |
| Half Dollar | 1964–2025 | Kennedy 90% silver, 40% silver, clad |
| Dollar | 2000–2020 | Sacagawea, Presidential |

## Famous Errors in Database

- 1955/1969-S/1972/1983/1995 Doubled Die pennies
- 1943 Copper / 1944 Steel wrong planchet cents
- Wide AM / Close AM varieties (1992, 1998, 1999, 2000)
- 2004-D Wisconsin Extra Leaf quarters
- Missing S proof dimes (1968, 1970, 1975, 1982, 1983)
- Presidential dollar missing edge lettering
- Sacagawea Cheerios / Wounded Eagle
- 60+ total entries with estimated premiums

## No API Key? No Problem

The app works fully offline with the built-in database. The Numista API and CoinGecko silver price are optional enhancements.
