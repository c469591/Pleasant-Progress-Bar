# -*- coding: utf-8 -*-
# 悅耳進度條
# 接管 tones.beep 把進度條提示音改為悅耳的波形（含音頻緩存）
# 支援用戶自定義配置：淡入淡出算法、音量、頻率範圍
import wx
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
    log.warning("悅耳進度條：配置模塊載入失敗: %s", e)


def map_percentage_to_frequency(percentage, min_frequency, max_frequency):
    """Map a progress percentage to the configured output frequency range."""
    percentage = float(percentage)
    min_frequency = float(min_frequency)
    max_frequency = float(max_frequency)

    if not 0.0 <= percentage <= 100.0:
        raise ValueError("percentage must be between 0 and 100")
    if min_frequency >= max_frequency:
        raise ValueError("minimum frequency must be lower than maximum frequency")

    return min_frequency + (percentage / 100.0) * (max_frequency - min_frequency)


# 音頻緩衝區對齊輔助函數


def align_audio_buffer(audio_array):
    """確保音頻緩衝區大小是 4 bytes 的倍數，避免邊界問題"""
    try:
        # 確保緩衝區大小是 4 bytes 的倍數
        buffer_size = len(audio_array)
        alignment_bytes = 4
        
        if buffer_size % alignment_bytes != 0:
            # 填充到對齊邊界
            padding_needed = alignment_bytes - (buffer_size % alignment_bytes)
            for _ in range(padding_needed // 2):  # 每個樣本2字節
                audio_array.append(0)
        
        return audio_array
    except Exception as e:
        log.error("悅耳進度條：音頻緩衝區對齊錯誤: %s", e)
        return audio_array

# =============================================================================
# 內嵌PyAudio代碼
# =============================================================================

plugin_dir = os.path.dirname(__file__)

try:
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    
    import _portaudio as pa
    PYAUDIO_AVAILABLE = True
except ImportError as e:
    log.warning("悅耳進度條：無法導入_portaudio模塊: %s", e)
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

    def old_get_device_info_by_index(device_index):
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

    def get_device_info_by_index(self, device_index):
        """根據索引獲取設備信息 - 修正版本"""
        try:
            # 使用正確的函數名稱
            device_info = pa.get_device_info(device_index)
            
            # 提取設備信息
            name = device_info.name
            # 處理 bytes 格式的名稱
            if isinstance(name, bytes):
                name = name.decode('utf-8', errors='ignore')
            
            return {
                'index': device_index,
                'name': name,
                'defaultSampleRate': float(device_info.defaultSampleRate),
                'maxOutputChannels': int(device_info.maxOutputChannels)
            }
            
        except Exception as e:
            # 降級到通用名稱
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
            
            # 添加Host API掃描功能 - 參考ooo.py
            self.host_apis = self._scan_host_apis()
            self.preferred_host_api = self._select_preferred_host_api()
            
            if self.debug_mode if hasattr(self, 'debug_mode') else False:
                if self.preferred_host_api:
                    pass
                else:
                    pass
        
        def _scan_host_apis(self):
            """掃描所有可用的Host API - 參考ooo.py"""
            host_apis = {}
            try:
                host_api_count = pa.get_host_api_count()
                
                for i in range(host_api_count):
                    host_api_info = pa.get_host_api_info(i)
                    
                    # 直接訪問屬性
                    api_name = host_api_info.name if hasattr(host_api_info, 'name') else f'Host API {i}'
                    device_count = host_api_info.deviceCount if hasattr(host_api_info, 'deviceCount') else 0
                    
                    host_apis[i] = {
                        'index': i,
                        'name': api_name,
                        'info': host_api_info,
                        'device_count': device_count
                    }
                
                return host_apis
            except Exception as e:
                log.warning("悅耳進度條：Host API掃描失敗: %s", e)
                return {}

        def _select_preferred_host_api(self):
            """選擇首選Host API - 優先WASAPI用於設備名稱獲取"""
            api_priority = [
                'Windows WASAPI',
                'WASAPI', 
                'Windows DirectSound',
                'DirectSound',
                'WDM-KS',
                'MME'
            ]
            
            for preferred_name in api_priority:
                for api_index, api_data in self.host_apis.items():
                    api_name = api_data['name']
                    if preferred_name.lower() in api_name.lower():
                        return api_data
            
            # 降級到第一個有設備的API
            for api_index, api_data in self.host_apis.items():
                if api_data['device_count'] > 0:
                    return api_data
            
            return None

        def get_devices_by_host_api(self, host_api_index):
            """獲取指定Host API的所有設備 - 參考ooo.py"""
            devices = []
            try:
                total_device_count = pa.get_device_count()
                
                for global_index in range(total_device_count):
                    device_info = pa.get_device_info(global_index)
                    
                    # 直接訪問屬性
                    device_host_api = device_info.hostApi if hasattr(device_info, 'hostApi') else -1
                    
                    if device_host_api == host_api_index:
                        devices.append({
                            'global_index': global_index,
                            'name': device_info.name if hasattr(device_info, 'name') else f'Device {global_index}',
                            'maxOutputChannels': device_info.maxOutputChannels if hasattr(device_info, 'maxOutputChannels') else 0,
                            'hostApi': device_host_api
                        })
                
                return devices
                
            except Exception as e:
                log.warning("悅耳進度條：獲取Host API %s 設備失敗: %s", host_api_index, e)
                return []
        
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
            """獲取設備信息 - 改進版本參考ooo.py"""
            try:
                device_info = pa.get_device_info(device_index)
                
                # 直接訪問屬性並處理設備名稱
                name = device_info.name if hasattr(device_info, 'name') else f'Device {device_index}'
                if isinstance(name, bytes):
                    name = name.decode('utf-8', errors='ignore')
                
                # 建立設備信息字典
                result = {
                    'index': device_index,
                    'name': name.strip() if name else f'Device {device_index}',
                    'defaultSampleRate': float(device_info.defaultSampleRate) if hasattr(device_info, 'defaultSampleRate') else 44100.0,
                    'maxOutputChannels': int(device_info.maxOutputChannels) if hasattr(device_info, 'maxOutputChannels') else 0,
                    'hostApi': device_info.hostApi if hasattr(device_info, 'hostApi') else -1
                }
                
                # 添加Host API名稱
                host_api_index = result['hostApi']
                if hasattr(self, 'host_apis') and host_api_index in self.host_apis:
                    result['host_api_name'] = self.host_apis[host_api_index]['name']
                else:
                    result['host_api_name'] = f'Host API {host_api_index}'
                
                return result
                
            except Exception as e:
                log.warning("悅耳進度條：獲取設備信息失敗: %s", e)
                return {
                    'index': device_index,
                    'name': f'Device {device_index}',
                    'defaultSampleRate': 44100.0,
                    'maxOutputChannels': 0,
                    'hostApi': -1,
                    'host_api_name': 'Unknown',
                    'error': str(e)
                }
        
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

        # 檢測設備最佳音頻參數
        self.detect_optimal_audio_params()
        
        # 音頻參數配置
        self.frames_per_buffer = 128  #緩衝大小
        self.exception_on_overflow = False  # underflow 不拋例外，避免偶發中斷
        # 動態計算線程間隔：波形長度 + 40ms
        self.thread_sleep_interval = self.audio_duration + 0.04
        
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
        self.play_preview_settings = None  # 設定面板的一次性預覽參數
        self.play_id = None          # 唯一播放標誌（時間戳）
        self.play_request_lock = threading.Lock()
        
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
        
        # 註冊設定面板到NVDA設定對話框
        self.register_settings_panel()
        
        if not PYAUDIO_AVAILABLE:
            log.warning("悅耳進度條：內嵌PyAudio不可用，將使用原始音效")

    def load_user_config(self):
        """載入用戶配置"""
        if CONFIG_AVAILABLE:
            try:
                # 載入配置
                algorithm = sine_progress_config.get_fade_algorithm()
                volume = sine_progress_config.get_volume()
                min_freq, max_freq = sine_progress_config.get_frequency_range()
                
            except Exception as e:
                log.error("悅耳進度條：載入用戶配置時發生錯誤: %s", e)
        else:
            log.warning("悅耳進度條：配置模塊不可用，使用預設參數")


    def calculate_thread_interval(self):
        # 波形長度 + 40ms的緩衝時間
        self.thread_sleep_interval = self.audio_duration + 0.04

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
                
                # 根據算法設定淡入淡出比例
                if self.fade_algorithm == 'gaussian':
                    self.fade_ratio = 0.3  # 高斯算法使用較小的淡入淡出比例
                else:
                    self.fade_ratio = 0.45  # 余弦算法使用原來的比例
                
                # 重新計算線程間隔
                self.calculate_thread_interval()

            except Exception as e:
                log.error("悅耳進度條：應用配置參數時發生錯誤: %s", e)
                self.apply_default_parameters()
        else:
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

    def register_settings_panel(self):
        """註冊設定面板到NVDA設定對話框"""
        if CONFIG_AVAILABLE:
            try:
                # 將設定面板添加到NVDA設定對話框的類別列表中
                if hasattr(NVDASettingsDialog, 'categoryClasses'):
                    if SineProgressSettingsPanel not in NVDASettingsDialog.categoryClasses:
                        NVDASettingsDialog.categoryClasses.append(SineProgressSettingsPanel)
                else:
                    log.error("悅耳進度條：無法註冊設定面板 - NVDASettingsDialog.categoryClasses不存在")
            except Exception as e:
                log.error("悅耳進度條：註冊設定面板時發生錯誤: %s", e)

    def reload_configuration(self):
        """重新載入配置並重新初始化（由設定面板調用）"""
    
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
                self.init_audio_stream()
                self.start_audio_daemon()

        # 重新計算線程間隔
            self.calculate_thread_interval()
            
        except Exception as e:
            log.error("悅耳進度條：重新載入配置時發生錯誤: %s", e)


    # 修改reinitialize_audio_system方法
    def reinitialize_audio_system(self):
        """重新初始化音頻系統"""
        try:
            # 停止守護線程
            self.stop_audio_daemon()
            
            # 清理現有音頻資源
            self.cleanup_audio_resources()
            
            # 清理音頻緩存
            self.clear_audio_cache()
            
            # 重新檢測設備參數
            self.detect_optimal_audio_params()
            
            # 重新初始化PyAudio音頻流
            if PYAUDIO_AVAILABLE:
                self.init_audio_stream()
                self.start_audio_daemon()
            
        except Exception as e:
            log.error("悅耳進度條：重新初始化音頻系統時發生錯誤: %s", e)


    def get_frequency_cache_key(self, frequency, volume=None, waveform_type=None):
        """生成頻率的緩存鍵，將頻率四捨五入到小數點後1位"""
        # 使用當前配置值作為默認值
        if volume is None:
            volume = self.volume
        if waveform_type is None:
            waveform_type = self.waveform_type
        
        # 創建包含所有參數的緩存鍵
        freq_key = round(frequency, 1)
        volume_key = round(volume, 2)  # 音量精確到小數點後2位
        
        return f"{freq_key}Hz_{volume_key}vol_{waveform_type}"


    def get_cached_audio_or_generate(self, frequency, duration, sample_rate, volume):
        """獲取緩存的音頻或生成新的音頻"""
        # 生成包含音量和波形類型的緩存鍵
        cache_key = self.get_frequency_cache_key(frequency, volume, self.waveform_type)
        
        # 檢查緩存
        if cache_key in self.audio_cache:
            self.cache_hits += 1
            return self.audio_cache[cache_key]
        
        # 緩存未命中，生成新音頻
        self.cache_misses += 1
        
        # 根據配置選擇波形類型生成音頻數據
        audio_array = self.generate_waveform(
            frequency=frequency,
            duration=duration,
            sample_rate=sample_rate,
            volume=volume,
            waveform_type=self.waveform_type
        )        

        # 音頻緩衝區對齊處理
        audio_array = align_audio_buffer(audio_array)
        
        # 管理緩存大小
        if len(self.audio_cache) >= self.max_cache_size:
            # 移除最早添加的緩存項（簡單FIFO策略）
            oldest_key = next(iter(self.audio_cache))
            del self.audio_cache[oldest_key]
        
        # 添加到緩存
        self.audio_cache[cache_key] = audio_array
        
        return audio_array

    def old_detect_optimal_audio_params(self):
        """檢測當前播放設備的最佳音頻參數"""
        if not PYAUDIO_AVAILABLE:
            # 後備默認值
            self.sample_rate = 48000
            self.optimal_format = paInt16
            return
        
        try:
            temp_pyaudio = PyAudio()
            
            # 獲取默認輸出設備信息
            default_device = temp_pyaudio.get_default_output_device_info()
            device_index = default_device['index']
            
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
                        temp_pyaudio.terminate()
                        return
                        
                    except Exception:
                        continue
            
            temp_pyaudio.terminate()
            
        except Exception as e:
            # 檢測失敗，使用安全默認值
            self.sample_rate = 48000
            self.optimal_format = paInt16
            log.warning("悅耳進度條：設備檢測失敗，使用默認配置: %s", e)

    def detect_optimal_audio_params(self):
        """檢測當前播放設備的最佳音頻參數"""
        if not PYAUDIO_AVAILABLE:
            # 後備默認值
            self.sample_rate = 48000
            paInt16 = 8
            self.optimal_format = paInt16
            self.output_device_index = None
            return
        
        # 使用默認設備配置
        self.sample_rate = 48000
        self.optimal_format = paInt16
        self.output_device_index = None

    def old_init_audio_stream_32bit(self):
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
                
        except Exception as e:
            log.error("悅耳進度條：守護線程：PyAudio流初始化失敗: %s", e)
            self.stream_initialized = False
            self.pyaudio_instance = None
            self.audio_stream = None


    def init_audio_stream(self):
        """初始化PyAudio音頻流"""
        if not PYAUDIO_AVAILABLE or self.stream_initialized:
            return
        
        try:
            self.pyaudio_instance = PyAudio()
            
            # 使用檢測到的最佳配置和具體設備索引
            stream_config = {
                'format': self.optimal_format,
                'channels': 1,
                'rate': self.sample_rate,
                'output': True,
                'frames_per_buffer': self.frames_per_buffer
            }
            
            # 如果有具體的設備索引，則指定輸出設備
            if hasattr(self, 'output_device_index') and self.output_device_index is not None:
                stream_config['output_device_index'] = self.output_device_index
                
                # 驗證設備信息
                try:
                    self.pyaudio_instance.get_device_info_by_index(self.output_device_index)
                except Exception as device_info_error:
                    log.warning("悅耳進度條：無法獲取設備信息: %s", device_info_error)
            
            self.audio_stream = self.pyaudio_instance.open(**stream_config)
            self.stream_initialized = True
                
        except Exception as e:
            # 如果指定設備失敗，嘗試使用默認設備
            if hasattr(self, 'output_device_index') and self.output_device_index is not None:
                log.warning("悅耳進度條：指定設備初始化失敗，嘗試使用默認設備: %s", e)
                try:
                    self.cleanup_audio_resources()
                    # 暫時移除設備索引，使用默認
                    temp_device_index = self.output_device_index
                    self.output_device_index = None
                    
                    # 重新嘗試初始化
                    self.pyaudio_instance = PyAudio()
                    stream_config = {
                        'format': self.optimal_format,
                        'channels': 1,
                        'rate': self.sample_rate,
                        'output': True,
                        'frames_per_buffer': self.frames_per_buffer
                    }
                    self.audio_stream = self.pyaudio_instance.open(**stream_config)
                    self.stream_initialized = True
                    
                    # 恢復設備索引（保留用戶設置）
                    self.output_device_index = temp_device_index
                    
                except Exception as default_error:
                    log.error("悅耳進度條：默認設備初始化也失敗: %s", default_error)
                    self.stream_initialized = False
                    self.pyaudio_instance = None
                    self.audio_stream = None
            else:
                log.error("悅耳進度條：守護線程：PyAudio流初始化失敗: %s", e)
                self.stream_initialized = False
                self.pyaudio_instance = None
                self.audio_stream = None

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
    
    def audio_daemon_worker(self):
        """守護線程：循環檢查播放請求屬性，發現新請求就播放"""
        while self.thread_running:
            try:
                with self.play_request_lock:
                    request_id = self.play_id
                    request_frequency = self.play_frequency
                    preview_settings = self.play_preview_settings

                # 檢查是否有新的播放請求
                if (request_id is not None and
                    request_id != self.last_played_id and
                    (request_frequency is not None or preview_settings is not None)):
                    is_preview = preview_settings is not None
                    
                    # 設定面板預覽即使在插件停用時也應播放。
                    if (not is_preview and not self.enabled) or not self.stream_initialized:
                        # 插件已停用，跳過播放但更新ID避免重複檢查
                        self.last_played_id = request_id
                        continue
                    
                    # 執行播放
                    try:
                        if is_preview:
                            self.execute_preview_audio(preview_settings)
                        else:
                            self.execute_audio_play(request_frequency)
                        # 更新最後播放的ID
                        self.last_played_id = request_id
                            
                    except Exception as e:
                        log.error("悅耳進度條：守護線程播放錯誤: %s", e)
                        # 即使播放失敗也要更新ID，避免重複嘗試
                        self.last_played_id = request_id
                
                # 循環間隔由波形長度決定，見 calculate_thread_interval
                time.sleep(self.thread_sleep_interval)
                
            except Exception as e:
                log.error("悅耳進度條：守護線程循環錯誤: %s", e)
                time.sleep(0.1)  # 出錯也要延遲，避免瘋狂循環

    def old_execute_audio_play_32bit(self, original_hz):
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
                volume=self.volume
                #volume=0.2  # 進一步降低音量避免32位系統報音
            )
            
            # 播放音頻
            if self.enabled and self.stream_initialized and self.audio_stream:
                try:
                    # 檢查流是否仍然活躍
                    if hasattr(self.audio_stream, 'is_active') and not self.audio_stream.is_active():
                        log.warning("悅耳進度條：音頻流不活躍，嘗試重新初始化")
                        self.cleanup_audio_resources()
                        self.init_audio_stream()

                    if self.audio_stream:
                        # 按設定的 underflow 處理策略寫入
                        self.audio_stream.write(
                            audio_array.tobytes(),
                            exception_on_underflow=self.exception_on_overflow
                        )
                            
                except Exception as stream_error:
                    log.error("悅耳進度條：音頻流寫入錯誤: %s", stream_error)
                    # 嘗試重新初始化音頻流
                    try:
                        self.cleanup_audio_resources()
                        self.init_audio_stream()
                    except Exception as init_error:
                        log.error("悅耳進度條：音頻流重新初始化失敗: %s", init_error)
            
        except Exception as e:
            log.error("悅耳進度條：音頻播放執行錯誤: %s", e)

    def execute_audio_play(self, original_hz):
        """在守護線程中執行音頻播放，含音頻緩存與頻率映射"""
        try:
            # 修正頻率映射邏輯：將原始進度條頻率範圍重新映射到用戶設定範圍
            
            # 原始進度條的頻率範圍（根據is_progress_beep函數定義）
            ORIGINAL_MIN_FREQ = 110   # 原始進度條最低頻率
            ORIGINAL_MAX_FREQ = 1800  # 原始進度條最高頻率
            
            # 計算原始頻率在原始範圍中的進度比例
            original_progress = (original_hz - ORIGINAL_MIN_FREQ) / (ORIGINAL_MAX_FREQ - ORIGINAL_MIN_FREQ)
            # 確保進度在0-1範圍內
            original_progress = max(0.0, min(1.0, original_progress))
            
            # 將進度比例映射到用戶設定的頻率範圍
            mapped_freq = self.mapped_min_freq + original_progress * (self.mapped_max_freq - self.mapped_min_freq)
            
            # 使用音頻緩存系統獲取或生成音頻數據
            audio_array = self.get_cached_audio_or_generate(
                frequency=mapped_freq,
                duration=self.audio_duration,
                sample_rate=self.sample_rate,
                volume=self.volume
            )
            
            # 播放音頻
            if self.enabled and self.stream_initialized and self.audio_stream:
                try:
                    # 檢查流是否仍然活躍
                    if hasattr(self.audio_stream, 'is_active') and not self.audio_stream.is_active():
                        log.warning("悅耳進度條：音頻流不活躍，嘗試重新初始化到當前設備")
                        device_index_backup = getattr(self, 'output_device_index', None)
                        self.cleanup_audio_resources()
                        # 保持原有的設備索引
                        if device_index_backup is not None:
                            self.output_device_index = device_index_backup
                        self.init_audio_stream()

                    if self.audio_stream:
                        # 按設定的 underflow 處理策略寫入
                        self.audio_stream.write(
                            audio_array.tobytes(),
                            exception_on_underflow=self.exception_on_overflow
                        )
                            
                except Exception as stream_error:
                    log.error("悅耳進度條：音頻流寫入錯誤: %s", stream_error)
                    # 嘗試重新初始化音頻流，保持當前設備索引
                    try:
                        device_index_backup = getattr(self, 'output_device_index', None)
                        self.cleanup_audio_resources()
                        # 保持原有的設備索引
                        if device_index_backup is not None:
                            self.output_device_index = device_index_backup
                        self.init_audio_stream()
                    except Exception as init_error:
                        log.error("悅耳進度條：音頻流重新初始化失敗: %s", init_error)
            
        except Exception as e:
            log.error("悅耳進度條：音頻播放執行錯誤: %s", e)

    def execute_preview_audio(self, preview_settings):
        """Play one settings-panel preview without changing the saved configuration."""
        frequency = map_percentage_to_frequency(
            preview_settings['percentage'],
            preview_settings['min_frequency'],
            preview_settings['max_frequency']
        )
        audio_array = self.generate_waveform(
            frequency=frequency,
            duration=preview_settings['audio_duration'],
            sample_rate=self.sample_rate,
            volume=preview_settings['volume'],
            waveform_type=preview_settings['waveform_type'],
            fade_algorithm=preview_settings['fade_algorithm']
        )
        audio_array = align_audio_buffer(audio_array)

        if self.audio_stream and hasattr(self.audio_stream, 'is_active'):
            if not self.audio_stream.is_active():
                log.warning("悅耳進度條：測試音效時音頻流不活躍，嘗試重新初始化")
                self.cleanup_audio_resources()
                self.init_audio_stream()

        if not self.audio_stream:
            raise RuntimeError("audio stream is not available for preview")

        self.audio_stream.write(
            audio_array.tobytes(),
            exception_on_underflow=self.exception_on_overflow
        )

    def _submit_audio_request(self, frequency=None, preview_settings=None):
        """Atomically publish a normal or preview request to the audio worker."""
        with self.play_request_lock:
            self.play_frequency = frequency
            self.play_preview_settings = preview_settings
            self.play_id = time.time()

    def preview_progress_percentage(
        self,
        percentage,
        waveform_type,
        fade_algorithm,
        volume,
        min_frequency,
        max_frequency,
        audio_duration
    ):
        """Queue a test tone using the settings currently selected in the UI."""
        if waveform_type not in {
            'sine', 'square', 'triangle', 'sawtooth', 'pulse', 'white_noise'
        }:
            raise ValueError("unsupported waveform type")
        if fade_algorithm not in {'cosine', 'gaussian'}:
            raise ValueError("unsupported fade algorithm")
        if not 0.0 < float(volume) <= 1.0:
            raise ValueError("volume must be greater than 0 and no greater than 1")
        if float(audio_duration) <= 0.0:
            raise ValueError("audio duration must be greater than 0")

        # Validate the percentage and frequency range before queueing the request.
        map_percentage_to_frequency(percentage, min_frequency, max_frequency)

        if not PYAUDIO_AVAILABLE:
            return False
        if not self.stream_initialized:
            self.init_audio_stream()
        if not self.thread_running:
            self.start_audio_daemon()
        if not self.stream_initialized or not self.thread_running:
            return False

        self._submit_audio_request(preview_settings={
            'percentage': float(percentage),
            'waveform_type': waveform_type,
            'fade_algorithm': fade_algorithm,
            'volume': float(volume),
            'min_frequency': float(min_frequency),
            'max_frequency': float(max_frequency),
            'audio_duration': float(audio_duration)
        })
        return True
            
    def request_audio_play(self, frequency):
        """請求播放音頻：設置屬性，由守護線程檢查和播放"""
        try:
            self._submit_audio_request(frequency=frequency)
                
        except Exception as e:
            log.error("悅耳進度條：提交播放請求錯誤: %s", e)
    
    def hook_beep_function(self):
        """攔截tones.beep函數"""
        if not self.original_beep:
            self.original_beep = tones.beep
            tones.beep = self.optimized_beep
    
    def unhook_beep_function(self):
        """恢復原始beep函數"""
        if self.original_beep:
            tones.beep = self.original_beep
            self.original_beep = None
    
    def optimized_beep(self, hz, length, left=50, right=50):
        """接管 tones.beep：識別進度條音效並改用悅耳波形，其它音效照原樣播放"""
        # 檢查是否為進度條音效
        if self.is_progress_beep(hz, length, left, right):
            if self.enabled and PYAUDIO_AVAILABLE and self.thread_running:
                # 調用回調函數請求播放（立即返回，不阻塞）
                self.request_audio_play(hz)
                return  # 不播放原始音效
            elif self.enabled:
                log.warning("悅耳進度條：守護線程：PyAudio不可用，使用原始音效")
                # 插件啟用但PyAudio不可用，播放原始音效
            # 如果插件停用，繼續執行到最後播放原始音效
        
        # 播放原始音效（進度條音效且插件停用時，或者非進度條音效時）
        if self.original_beep:
            self.original_beep(hz, length, left, right)

    def old_generate_clean_sine_wave_32bit(self, frequency, duration=0.08, sample_rate=44100, volume=0.6):
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
    
    def old_generate_gaussian_sine_wave_32bit(self, frequency, duration=0.08, sample_rate=44100, volume=0.6):
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


    def generate_waveform(
        self,
        frequency,
        duration=0.08,
        sample_rate=44100,
        volume=0.6,
        waveform_type='sine',
        fade_algorithm=None
    ):
        """通用波形生成器，依 waveform_type 分派到對應子函式"""
        
        # 根據波形類型調用對應的生成函數
        if waveform_type == 'sine':
            return self.generate_sine_wave(
                frequency, duration, sample_rate, volume, fade_algorithm=fade_algorithm
            )
        elif waveform_type == 'square':
            return self.generate_square_wave(
                frequency, duration, sample_rate, volume, fade_algorithm=fade_algorithm
            )
        elif waveform_type == 'triangle':
            return self.generate_triangle_wave(
                frequency, duration, sample_rate, volume, fade_algorithm=fade_algorithm
            )
        elif waveform_type == 'sawtooth':
            return self.generate_sawtooth_wave(
                frequency, duration, sample_rate, volume, fade_algorithm=fade_algorithm
            )
        elif waveform_type == 'pulse':
            return self.generate_pulse_wave(
                frequency, duration, sample_rate, volume, fade_algorithm=fade_algorithm
            )
        elif waveform_type == 'white_noise':
            return self.generate_white_noise(
                frequency, duration, sample_rate, volume, fade_algorithm=fade_algorithm
            )
        else:
            # 默認使用正弦波
            return self.generate_sine_wave(
                frequency, duration, sample_rate, volume, fade_algorithm=fade_algorithm
            )

    def generate_sine_wave(self, frequency, duration, sample_rate, volume, fade_algorithm=None):
        """正弦波生成器"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')
        
        two_pi_f = 2.0 * math.pi * frequency
        sample_rate_inv = 1.0 / sample_rate
        max_amplitude = 30000
        
        for i in range(samples):
            t = i * sample_rate_inv
            sample = math.sin(two_pi_f * t)
            sample = self.apply_fade_effect(sample, i, samples, fade_algorithm)
            
            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)
        
        return audio_array

    def generate_square_wave(self, frequency, duration, sample_rate, volume, fade_algorithm=None):
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
            sample = self.apply_fade_effect(sample, i, samples, fade_algorithm)
            
            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)
        
        return audio_array

    def generate_triangle_wave(self, frequency, duration, sample_rate, volume, fade_algorithm=None):
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
            
            sample = self.apply_fade_effect(sample, i, samples, fade_algorithm)
            
            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)
        
        return audio_array

    def generate_sawtooth_wave(self, frequency, duration, sample_rate, volume, fade_algorithm=None):
        """鋸齒波生成器"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')
        
        period_samples = int(sample_rate / frequency)
        max_amplitude = 30000
        
        for i in range(samples):
            # 鋸齒波：線性上升然後瞬間下降
            position_in_period = i % period_samples
            sample = (position_in_period / period_samples) * 2.0 - 1.0
            sample = self.apply_fade_effect(sample, i, samples, fade_algorithm)
            
            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)
        
        return audio_array

    def generate_pulse_wave(
        self,
        frequency,
        duration,
        sample_rate,
        volume,
        duty_cycle=0.25,
        fade_algorithm=None
    ):
        """脈衝波生成器（可調佔空比的方波）"""
        samples = int(sample_rate * duration)
        audio_array = array.array('h')
        
        period_samples = int(sample_rate / frequency)
        max_amplitude = 30000
        
        for i in range(samples):
            position_in_period = i % period_samples
            # 脈衝波：佔空比控制高電平時間
            sample = 1.0 if (position_in_period / period_samples) < duty_cycle else -1.0
            sample = self.apply_fade_effect(sample, i, samples, fade_algorithm)
            
            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)
        
        return audio_array

    def generate_white_noise(self, frequency, duration, sample_rate, volume, fade_algorithm=None):
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
            sample = self.apply_fade_effect(sample, i, samples, fade_algorithm)
            
            audio_sample = int(sample * max_amplitude * volume)
            audio_sample = max(-32768, min(32767, audio_sample))
            audio_array.append(audio_sample)
        
        return audio_array

    def apply_fade_effect(self, sample, current_index, total_samples, fade_algorithm=None):
        """應用淡入淡出效果"""
        if fade_algorithm is None:
            selected_fade_algorithm = self.fade_algorithm
            fade_ratio = self.fade_ratio
        else:
            selected_fade_algorithm = fade_algorithm
            fade_ratio = 0.3 if fade_algorithm == 'gaussian' else 0.45

        fade_samples = int(total_samples * fade_ratio)
        
        if selected_fade_algorithm == 'gaussian':
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

    def is_progress_beep(self, hz, length, left, right):
        """檢查是否為進度條音效"""
        return (
            110 <= hz <= 1800 and
            38 <= length <= 42 and
            left == 50 and right == 50
        )

    def clear_audio_cache(self):
        """清理音頻緩存"""
        self.audio_cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
    
    def stop_audio_daemon(self):
        """停止守護線程"""
        if self.audio_thread and self.thread_running:
            self.thread_running = False
            
            # 等待線程退出（最多1秒）
            self.audio_thread.join(timeout=1.0)
            
            if self.audio_thread.is_alive():
                log.warning("悅耳進度條：守護線程未能正常退出")
    
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
        except Exception as e:
            log.error("悅耳進度條：清理PyAudio資源時發生錯誤: %s", e)
    
    def terminate(self):
        """插件清理"""
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
            except Exception as e:
                log.error("悅耳進度條：移除設定面板時發生錯誤: %s", e)
        
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
