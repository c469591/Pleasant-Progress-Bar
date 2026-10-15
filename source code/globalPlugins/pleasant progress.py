# -*- coding: utf-8 -*-
# 悅耳進度條
# 接管 tones.beep 把所有提示音改為悅耳的波形（含音頻緩存）
# 進度條提示音使用用戶的頻率範圍與波形長度設定；縮排提示音使用縮排提示音長度設定；
# 其它提示音（大寫字母、第三方插件等）保持呼叫者指定的頻率、長度與左右聲道
# 支援用戶自定義配置：淡入淡出算法、音量、頻率範圍
#
# 播放經由 NVDA 自身的 tones.player，因此會跟隨 NVDA 的輸出設備設定、
# Windows 預設設備切換，以及 NVDA 的音效音量設定。
import globalPluginHandler
import tones
import array
import math
from scriptHandler import script
import ui
import os
from gui.settingsDialogs import NVDASettingsDialog
import gettext
import languageHandler
from logHandler import log

# =============================================================================
# 國際化初始化
# =============================================================================
def initTranslation():
    """初始化插件的國際化翻譯"""
    try:
        # 獲取插件目錄和locale資料夾路徑
        addon_dir = os.path.dirname(__file__)  # 獲取當前文件所在目錄（globalPlugins）
        parent_dir = os.path.dirname(addon_dir)  # 獲取父目錄
        locale_dir = os.path.join(parent_dir, "locale")  # 父目錄下的locale資料夾


        # 獲取當前NVDA使用的語言
        lang = languageHandler.getLanguage()

        # 構建語言回退列表
        languages = [lang]  # 首先嘗試完整語言代碼

        # 如果語言代碼包含下劃線，也嘗試主要語言代碼
        if '_' in lang:
            main_lang = lang.split('_')[0]
            languages.append(main_lang)

        # 如果不是中文，添加英文作為回退
        if not lang.startswith('zh'):
            languages.append('en')

        # 創建翻譯對象
        translation = gettext.translation(
            "nvda",                    # domain name
            localedir=locale_dir,      # locale資料夾路徑
            languages=languages,       # 語言回退列表
            fallback=True              # 找不到翻譯時使用原文
        )

        # 返回gettext函數
        return translation.gettext

    except Exception:
        # 如果初始化失敗，返回簡單的fallback函數
        return lambda x: x

# 初始化並獲取翻譯函數
addonGettext = initTranslation()

# 導入配置管理和設定UI模塊
try:
    from ._pleasant_progressconfig import sine_progress_config
    from ._Pleasant_progress_settings import SineProgressSettingsPanel
    CONFIG_AVAILABLE = True
except ImportError as e:
    CONFIG_AVAILABLE = False
    print(f"悅耳進度條：配置模塊載入失敗: {e}")


# tones.player 的格式：44.1kHz、16位、雙聲道
SAMPLE_RATE = int(getattr(tones, "SAMPLE_RATE", 44100))

# 原始進度條的頻率範圍，用於映射到用戶設定範圍
ORIGINAL_MIN_FREQ = 110
ORIGINAL_MAX_FREQ = 1800

# NVDA 進度條提示音：tones.beep(beepMinHZ * 2 ** (percent / 25.0), 40)
PROGRESS_BEEP_LENGTH = 40
# NVDA 縮排提示音：BeepCommand(220 * 2 ** (quarterTones / 24.0), indentToneDuration)，quarterTones 為 0 至 72
INDENT_BASE_FREQUENCY = 220
INDENT_MAX_QUARTER_TONES = 72

# 提示音類型
BEEP_PROGRESS = "progress"
BEEP_INDENT = "indent"
BEEP_OTHER = "other"


