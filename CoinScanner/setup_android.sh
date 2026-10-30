#!/bin/bash
cd /tmp
wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O cmdline-tools.zip
unzip -q -o cmdline-tools.zip
mkdir -p ~/Android/Sdk/cmdline-tools
mv cmdline-tools ~/Android/Sdk/cmdline-tools/latest
echo "export ANDROID_HOME=~/Android/Sdk" >> ~/.bashrc
echo "export PATH=\$PATH:\$ANDROID_HOME/cmdline-tools/latest/bin" >> ~/.bashrc
export ANDROID_HOME=~/Android/Sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin
yes | sdkmanager --licenses > /dev/null 2>&1
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" > /dev/null 2>&1
echo "Android SDK setup complete"
