# -*- coding: utf-8 -*-
# 正弦波進度條音效插件 - 守護線程屬性檢查版本
# 使用守護線程+屬性檢查，避免破音和重疊，無隊列設計

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
# 內嵌PyAudio代碼（保持不變）
# =============================================================================

plugin_dir = os.path.dirname(__file__)
print(f"插件目錄: {plugin_dir}")

try:
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    
    import _portaudio as pa
    PYAUDIO_AVAILABLE = True
    print("✓ _portaudio模塊載入成功")
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
# 內嵌PyAudio代碼結束
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
        self.mapped_min_freq = 200
        self.mapped_max_freq = 1200
        
        # 音頻生成參數
        self.audio_duration = 0.08  # 80ms播放時長
        self.fade_ratio = 0.45
        self.sample_rate = 44100
        self.volume = 0.4
        
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
            self.init_audio_stream()
            self.start_audio_daemon()
        
        # 顯示插件狀態
        pyaudio_status = "可用" if PYAUDIO_AVAILABLE else "不可用"
        print(f"正弦波進度條音效插件已啟動")
        print(f"內嵌PyAudio: {pyaudio_status}")
        print(f"播放架構: {'守護線程屬性檢查' if PYAUDIO_AVAILABLE else '原始音效'}")
        
        if not PYAUDIO_AVAILABLE:
            print("警告：內嵌PyAudio不可用，將使用原始音效")
    
    # 初始化音頻流
    def init_audio_stream(self):
        """初始化PyAudio音頻流"""
        if not PYAUDIO_AVAILABLE or self.stream_initialized:
            return
        
        try:
            self.pyaudio_instance = PyAudio()
            self.audio_stream = self.pyaudio_instance.open(
                format=paInt16,
                channels=1,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=1024
            )
            self.stream_initialized = True
            
            if self.debug_mode:
                print("守護線程：PyAudio音頻流初始化成功")
                
        except Exception as e:
            print(f"守護線程：PyAudio流初始化失敗: {e}")
            self.stream_initialized = False
    
    # 啟動守護線程
    def start_audio_daemon(self):
        """啟動守護線程進行屬性檢查和播放"""
        if not PYAUDIO_AVAILABLE or self.thread_running:
            return
        
        self.thread_running = True
        self.audio_thread = threading.Thread(
            target=self.audio_daemon_worker,
            daemon=True  # 守護線程，程式退出時自動結束
        )
        self.audio_thread.start()
        print("守護線程已啟動：屬性檢查模式")
    
    # 守護線程工作函數
    def audio_daemon_worker(self):
        """守護線程：循環檢查播放請求屬性"""
        print("守護線程開始工作：循環間隔100ms")
        
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
                        self.execute_audio_play(self.play_frequency)
                        # 更新最後播放的ID
                        self.last_played_id = self.play_id
                        
                        if self.debug_mode:
                            print(f"守護線程播放完成: ID={self.play_id}")
                            
                    except Exception as e:
                        print(f"守護線程播放錯誤: {e}")
                        # 即使播放失敗也要更新ID，避免重複嘗試
                        self.last_played_id = self.play_id
                
                # 循環延遲：100ms，大於80ms播放時長，確保不重疊
                time.sleep(0.1)
                
            except Exception as e:
                print(f"守護線程循環錯誤: {e}")
                time.sleep(0.1)  # 出錯也要延遲，避免瘋狂循環
        
        print("守護線程已退出")
    
    # 執行音頻播放（在守護線程中調用）
    def execute_audio_play(self, original_hz):
        """在守護線程中執行音頻播放"""
        try:
            # 頻率映射：110-1760Hz → 200-1200Hz
            progress = (original_hz - self.min_frequency) / (self.max_frequency - self.min_frequency)
            progress = max(0.0, min(1.0, progress))
            mapped_freq = self.mapped_min_freq + progress * (self.mapped_max_freq - self.mapped_min_freq)
            
            # 生成音頻數據
            audio_array = self.generate_clean_sine_wave(
                frequency=mapped_freq,
                duration=self.audio_duration,
                sample_rate=self.sample_rate,
                volume=self.volume
            )
            
            # 播放音頻
            if self.enabled and self.stream_initialized and self.audio_stream:
                self.audio_stream.write(audio_array.tobytes())
                
                if self.debug_mode:
                    progress_percent = progress * 100
                    print(f"守護線程執行播放: {original_hz}Hz → {mapped_freq:.1f}Hz (進度: {progress_percent:.1f}%)")
            
        except Exception as e:
            print(f"音頻播放執行錯誤: {e}")
    
    # 請求播放回調函數（從攔截函數調用）
    def request_audio_play(self, frequency):
        """請求播放音頻：設置屬性，由守護線程檢查和播放"""
        try:
            # 生成唯一時間戳ID
            new_play_id = time.time()
            
            # 設置播放屬性（原子操作）
            self.play_frequency = frequency
            self.play_id = new_play_id
            
            if self.debug_mode:
                print(f"播放請求已提交: {frequency}Hz, ID={new_play_id}")
                
        except Exception as e:
            print(f"提交播放請求錯誤: {e}")
    
    # 攔截tones.beep函數
    def hook_beep_function(self):
        if not self.original_beep:
            self.original_beep = tones.beep
            tones.beep = self.optimized_beep
            print("已攔截tones.beep函數（守護線程屬性檢查版本）")
    
    # 恢復原始beep函數
    def unhook_beep_function(self):
        if self.original_beep:
            tones.beep = self.original_beep
            self.original_beep = None
            print("已恢復原始tones.beep函數")
    
    # 優化版本的beep函數
    def optimized_beep(self, hz, length, left=50, right=50):
        # 記錄所有beep調用
        if self.debug_mode:
            beep_info = {
                'hz': hz, 'length': length, 'left': left, 'right': right,
                'time': time.time()
            }
            self.beep_log.append(beep_info)
            print(f"攔截到音效: {hz}Hz, {length}ms, L:{left}, R:{right}")
        
        # 檢查是否為進度條音效
        if self.is_progress_beep(hz, length, left, right):
            if self.debug_mode:
                print(f"識別為進度條音效: {hz}Hz")
            
            if self.enabled and PYAUDIO_AVAILABLE and self.thread_running:
                # 調用回調函數請求播放（立即返回，不阻塞）
                self.request_audio_play(hz)
                return  # 不播放原始音效
            elif self.enabled:
                print("守護線程：PyAudio不可用，使用原始音效")
        
        # 播放原始音效
        if self.original_beep:
            self.original_beep(hz, length, left, right)
    
    # 純Python生成正弦波（保持不變）
    def old_generate_clean_sine_wave(self, frequency, duration=0.08, sample_rate=44100, volume=0.6):
        """純Python生成乾淨的正弦波音效"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')
        
        fade_samples = int(samples * self.fade_ratio)
        two_pi_f = 2.0 * math.pi * frequency
        sample_rate_inv = 1.0 / sample_rate
        
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
            
            audio_sample = int(sample * 32767 * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)
        
        return audio_array

    def generate_clean_sine_wave(self, frequency, duration=0.08, sample_rate=44100, volume=0.35):
        """純Python生成乾淨的正弦波音效（高斯淡入淡出版本）"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')
        
        # 增加淡入淡出時間到50%，配合高斯曲線提供極致平滑過渡
        fade_samples = int(samples * 0.5)
        
        # 預計算常數
        two_pi_f = 2.0 * math.pi * frequency
        sample_rate_inv = 1.0 / sample_rate
        
        for i in range(samples):
            # 計算時間和正弦波樣本
            t = i * sample_rate_inv
            sample = math.sin(two_pi_f * t)
            
            # 高斯淡入淡出效果
            if i < fade_samples:
                # 高斯淡入：從-3標準差到0，創造平滑上升
                # 將樣本位置映射到-3到0的範圍
                x = (i / fade_samples) * 3 - 3  # 從-3到0
                # 高斯函數：e^(-x²/2)，當x從-3到0時，值從接近0平滑上升到1
                fade_factor = math.exp(-(x * x) / 2)
                sample *= fade_factor
                
            elif i >= samples - fade_samples:
                # 高斯淡出：從0到-3標準差，創造平滑下降
                fade_index = samples - i - 1  # 從fade_samples-1到0
                # 將位置映射到0到-3的範圍
                x = (fade_index / fade_samples) * 3 - 3  # 從0到-3
                # 高斯函數：當x從0到-3時，值從1平滑下降到接近0
                fade_factor = math.exp(-(x * x) / 2)
                sample *= fade_factor
            
            # 轉換為16位整數（使用較低音量35%避免爆音）
            audio_sample = int(sample * 32767 * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)
        
        return audio_array    
    
    # 進度條音效判斷
    def is_progress_beep(self, hz, length, left, right):
        return (
            110 <= hz <= 1800 and
            38 <= length <= 42 and
            left == 50 and right == 50
        )
    
    # 停止守護線程
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
    
    # 清理資源
    def cleanup_audio_resources(self):
        try:
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
                self.audio_stream = None
            
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None
            
            self.stream_initialized = False
            print("守護線程：PyAudio資源清理完成")
        except Exception as e:
            print(f"清理PyAudio資源時發生錯誤: {e}")
    
    # 插件清理
    def terminate(self):
        print("正弦波進度條音效插件正在停用...")
        
        # 停用播放
        self.enabled = False
        
        # 停止守護線程
        self.stop_audio_daemon()
        
        # 清理音頻資源
        self.cleanup_audio_resources()
        
        # 恢復原始beep函數
        self.unhook_beep_function()
        
        # 清理記錄
        self.beep_log.clear()
        
        print("正弦波進度條音效插件已完全停用")
        super().terminate()
    
    # 快捷鍵：切換插件
    @script(description="切換守護線程進度條音效開關", gesture="kb:NVDA+shift+p")
    def script_toggleDaemonProgress(self, gesture):
        self.enabled = not self.enabled
        state_text = "啟用" if self.enabled else "停用"
        
        if PYAUDIO_AVAILABLE and self.thread_running:
            status = "（守護線程屬性檢查可用）"
        else:
            status = "（降級到原始音效）"
        
        ui.message(f"守護線程進度條音效已{state_text}{status}")
        print(f"用戶切換音效狀態: {state_text}")
    
    # 快捷鍵：檢查狀態
    @script(description="檢查守護線程插件狀態", gesture="kb:NVDA+shift+c")
    def script_checkDaemonStatus(self, gesture):
        portaudio_exists = os.path.exists(os.path.join(plugin_dir, "_portaudio.pyd"))
        
        # 檢查線程狀態
        thread_alive = self.audio_thread.is_alive() if self.audio_thread else False
        
        ui.message("守護線程插件狀態：")
        ui.message(f"_portaudio.pyd文件: {'存在' if portaudio_exists else '不存在'}")
        ui.message(f"內嵌PyAudio載入: {'成功' if PYAUDIO_AVAILABLE else '失敗'}")
        ui.message(f"音頻流狀態: {'已初始化' if self.stream_initialized else '未初始化'}")
        ui.message(f"守護線程: {'運行中' if thread_alive else '已停止'}")
        ui.message(f"當前播放ID: {self.play_id}")
        ui.message(f"最後播放ID: {self.last_played_id}")
        
        print(f"守護線程插件詳細狀態:")
        print(f"  PyAudio可用: {PYAUDIO_AVAILABLE}")
        print(f"  音頻流初始化: {self.stream_initialized}")
        print(f"  線程運行狀態: {self.thread_running}")
        print(f"  線程存活狀態: {thread_alive}")
        print(f"  當前播放請求: freq={self.play_frequency}, id={self.play_id}")
        print(f"  最後播放ID: {self.last_played_id}")
        print(f"  播放架構: 守護線程屬性檢查（100ms循環）")
    
    # 快捷鍵：測試
    @script(description="測試守護線程音效序列", gesture="kb:NVDA+shift+t")
    def script_testDaemonSequence(self, gesture):
        if not (PYAUDIO_AVAILABLE and self.thread_running):
            ui.message("守護線程不可用，無法測試")
            return
        
        ui.message("測試守護線程音效：100ms間隔播放序列")
        
        test_frequencies = [110, 200, 350, 500, 700, 900, 1200, 1500, 1760]
        
        def sequence_test():
            for i, freq in enumerate(test_frequencies):
                self.request_audio_play(freq)
                print(f"提交測試請求 {i+1}/{len(test_frequencies)}: {freq}Hz")
                time.sleep(0.15)  # 150ms間隔，讓守護線程有時間處理
        
        threading.Thread(target=sequence_test, daemon=True).start()
    
    # 快捷鍵：切換調試模式
    @script(description="切換調試模式", gesture="kb:NVDA+shift+d")
    def script_toggleDebug(self, gesture):
        self.debug_mode = not self.debug_mode
        state_text = "開啟" if self.debug_mode else "關閉"
        ui.message(f"調試模式已{state_text}")
        print(f"調試模式: {state_text}")