# -*- coding: utf-8 -*-
# 悅耳進度條 - 配置管理模塊

import os
import globalVars
from configobj import ConfigObj

# 配置文件路徑
CONFIG_FILE_NAME = "sineProgress.ini"
CONFIG_FILE_PATH = os.path.join(globalVars.appArgs.configPath, CONFIG_FILE_NAME)

# 預設配置值
DEFAULT_CONFIG = {
    'fade_algorithm': 'cosine',    # 余弦
    'waveform_type': 'sine',       # 新增：波形類型
    'volume': 0.4,                # 音量
    'min_frequency': 110,         # 起點頻率（低頻）
    'max_frequency': 1720,        # 終點頻率（高頻）
}

# 可用選項定義
FADE_ALGORITHMS = {
    'cosine': '余弦',
    'gaussian': '高斯'
}

# 新增：波形類型選項
WAVEFORM_TYPES = {
    'sine': '正弦波',
    'square': '方波', 
    'triangle': '三角波',
    'sawtooth': '鋸齒波',
    'pulse': '脈衝波',
    'white_noise': '白噪音'
}

# 生成音量選項（0.1到1.0，步進0.1）
VOLUME_OPTIONS = [round(i * 0.1, 1) for i in range(1, 11)]

# 生成頻率選項
MIN_FREQUENCY_OPTIONS = list(range(110, 301, 10))  # 110到300，每10Hz
MAX_FREQUENCY_OPTIONS = list(range(1200, 1751, 10))  # 1200到1750，每10Hz

