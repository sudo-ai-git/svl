package com.coinscanner.app;

import android.os.Bundle;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        
        TextView textView = findViewById(R.id.textView);
        textView.setText("CoinScanner App\n\nCryptocurrency Scanner");
        
        Toast.makeText(this, "Welcome to CoinScanner!", Toast.LENGTH_SHORT).show();
    }
}
