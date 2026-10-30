package com.coinscanner.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import com.coinscanner.CoinScannerApp
import com.coinscanner.analysis.CoinTextParser
import com.coinscanner.analysis.CoinValuator
import com.coinscanner.databinding.ActivityCameraBinding
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import kotlinx.coroutines.*
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

class CameraActivity : AppCompatActivity() {

    private lateinit var binding: ActivityCameraBinding
    private var imageCapture: ImageCapture? = null
    private var obverseUri: Uri? = null
    private var reverseUri: Uri? = null
    private var currentSide = Side.OBVERSE
    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())

    enum class Side { OBVERSE, REVERSE }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) startCamera() else {
            Toast.makeText(this, "Camera permission required", Toast.LENGTH_SHORT).show()
            finish()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityCameraBinding.inflate(layoutInflater)
        setContentView(binding.root)

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }

        updateInstructions()

        binding.btnCapture.setOnClickListener { takePhoto() }
        binding.btnRetake.setOnClickListener { retakeCurrentSide() }
    }

    private fun updateInstructions() {
        binding.tvInstructions.text = when (currentSide) {
            Side.OBVERSE -> "📷 Position the FRONT (obverse) of the coin\nFill the circle, good lighting, flat angle"
            Side.REVERSE -> "📷 Now flip! Position the BACK (reverse)\nKeep same distance and lighting"
        }
        binding.tvSideLabel.text = if (currentSide == Side.OBVERSE) "FRONT" else "BACK"
        binding.btnRetake.visibility = View.GONE
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(binding.viewFinder.surfaceProvider)
            }
            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
                .build()

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, preview, imageCapture)
            } catch (e: Exception) {
                Log.e("CoinScanner", "Camera bind failed", e)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun takePhoto() {
        val capture = imageCapture ?: return
        val file = File(
            getExternalFilesDir(null),
            "coin_${currentSide.name.lowercase()}_${SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())}.jpg"
        )
        val outputOptions = ImageCapture.OutputFileOptions.Builder(file).build()

        binding.btnCapture.isEnabled = false
        binding.progressBar.visibility = View.VISIBLE

        capture.takePicture(outputOptions, ContextCompat.getMainExecutor(this),
            object : ImageCapture.OnImageSavedCallback {
                override fun onImageSaved(output: ImageCapture.OutputFileResults) {
                    val uri = Uri.fromFile(file)
                    when (currentSide) {
                        Side.OBVERSE -> {
                            obverseUri = uri
                            binding.imgObversePreview.setImageURI(uri)
                            binding.imgObversePreview.visibility = View.VISIBLE
                            binding.btnRetake.visibility = View.VISIBLE
                            binding.btnCapture.isEnabled = true
                            binding.progressBar.visibility = View.GONE
                            // Move to reverse
                            currentSide = Side.REVERSE
                            updateInstructions()
                        }
                        Side.REVERSE -> {
                            reverseUri = uri
                            binding.imgReversePreview.setImageURI(uri)
                            binding.imgReversePreview.visibility = View.VISIBLE
                            binding.progressBar.visibility = View.VISIBLE
                            // Both captured - process
                            processImages()
                        }
                    }
                }

                override fun onError(e: ImageCaptureException) {
                    binding.btnCapture.isEnabled = true
                    binding.progressBar.visibility = View.GONE
                    Toast.makeText(this@CameraActivity, "Capture failed: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            })
    }

    private fun retakeCurrentSide() {
        when (currentSide) {
            Side.OBVERSE -> obverseUri = null
            Side.REVERSE -> {
                // Go back to obverse retake
                currentSide = Side.OBVERSE
                obverseUri = null
                binding.imgObversePreview.visibility = View.GONE
            }
        }
        updateInstructions()
    }

    private fun processImages() {
        val obUri = obverseUri ?: return
        val revUri = reverseUri ?: return

        binding.tvInstructions.text = "🔍 Analyzing coin..."
        binding.btnCapture.isEnabled = false

        val recognizer = TextRecognition.getClient(TextRecognizerOptions.Builder().build())

        scope.launch {
            try {
                val obImage = InputImage.fromFilePath(this@CameraActivity, obUri)
                val revImage = InputImage.fromFilePath(this@CameraActivity, revUri)

                // OCR both sides
                val obText = withContext(Dispatchers.IO) {
                    suspendCancellableCoroutine<String> { cont ->
                        recognizer.process(obImage)
                            .addOnSuccessListener { result -> cont.resumeWith(Result.success(result.text)) }
                            .addOnFailureListener { e -> cont.resumeWith(Result.success("")) }
                    }
                }
                val revText = withContext(Dispatchers.IO) {
                    suspendCancellableCoroutine<String> { cont ->
                        recognizer.process(revImage)
                            .addOnSuccessListener { result -> cont.resumeWith(Result.success(result.text)) }
                            .addOnFailureListener { e -> cont.resumeWith(Result.success("")) }
                    }
                }

                // Parse and valuate
                val scan = CoinTextParser.parse(obText, revText)
                val app = application as CoinScannerApp
                val valuation = CoinValuator(app.database).valuate(scan)

                // Navigate to results
                val intent = Intent(this@CameraActivity, ResultActivity::class.java).apply {
                    putExtra("description", valuation.coinDescription)
                    putExtra("face_value", valuation.faceValueCents)
                    putExtra("estimated_value", valuation.estimatedValueCents ?: -1)
                    putExtra("price_source", valuation.priceSource)
                    putExtra("error_count", valuation.errors.size)
                    putExtra("error_premium", valuation.errorPremiumCents)
                    putExtra("above_face", valuation.aboveFaceValue)
                    putExtra("notes", valuation.notes)
                    putExtra("obverse_text", scan.obverseText)
                    putExtra("reverse_text", scan.reverseText)
                    putExtra("errors_detail", valuation.errors.joinToString("\n") {
                        "${it.errorType.label} (${it.severity}): ${it.description}"
                    })
                    putExtra("obverse_uri", obUri.toString())
                    putExtra("reverse_uri", revUri.toString())
                }
                startActivity(intent)
                finish()

            } catch (e: Exception) {
                Toast.makeText(this@CameraActivity, "Analysis failed: ${e.message}", Toast.LENGTH_LONG).show()
                binding.btnCapture.isEnabled = true
                binding.progressBar.visibility = View.GONE
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
    }
}