class SineProgressConfig:
    """悅耳進度條配置管理類"""
    
    def __init__(self):
        self.config = None
        self.load_config()
    
    def load_config(self):
        """載入配置文件"""
        try:
            if os.path.exists(CONFIG_FILE_PATH):
                self.config = ConfigObj(CONFIG_FILE_PATH, encoding='utf-8')
                print("悅耳進度條：配置文件載入成功")
            else:
                self.config = ConfigObj(encoding='utf-8')
                print("悅耳進度條：配置文件不存在，使用預設配置")
            
            # 確保所有必要的配置項存在
            self._ensure_config_completeness()
            
        except Exception as e:
            print(f"悅耳進度條：載入配置文件錯誤: {e}")
            self.config = ConfigObj(encoding='utf-8')
            self._apply_default_config()
    
    def _ensure_config_completeness(self):
        """確保配置完整性，補充缺少的配置項"""
        config_changed = False
        
        for key, default_value in DEFAULT_CONFIG.items():
            if key not in self.config:
                self.config[key] = default_value
                config_changed = True
                print(f"悅耳進度條：補充配置項 {key} = {default_value}")
        
        # 驗證配置值的有效性
        if not self._validate_config():
            self._apply_default_config()
            config_changed = True
        
        if config_changed:
            self.save_config()
    
    def _validate_config(self):
        """驗證配置值的有效性"""
        try:
            # 驗證淡入淡出算法
            if self.config.get('fade_algorithm') not in FADE_ALGORITHMS:
                print("悅耳進度條：無效的淡入淡出算法配置")
                return False
            
            # 驗證波形類型
            if self.config.get('waveform_type') not in WAVEFORM_TYPES:
                print("悅耳進度條：無效的波形類型配置")
                return False
            
            # 驗證音量
            volume = float(self.config.get('volume', 0.5))
            if volume not in VOLUME_OPTIONS:
                print("悅耳進度條：無效的音量配置")
                return False
            
            # 驗證頻率範圍
            min_freq = int(self.config.get('min_frequency', 110))
            max_freq = int(self.config.get('max_frequency', 1720))
            
            if (min_freq not in MIN_FREQUENCY_OPTIONS or 
                max_freq not in MAX_FREQUENCY_OPTIONS or
                min_freq >= max_freq):
                print("悅耳進度條：無效的頻率範圍配置")
                return False
            
            return True
            
        except (ValueError, TypeError) as e:
            print(f"悅耳進度條：配置驗證錯誤: {e}")
            return False
    
    def _apply_default_config(self):
        """應用預設配置"""
        for key, value in DEFAULT_CONFIG.items():
            self.config[key] = value
        print("悅耳進度條：已應用預設配置")
    
    def save_config(self):
        """保存配置到文件"""
        try:
            self.config.filename = CONFIG_FILE_PATH
            self.config.write()
            print("悅耳進度條：配置已保存")
        except Exception as e:
            print(f"悅耳進度條：保存配置錯誤: {e}")
    
    def get_fade_algorithm(self):
        """獲取淡入淡出算法"""
        return self.config.get('fade_algorithm', DEFAULT_CONFIG['fade_algorithm'])
    
    def set_fade_algorithm(self, algorithm):
        """設置淡入淡出算法"""
        if algorithm in FADE_ALGORITHMS:
            self.config['fade_algorithm'] = algorithm
            print(f"悅耳進度條：淡入淡出算法設為 {FADE_ALGORITHMS[algorithm]}")
    
    def get_waveform_type(self):
        """獲取波形類型"""
        return self.config.get('waveform_type', DEFAULT_CONFIG['waveform_type'])
    
    def set_waveform_type(self, waveform):
        """設置波形類型"""
        if waveform in WAVEFORM_TYPES:
            self.config['waveform_type'] = waveform
            print(f"悅耳進度條：波形類型設為 {WAVEFORM_TYPES[waveform]}")
    
    def get_volume(self):
        """獲取音量"""
        return float(self.config.get('volume', DEFAULT_CONFIG['volume']))
    
    def set_volume(self, volume):
        """設置音量"""
        if volume in VOLUME_OPTIONS:
            self.config['volume'] = volume
            print(f"悅耳進度條：音量設為 {volume}")
    
    def get_min_frequency(self):
        """獲取起點頻率（低頻）"""
        return int(self.config.get('min_frequency', DEFAULT_CONFIG['min_frequency']))
    
    def set_min_frequency(self, frequency):
        """設置起點頻率（低頻）"""
        if frequency in MIN_FREQUENCY_OPTIONS:
            self.config['min_frequency'] = frequency
            print(f"悅耳進度條：起點頻率設為 {frequency}Hz")
    
    def get_max_frequency(self):
        """獲取終點頻率（高頻）"""
        return int(self.config.get('max_frequency', DEFAULT_CONFIG['max_frequency']))
    
    def set_max_frequency(self, frequency):
        """設置終點頻率（高頻）"""
        if frequency in MAX_FREQUENCY_OPTIONS:
            self.config['max_frequency'] = frequency
            print(f"悅耳進度條：終點頻率設為 {frequency}Hz")
    
    def get_frequency_range(self):
        """獲取頻率範圍"""
        return self.get_min_frequency(), self.get_max_frequency()
    
    def update_config(self, fade_algorithm=None, waveform_type=None, volume=None, 
                     min_frequency=None, max_frequency=None):
        """批量更新配置"""
        config_changed = False
        
        if fade_algorithm is not None:
            self.set_fade_algorithm(fade_algorithm)
            config_changed = True
        
        if waveform_type is not None:
            self.set_waveform_type(waveform_type)
            config_changed = True
        
        if volume is not None:
            self.set_volume(volume)
            config_changed = True
        
        if min_frequency is not None:
            self.set_min_frequency(min_frequency)
            config_changed = True
        
        if max_frequency is not None:
            self.set_max_frequency(max_frequency)
            config_changed = True
        
        if config_changed:
            # 驗證頻率範圍
            if self.get_min_frequency() >= self.get_max_frequency():
                print("悅耳進度條：警告：起點頻率不能大於等於終點頻率")
                return False
            
            self.save_config()
            return True
        
        return False
    
    def reset_to_default(self):
        """重置為預設配置"""
        self._apply_default_config()
        self.save_config()
        print("悅耳進度條：已重置為預設配置")

# 全局配置實例
sine_progress_config = SineProgressConfig()