# -*- coding: utf-8 -*-
# 悅耳進度條 - 設定UI模塊

import wx
import gui
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
import os
import gettext
import languageHandler
from ._pleasant_progressconfig import (
    sine_progress_config,
    FADE_ALGORITHMS,
    WAVEFORM_TYPES,
    VOLUME_OPTIONS,
    MIN_FREQUENCY_OPTIONS,
    MAX_FREQUENCY_OPTIONS,
    AUDIO_DURATION_OPTIONS,
    DEFAULT_CONFIG  # 直接導入預設配置
)

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

# 翻譯字典和常數
WAVEFORM_TYPES_TRANSLATED = {
    'sine': addonGettext('正弦波'),
    'square': addonGettext('方波'), 
    'triangle': addonGettext('三角波'),
    'sawtooth': addonGettext('鋸齒波'),
    'pulse': addonGettext('脈衝波'),
    'white_noise': addonGettext('白噪音')
}

FADE_ALGORITHMS_TRANSLATED = {
    'cosine': addonGettext('余弦'),
    'gaussian': addonGettext('高斯')
}

class SineProgressSettingsPanel(SettingsPanel):
    """悅耳進度條設定面板"""
    
    # 設定面板標題
    title = addonGettext("悅耳進度條")
    helpId = "PleasantProgressBarSettings"
    
    # 面板描述
    panelDescription = addonGettext("配置悅耳進度條的音效參數，包括波形類型、淡入淡出算法、音量和頻率範圍設定。")
    
    def makeSettings(self, settingsSizer):
        """創建設定控件"""
        settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
        
        # 波形類型選擇
        waveform_label = addonGettext("波形類型(&W)：")
        waveform_choices = list(WAVEFORM_TYPES_TRANSLATED.values())  # ['正弦波', '方波', '三角波', ...]
        self.waveform_choice = settingsSizerHelper.addLabeledControl(
            waveform_label,
            wx.Choice,
            choices=waveform_choices
        )
        
        # 設置當前選中的波形
        current_waveform = sine_progress_config.get_waveform_type()
        waveform_index = list(WAVEFORM_TYPES.keys()).index(current_waveform)
        self.waveform_choice.SetSelection(waveform_index)
        
        # 淡入淡出算法選擇
        fade_algorithm_label = addonGettext("淡入淡出算法(&A)：")
        fade_algorithm_choices = list(FADE_ALGORITHMS_TRANSLATED.values())  # ['余弦', '高斯']
        self.fade_algorithm_choice = settingsSizerHelper.addLabeledControl(
            fade_algorithm_label,
            wx.Choice,
            choices=fade_algorithm_choices
        )
        
        # 設置當前選中的算法
        current_algorithm = sine_progress_config.get_fade_algorithm()
        algorithm_index = list(FADE_ALGORITHMS.keys()).index(current_algorithm)
        self.fade_algorithm_choice.SetSelection(algorithm_index)
        
        # 音量調整
        volume_label = addonGettext("音量調整(&V)：")
        volume_choices = [str(vol) for vol in VOLUME_OPTIONS]  # ['0.1', '0.2', ..., '1.0']
        self.volume_choice = settingsSizerHelper.addLabeledControl(
            volume_label,
            wx.Choice,
            choices=volume_choices
        )
        
        # 設置當前音量
        current_volume = sine_progress_config.get_volume()
        try:
            volume_index = VOLUME_OPTIONS.index(current_volume)
            self.volume_choice.SetSelection(volume_index)
        except ValueError:
            self.volume_choice.SetSelection(4)  # 預設0.4
        
                # 波形長度調整
        duration_label = addonGettext("波形長度(&D)：")
        duration_choices = [f"{int(duration*1000)}ms" for duration in AUDIO_DURATION_OPTIONS]
        self.duration_choice = settingsSizerHelper.addLabeledControl(
            duration_label,
            wx.Choice,
            choices=duration_choices
        )
        
        # 設置當前波形長度
        current_duration = sine_progress_config.get_audio_duration()
        try:
            duration_index = AUDIO_DURATION_OPTIONS.index(current_duration)
            self.duration_choice.SetSelection(duration_index)
        except ValueError:
            # 預設80ms (0.08秒)
            default_index = AUDIO_DURATION_OPTIONS.index(0.08) if 0.08 in AUDIO_DURATION_OPTIONS else 8
            self.duration_choice.SetSelection(default_index)

        # 起點頻率（低頻）
        min_freq_label = addonGettext("起點頻率 - 低頻(&L)：")
        min_freq_choices = [f"{freq}Hz" for freq in MIN_FREQUENCY_OPTIONS]
        self.min_frequency_choice = settingsSizerHelper.addLabeledControl(
            min_freq_label,
            wx.Choice,
            choices=min_freq_choices
        )
        
        # 設置當前起點頻率
        current_min_freq = sine_progress_config.get_min_frequency()
        try:
            min_freq_index = MIN_FREQUENCY_OPTIONS.index(current_min_freq)
            self.min_frequency_choice.SetSelection(min_freq_index)
        except ValueError:
            self.min_frequency_choice.SetSelection(0)  # 預設110Hz
        
        # 終點頻率（高頻）
        max_freq_label = addonGettext("終點頻率 - 高頻(&H)：")
        max_freq_choices = [f"{freq}Hz" for freq in MAX_FREQUENCY_OPTIONS]
        self.max_frequency_choice = settingsSizerHelper.addLabeledControl(
            max_freq_label,
            wx.Choice,
            choices=max_freq_choices
        )
        
        # 設置當前終點頻率
        current_max_freq = sine_progress_config.get_max_frequency()
        try:
            max_freq_index = MAX_FREQUENCY_OPTIONS.index(current_max_freq)
            self.max_frequency_choice.SetSelection(max_freq_index)
        except ValueError:
            self.max_frequency_choice.SetSelection(-1)  # 預設1720Hz（最後一個）
        
        # 綁定頻率選擇變更事件，用於驗證
        self.min_frequency_choice.Bind(wx.EVT_CHOICE, self.onFrequencyChange)
        self.max_frequency_choice.Bind(wx.EVT_CHOICE, self.onFrequencyChange)
        
        # 恢復到預設值按鈕
        restore_defaults_button = settingsSizerHelper.addItem(
            wx.Button(self, label=addonGettext("恢復到預設值(&R)"))
        )
        restore_defaults_button.Bind(wx.EVT_BUTTON, self.onRestoreDefaults)
    
    def onRestoreDefaults(self, event):
        """恢復到預設值按鈕點擊事件處理 - 簡化版本"""
        # 直接更新UI控件為預設值
        try:
            # 波形類型
            default_waveform = DEFAULT_CONFIG['waveform_type']
            waveform_index = list(WAVEFORM_TYPES.keys()).index(default_waveform)
            self.waveform_choice.SetSelection(waveform_index)
            
            # 淡入淡出算法
            default_algorithm = DEFAULT_CONFIG['fade_algorithm']
            algorithm_index = list(FADE_ALGORITHMS.keys()).index(default_algorithm)
            self.fade_algorithm_choice.SetSelection(algorithm_index)
            
            # 音量
            default_volume = DEFAULT_CONFIG['volume']
            volume_index = VOLUME_OPTIONS.index(default_volume)
            self.volume_choice.SetSelection(volume_index)
            
            # 起點頻率
            default_min_freq = DEFAULT_CONFIG['min_frequency']
            min_freq_index = MIN_FREQUENCY_OPTIONS.index(default_min_freq)
            self.min_frequency_choice.SetSelection(min_freq_index)
            
            # 終點頻率
            default_max_freq = DEFAULT_CONFIG['max_frequency']
            max_freq_index = MAX_FREQUENCY_OPTIONS.index(default_max_freq)
            self.max_frequency_choice.SetSelection(max_freq_index)
            
                    # 波形長度
            default_duration = DEFAULT_CONFIG['audio_duration']
            duration_index = AUDIO_DURATION_OPTIONS.index(default_duration)
            self.duration_choice.SetSelection(duration_index)

            print("悅耳進度條：UI已重置為預設值，用戶可選擇是否保存")
            
        except Exception as e:
            print(f"悅耳進度條：重置UI到預設值時發生錯誤: {e}")
    
    def onFrequencyChange(self, event):
        """頻率選擇變更事件處理"""
        # 獲取當前選擇的頻率值
        min_freq_index = self.min_frequency_choice.GetSelection()
        max_freq_index = self.max_frequency_choice.GetSelection()
        
        if min_freq_index >= 0 and max_freq_index >= 0:
            min_freq = MIN_FREQUENCY_OPTIONS[min_freq_index]
            max_freq = MAX_FREQUENCY_OPTIONS[max_freq_index]
            
            # 驗證頻率範圍
            if min_freq >= max_freq:
                # 顯示警告訊息
                wx.CallAfter(
                    gui.messageBox,
                    f"起點頻率({min_freq}Hz)不能大於等於終點頻率({max_freq}Hz)，請重新選擇。",
                    "頻率範圍錯誤",
                    wx.OK | wx.ICON_WARNING
                )
        
        event.Skip()
    
    def isValid(self):
        """驗證設定是否有效"""
        # 檢查頻率範圍
        min_freq_index = self.min_frequency_choice.GetSelection()
        max_freq_index = self.max_frequency_choice.GetSelection()
        
        if min_freq_index < 0 or max_freq_index < 0:
            gui.messageBox(
                "請選擇有效的起點頻率和終點頻率。",
                "設定錯誤",
                wx.OK | wx.ICON_ERROR
            )
            return False
        
        min_freq = MIN_FREQUENCY_OPTIONS[min_freq_index]
        max_freq = MAX_FREQUENCY_OPTIONS[max_freq_index]
        
        if min_freq >= max_freq:
            gui.messageBox(
                f"起點頻率({min_freq}Hz)必須小於終點頻率({max_freq}Hz)。",
                "頻率範圍錯誤",
                wx.OK | wx.ICON_ERROR
            )
            return False
        
        return True
    
    def onSave(self):
        """保存設定"""
        # 獲取選中的波形類型
        waveform_index = self.waveform_choice.GetSelection()
        selected_waveform = list(WAVEFORM_TYPES.keys())[waveform_index]
        
        # 獲取選中的淡入淡出算法
        algorithm_index = self.fade_algorithm_choice.GetSelection()
        selected_algorithm = list(FADE_ALGORITHMS.keys())[algorithm_index]
        
        # 獲取選中的音量
        volume_index = self.volume_choice.GetSelection()
        selected_volume = VOLUME_OPTIONS[volume_index]
        
        # 獲取選中的頻率
        min_freq_index = self.min_frequency_choice.GetSelection()
        max_freq_index = self.max_frequency_choice.GetSelection()
        selected_min_freq = MIN_FREQUENCY_OPTIONS[min_freq_index]
        selected_max_freq = MAX_FREQUENCY_OPTIONS[max_freq_index]
        
            # 獲取選中的波形長度
        duration_index = self.duration_choice.GetSelection()
        selected_duration = AUDIO_DURATION_OPTIONS[duration_index]

        # 檢查配置是否有變更
        config_changed = (
            selected_waveform != sine_progress_config.get_waveform_type() or
            selected_algorithm != sine_progress_config.get_fade_algorithm() or
            selected_volume != sine_progress_config.get_volume() or
            selected_min_freq != sine_progress_config.get_min_frequency() or
            selected_max_freq != sine_progress_config.get_max_frequency() or
            selected_duration != sine_progress_config.get_audio_duration()  # 新增
        )
        
        if config_changed:
            # 更新配置
            success = sine_progress_config.update_config(
                waveform_type=selected_waveform,
                fade_algorithm=selected_algorithm,
                volume=selected_volume,
                min_frequency=selected_min_freq,
                max_frequency=selected_max_freq,
                audio_duration=selected_duration  # 新增
            )
            
            if success:
                print("悅耳進度條：設定已保存，準備重新初始化")
                # 通知主插件重新初始化
                self._notify_plugin_reload()
            else:
                gui.messageBox(
                    "保存設定時發生錯誤，請檢查頻率範圍設定。",
                    "保存錯誤",
                    wx.OK | wx.ICON_ERROR
                )
        else:
            print("悅耳進度條：設定無變更")
    
    def _notify_plugin_reload(self):
        """通知主插件重新載入配置"""
        try:
            # 導入主插件並觸發重新初始化
            import globalPluginHandler
            
            # 查找悅耳進度條插件實例
            for plugin in globalPluginHandler.runningPlugins:
                if hasattr(plugin, 'reload_configuration'):
                    plugin.reload_configuration()
                    print("悅耳進度條：已通知主插件重新載入配置")
                    break
            else:
                print("悅耳進度條：未找到主插件實例")
                
        except Exception as e:
            print(f"悅耳進度條：通知主插件重新載入時發生錯誤: {e}")
    
    def onDiscard(self):
        """放棄變更時的處理"""
        print("悅耳進度條：用戶放棄了設定變更")
    
    def onPanelActivated(self):
        """面板啟動時的處理"""
        print("悅耳進度條：設定面板已開啟")
        super().onPanelActivated()
    
    def onPanelDeactivated(self):
        """面板停用時的處理"""
        print("悅耳進度條：設定面板已關閉")
        super().onPanelDeactivated()