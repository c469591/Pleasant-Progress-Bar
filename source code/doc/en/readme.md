# Pleasant Progress Bar NVDA Add-on

Make NVDA's progress bar sound effects more pleasant and melodious, supporting multiple waveforms and custom configurations.

## Audio Preview

Traditional progress bar sound: Monotonous beeping →
[Click to download original progress bar recording.wav](https://github.com/c469591/Pleasant-Progress-Bar/raw/main/listen/Original_progress_bar.wav)
Pleasant progress bar with sine wave and cosine fade in/out effects →
[Click to download pleasant progress bar recording.wav](https://github.com/c469591/Pleasant-Progress-Bar/raw/main/listen/Pleasant_progress_bar.wav)


## Download and GitHub Repository

* You can
[click here to download V0.21 version](https://github.com/c469591/Pleasant-Progress-Bar/raw/main/historical_version_addon/pleasant_progress_bar_V0.21.nvda-addon)
of the NVDA add-on.
* You can also visit my GitHub repository page
[Click to visit the Pleasant Progress Bar GitHub repository](https://github.com/c469591/Pleasant-Progress-Bar)

## Compatibility

Theoretically supports all versions after 2019.3, but only tested on NVDA 2025.2.

## 🚀 Features

* Multiple waveform support: Sine wave, square wave, triangle wave, sawtooth wave, pulse wave, white noise
* Smart fade in/out: Cosine and Gaussian smooth algorithms
* Custom configuration: Volume and frequency range fully adjustable


## ⌨️ Keyboard Shortcuts

* NVDA+Shift+P: Toggle Pleasant Progress Bar function

## 🔧 Usage


1. Restart NVDA after installing the add-on
1. Press `NVDA+Shift+P` to toggle the add-on functionality on or off. (Default is enabled)
1. Experience pleasant sound effects in any application with progress bars
1. Customize audio parameters through the NVDA settings panel

### Configuration Settings

1. Open NVDA menu → Preferences → Settings
1. Find "Pleasant Progress Bar" in the category list
1. Adjust the following settings according to personal preferences:
   * Waveform type: Choose your preferred waveform (sine wave is softest, square wave is crispest)
   * Fade algorithm: Cosine (classic) or Gaussian (smoother)
   * Volume adjustment: 0.1 minimum to 1.0 maximum
   * Waveform length: From 40 milliseconds to 100 milliseconds, default is 80 milliseconds, 40 milliseconds effect is closest to the original progress bar style,
but waveform lengths below 80 milliseconds may introduce popping sounds, which is a defect caused by 32-bit audio systems, and there is currently no method found to completely fix this
   * Start frequency (low frequency): 110Hz to 300Hz range
   * End frequency (high frequency): 1200Hz to 1750Hz range



## 🛠️ Troubleshooting

### When progress bar sound effects don't change

1. Check add-on status
   * Press `NVDA+Shift+P` to confirm the add-on is enabled
   * Hearing "Pleasant Progress Bar enabled" prompt indicates the function is active
1. Check audio system
   * Ensure your computer's audio output device is working properly
   * Try increasing system volume or NVDA volume
   * Increase volume in Pleasant Progress Bar settings
1. Reset settings
If sound effects are abnormal, you can in the settings panel:
   * Reset all settings to default values
   * Or remove the add-on and reinstall

### Frequently Asked Questions

Q: Why is there sometimes audio delay?  
A: This may be due to audio buffering on 32-bit systems. The add-on has been optimized, but some older computers may still experience slight delays.

Q: Can multiple progress bar sound effects play simultaneously?  
A: The add-on is designed for mono playback. Multiple simultaneous progress bars will use the last triggered one to avoid audio confusion.

Q: What to do if the sound is too loud or too quiet?  
A: Please adjust the volume in the settings panel or check system audio settings.

### Export logs for developer diagnosis

   1. Open NVDA menu → Preferences → Settings → General
   1. Set "Log level" to "Debug"
   1. Find a place with a progress bar, confirm the add-on is enabled,
wait for a period of time with progress bar UI, for example 30 seconds,
this is to trigger the add-on's capture logic to generate logs
   1. Open NVDA menu → Tools → View log
   1. Select all and copy all content, paste it into Notepad and save, then send the file to the developer for diagnosis


## 🤝 Technical Support

If you encounter problems or have suggestions, feel free to contact:

* Email:
c469591@mail.batol.net
* Or visit the GitHub repository to ask questions:
[Click to visit the Pleasant Progress Bar GitHub repository](https://github.com/c469591/Pleasant-Progress-Bar)
* I also have more original articles and software, you can visit my website →
[Little Lamb Sharing Station](https://lamb.tw/)

## 📋 Changelog

### V0.21

*For unsupported system languages, English will always be used, and other functions will not change.

### V0.2


* Added controllable waveform length in settings options, minimum 40 milliseconds, maximum 100 milliseconds, 40 milliseconds effect is closer to the original progress bar style
* Now users can also modify the shortcut key for enabling and disabling Pleasant Progress Bar in NVDA's input gesture settings


### V0.1

* Initial release
* Support for multiple waveform types
* Audio caching system
* Complete settings panel
* Cosine and Gaussian fade in/out algorithms


## 📝 License

This add-on is released under [GPL v3], see LICENSE file for detailed terms.

---

Enjoy a more pleasant progress bar experience! 🎵
