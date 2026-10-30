package com.coinscanner.db

import com.coinscanner.data.CoinErrorEntity
import com.coinscanner.data.CoinValueEntity

/**
 * Seeds the database with a comprehensive collection of US coin values and known errors.
 * Values are in CENTS. Grades: VG=Very Good, F=Fine, VF=Very Fine, EF=Extremely Fine, AU=About Unc, UNC=Uncirculated.
 * This is a curated subset of key dates, semi-keys, and common dates with notable premiums.
 */
object DatabaseSeeder {

    suspend fun seed(db: CoinDatabase) {
        db.coinValueDao().insertAll(coinValues())
        db.coinErrorDao().insertAll(coinErrors())
    }

    private fun coinValues(): List<CoinValueEntity> = buildList {
        // ════════════════════════════════════════════════
        //  LINCOLN PENNIES (Wheat: 1909-1958, Memorial: 1959-2008, Shield: 2010+)
        // ════════════════════════════════════════════════
        
        // Key dates - Wheat cents
        cv("PENNY", 1909, "S", "Lincoln Wheat VDB", 90000, 110000, 150000, 200000, 280000, 450000)
        cv("PENNY", 1909, "S", "Lincoln Wheat", 10000, 14000, 20000, 30000, 45000, 75000)
        cv("PENNY", 1909, null, "Lincoln Wheat VDB", 1000, 1500, 2000, 3000, 5000, 12000)
        cv("PENNY", 1914, "D", "Lincoln Wheat", 25000, 40000, 75000, 130000, 200000, 400000)
        cv("PENNY", 1922, null, "Lincoln Wheat No D", 60000, 85000, 150000, 300000, 500000, null)
        cv("PENNY", 1931, "S", "Lincoln Wheat", 8000, 10000, 13000, 16000, 22000, 35000)
        cv("PENNY", 1943, null, "Lincoln Steel", 10, 15, 25, 50, 100, 300)
        cv("PENNY", 1943, "D", "Lincoln Steel", 10, 20, 30, 60, 120, 400)
        cv("PENNY", 1943, "S", "Lincoln Steel", 15, 25, 40, 75, 150, 500)
        cv("PENNY", 1944, "D", "Lincoln Wheat", 5, 10, 15, 25, 50, 200)
        // 1943 copper & 1944 steel are extreme rarities
        cv("PENNY", 1955, null, "Lincoln Wheat", 5, 8, 15, 30, 75, 250)
        cv("PENNY", 1958, null, "Lincoln Wheat", 5, 8, 12, 20, 50, 150)
        
        // Semi-key wheat cents
        for (y in listOf(1910, 1911, 1912, 1913, 1915)) {
            cv("PENNY", y, "S", "Lincoln Wheat", 1500, 2500, 5000, 8000, 12000, 25000)
        }
        cv("PENNY", 1924, "D", "Lincoln Wheat", 3500, 5000, 10000, 20000, 35000, 65000)
        cv("PENNY", 1926, "S", "Lincoln Wheat", 1000, 1800, 4000, 8000, 15000, 35000)
        
        // Common wheat cents (representative)
        for (y in 1940..1958) {
            if (y != 1943) cv("PENNY", y, null, "Lincoln Wheat", 3, 5, 8, 15, 30, 100)
        }
        
        // Lincoln Memorial key/semi-key
        cv("PENNY", 1960, null, "Lincoln Memorial Small Date", 25, 50, 100, 200, 400, 1500)
        cv("PENNY", 1960, "D", "Lincoln Memorial Small Date", 5, 10, 15, 25, 50, 200)
        cv("PENNY", 1969, "S", "Lincoln Memorial", 5, 10, 15, 30, 75, 300)
        cv("PENNY", 1972, null, "Lincoln Memorial", 2, 3, 5, 10, 25, 100)
        cv("PENNY", 1982, null, "Lincoln Memorial Zinc Small Date", 2, 3, 5, 10, 25, 100)
        cv("PENNY", 1982, null, "Lincoln Memorial Copper Large Date", 2, 3, 5, 10, 25, 100)
        cv("PENNY", 1983, null, "Lincoln Memorial Zinc", 1, 2, 3, 5, 10, 50)
        cv("PENNY", 1992, "D", "Lincoln Memorial Close AM", 2000, 5000, 10000, 15000, 20000, 50000)
        cv("PENNY", 1998, null, "Lincoln Memorial Wide AM", 2000, 5000, 15000, 20000, 25000, 40000)
        cv("PENNY", 1999, null, "Lincoln Memorial Wide AM", 5000, 10000, 20000, 30000, 40000, 75000)
        cv("PENNY", 2000, null, "Lincoln Memorial Wide AM", 2000, 5000, 10000, 15000, 20000, 30000)
        
        // Common modern pennies (2000+)
        for (y in 2000..2025) {
            cv("PENNY", y, null, "Lincoln", 1, 1, 1, 1, 1, 25)
            cv("PENNY", y, "D", "Lincoln", 1, 1, 1, 1, 1, 25)
        }

        // ════════════════════════════════════════════════
        //  JEFFERSON NICKELS (1938+)
        // ════════════════════════════════════════════════
        cv("NICKEL", 1938, "D", "Jefferson", 200, 300, 500, 800, 1200, 2500)
        cv("NICKEL", 1939, "D", "Jefferson", 500, 800, 1500, 3000, 5500, 12000)
        cv("NICKEL", 1939, "S", "Jefferson", 300, 500, 800, 1200, 2000, 5000)
        cv("NICKEL", 1942, "D", "Jefferson", 50, 75, 150, 250, 400, 800)
        // War Nickels (silver, 35% Ag) 1942P-1945
        for (y in 1942..1945) {
            cv("NICKEL", y, "P", "Jefferson War Silver", 100, 150, 200, 300, 500, 1200)
            cv("NICKEL", y, "S", "Jefferson War Silver", 100, 150, 200, 300, 500, 1200)
            if (y >= 1943) cv("NICKEL", y, "D", "Jefferson War Silver", 100, 150, 200, 300, 500, 1500)
        }
        cv("NICKEL", 1950, "D", "Jefferson", 1500, 2000, 2500, 3000, 4000, 8000)
        
        // Common modern nickels
        for (y in 2000..2025) {
            cv("NICKEL", y, null, "Jefferson", 5, 5, 5, 5, 10, 50)
            cv("NICKEL", y, "D", "Jefferson", 5, 5, 5, 5, 10, 50)
        }

        // ════════════════════════════════════════════════
        //  ROOSEVELT DIMES (1946+)
        // ════════════════════════════════════════════════
        // Silver Roosevelts (1946-1964) - 90% silver
        for (y in 1946..1964) {
            val base = if (y < 1955) 200 else 150
            cv("DIME", y, null, "Roosevelt Silver", base, base+50, base+100, base+200, base+400, base+1000)
            cv("DIME", y, "D", "Roosevelt Silver", base, base+50, base+100, base+200, base+400, base+1000)
            if (y in 1946..1955) cv("DIME", y, "S", "Roosevelt Silver", base, base+50, base+100, base+200, base+400, base+1200)
        }
        cv("DIME", 1949, "S", "Roosevelt Silver", 300, 500, 800, 1500, 2500, 6000)
        cv("DIME", 1950, "S", "Roosevelt Silver", 250, 400, 600, 1200, 2000, 4500)
        cv("DIME", 1955, "D", "Roosevelt Silver", 150, 200, 250, 350, 500, 1200)
        cv("DIME", 1996, "W", "Roosevelt", 500, 800, 1200, 1800, 2500, 5000)
        
        // Common clad dimes
        for (y in 2000..2025) {
            cv("DIME", y, null, "Roosevelt", 10, 10, 10, 10, 15, 50)
            cv("DIME", y, "D", "Roosevelt", 10, 10, 10, 10, 15, 50)
        }

        // ════════════════════════════════════════════════
        //  WASHINGTON QUARTERS (1932+)
        // ════════════════════════════════════════════════
        cv("QUARTER", 1932, "D", "Washington Silver", 10000, 15000, 25000, 40000, 55000, 100000)
        cv("QUARTER", 1932, "S", "Washington Silver", 8000, 12000, 18000, 28000, 40000, 70000)
        cv("QUARTER", 1936, "D", "Washington Silver", 2000, 4000, 10000, 20000, 40000, 70000)
        cv("QUARTER", 1937, "S", "Washington Silver", 1500, 3000, 8000, 15000, 25000, 45000)
        cv("QUARTER", 1940, "D", "Washington Silver", 500, 800, 1200, 2000, 3500, 8000)
        
        // Silver Washingtons general (1932-1964)
        for (y in 1945..1964) {
            cv("QUARTER", y, null, "Washington Silver", 500, 550, 600, 700, 1000, 2000)
            cv("QUARTER", y, "D", "Washington Silver", 500, 550, 600, 700, 1000, 2000)
        }
        
        // State Quarters (1999-2008) - most common
        for (y in 1999..2008) {
            cv("QUARTER", y, null, "State Quarter", 25, 25, 25, 25, 50, 200)
            cv("QUARTER", y, "D", "State Quarter", 25, 25, 25, 25, 50, 200)
        }
        // ATB Quarters (2010-2021)
        for (y in 2010..2021) {
            cv("QUARTER", y, null, "ATB Quarter", 25, 25, 25, 25, 50, 150)
            cv("QUARTER", y, "D", "ATB Quarter", 25, 25, 25, 25, 50, 150)
        }
        // Women/American quarters (2022+)
        for (y in 2022..2025) {
            cv("QUARTER", y, null, "American Quarter", 25, 25, 25, 25, 50, 150)
            cv("QUARTER", y, "D", "American Quarter", 25, 25, 25, 25, 50, 150)
        }

        // ════════════════════════════════════════════════
        //  KENNEDY HALF DOLLARS (1964+)
        // ════════════════════════════════════════════════
        cv("HALF_DOLLAR", 1964, null, "Kennedy Silver 90%", 800, 900, 1000, 1100, 1200, 2000)
        cv("HALF_DOLLAR", 1964, "D", "Kennedy Silver 90%", 800, 900, 1000, 1100, 1200, 2000)
        for (y in 1965..1970) {
            cv("HALF_DOLLAR", y, null, "Kennedy Silver 40%", 300, 350, 400, 500, 600, 1200)
        }
        cv("HALF_DOLLAR", 1970, "D", "Kennedy Silver 40%", 2000, 3000, 5000, 8000, 12000, 25000)
        
        // Clad halves
        for (y in 2000..2025) {
            cv("HALF_DOLLAR", y, null, "Kennedy", 50, 50, 50, 50, 75, 200)
            cv("HALF_DOLLAR", y, "D", "Kennedy", 50, 50, 50, 50, 75, 200)
        }

        // ════════════════════════════════════════════════
        //  DOLLAR COINS
        // ════════════════════════════════════════════════
        // Sacagawea
        cv("DOLLAR", 2000, "P", "Sacagawea Cheerios", 500000, 750000, 1000000, null, null, null)
        cv("DOLLAR", 2000, "P", "Sacagawea Wounded Eagle", 5000, 10000, 20000, 30000, 40000, 75000)
        for (y in 2000..2008) {
            cv("DOLLAR", y, null, "Sacagawea", 100, 100, 100, 100, 150, 300)
            cv("DOLLAR", y, "D", "Sacagawea", 100, 100, 100, 100, 150, 300)
        }
        // Presidential Dollars
        for (y in 2007..2020) {
            cv("DOLLAR", y, null, "Presidential", 100, 100, 100, 100, 150, 300)
            cv("DOLLAR", y, "D", "Presidential", 100, 100, 100, 100, 150, 300)
        }
    }

