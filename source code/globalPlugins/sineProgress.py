# -*- coding: utf-8 -*-
# 悅耳進度條 - 32位優化版本
# 針對NVDA 32位環境優化，解決報音和雙音調問題，並使用音頻緩存提升性能
# 支援用戶自定義配置：淡入淡出算法、音量、頻率範圍

import globalPluginHandler
import threading
import time
import tones
import array
import math
from scriptHandler import script
import ui
import sys
import os
import gui
from gui.settingsDialogs import NVDASettingsDialog

# 導入配置管理和設定UI模塊
try:
    from ._sineProgressConfig import sine_progress_config
    from ._sineProgressSettings import SineProgressSettingsPanel
    CONFIG_AVAILABLE = True
    print("悅耳進度條：配置模塊載入成功")
except ImportError as e:
    CONFIG_AVAILABLE = False
    print(f"悅耳進度條：配置模塊載入失敗: {e}")

# =============================================================================
# 32位音頻緩衝區對齊優化函數
# =============================================================================

def align_audio_buffer_32bit(audio_array):
    """確保音頻緩衝區在32位系統中正確對齊"""
    try:
        # 32位系統：確保緩衝區大小是4字節的倍數
        buffer_size = len(audio_array)
        alignment_bytes = 4
        
        if buffer_size % alignment_bytes != 0:
            # 填充到對齊邊界
            padding_needed = alignment_bytes - (buffer_size % alignment_bytes)
            for _ in range(padding_needed // 2):  # 每個樣本2字節
                audio_array.append(0)
        
        return audio_array
    except Exception as e:
        print(f"悅耳進度條：32位音頻緩衝區對齊錯誤: {e}")
        return audio_array

# =============================================================================
# 內嵌PyAudio代碼
# =============================================================================

plugin_dir = os.path.dirname(__file__)
print(f"悅耳進度條：插件目錄: {plugin_dir}")

try:
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    
    import _portaudio as pa
    PYAUDIO_AVAILABLE = True
    print("悅耳進度條：✓ _portaudio模塊載入成功（32位優化模式）")
except ImportError as e:
    print(f"悅耳進度條：✗ 無法導入_portaudio模塊: {e}")
    pa = None
    PYAUDIO_AVAILABLE = False

if PYAUDIO_AVAILABLE:
    # PyAudio常量定義
    paFloat32 = pa.paFloat32
    paInt32 = pa.paInt32
    paInt24 = pa.paInt24
    paInt16 = pa.paInt16
    paInt8 = pa.paInt8
    paUInt8 = pa.paUInt8
    paCustomFormat = pa.paCustomFormat
    
    paNoError = pa.paNoError
    paNotInitialized = pa.paNotInitialized
    paInvalidDevice = pa.paInvalidDevice
    paCanNotWriteToAnInputOnlyStream = pa.paCanNotWriteToAnInputOnlyStream
    paCanNotReadFromAnOutputOnlyStream = pa.paCanNotReadFromAnOutputOnlyStream
    
    paContinue = pa.paContinue
    paComplete = pa.paComplete
    paAbort = pa.paAbort
    
    paFramesPerBufferUnspecified = pa.paFramesPerBufferUnspecified

    def get_sample_size(format):
        return pa.get_sample_size(format)

    def get_format_from_width(width, unsigned=True):
        if width == 1:
            return paUInt8 if unsigned else paInt8
        if width == 2:
            return paInt16
        if width == 3:
            return paInt24
        if width == 4:
            return paFloat32
        raise ValueError(f"Invalid width: {width}")

    # 添加設備信息相關函數
    def get_default_output_device_info():
        """獲取默認輸出設備信息"""
        try:
            return pa.get_default_output_device_info()
        except AttributeError:
            # 如果_portaudio模塊沒有此函數，返回模擬的設備信息
            return {
                'index': 0,
                'name': 'Default Output Device',
                'defaultSampleRate': 44100.0,
                'maxOutputChannels': 2
            }

    def get_device_info_by_index(device_index):
        """根據索引獲取設備信息"""
        try:
            return pa.get_device_info_by_index(device_index)
        except AttributeError:
            # 如果_portaudio模塊沒有此函數，返回模擬的設備信息
            return {
                'index': device_index,
                'name': f'Audio Device {device_index}',
                'defaultSampleRate': 44100.0,
                'maxOutputChannels': 2
            }

    def get_device_count():
        """獲取設備數量"""
        try:
            return pa.get_device_count()
        except AttributeError:
            return 1  # 至少返回一個設備
        
    class PyAudio:
        class Stream:
            def __init__(self, PA_manager, rate, channels, format, input=False, output=False,
                         input_device_index=None, output_device_index=None,
                         frames_per_buffer=paFramesPerBufferUnspecified, start=True,
                         input_host_api_specific_stream_info=None,
                         output_host_api_specific_stream_info=None, stream_callback=None):
                
                if not (input or output):
                    raise ValueError("Must specify an input or output stream.")
                
                self._parent = PA_manager
                self._is_input = input
                self._is_output = output
                self._is_running = start
                self._rate = rate
                self._channels = channels
                self._format = format
                self._frames_per_buffer = frames_per_buffer
                
                arguments = {
                    'rate': rate, 'channels': channels, 'format': format,
                    'input': input, 'output': output,
                    'input_device_index': input_device_index,
                    'output_device_index': output_device_index,
                    'frames_per_buffer': frames_per_buffer
                }
                
                if input_host_api_specific_stream_info:
                    arguments['input_host_api_specific_stream_info'] = input_host_api_specific_stream_info
                if output_host_api_specific_stream_info:
                    arguments['output_host_api_specific_stream_info'] = output_host_api_specific_stream_info
                if stream_callback:
                    arguments['stream_callback'] = stream_callback
                
                self._stream = pa.open(**arguments)
                self._input_latency = self._stream.inputLatency
                self._output_latency = self._stream.outputLatency
                
                if self._is_running:
                    pa.start_stream(self._stream)
            
            def close(self):
                pa.close(self._stream)
                self._is_running = False
                self._parent._remove_stream(self)
            
            def write(self, frames, num_frames=None, exception_on_underflow=False):
                if not self._is_output:
                    raise IOError("Not output stream", paCanNotWriteToAnInputOnlyStream)
                
                if num_frames is None:
                    width = get_sample_size(self._format)
                    num_frames = int(len(frames) / (self._channels * width))
                
                pa.write_stream(self._stream, frames, num_frames, exception_on_underflow)
            
            def stop_stream(self):
                if not self._is_running:
                    return
                pa.stop_stream(self._stream)
                self._is_running = False
            
            def is_active(self):
                return pa.is_stream_active(self._stream)
        
        def __init__(self):
            pa.initialize()
            self._streams = set()
        
        def terminate(self):
            for stream in self._streams.copy():
                stream.close()
            self._streams = set()
            pa.terminate()
        
        def open(self, *args, **kwargs):
            stream = PyAudio.Stream(self, *args, **kwargs)
            self._streams.add(stream)
            return stream
        
        def get_default_output_device_info(self):
            """獲取默認輸出設備信息"""
            # 調用全局函數，而不是自己
            return get_default_output_device_info()

        def get_device_info_by_index(self, device_index):
            """根據索引獲取設備信息"""
            # 調用全局函數，而不是自己
            return get_device_info_by_index(device_index)
        
        def _remove_stream(self, stream):
            """移除流"""
            if stream in self._streams:
                self._streams.remove(stream)

# =============================================================================
# 核心插件類 - 悅耳進度條
# =============================================================================

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    
    def __init__(self):
        super().__init__()
        # 載入用戶配置
        self.load_user_config()
        
        # 插件啟用狀態
        self.enabled = True
        # 原始進度條音效函數的備份
        self.original_beep = None
        self.debug_mode = True
        self.beep_log = []
        
        # 從配置載入音效參數（移除硬編碼值）
        self.apply_config_parameters()
        
        # 32位優化的音頻生成參數
        self.audio_duration = 0.08  # 80ms播放時長
        
        # 檢測設備最佳音頻參數
        self.detect_optimal_audio_params()
        
        # 32位優化配置
        self.frames_per_buffer = 128  # 從4096降低到1024
        self.exception_on_overflow = False  # 防止32位系統溢出崩潰
        self.thread_sleep_interval = 0.12  # 修正線程間隔：120ms
        
        # 音頻緩存系統
        self.audio_cache = {}  # 頻率 -> 音頻數據的緩存字典
        self.cache_hits = 0    # 緩存命中次數統計
        self.cache_misses = 0  # 緩存未命中次數統計
        self.max_cache_size = 300  # 最大緩存條目數量
        
        # 守護線程屬性檢查機制
        self.audio_thread = None
        self.thread_running = False
        
        # 播放請求屬性（線程間通信）
        self.play_frequency = None    # 要播放的頻率
        self.play_id = None          # 唯一播放標誌（時間戳）
        
        # 線程內部狀態（只在守護線程中使用）
        self.last_played_id = None   # 最後播放的ID
        self.skipped_requests = 0    # 跳過的請求數量統計
        
        # PyAudio相關
        self.pyaudio_instance = None
        self.audio_stream = None
        self.stream_initialized = False
        
        # 攔截tones.beep函數
        self.hook_beep_function()
        
        # 初始化PyAudio和守護線程
        if PYAUDIO_AVAILABLE:
            self.init_audio_stream_32bit()
            self.start_audio_daemon()
        
        # 註冊設定面板到NVDA設定對話框
        self.register_settings_panel()
        
        # 顯示插件狀態
        pyaudio_status = "可用" if PYAUDIO_AVAILABLE else "不可用"
        config_status = "可用" if CONFIG_AVAILABLE else "不可用"
        print(f"悅耳進度條：已啟動（32位優化 + 音頻緩存 + 用戶配置）")
        print(f"悅耳進度條：內嵌PyAudio: {pyaudio_status}")
        print(f"悅耳進度條：配置管理: {config_status}")
        print(f"悅耳進度條：緩衝區配置: {self.frames_per_buffer} frames")
        print(f"悅耳進度條：音量調整: {self.volume:.2f}")
        print(f"悅耳進度條：頻率範圍: {self.mapped_min_freq}Hz - {self.mapped_max_freq}Hz")
        print(f"悅耳進度條：淡入淡出: {self.fade_algorithm}")
        print(f"悅耳進度條：音頻緩存: 最大 {self.max_cache_size} 條目")
        
        if not PYAUDIO_AVAILABLE:
            print("悅耳進度條：警告：內嵌PyAudio不可用，將使用原始音效")

    def load_user_config(self):
        """載入用戶配置"""
        if CONFIG_AVAILABLE:
            try:
                # 載入配置並打印當前設定
                algorithm = sine_progress_config.get_fade_algorithm()
                volume = sine_progress_config.get_volume()
                min_freq, max_freq = sine_progress_config.get_frequency_range()
                
                print(f"悅耳進度條：載入用戶配置")
                print(f"  - 淡入淡出算法: {algorithm}")
                print(f"  - 音量: {volume}")
                print(f"  - 頻率範圍: {min_freq}Hz - {max_freq}Hz")
                
            except Exception as e:
                print(f"悅耳進度條：載入用戶配置時發生錯誤: {e}")
        else:
            print("悅耳進度條：配置模塊不可用，使用預設參數")

    def apply_config_parameters(self):
        """應用配置參數到插件"""
        if CONFIG_AVAILABLE:
            try:
                # 獲取淡入淡出算法
                self.fade_algorithm = sine_progress_config.get_fade_algorithm()
                
                # 獲取音量設定
                self.volume = sine_progress_config.get_volume()
                
                # 獲取頻率範圍設定
                self.min_frequency, self.max_frequency = sine_progress_config.get_frequency_range()
                self.mapped_min_freq = self.min_frequency
                self.mapped_max_freq = self.max_frequency
                
                # 根據算法設定淡入淡出比例
                if self.fade_algorithm == 'gaussian':
                    self.fade_ratio = 0.3  # 高斯算法使用較小的淡入淡出比例
                else:
                    self.fade_ratio = 0.45  # 余弦算法使用原來的比例
                
                print(f"悅耳進度條：配置參數已應用")
                
            except Exception as e:
                print(f"悅耳進度條：應用配置參數時發生錯誤: {e}")
                self.apply_default_parameters()
        else:
            self.apply_default_parameters()

    def apply_default_parameters(self):
        """應用預設參數"""
        self.fade_algorithm = 'cosine'
        self.volume = 0.5
        self.min_frequency = 110
        self.max_frequency = 1760
        self.mapped_min_freq = 110
        self.mapped_max_freq = 1760
        self.fade_ratio = 0.45
        print("悅耳進度條：已應用預設參數")

    def register_settings_panel(self):
        """註冊設定面板到NVDA設定對話框"""
        if CONFIG_AVAILABLE:
            try:
                # 將設定面板添加到NVDA設定對話框的類別列表中
                if hasattr(NVDASettingsDialog, 'categoryClasses'):
                    if SineProgressSettingsPanel not in NVDASettingsDialog.categoryClasses:
                        NVDASettingsDialog.categoryClasses.append(SineProgressSettingsPanel)
                        print("悅耳進度條：設定面板已註冊到NVDA設定對話框")
                else:
                    print("悅耳進度條：無法註冊設定面板 - NVDASettingsDialog.categoryClasses不存在")
            except Exception as e:
                print(f"悅耳進度條：註冊設定面板時發生錯誤: {e}")

    def reload_configuration(self):
        """重新載入配置並重新初始化（由設定面板調用）"""
        print("悅耳進度條：開始重新載入配置...")
        
        try:
            # 停止當前的音頻處理
            self.stop_audio_daemon()
            self.cleanup_audio_resources()
            
            # 清理音頻緩存
            self.clear_audio_cache()
            
            # 重新載入配置
            if CONFIG_AVAILABLE:
                sine_progress_config.load_config()
            
            # 重新應用配置參數
            self.apply_config_parameters()
            
            # 重新初始化音頻系統
            if PYAUDIO_AVAILABLE:
                self.init_audio_stream_32bit()
                self.start_audio_daemon()
            
            print("悅耳進度條：配置重新載入完成")
            print(f"  - 淡入淡出算法: {self.fade_algorithm}")
            print(f"  - 音量: {self.volume}")
            print(f"  - 頻率範圍: {self.mapped_min_freq}Hz - {self.mapped_max_freq}Hz")
            
        except Exception as e:
            print(f"悅耳進度條：重新載入配置時發生錯誤: {e}")

    def get_frequency_cache_key(self, frequency):
        """生成頻率的緩存鍵，將頻率四捨五入到小數點後1位"""
        return round(frequency, 1)

    def get_cached_audio_or_generate(self, frequency, duration, sample_rate, volume):
        """獲取緩存的音頻或生成新的音頻"""
        cache_key = self.get_frequency_cache_key(frequency)
        
        # 檢查緩存
        if cache_key in self.audio_cache:
            self.cache_hits += 1
            if self.debug_mode:
                print(f"悅耳進度條：音頻緩存命中: {cache_key}Hz (命中率: {self.cache_hits}/{self.cache_hits + self.cache_misses})")
            return self.audio_cache[cache_key]
        
        # 緩存未命中，生成新音頻
        self.cache_misses += 1
        if self.debug_mode:
            print(f"悅耳進度條：音頻緩存未命中，正在生成: {cache_key}Hz")
        
        # 根據配置選擇淡入淡出算法生成音頻數據
        if self.fade_algorithm == 'gaussian':
            audio_array = self.generate_gaussian_sine_wave_32bit(frequency, duration, sample_rate, volume)
        else:
            audio_array = self.generate_clean_sine_wave_32bit(frequency, duration, sample_rate, volume)
        
        # 32位系統音頻緩衝區對齊優化
        audio_array = align_audio_buffer_32bit(audio_array)
        
        # 管理緩存大小
        if len(self.audio_cache) >= self.max_cache_size:
            # 移除最早添加的緩存項（簡單FIFO策略）
            oldest_key = next(iter(self.audio_cache))
            del self.audio_cache[oldest_key]
            if self.debug_mode:
                print(f"悅耳進度條：緩存已滿，移除最舊條目: {oldest_key}Hz")
        
        # 添加到緩存
        self.audio_cache[cache_key] = audio_array
        
        if self.debug_mode:
            cache_size = len(self.audio_cache)
            print(f"悅耳進度條：音頻已緩存: {cache_key}Hz (緩存大小: {cache_size}/{self.max_cache_size})")
        
        return audio_array

    def detect_optimal_audio_params(self):
        """檢測當前播放設備的最佳音頻參數"""
        if not PYAUDIO_AVAILABLE:
            # 後備默認值
            self.sample_rate = 48000
            self.optimal_format = paInt16
            print("悅耳進度條：PyAudio不可用，使用默認音頻參數")
            return
        
        try:
            temp_pyaudio = PyAudio()
            
            # 獲取默認輸出設備信息
            default_device = temp_pyaudio.get_default_output_device_info()
            device_index = default_device['index']
            
            print(f"悅耳進度條：檢測到播放設備: {default_device['name']}")
            
            # 設備支持的採樣率優先級列表（從高到低）
            preferred_rates = [
                int(default_device['defaultSampleRate']),  # 設備默認採樣率優先
                48000, 44100, 96000, 22050, 16000
            ]
            
            # 移除重複並測試支持的採樣率
            tested_rates = []
            for rate in preferred_rates:
                if rate not in tested_rates:
                    tested_rates.append(rate)
            
            # 測試格式優先級：16位 > 24位 > 32位浮點
            preferred_formats = [paInt16, paInt24, paFloat32]
            
            self.sample_rate = 48000  # 默認值
            self.optimal_format = paInt16  # 默認值
            
            # 測試最佳組合
            for rate in tested_rates:
                for fmt in preferred_formats:
                    try:
                        # 測試是否支持此配置
                        test_stream = temp_pyaudio.open(
                            format=fmt,
                            channels=1,
                            rate=rate,
                            output=True,
                            output_device_index=device_index,
                            frames_per_buffer=1024
                        )
                        test_stream.close()
                        
                        # 成功，使用此配置
                        self.sample_rate = rate
                        self.optimal_format = fmt
                        format_name = {paInt16: "16位整數", paInt24: "24位整數", paFloat32: "32位浮點"}
                        print(f"悅耳進度條：最佳音頻配置: {rate}Hz, {format_name.get(fmt, '未知格式')}")
                        temp_pyaudio.terminate()
                        return
                        
                    except Exception:
                        continue
            
            temp_pyaudio.terminate()
            print(f"悅耳進度條：使用檢測配置: {self.sample_rate}Hz, 16位整數")
            
        except Exception as e:
            # 檢測失敗，使用安全默認值
            self.sample_rate = 48000
            self.optimal_format = paInt16
            print(f"悅耳進度條：設備檢測失敗，使用默認配置: {e}")
            
    def init_audio_stream_32bit(self):
        """初始化PyAudio音頻流 - 32位優化版本"""
        if not PYAUDIO_AVAILABLE or self.stream_initialized:
            return
        
        try:
            self.pyaudio_instance = PyAudio()
            
            # 使用檢測到的最佳配置
            stream_config = {
                'format': self.optimal_format,  # 使用檢測到的最佳格式
                'channels': 1,
                'rate': self.sample_rate,  # 使用檢測到的最佳採樣率
                'output': True,
                'frames_per_buffer': self.frames_per_buffer  # 1024 frames
            }
            
            self.audio_stream = self.pyaudio_instance.open(**stream_config)
            self.stream_initialized = True
            
            if self.debug_mode:
                buffer_ms = self.frames_per_buffer / self.sample_rate * 1000
                format_name = {paInt16: "16位", paInt24: "24位", paFloat32: "32位浮點"}
                print("悅耳進度條：守護線程：PyAudio音頻流初始化成功（設備優化）")
                print(f"悅耳進度條：音頻配置：{self.sample_rate}Hz, {format_name.get(self.optimal_format, '未知')}")
                print(f"悅耳進度條：緩衝區大小：{self.frames_per_buffer} frames (約{buffer_ms:.1f}ms)")
                print(f"悅耳進度條：溢出處理：{'停用（32位兼容）' if not self.exception_on_overflow else '啟用'}")
                
        except Exception as e:
            print(f"悅耳進度條：守護線程：PyAudio流初始化失敗: {e}")
            self.stream_initialized = False
            self.pyaudio_instance = None
            self.audio_stream = None

    def start_audio_daemon(self):
        """啟動守護線程進行屬性檢查和播放"""
        if not PYAUDIO_AVAILABLE or self.thread_running:
            return
        
        self.thread_running = True
        self.audio_thread = threading.Thread(
            target=self.audio_daemon_worker_32bit,
            daemon=True  # 守護線程，程式退出時自動結束
        )
        self.audio_thread.start()
        print(f"悅耳進度條：守護線程已啟動：32位優化模式（間隔{self.thread_sleep_interval*1000:.0f}ms）")
    
    def audio_daemon_worker_32bit(self):
        """守護線程：循環檢查播放請求屬性 - 32位優化版本"""
        print("悅耳進度條：守護線程開始工作：32位架構適配循環 + 音頻緩存")
        
        while self.thread_running:
            try:
                # 檢查是否有新的播放請求
                if (self.play_id is not None and 
                    self.play_id != self.last_played_id and 
                    self.play_frequency is not None):
                    
                    # 檢查插件是否仍然啟用
                    if not self.enabled or not self.stream_initialized:
                        # 插件已停用，跳過播放但更新ID避免重複檢查
                        self.last_played_id = self.play_id
                        continue
                    
                    # 執行播放
                    try:
                        self.execute_audio_play_32bit(self.play_frequency)
                        # 更新最後播放的ID
                        self.last_played_id = self.play_id
                        
                        if self.debug_mode:
                            print(f"悅耳進度條：守護線程播放完成（32位優化）: ID={self.play_id}")
                            
                    except Exception as e:
                        print(f"悅耳進度條：守護線程播放錯誤: {e}")
                        # 即使播放失敗也要更新ID，避免重複嘗試
                        self.last_played_id = self.play_id
                
                # 使用32位優化的循環間隔：120ms
                time.sleep(self.thread_sleep_interval)
                
            except Exception as e:
                print(f"悅耳進度條：守護線程循環錯誤: {e}")
                time.sleep(0.1)  # 出錯也要延遲，避免瘋狂循環
        
        print("悅耳進度條：守護線程已退出")

    def execute_audio_play_32bit(self, original_hz):
        """在守護線程中執行音頻播放 - 32位優化版本 + 音頻緩存"""
        try:
            # 頻率映射：使用用戶配置的頻率範圍
            progress = (original_hz - self.min_frequency) / (self.max_frequency - self.min_frequency)
            progress = max(0.0, min(1.0, progress))
            mapped_freq = self.mapped_min_freq + progress * (self.mapped_max_freq - self.mapped_min_freq)
            
            # 使用音頻緩存系統獲取或生成音頻數據
            audio_array = self.get_cached_audio_or_generate(
                frequency=mapped_freq,
                duration=self.audio_duration,
                sample_rate=self.sample_rate,
                volume=0.2  # 進一步降低音量避免32位系統報音
            )
            
            # 播放音頻
            if self.enabled and self.stream_initialized and self.audio_stream:
                try:
                    # 檢查流是否仍然活躍
                    if hasattr(self.audio_stream, 'is_active') and not self.audio_stream.is_active():
                        print("悅耳進度條：警告：音頻流不活躍，嘗試重新初始化")
                        self.cleanup_audio_resources()
                        self.init_audio_stream_32bit()

                    if self.audio_stream:
                        # 使用32位優化的溢出處理策略
                        self.audio_stream.write(
                            audio_array.tobytes(),
                            exception_on_underflow=self.exception_on_overflow
                        )
                        
                        if self.debug_mode:
                            progress_percent = progress * 100
                            cache_key = self.get_frequency_cache_key(mapped_freq)
                            print(f"悅耳進度條：守護線程執行播放（用戶配置）: {original_hz}Hz → {mapped_freq:.1f}Hz (進度: {progress_percent:.1f}%) [算法: {self.fade_algorithm}] [緩存: {cache_key}Hz]")
                            
                except Exception as stream_error:
                    print(f"悅耳進度條：音頻流寫入錯誤: {stream_error}")
                    # 嘗試重新初始化音頻流
                    try:
                        self.cleanup_audio_resources()
                        self.init_audio_stream_32bit()
                        print("悅耳進度條：音頻流重新初始化完成（32位模式）")
                    except Exception as init_error:
                        print(f"悅耳進度條：音頻流重新初始化失敗: {init_error}")
            
        except Exception as e:
            print(f"悅耳進度條：音頻播放執行錯誤: {e}")

    def request_audio_play(self, frequency):
        """請求播放音頻：設置屬性，由守護線程檢查和播放"""
        try:
            # 生成唯一時間戳ID
            new_play_id = time.time()
            
            # 設置播放屬性（原子操作）
            self.play_frequency = frequency
            self.play_id = new_play_id
            
            if self.debug_mode:
                print(f"悅耳進度條：播放請求已提交（32位）: {frequency}Hz, ID={new_play_id}")
                
        except Exception as e:
            print(f"悅耳進度條：提交播放請求錯誤: {e}")
    
    def hook_beep_function(self):
        """攔截tones.beep函數"""
        if not self.original_beep:
            self.original_beep = tones.beep
            tones.beep = self.optimized_beep_32bit
            print("悅耳進度條：已攔截tones.beep函數（32位優化 + 用戶配置版本）")
    
    def unhook_beep_function(self):
        """恢復原始beep函數"""
        if self.original_beep:
            tones.beep = self.original_beep
            self.original_beep = None
            print("悅耳進度條：已恢復原始tones.beep函數")
    
    def optimized_beep_32bit(self, hz, length, left=50, right=50):
        """優化的beep函數 - 32位版本 - 修復原始音效播放問題"""
        # 檢查是否為進度條音效
        if self.is_progress_beep(hz, length, left, right):
            if self.debug_mode:
                print(f"悅耳進度條：識別為進度條音效（32位處理）: {hz}Hz")
            
            if self.enabled and PYAUDIO_AVAILABLE and self.thread_running:
                # 調用回調函數請求播放（立即返回，不阻塞）
                self.request_audio_play(hz)
                return  # 不播放原始音效
            elif self.enabled:
                print("悅耳進度條：守護線程：PyAudio不可用，使用原始音效")
                # 插件啟用但PyAudio不可用，播放原始音效
            # 如果插件停用，繼續執行到最後播放原始音效
        
        # 播放原始音效（進度條音效且插件停用時，或者非進度條音效時）
        if self.original_beep:
            self.original_beep(hz, length, left, right)
    def generate_clean_sine_wave_32bit(self, frequency, duration=0.08, sample_rate=44100, volume=0.6):
        """純Python生成乾淨的正弦波音效 - 32位優化版本（余弦淡入淡出）"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')
        
        fade_samples = int(samples * self.fade_ratio)
        two_pi_f = 2.0 * math.pi * frequency
        sample_rate_inv = 1.0 / sample_rate
        
        # 32位系統使用更保守的音量限制避免報音
        max_amplitude = 30000  # 從32767降低到30000
        
        for i in range(samples):
            t = i * sample_rate_inv
            sample = math.sin(two_pi_f * t)
            
            # 淡入淡出（Raised Cosine曲線）
            if i < fade_samples:
                fade_factor = (1.0 - math.cos(math.pi * i / fade_samples)) / 2.0
                sample *= fade_factor
            elif i >= samples - fade_samples:
                fade_index = samples - i - 1
                fade_factor = (1.0 - math.cos(math.pi * fade_index / fade_samples)) / 2.0
                sample *= fade_factor
            
            # 使用傳入的volume參數，不是self.volume！
            audio_sample = int(sample * max_amplitude * volume)  # ← 修正這裡
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)
        
        return audio_array
    def generate_gaussian_sine_wave_32bit(self, frequency, duration=0.08, sample_rate=44100, volume=0.6):
        """純Python生成高斯淡入淡出的正弦波音效 - 32位優化版本"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')
        
        two_pi_f = 2.0 * math.pi * frequency
        sample_rate_inv = 1.0 / sample_rate
        
        # 32位系統使用更保守的音量限制避免報音
        max_amplitude = 30000
        
        # 高斯參數設定
        sigma = samples * 0.25  # 標準差，控制淡入淡出的平滑度
        center = samples / 2.0  # 高斯分佈的中心
        
        for i in range(samples):
            t = i * sample_rate_inv
            sample = math.sin(two_pi_f * t)
            
            # 高斯淡入淡出
            gaussian_factor = math.exp(-0.5 * ((i - center) / sigma) ** 2)
            sample *= gaussian_factor
            
            # 使用傳入的volume參數，不是self.volume！
            audio_sample = int(sample * max_amplitude * volume)  # ← 修正這裡
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)
        
        return audio_array    
    
    def is_progress_beep(self, hz, length, left, right):
        """檢查是否為進度條音效"""
        return (
            110 <= hz <= 1800 and
            38 <= length <= 42 and
            left == 50 and right == 50
        )

    def clear_audio_cache(self):
        """清理音頻緩存"""
        cache_size = len(self.audio_cache)
        self.audio_cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        print(f"悅耳進度條：音頻緩存已清理（清理了 {cache_size} 個條目）")
    
    def stop_audio_daemon(self):
        """停止守護線程"""
        if self.audio_thread and self.thread_running:
            print("悅耳進度條：正在停止守護線程...")
            self.thread_running = False
            
            # 等待線程退出（最多1秒）
            self.audio_thread.join(timeout=1.0)
            
            if self.audio_thread.is_alive():
                print("悅耳進度條：警告：守護線程未能正常退出")
            else:
                print("悅耳進度條：守護線程已正常退出")
    
    def cleanup_audio_resources(self):
        """清理音頻資源"""
        try:
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
                self.audio_stream = None
            
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None
            
            self.stream_initialized = False
            print("悅耳進度條：守護線程：PyAudio資源清理完成（32位模式）")
        except Exception as e:
            print(f"悅耳進度條：清理PyAudio資源時發生錯誤: {e}")
    
    def terminate(self):
        """插件清理"""
        print("悅耳進度條：正在停用（32位優化 + 用戶配置版本）...")
        
        # 停用播放
        self.enabled = False
        
        # 停止守護線程
        self.stop_audio_daemon()
        
        # 清理音頻資源
        self.cleanup_audio_resources()
        
        # 清理音頻緩存
        self.clear_audio_cache()
        
        # 恢復原始beep函數
        self.unhook_beep_function()
        
        # 清理記錄
        self.beep_log.clear()
        
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
    @script(description="切換悅耳進度條開關", gesture="kb:NVDA+shift+p")
    def script_toggleProgressSound(self, gesture):
        self.enabled = not self.enabled
        
        if self.enabled:
            ui.message("開啟 悅耳進度條")
        else:
            ui.message("關閉 悅耳進度條")
        
        # 詳細日誌
        state_text = "啟用" if self.enabled else "停用"
        if PYAUDIO_AVAILABLE and self.thread_running:
            status = "（32位優化 + 用戶配置可用）"
        else:
            status = "（降級到原始音效）"
        print(f"悅耳進度條：用戶切換音效狀態: {state_text}{status}")