def _is_on_pitch_scale(hz, base, steps_per_octave, max_steps):
    """檢查 hz 是否等於 base * 2 ** (n / steps_per_octave)，n 為 0 至 max_steps 的整數"""
    if hz <= 0 or base <= 0:
        return False
    steps = math.log2(hz / base) * steps_per_octave
    nearest = round(steps)
    return 0 <= nearest <= max_steps and abs(steps - nearest) < 0.01


def _get_nvda_config(section, key, default, subsection=None):
    """讀取 NVDA 配置值，失敗時返回預設值"""
    try:
        import config
        conf = config.conf[section]
        if subsection:
            conf = conf[subsection]
        return conf[key]
    except Exception:
        return default

# =============================================================================
# 核心插件類 - 悅耳進度條
# =============================================================================

class GlobalPlugin(globalPluginHandler.GlobalPlugin):

    def __init__(self):
        super().__init__()

        # 插件啟用狀態
        self.enabled = True
        # 原始 tones.beep 的備份；即使解除攔截後也保留，供仍持有本函數引用的其他插件回退使用
        self.original_beep = None
        self._fallback_beep = tones.beep
        self.debug_mode = False

        # 從配置載入音效參數
        self.apply_config_parameters()

        # 音頻緩存系統：緩存鍵 -> 可直接送入 tones.player 的雙聲道 PCM bytes
        self.audio_cache = {}
        self.cache_hits = 0
        self.cache_misses = 0
        self.max_cache_size = 300

        # 攔截tones.beep函數
        self.hook_beep_function()

        # 註冊設定面板到NVDA設定對話框
        self.register_settings_panel()

    def apply_config_parameters(self):
        """應用配置參數到插件"""
        if CONFIG_AVAILABLE:
            try:
                # 獲取波形類型
                self.waveform_type = sine_progress_config.get_waveform_type()

                # 獲取淡入淡出算法
                self.fade_algorithm = sine_progress_config.get_fade_algorithm()

                # 獲取音量設定
                self.volume = sine_progress_config.get_volume()

                # 獲取頻率範圍設定
                self.min_frequency, self.max_frequency = sine_progress_config.get_frequency_range()
                self.mapped_min_freq = self.min_frequency
                self.mapped_max_freq = self.max_frequency

                #波形長度
                self.audio_duration = sine_progress_config.get_audio_duration()

                # 縮排提示音長度（秒）
                self.indent_duration = sine_progress_config.get_indent_duration() / 1000.0

                # 根據算法設定淡入淡出比例
                if self.fade_algorithm == 'gaussian':
                    self.fade_ratio = 0.3  # 高斯算法使用較小的淡入淡出比例
                else:
                    self.fade_ratio = 0.45  # 余弦算法使用原來的比例

            except Exception as e:
                print(f"悅耳進度條：應用配置參數時發生錯誤: {e}")
                self.apply_default_parameters()
        else:
            print("悅耳進度條：警告：配置模塊不可用，使用預設參數")
            self.apply_default_parameters()

    def apply_default_parameters(self):
        """應用預設參數"""
        self.waveform_type = 'sine'
        self.fade_algorithm = 'cosine'
        self.volume = 0.4
        self.min_frequency = 110
        self.max_frequency = 1760
        self.mapped_min_freq = 110
        self.mapped_max_freq = 1760
        self.fade_ratio = 0.45
        self.audio_duration = 0.08  # 預設80ms
        self.indent_duration = 0.15  # 預設150ms

    def register_settings_panel(self):
        """註冊設定面板到NVDA設定對話框"""
        if CONFIG_AVAILABLE:
            try:
                # 將設定面板添加到NVDA設定對話框的類別列表中
                if hasattr(NVDASettingsDialog, 'categoryClasses'):
                    if SineProgressSettingsPanel not in NVDASettingsDialog.categoryClasses:
                        NVDASettingsDialog.categoryClasses.append(SineProgressSettingsPanel)
                else:
                    print("悅耳進度條：錯誤：無法註冊設定面板 - NVDASettingsDialog.categoryClasses不存在")
            except Exception as e:
                print(f"悅耳進度條：註冊設定面板時發生錯誤: {e}")

    def reload_configuration(self):
        """重新載入配置（由設定面板調用）"""
        try:
            # 清理音頻緩存
            self.clear_audio_cache()

            # 重新載入配置
            if CONFIG_AVAILABLE:
                sine_progress_config.load_config()

            # 重新應用配置參數
            self.apply_config_parameters()

            print("悅耳進度條：配置重新載入完成")
            print(f"  - 淡入淡出算法: {self.fade_algorithm}")
            print(f"  - 音量: {self.volume}")
            print(f"  - 頻率範圍: {self.mapped_min_freq}Hz - {self.mapped_max_freq}Hz")

        except Exception as e:
            print(f"悅耳進度條：重新載入配置時發生錯誤: {e}")

    # 超過此長度的提示音不緩存，避免佔用過多記憶體
    MAX_CACHED_DURATION = 0.5

    def get_cached_audio_or_generate(self, frequency, duration, sample_rate, volume, left_gain=1.0, right_gain=1.0):
        """獲取緩存的音頻或生成新的音頻（雙聲道 16 位 PCM bytes）"""
        # 緩存鍵包含頻率、長度、音量、左右聲道增益與波形類型
        cache_key = (
            round(frequency, 1),
            round(duration, 4),
            round(volume, 2),
            round(left_gain, 3),
            round(right_gain, 3),
            self.waveform_type,
        )

        # 檢查緩存
        if cache_key in self.audio_cache:
            self.cache_hits += 1
            return self.audio_cache[cache_key]

        # 緩存未命中，生成新音頻
        self.cache_misses += 1
        if self.debug_mode:
            print(f"悅耳進度條：音頻緩存未命中，正在生成: {cache_key}")

        # 根據配置選擇波形類型生成單聲道音頻數據
        mono = self.generate_waveform(
            frequency=frequency,
            duration=duration,
            sample_rate=sample_rate,
            volume=volume,
            waveform_type=self.waveform_type
        )

        # tones.player 為雙聲道，依左右聲道增益交錯寫入
        stereo = array.array('h', bytes(len(mono) * 4))
        if left_gain == 1.0:
            stereo[0::2] = mono
        else:
            stereo[0::2] = array.array('h', (int(s * left_gain) for s in mono))
        if right_gain == 1.0:
            stereo[1::2] = mono
        else:
            stereo[1::2] = array.array('h', (int(s * right_gain) for s in mono))
        audio_data = stereo.tobytes()

        if duration <= self.MAX_CACHED_DURATION:
            # 管理緩存大小
            if len(self.audio_cache) >= self.max_cache_size:
                # 移除最早添加的緩存項（簡單FIFO策略）
                oldest_key = next(iter(self.audio_cache))
                del self.audio_cache[oldest_key]

            # 添加到緩存
            self.audio_cache[cache_key] = audio_data
        return audio_data

    def classify_beep(self, hz, length, left, right, isSpeechBeepCommand):
        """判斷提示音類型：NVDA 進度條、NVDA 縮排，或其它（大寫字母、第三方插件等）"""
        if left != 50 or right != 50:
            return BEEP_OTHER
        if not isSpeechBeepCommand:
            # 進度條提示音不經語音序列，長度固定 40 毫秒，頻率位於 beepMinHZ 起每 25% 一個八度的音階上
            if length == PROGRESS_BEEP_LENGTH:
                beep_min_hz = _get_nvda_config("presentation", "beepMinHZ", 110, subsection="progressBarUpdates")
                if _is_on_pitch_scale(hz, beep_min_hz, 25, 100):
                    return BEEP_PROGRESS
            return BEEP_OTHER
        # 縮排提示音來自語音序列，長度為 NVDA 的 indentToneDuration，頻率位於 220Hz 起的四分音音階上
        indent_tone_duration = _get_nvda_config("documentFormatting", "indentToneDuration", 40)
        if length == indent_tone_duration and _is_on_pitch_scale(
            hz, INDENT_BASE_FREQUENCY, 24, INDENT_MAX_QUARTER_TONES
        ):
            return BEEP_INDENT
        return BEEP_OTHER

    def play_pleasant_beep(self, hz, length, left, right, isSpeechBeepCommand=False):
        """經由 NVDA 的 tones.player 播放悅耳波形。成功處理返回 True，否則返回 False 以回退到原始音效。"""
        # 無法以波形表示的頻率交回原始函數處理
        if not (20 <= hz < SAMPLE_RATE / 2):
            return False

        # 每次都重新讀取 tones.player：NVDA 更換輸出設備時會重建它
        player = getattr(tones, "player", None)
        if not player:
            return False

        # 尊重 tones.decide_beep 擴展點（例如遠端存取會藉此轉發或取消提示音）
        decide_beep = getattr(tones, "decide_beep", None)
        if decide_beep is not None and not decide_beep.decide(
            hz=hz,
            length=length,
            left=left,
            right=right,
            isSpeechBeepCommand=isSpeechBeepCommand,
        ):
            return True

        beep_type = self.classify_beep(hz, length, left, right, isSpeechBeepCommand)
        if beep_type == BEEP_PROGRESS:
            # 將原始進度條頻率範圍重新映射到用戶設定範圍，長度使用波形長度設定
            original_progress = (hz - ORIGINAL_MIN_FREQ) / (ORIGINAL_MAX_FREQ - ORIGINAL_MIN_FREQ)
            original_progress = max(0.0, min(1.0, original_progress))
            frequency = self.mapped_min_freq + original_progress * (self.mapped_max_freq - self.mapped_min_freq)
            duration = self.audio_duration
        elif beep_type == BEEP_INDENT:
            # 縮排提示音保持原頻率，長度使用縮排提示音長度設定
            frequency = hz
            duration = self.indent_duration
        else:
            # 其它提示音保持呼叫者指定的頻率與長度
            frequency = hz
            duration = length / 1000.0

        if duration <= 0:
            return True

        # left/right 為 0 至 100 的聲道音量，50 為標準音量；按比例縮放並避免超過滿幅
        peak = max(50, left, right)
        left_gain = max(0, left) / peak
        right_gain = max(0, right) / peak

        audio_data = self.get_cached_audio_or_generate(
            frequency=frequency,
            duration=duration,
            sample_rate=SAMPLE_RATE,
            volume=self.volume,
            left_gain=left_gain,
            right_gain=right_gain,
        )

        # 與 tones.beep 相同：停止上一個提示音再播放新的
        player.stop()
        player.feed(audio_data)

        if self.debug_mode:
            print(f"悅耳進度條：{beep_type}: {hz}Hz {length}ms → {frequency:.1f}Hz {duration * 1000:.0f}ms")
        return True

    def hook_beep_function(self):
        """攔截tones.beep函數"""
        if not self.original_beep:
            self.original_beep = tones.beep
            self._fallback_beep = tones.beep
            tones.beep = self.optimized_beep
            print("悅耳進度條：已攔截 tones.beep 函數")

    def unhook_beep_function(self):
        """恢復原始beep函數"""
        if self.original_beep:
            # 只有當 tones.beep 仍是本插件的函數時才恢復，避免覆蓋之後其他插件安裝的攔截
            if tones.beep == self.optimized_beep:
                tones.beep = self.original_beep
                print("悅耳進度條：已恢復原始tones.beep函數")
            self.original_beep = None

    def optimized_beep(self, hz, length, left=50, right=50, *args, **kwargs):
        """接管 tones.beep：所有提示音改用悅耳波形播放。
        額外參數（例如 NVDA 2024.4+ 的 isSpeechBeepCommand）在回退時原樣轉交給原始函數。"""
        if self.enabled:
            try:
                isSpeechBeepCommand = kwargs.get("isSpeechBeepCommand", args[0] if args else False)
                if self.play_pleasant_beep(hz, length, left, right, isSpeechBeepCommand):
                    return
            except Exception:
                log.error("悅耳進度條：播放悅耳提示音失敗，改用原始音效", exc_info=True)

        # 播放原始音效（插件停用、無法以波形表示或播放失敗時）
        original_beep = self.original_beep or self._fallback_beep
        original_beep(hz, length, left, right, *args, **kwargs)

    def generate_waveform(self, frequency, duration=0.08, sample_rate=44100, volume=0.6, waveform_type='sine'):
        """通用波形生成器，依 waveform_type 分派到對應子函式"""

        # 根據波形類型調用對應的生成函數
        if waveform_type == 'sine':
            return self.generate_sine_wave(frequency, duration, sample_rate, volume)
        elif waveform_type == 'square':
            return self.generate_square_wave(frequency, duration, sample_rate, volume)
        elif waveform_type == 'triangle':
            return self.generate_triangle_wave(frequency, duration, sample_rate, volume)
        elif waveform_type == 'sawtooth':
            return self.generate_sawtooth_wave(frequency, duration, sample_rate, volume)
        elif waveform_type == 'pulse':
            return self.generate_pulse_wave(frequency, duration, sample_rate, volume)
        elif waveform_type == 'white_noise':
            return self.generate_white_noise(frequency, duration, sample_rate, volume)
        else:
            # 默認使用正弦波
            return self.generate_sine_wave(frequency, duration, sample_rate, volume)

    def generate_sine_wave(self, frequency, duration, sample_rate, volume):
        """正弦波生成器"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')

        two_pi_f = 2.0 * math.pi * frequency
        sample_rate_inv = 1.0 / sample_rate
        max_amplitude = 30000

        for i in range(samples):
            t = i * sample_rate_inv
            sample = math.sin(two_pi_f * t)
            sample = self.apply_fade_effect(sample, i, samples)

            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)

        return audio_array

    def generate_square_wave(self, frequency, duration, sample_rate, volume):
        """方波生成器"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')

        two_pi_f = 2.0 * math.pi * frequency
        sample_rate_inv = 1.0 / sample_rate
        max_amplitude = 30000

        for i in range(samples):
            t = i * sample_rate_inv
            # 方波：基於正弦波的符號函數
            sine_val = math.sin(two_pi_f * t)
            sample = 1.0 if sine_val >= 0 else -1.0
            sample = self.apply_fade_effect(sample, i, samples)

            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)

        return audio_array

    def generate_triangle_wave(self, frequency, duration, sample_rate, volume):
        """三角波生成器"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')

        period_samples = int(sample_rate / frequency)
        max_amplitude = 30000

        for i in range(samples):
            # 三角波：線性上升下降
            position_in_period = i % period_samples
            half_period = period_samples / 2.0

            if position_in_period <= half_period:
                # 上升階段：從-1到+1
                sample = (position_in_period / half_period) * 2.0 - 1.0
            else:
                # 下降階段：從+1到-1
                sample = 1.0 - ((position_in_period - half_period) / half_period) * 2.0

            sample = self.apply_fade_effect(sample, i, samples)

            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)

        return audio_array

    def generate_sawtooth_wave(self, frequency, duration, sample_rate, volume):
        """鋸齒波生成器"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')

        period_samples = int(sample_rate / frequency)
        max_amplitude = 30000

        for i in range(samples):
            # 鋸齒波：線性上升然後瞬間下降
            position_in_period = i % period_samples
            sample = (position_in_period / period_samples) * 2.0 - 1.0
            sample = self.apply_fade_effect(sample, i, samples)

            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)

        return audio_array

    def generate_pulse_wave(self, frequency, duration, sample_rate, volume, duty_cycle=0.25):
        """脈衝波生成器（可調佔空比的方波）"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')

        period_samples = int(sample_rate / frequency)
        max_amplitude = 30000

        for i in range(samples):
            position_in_period = i % period_samples
            # 脈衝波：佔空比控制高電平時間
            sample = 1.0 if (position_in_period / period_samples) < duty_cycle else -1.0
            sample = self.apply_fade_effect(sample, i, samples)

            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)

        return audio_array

    def generate_white_noise(self, frequency, duration, sample_rate, volume):
        """白噪音生成器（頻率參數用於調制強度）"""
        import random
        samples = int(sample_rate * duration)
        audio_array = array.array('h')

        max_amplitude = 30000
        # 使用頻率來調制噪音的強度變化
        modulation_factor = frequency / 1000.0  # 將頻率轉換為調制因子

        for i in range(samples):
            # 生成隨機噪音
            noise = random.uniform(-1.0, 1.0)
            # 根據頻率進行輕微調制
            modulation = 1.0 + 0.3 * math.sin(2.0 * math.pi * modulation_factor * i / sample_rate)
            sample = noise * modulation
            sample = self.apply_fade_effect(sample, i, samples)

            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)

        return audio_array

    def apply_fade_effect(self, sample, current_index, total_samples):
        """應用淡入淡出效果"""
        fade_samples = int(total_samples * self.fade_ratio)

        if self.fade_algorithm == 'gaussian':
            # 高斯淡入淡出
            sigma = total_samples * 0.25
            center = total_samples / 2.0
            gaussian_factor = math.exp(-0.5 * ((current_index - center) / sigma) ** 2)
            return sample * gaussian_factor
        else:
            # 余弦淡入淡出
            if current_index < fade_samples:
                fade_factor = (1.0 - math.cos(math.pi * current_index / fade_samples)) / 2.0
                return sample * fade_factor
            elif current_index >= total_samples - fade_samples:
                fade_index = total_samples - current_index - 1
                fade_factor = (1.0 - math.cos(math.pi * fade_index / fade_samples)) / 2.0
                return sample * fade_factor
            else:
                return sample

    def clear_audio_cache(self):
        """清理音頻緩存"""
        cache_size = len(self.audio_cache)
        self.audio_cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        print(f"悅耳進度條：音頻緩存已清理（清理了 {cache_size} 個條目）")

    def terminate(self):
        """插件清理"""
        print("悅耳進度條：正在停用...")

        # 停用播放
        self.enabled = False

        # 清理音頻緩存
        self.clear_audio_cache()

        # 恢復原始beep函數
        self.unhook_beep_function()

        # 移除設定面板註冊
        if CONFIG_AVAILABLE:
            try:
                if hasattr(NVDASettingsDialog, 'categoryClasses'):
                    if SineProgressSettingsPanel in NVDASettingsDialog.categoryClasses:
                        NVDASettingsDialog.categoryClasses.remove(SineProgressSettingsPanel)
                        print("悅耳進度條：設定面板已從NVDA設定對話框移除")
            except Exception as e:
                print(f"悅耳進度條：移除設定面板時發生錯誤: {e}")

        print("悅耳進度條：已完全停用")
        super().terminate()

    # 快捷鍵：切換插件（唯一保留的快捷鍵）
    @script(
        description=addonGettext("切換悅耳進度條開關"),
        gesture="kb:NVDA+shift+p",  # 預設快捷鍵
        category=addonGettext("悅耳進度條")  # 在輸入手勢對話框中的分類
    )
    def script_toggleProgressSound(self, gesture):
        self.enabled = not self.enabled

        if self.enabled:
            ui.message(addonGettext("開啟 悅耳進度條"))
        else:
            ui.message(addonGettext("關閉 悅耳進度條"))

        state_text = "啟用" if self.enabled else "停用"
        print(f"悅耳進度條：用戶切換音效狀態: {state_text}")
