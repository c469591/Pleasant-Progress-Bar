# -*- coding: utf-8 -*-
# 悅耳進度條 - 設定UI模塊

import wx
import gui
from gui import guiHelper
from gui.settingsDialogs import SettingsPanel
from ._sineProgressConfig import (
    sine_progress_config,
    FADE_ALGORITHMS,
    WAVEFORM_TYPES,
    VOLUME_OPTIONS,
    MIN_FREQUENCY_OPTIONS,
    MAX_FREQUENCY_OPTIONS,
    DEFAULT_CONFIG  # 新增：直接導入預設配置
)

class SineProgressSettingsPanel(SettingsPanel):
    """悅耳進度條設定面板"""
    
    # 設定面板標題
    title = "悅耳進度條"
    helpId = "SineProgressSettings"
    
    # 面板描述
    panelDescription = "配置悅耳進度條的音效參數，包括波形類型、淡入淡出算法、音量和頻率範圍設定。"
    
    def makeSettings(self, settingsSizer):
        """創建設定控件"""
        settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
        
        # 波形類型選擇
        waveform_label = "波形類型(&W)："
        waveform_choices = list(WAVEFORM_TYPES.values())  # ['正弦波', '方波', '三角波', ...]
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
        fade_algorithm_label = "淡入淡出算法(&A)："
        fade_algorithm_choices = list(FADE_ALGORITHMS.values())  # ['余弦', '高斯']
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
        volume_label = "音量調整(&V)："
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
        
        # 起點頻率（低頻）
        min_freq_label = "起點頻率 - 低頻(&L)："
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
        max_freq_label = "終點頻率 - 高頻(&H)："
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
            wx.Button(self, label="恢復到預設值(&R)")
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
        
        # 檢查配置是否有變更
        config_changed = (
            selected_waveform != sine_progress_config.get_waveform_type() or
            selected_algorithm != sine_progress_config.get_fade_algorithm() or
            selected_volume != sine_progress_config.get_volume() or
            selected_min_freq != sine_progress_config.get_min_frequency() or
            selected_max_freq != sine_progress_config.get_max_frequency()
        )
        
        if config_changed:
            # 更新配置
            success = sine_progress_config.update_config(
                waveform_type=selected_waveform,
                fade_algorithm=selected_algorithm,
                volume=selected_volume,
                min_frequency=selected_min_freq,
                max_frequency=selected_max_freq
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