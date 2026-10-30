package com.coinscanner.ui

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.coinscanner.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.btnScanCoin.setOnClickListener {
            startActivity(Intent(this, CameraActivity::class.java))
        }

        binding.btnAbout.setOnClickListener {
            Toast.makeText(this,
                "Coin Scanner v1.0\n\nTake photos of both sides of a US coin to identify it, detect minting errors, and estimate its value.",
                Toast.LENGTH_LONG
            ).show()
        }
    }
}