    private fun coinErrors(): List<CoinErrorEntity> = buildList {
        // ════════════════════════════════════════════════
        //  FAMOUS PENNY ERRORS
        // ════════════════════════════════════════════════
        ce("PENNY", 1955, null, "DOUBLED_DIE", "1955 Doubled Die Obverse - dramatic doubling of date and legends", "RARE", 150000, "Rare")
        ce("PENNY", 1969, "S", "DOUBLED_DIE", "1969-S Doubled Die Obverse - strong doubling of LIBERTY and IN GOD WE TRUST", "RARE", 5000000, "Very Rare")
        ce("PENNY", 1972, null, "DOUBLED_DIE", "1972 Doubled Die Obverse - strong doubling visible on date", "MAJOR", 50000, "Scarce")
        ce("PENNY", 1983, null, "DOUBLED_DIE", "1983 Doubled Die Reverse - ONE CENT strongly doubled", "MAJOR", 40000, "Scarce")
        ce("PENNY", 1984, null, "DOUBLED_DIE", "1984 Doubled Die Obverse - doubled ear on Lincoln", "MODERATE", 15000, "Scarce")
        ce("PENNY", 1995, null, "DOUBLED_DIE", "1995 Doubled Die Obverse - doubling of LIBERTY and IN GOD WE TRUST", "MAJOR", 5000, "Common")
        ce("PENNY", 2017, null, "DOUBLED_DIE", "2017-P Doubled Die Obverse - doubling on IN GOD WE TRUST", "MINOR", 2500, "Common")
        
        // 1943 Copper penny (wrong planchet)
        ce("PENNY", 1943, null, "WRONG_PLANCHET", "1943 Bronze/Copper Cent - struck on copper planchet instead of steel", "RARE", 20000000, "Unique")
        ce("PENNY", 1943, "D", "WRONG_PLANCHET", "1943-D Bronze/Copper Cent", "RARE", 15000000, "Unique")
        ce("PENNY", 1943, "S", "WRONG_PLANCHET", "1943-S Bronze/Copper Cent", "RARE", 10000000, "Unique")
        
        // 1944 Steel penny (wrong planchet)
        ce("PENNY", 1944, null, "WRONG_PLANCHET", "1944 Steel Cent - struck on steel planchet instead of copper", "RARE", 7500000, "Very Rare")
        ce("PENNY", 1944, "D", "WRONG_PLANCHET", "1944-D Steel Cent", "RARE", 5000000, "Very Rare")
        ce("PENNY", 1944, "S", "WRONG_PLANCHET", "1944-S Steel Cent", "RARE", 10000000, "Very Rare")
        
        // BIE errors (die breaks spelling BIE in LIBERTY)
        for (y in 1950..1970) {
            ce("PENNY", y, null, "DIE_CRACK", "BIE error - die crack between B and E of LIBERTY appears as letter I", "MINOR", 500, "Common")
        }
        
        // Off-center strikes (generic, can occur any year)
        ce("PENNY", 1999, null, "OFF_CENTER", "Off-center strike - date visible, 10-50% off center", "MODERATE", 2000, "Scarce")
        
        // Wide AM / Close AM varieties
        ce("PENNY", 1992, "D", "OTHER", "1992-D Close AM reverse - AM in AMERICA touching", "RARE", 50000, "Very Rare")
        ce("PENNY", 1998, null, "OTHER", "1998 Wide AM reverse - AM in AMERICA spaced apart", "MAJOR", 25000, "Rare")
        ce("PENNY", 1999, null, "OTHER", "1999 Wide AM reverse - AM in AMERICA spaced apart", "MAJOR", 50000, "Rare")
        ce("PENNY", 2000, null, "OTHER", "2000 Wide AM reverse - AM in AMERICA spaced apart", "MAJOR", 20000, "Scarce")
        
        // ════════════════════════════════════════════════
        //  NICKEL ERRORS
        // ════════════════════════════════════════════════
        ce("NICKEL", 1939, null, "DOUBLED_DIE", "1939 Doubled Die Reverse - MONTICELLO doubled", "MAJOR", 10000, "Scarce")
        ce("NICKEL", 1943, "P", "DOUBLED_DIE", "1943-P Doubled Die Obverse - eye doubled", "MODERATE", 5000, "Scarce")
        ce("NICKEL", 1949, "D", "REPUNCHED_MINTMARK", "1949-D/S Overmintmark - D over S visible", "MODERATE", 8000, "Scarce")
        ce("NICKEL", 1954, "S", "REPUNCHED_MINTMARK", "1954-S/D Overmintmark", "MODERATE", 3000, "Scarce")
        ce("NICKEL", 1964, "D", "DOUBLED_DIE", "1964-D Doubled Die - FIVE CENTS doubled", "MODERATE", 3000, "Common")
        ce("NICKEL", 2004, "D", "EXTRA_METAL", "2004-D Wisconsin Extra Leaf quarter struck on nickel planchet", "RARE", 100000, "Very Rare")
        ce("NICKEL", 2005, null, "DOUBLED_DIE", "2005-P Bison Speared Bison - die gouge through bison", "MODERATE", 5000, "Common")
        
        // ════════════════════════════════════════════════
        //  DIME ERRORS
        // ════════════════════════════════════════════════
        ce("DIME", 1942, null, "DOUBLED_DIE", "1942/1 Mercury Dime - overdate clearly visible", "RARE", 50000, "Rare")
        ce("DIME", 1964, "D", "DOUBLED_DIE", "1964-D Doubled Die Reverse", "MODERATE", 3000, "Scarce")
        ce("DIME", 1965, null, "WRONG_PLANCHET", "1965 Silver Dime - struck on 90% silver planchet", "RARE", 900000, "Very Rare")
        ce("DIME", 1968, null, "MISSING_LETTERS", "1968 No S Proof Dime - missing S mintmark on proof", "RARE", 2000000, "Very Rare")
        ce("DIME", 1970, null, "MISSING_LETTERS", "1970 No S Proof Dime", "RARE", 5000000, "Very Rare")
        ce("DIME", 1975, null, "MISSING_LETTERS", "1975 No S Proof Dime", "RARE", 30000000, "Unique")
        ce("DIME", 1982, null, "MISSING_LETTERS", "1982 No Mintmark Dime (No P) - missing P mintmark", "MAJOR", 10000, "Scarce")
        ce("DIME", 1983, null, "MISSING_LETTERS", "1983 No S Proof Dime", "RARE", 1500000, "Very Rare")
        
        // ════════════════════════════════════════════════
        //  QUARTER ERRORS
        // ════════════════════════════════════════════════
        ce("QUARTER", 1937, null, "DOUBLED_DIE", "1937 Doubled Die Obverse", "MAJOR", 30000, "Rare")
        ce("QUARTER", 1964, "D", "DOUBLED_DIE", "1964-D Doubled Die Reverse - heavy doubling", "MAJOR", 15000, "Scarce")
        ce("QUARTER", 1970, null, "WRONG_PLANCHET", "1970 Quarter struck on 1941 Canadian quarter", "RARE", 3500000, "Unique")
        
        // State Quarter errors
        ce("QUARTER", 1999, null, "OFF_CENTER", "1999 Delaware Quarter off-center strike", "MODERATE", 5000, "Scarce")
        ce("QUARTER", 2000, null, "WRONG_PLANCHET", "2000 Sacagawea dollar / State Quarter mule", "RARE", 10000000, "Unique")
        ce("QUARTER", 2004, "D", "EXTRA_METAL", "2004-D Wisconsin Extra Leaf High - extra leaf on corn", "MAJOR", 30000, "Scarce")
        ce("QUARTER", 2004, "D", "EXTRA_METAL", "2004-D Wisconsin Extra Leaf Low - extra leaf on corn", "MAJOR", 20000, "Scarce")
        ce("QUARTER", 2005, null, "MISSING_LETTERS", "2005 Minnesota Quarter Extra Tree / Die Breaks", "MODERATE", 5000, "Common")
        ce("QUARTER", 2005, null, "DIE_CRACK", "2005 Kansas Quarter In God We Rust - die fill error", "MINOR", 10000, "Scarce")
        ce("QUARTER", 2009, "D", "DOUBLED_DIE", "2009-D DC Quarter Doubled Die Reverse", "MODERATE", 2500, "Common")
        
        // ════════════════════════════════════════════════
        //  HALF DOLLAR ERRORS
        // ════════════════════════════════════════════════
        ce("HALF_DOLLAR", 1964, null, "DOUBLED_DIE", "1964 Kennedy Accented Hair - enhanced hair detail", "MAJOR", 20000, "Scarce")
        ce("HALF_DOLLAR", 1964, "D", "DOUBLED_DIE", "1964-D Double Die Obverse", "MODERATE", 5000, "Scarce")
        ce("HALF_DOLLAR", 1966, null, "DOUBLED_DIE", "1966 Doubled Die Obverse - strong doubling on IN GOD WE TRUST", "MAJOR", 15000, "Scarce")
        ce("HALF_DOLLAR", 1974, "D", "DOUBLED_DIE", "1974-D Doubled Die Obverse", "MODERATE", 3000, "Common")
        
        // ════════════════════════════════════════════════
        //  DOLLAR ERRORS
        // ════════════════════════════════════════════════
        ce("DOLLAR", 2000, null, "OTHER", "2000-P Sacagawea Wounded Eagle - die gouge on eagle's breast", "MAJOR", 30000, "Scarce")
        ce("DOLLAR", 2000, null, "OTHER", "2000-P Sacagawea Cheerios Dollar - enhanced tail feathers", "RARE", 500000, "Very Rare")
        ce("DOLLAR", 2007, null, "MISSING_EDGE_LETTERING", "2007 Washington Dollar Missing Edge Lettering", "MAJOR", 5000, "Common")
        ce("DOLLAR", 2007, null, "MISSING_EDGE_LETTERING", "2007 Adams Dollar Missing Edge Lettering", "MAJOR", 5000, "Common")
        ce("DOLLAR", 2007, null, "MISSING_EDGE_LETTERING", "2007 Jefferson Dollar Missing Edge Lettering", "MAJOR", 5000, "Common")
        ce("DOLLAR", 2008, null, "MISSING_EDGE_LETTERING", "2008 Presidential Dollar Missing Edge Lettering", "MAJOR", 3000, "Common")
        ce("DOLLAR", 2014, "D", "MISSING_EDGE_LETTERING", "2014-D Presidential Dollar Missing Edge Lettering", "MAJOR", 3000, "Scarce")
        
        // Generic error types that can appear on any denomination/year
        // These serve as reference for the error detection algorithm
    }

    private fun MutableList<CoinValueEntity>.cv(
        denom: String, year: Int, mint: String?, design: String?,
        vg: Int?, f: Int?, vf: Int?, ef: Int?, au: Int?, unc: Int?, notes: String? = null
    ) {
        add(CoinValueEntity(0, denom, year, mint, design, vg, f, vf, ef, au, unc, notes))
    }

    private fun MutableList<CoinErrorEntity>.ce(
        denom: String, year: Int, mint: String?, errorType: String,
        desc: String, severity: String, premium: Int, rarity: String?
    ) {
        add(CoinErrorEntity(0, denom, year, mint, errorType, desc, severity, premium, rarity))
    }
}
