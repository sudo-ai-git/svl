package com.coinscanner.ui

import android.net.Uri
import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import com.coinscanner.databinding.ActivityResultBinding

class ResultActivity : AppCompatActivity() {

    private lateinit var binding: ActivityResultBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityResultBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val description = intent.getStringExtra("description") ?: "Unknown"
        val faceValue = intent.getIntExtra("face_value", 0)
        val estimatedValue = intent.getIntExtra("estimated_value", -1)
        val priceSource = intent.getStringExtra("price_source") ?: ""
        val errorCount = intent.getIntExtra("error_count", 0)
        val errorPremium = intent.getIntExtra("error_premium", 0)
        val aboveFace = intent.getBooleanExtra("above_face", false)
        val notes = intent.getStringExtra("notes") ?: ""
        val obverseText = intent.getStringExtra("obverse_text") ?: ""
        val reverseText = intent.getStringExtra("reverse_text") ?: ""
        val errorsDetail = intent.getStringExtra("errors_detail") ?: ""
        val obverseUri = intent.getStringExtra("obverse_uri")
        val reverseUri = intent.getStringExtra("reverse_uri")

        // Show coin images
        obverseUri?.let {
            binding.imgObverse.setImageURI(Uri.parse(it))
            binding.imgObverse.visibility = View.VISIBLE
        }
        reverseUri?.let {
            binding.imgReverse.setImageURI(Uri.parse(it))
            binding.imgReverse.visibility = View.VISIBLE
        }

        // Coin identification
        binding.tvCoinDescription.text = description
        binding.tvFaceValue.text = "Face Value: ${formatCents(faceValue)}"

        // Estimated value
        if (estimatedValue > 0) {
            binding.tvEstimatedValue.text = "Estimated Value: ${formatCents(estimatedValue)}"
            binding.tvEstimatedValue.visibility = View.VISIBLE
        } else {
            binding.tvEstimatedValue.text = "Estimated Value: Face value only"
            binding.tvEstimatedValue.visibility = View.VISIBLE
        }

        // Above face value highlight
        if (aboveFace) {
            binding.cardPremium.visibility = View.VISIBLE
            val premium = (estimatedValue - faceValue)
            binding.tvPremiumValue.text = "💰 Worth ${formatCents(estimatedValue)}!\nThat's ${formatCents(premium)} above face value!"
        } else {
            binding.cardPremium.visibility = View.GONE
        }

        // Price source
        binding.tvPriceSource.text = "Source: $priceSource"

        // Errors
        if (errorCount > 0) {
            binding.cardErrors.visibility = View.VISIBLE
            binding.tvErrorCount.text = "$errorCount potential error(s) detected"
            binding.tvErrorDetails.text = errorsDetail
            if (errorPremium > 0) {
                binding.tvErrorPremium.text = "Error premium: +${formatCents(errorPremium)}"
                binding.tvErrorPremium.visibility = View.VISIBLE
            }
        } else {
            binding.cardErrors.visibility = View.GONE
        }

        // OCR debug info
        binding.tvOcrObverse.text = "Obverse OCR:\n$obverseText"
        binding.tvOcrReverse.text = "Reverse OCR:\n$reverseText"

        // Notes
        binding.tvNotes.text = notes

        // Scan another
        binding.btnScanAnother.setOnClickListener { finish() }
    }

    private fun formatCents(cents: Int): String {
        return if (cents >= 100) {
            "$${String.format("%.2f", cents / 100.0)}"
        } else {
            "${cents}¢"
        }
    }
}
