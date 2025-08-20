# -*- coding: utf-8 -*-
# 正弦波進度條音效插件 - 32位優化版本 + 音頻緩存
# 針對NVDA 32位環境優化，解決報音和雙音調問題，並使用音頻緩存提升性能

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
        print(f"32位音頻緩衝區對齊錯誤: {e}")
        return audio_array

# =============================================================================
# 內嵌PyAudio代碼（保持不變）
# =============================================================================

plugin_dir = os.path.dirname(__file__)
print(f"插件目錄: {plugin_dir}")

try:
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    
    import _portaudio as pa
    PYAUDIO_AVAILABLE = True
    print("✓ _portaudio模塊載入成功（32位優化模式）")
except ImportError as e:
    print(f"✗ 無法導入_portaudio模塊: {e}")
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
        
        def _remove_stream(self, stream):
            if stream in self._streams:
                self._streams.remove(stream)

# =============================================================================
# 核心插件類 - 32位優化版本 + 音頻緩存
# =============================================================================

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    
    def __init__(self):
        super().__init__()
        # 插件啟用狀態
        self.enabled = True
        # 原始進度條音效函數的備份
        self.original_beep = None
        self.debug_mode = True
        self.beep_log = []
        
        # 音效參數
        self.min_frequency = 110
        self.max_frequency = 1760
        self.mapped_min_freq = 150
        self.mapped_max_freq = 1500
        
        # 32位優化的音頻生成參數
        self.audio_duration = 0.08  # 80ms播放時長
        self.fade_ratio = 0.45
        self.sample_rate = 48000
        self.volume = 0.5  # 32位系統音量
        
        # 32位優化配置
        self.frames_per_buffer = 1024  # 從4096降低到1024
        self.exception_on_overflow = False  # 防止32位系統溢出崩潰
        self.thread_sleep_interval = 0.12  # 修正線程間隔：120ms
        
        # 音頻緩存系統
        self.audio_cache = {}  # 頻率 -> 音頻數據的緩存字典
        self.cache_hits = 0    # 緩存命中次數統計
        self.cache_misses = 0  # 緩存未命中次數統計
        self.max_cache_size = 50  # 最大緩存條目數量
        
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
        
        # 顯示插件狀態
        pyaudio_status = "可用" if PYAUDIO_AVAILABLE else "不可用"
        print(f"正弦波進度條音效插件已啟動（32位優化 + 音頻緩存）")
        print(f"內嵌PyAudio: {pyaudio_status}")
        print(f"緩衝區配置: {self.frames_per_buffer} frames")
        print(f"音量調整: {self.volume:.2f}")
        print(f"溢出保護: {'啟用' if not self.exception_on_overflow else '停用'}")
        print(f"線程間隔: {self.thread_sleep_interval*1000:.0f}ms")
        print(f"音頻緩存: 最大 {self.max_cache_size} 條目")
        
        if not PYAUDIO_AVAILABLE:
            print("警告：內嵌PyAudio不可用，將使用原始音效")

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
                print(f"音頻緩存命中: {cache_key}Hz (命中率: {self.cache_hits}/{self.cache_hits + self.cache_misses})")
            return self.audio_cache[cache_key]
        
        # 緩存未命中，生成新音頻
        self.cache_misses += 1
        if self.debug_mode:
            print(f"音頻緩存未命中，正在生成: {cache_key}Hz")
        
        # 生成音頻數據
        audio_array = self.generate_clean_sine_wave_32bit(frequency, duration, sample_rate, volume)
        
        # 32位系統音頻緩衝區對齊優化
        audio_array = align_audio_buffer_32bit(audio_array)
        
        # 管理緩存大小
        if len(self.audio_cache) >= self.max_cache_size:
            # 移除最早添加的緩存項（簡單FIFO策略）
            oldest_key = next(iter(self.audio_cache))
            del self.audio_cache[oldest_key]
            if self.debug_mode:
                print(f"緩存已滿，移除最舊條目: {oldest_key}Hz")
        
        # 添加到緩存
        self.audio_cache[cache_key] = audio_array
        
        if self.debug_mode:
            cache_size = len(self.audio_cache)
            print(f"音頻已緩存: {cache_key}Hz (緩存大小: {cache_size}/{self.max_cache_size})")
        
        return audio_array

    def init_audio_stream_32bit(self):
        """初始化PyAudio音頻流 - 32位優化版本"""
        if not PYAUDIO_AVAILABLE or self.stream_initialized:
            return
        
        try:
            self.pyaudio_instance = PyAudio()
            
            # 32位優化配置
            stream_config = {
                'format': paInt16,  # 32位系統使用16位整數格式最穩定
                'channels': 1,
                'rate': self.sample_rate,
                'output': True,
                'frames_per_buffer': self.frames_per_buffer  # 1024 frames
            }
            
            self.audio_stream = self.pyaudio_instance.open(**stream_config)
            self.stream_initialized = True
            
            if self.debug_mode:
                buffer_ms = self.frames_per_buffer / self.sample_rate * 1000
                print("守護線程：PyAudio音頻流初始化成功（32位優化）")
                print(f"緩衝區大小：{self.frames_per_buffer} frames (約{buffer_ms:.1f}ms)")
                print(f"溢出處理：{'停用（32位兼容）' if not self.exception_on_overflow else '啟用'}")
                
        except Exception as e:
            print(f"守護線程：PyAudio流初始化失敗: {e}")
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
        print(f"守護線程已啟動：32位優化模式（間隔{self.thread_sleep_interval*1000:.0f}ms）")
    
    def audio_daemon_worker_32bit(self):
        """守護線程：循環檢查播放請求屬性 - 32位優化版本"""
        print("守護線程開始工作：32位架構適配循環 + 音頻緩存")
        
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
                            print(f"守護線程播放完成（32位優化）: ID={self.play_id}")
                            
                    except Exception as e:
                        print(f"守護線程播放錯誤: {e}")
                        # 即使播放失敗也要更新ID，避免重複嘗試
                        self.last_played_id = self.play_id
                
                # 使用32位優化的循環間隔：120ms
                time.sleep(self.thread_sleep_interval)
                
            except Exception as e:
                print(f"守護線程循環錯誤: {e}")
                time.sleep(0.1)  # 出錯也要延遲，避免瘋狂循環
        
        print("守護線程已退出")

    def execute_audio_play_32bit(self, original_hz):
        """在守護線程中執行音頻播放 - 32位優化版本 + 音頻緩存"""
        try:
            # 頻率映射：110-1760Hz → 150-1500Hz
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
                        print("警告：音頻流不活躍，嘗試重新初始化")
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
                            print(f"守護線程執行播放（32位緩存）: {original_hz}Hz → {mapped_freq:.1f}Hz (進度: {progress_percent:.1f}%) [緩存: {cache_key}Hz]")
                            
                except Exception as stream_error:
                    print(f"音頻流寫入錯誤: {stream_error}")
                    # 嘗試重新初始化音頻流
                    try:
                        self.cleanup_audio_resources()
                        self.init_audio_stream_32bit()
                        print("音頻流重新初始化完成（32位模式）")
                    except Exception as init_error:
                        print(f"音頻流重新初始化失敗: {init_error}")
            
        except Exception as e:
            print(f"音頻播放執行錯誤: {e}")

    def request_audio_play(self, frequency):
        """請求播放音頻：設置屬性，由守護線程檢查和播放"""
        try:
            # 生成唯一時間戳ID
            new_play_id = time.time()
            
            # 設置播放屬性（原子操作）
            self.play_frequency = frequency
            self.play_id = new_play_id
            
            if self.debug_mode:
                print(f"播放請求已提交（32位）: {frequency}Hz, ID={new_play_id}")
                
        except Exception as e:
            print(f"提交播放請求錯誤: {e}")
    
    def hook_beep_function(self):
        """攔截tones.beep函數"""
        if not self.original_beep:
            self.original_beep = tones.beep
            tones.beep = self.optimized_beep_32bit
            print("已攔截tones.beep函數（32位優化 + 音頻緩存版本）")
    
    def unhook_beep_function(self):
        """恢復原始beep函數"""
        if self.original_beep:
            tones.beep = self.original_beep
            self.original_beep = None
            print("已恢復原始tones.beep函數")
    
    def optimized_beep_32bit(self, hz, length, left=50, right=50):
        """優化的beep函數 - 32位版本"""
        # 檢查是否為進度條音效
        if self.is_progress_beep(hz, length, left, right):
            if self.debug_mode:
                print(f"識別為進度條音效（32位處理）: {hz}Hz")
            
            if self.enabled and PYAUDIO_AVAILABLE and self.thread_running:
                # 調用回調函數請求播放（立即返回，不阻塞）
                self.request_audio_play(hz)
                return  # 不播放原始音效
            elif self.enabled:
                print("守護線程：PyAudio不可用，使用原始音效")
                # 繼續播放原始音效
            else:
                return  # 插件停用時完全靜音
        
        # 播放原始音效
        if self.original_beep:
            self.original_beep(hz, length, left, right)

    def generate_clean_sine_wave_32bit(self, frequency, duration=0.08, sample_rate=44100, volume=0.6):
        """純Python生成乾淨的正弦波音效 - 32位優化版本"""
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
            
            # 淡入淡出
            if i < fade_samples:
                fade_factor = (1.0 - math.cos(math.pi * i / fade_samples)) / 2.0
                sample *= fade_factor
            elif i >= samples - fade_samples:
                fade_index = samples - i - 1
                fade_factor = (1.0 - math.cos(math.pi * fade_index / fade_samples)) / 2.0
                sample *= fade_factor
            
            # 使用保守的音量限制
            audio_sample = int(sample * max_amplitude * volume)
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
        print(f"音頻緩存已清理（清理了 {cache_size} 個條目）")
    
    def stop_audio_daemon(self):
        """停止守護線程"""
        if self.audio_thread and self.thread_running:
            print("正在停止守護線程...")
            self.thread_running = False
            
            # 等待線程退出（最多1秒）
            self.audio_thread.join(timeout=1.0)
            
            if self.audio_thread.is_alive():
                print("警告：守護線程未能正常退出")
            else:
                print("守護線程已正常退出")
    
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
            print("守護線程：PyAudio資源清理完成（32位模式）")
        except Exception as e:
            print(f"清理PyAudio資源時發生錯誤: {e}")
    
    def terminate(self):
        """插件清理"""
        print("正弦波進度條音效插件正在停用（32位優化 + 音頻緩存版本）...")
        
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
        
        print("正弦波進度條音效插件已完全停用")
        super().terminate()
    
    # 快捷鍵：切換插件
    @script(description="切換32位優化進度條音效開關", gesture="kb:NVDA+shift+p")
    def script_toggleDaemonProgress(self, gesture):
        self.enabled = not self.enabled
        state_text = "啟用" if self.enabled else "停用"
        
        if PYAUDIO_AVAILABLE and self.thread_running:
            status = "（32位優化 + 音頻緩存可用）"
        else:
            status = "（降級到原始音效）"
        
        ui.message(f"32位優化進度條音效已{state_text}{status}")
        print(f"用戶切換音效狀態: {state_text}")
    
    # 快捷鍵：檢查狀態
    @script(description="檢查32位優化插件狀態", gesture="kb:NVDA+shift+c")
    def script_checkDaemonStatus(self, gesture):
        portaudio_exists = os.path.exists(os.path.join(plugin_dir, "_portaudio.pyd"))
        
        # 檢查線程狀態
        thread_alive = self.audio_thread.is_alive() if self.audio_thread else False
        
        # 計算緩存命中率
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        ui.message("32位優化插件狀態：")
        ui.message(f"_portaudio.pyd文件: {'存在' if portaudio_exists else '不存在'}")
        ui.message(f"內嵌PyAudio載入: {'成功' if PYAUDIO_AVAILABLE else '失敗'}")
        ui.message(f"音頻流狀態: {'已初始化' if self.stream_initialized else '未初始化'}")
        ui.message(f"守護線程: {'運行中' if thread_alive else '已停止'}")
        ui.message(f"緩衝區配置: {self.frames_per_buffer} frames")
        ui.message(f"線程間隔: {self.thread_sleep_interval*1000:.0f}ms")
        ui.message(f"音量設定: {self.volume:.2f}")
        ui.message(f"音頻緩存: {len(self.audio_cache)}/{self.max_cache_size} 條目")
        ui.message(f"緩存命中率: {hit_rate:.1f}% ({self.cache_hits}/{total_requests})")
        
        print(f"32位優化插件詳細狀態:")
        print(f"  PyAudio可用: {PYAUDIO_AVAILABLE}")
        print(f"  音頻流初始化: {self.stream_initialized}")
        print(f"  線程運行狀態: {self.thread_running}")
        print(f"  線程存活狀態: {thread_alive}")
        print(f"  緩衝區大小: {self.frames_per_buffer} frames")
        print(f"  溢出保護: {'停用' if not self.exception_on_overflow else '啟用'}")
        print(f"  線程間隔: {self.thread_sleep_interval*1000:.0f}ms")
        print(f"  音量調整: {self.volume:.2f}")
        print(f"  音頻緩存大小: {len(self.audio_cache)}/{self.max_cache_size}")
        print(f"  緩存命中: {self.cache_hits}, 未命中: {self.cache_misses}")
        print(f"  緩存命中率: {hit_rate:.1f}%")
        print(f"  當前播放請求: freq={self.play_frequency}, id={self.play_id}")
        print(f"  最後播放ID: {self.last_played_id}")
        print(f"  播放架構: 32位優化守護線程 + 音頻緩存")
    
    # 快捷鍵：清理音頻緩存
    @script(description="清理音頻緩存", gesture="kb:NVDA+shift+x")
    def script_clearAudioCache(self, gesture):
        cache_size = len(self.audio_cache)
        hit_rate = (self.cache_hits / (self.cache_hits + self.cache_misses) * 100) if (self.cache_hits + self.cache_misses) > 0 else 0
        
        self.clear_audio_cache()
        
        ui.message(f"音頻緩存已清理")
        ui.message(f"清理前狀態: {cache_size} 條目，命中率 {hit_rate:.1f}%")
        print(f"用戶手動清理音頻緩存：清理了 {cache_size} 個條目")
    
    # 快捷鍵：切換調試模式
    @script(description="切換調試模式", gesture="kb:NVDA+shift+d")
    def script_toggleDebug(self, gesture):
        self.debug_mode = not self.debug_mode
        state_text = "開啟" if self.debug_mode else "關閉"
        ui.message(f"32位優化調試模式已{state_text}")
        print(f"調試模式: {state_text}")