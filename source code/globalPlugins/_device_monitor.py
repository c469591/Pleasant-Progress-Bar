# -*- coding: utf-8 -*-
# 悅耳進度條 - NVDA音頻設備監聽模塊

import threading
import time
import wx
import ui

class NVDADeviceMonitor:
    """NVDA音頻設備監聽器"""
    
    def __init__(self, on_device_change_callback=None, debug_mode=False, pyaudio_instance_getter=None):
        self.on_device_change_callback = on_device_change_callback
        self.debug_mode = debug_mode
        self.pyaudio_instance_getter = pyaudio_instance_getter  # 獲取PyAudio實例的回調函數
        
        # 監聽狀態
        self.monitoring_enabled = True
        self.monitoring_thread = None
        self.thread_running = False
        
        # 配置引用
        self.audio_config_section = None
        self.last_audio_device = None
        
        # 設備緩存
        self.device_cache = {}
        self.pyaudio_device_list = []
        
        # 初始化
        self.setup_config_monitoring()
        self.refresh_device_list()
        
    def setup_config_monitoring(self):
        """設置NVDA音頻配置監聽"""
        try:
            import config
            import versionInfo
            
            if hasattr(versionInfo, 'version_year') and versionInfo.version_year >= 2025:
                self.audio_config_section = config.conf["audio"]
                config_path = "config.conf['audio']['outputDevice']"
            else:
                self.audio_config_section = config.conf["speech"]
                config_path = "config.conf['speech']['outputDevice']"
            
            self.last_audio_device = self.audio_config_section.get("outputDevice", "default")
            
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 配置路徑 = {config_path}")
                print(f"NVDADeviceMonitor: 當前設備 = '{self.last_audio_device}'")
            
        except Exception as e:
            print(f"NVDADeviceMonitor: 設置監聽失敗 - {e}")
            self.audio_config_section = None
            self.last_audio_device = None

    def old_refresh_device_list(self):
        """刷新PyAudio設備列表並建立緩存"""
        try:
            if not self.pyaudio_instance_getter:
                return False
            
            # 獲取PyAudio實例（臨時）
            temp_pyaudio = self.pyaudio_instance_getter()
            if not temp_pyaudio:
                return False
            
            # 獲取設備數量和列表
            if hasattr(temp_pyaudio, 'get_device_count'):
                device_count = temp_pyaudio.get_device_count()
            else:
                device_count = temp_pyaudio.pyaudio_instance.get_device_count() if temp_pyaudio.pyaudio_instance else 0
            
            self.pyaudio_device_list = []
            self.device_cache.clear()
            
            for i in range(device_count):
                try:
                    if hasattr(temp_pyaudio, 'get_device_info_by_index'):
                        device_info = temp_pyaudio.get_device_info_by_index(i)
                    else:
                        device_info = temp_pyaudio.pyaudio_instance.get_device_info_by_index(i) if temp_pyaudio.pyaudio_instance else None
                    
                    if device_info and device_info.get('maxOutputChannels', 0) > 0:
                        self.pyaudio_device_list.append(device_info)
                        # 建立名稱到索引的映射緩存
                        device_name = device_info.get('name', f'Device {i}')
                        self.device_cache[device_name] = i
                        
                        if self.debug_mode:
                            print(f"NVDADeviceMonitor: 發現輸出設備 {i}: {device_name}")
                
                except Exception as e:
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 獲取設備 {i} 信息失敗: {e}")
            
            # 清理臨時實例
            if hasattr(temp_pyaudio, 'terminate'):
                temp_pyaudio.terminate()
            
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 設備列表刷新完成，找到 {len(self.pyaudio_device_list)} 個輸出設備")
            
            return True
            
        except Exception as e:
            print(f"NVDADeviceMonitor: 刷新設備列表失敗: {e}")
            return False

    def refresh_device_list(self):
        """刷新PyAudio設備列表並建立緩存"""
        try:
            if not self.pyaudio_instance_getter:
                return False
            
            # 獲取PyAudio實例（臨時）
            temp_pyaudio = self.pyaudio_instance_getter()
            if not temp_pyaudio:
                return False
            
            # 直接使用全局函數獲取設備數量
            try:
                # 首先嘗試使用全局函數
                import _portaudio as pa
                device_count = pa.get_device_count()
            except Exception:
                # 降級方案：使用默認值
                device_count = 1
            
            self.pyaudio_device_list = []
            self.device_cache.clear()
            
            for i in range(device_count):
                try:
                    # 直接使用PyAudio實例的方法
                    device_info = temp_pyaudio.get_device_info_by_index(i)
                    
                    if device_info and device_info.get('maxOutputChannels', 0) > 0:
                        self.pyaudio_device_list.append(device_info)
                        # 建立名稱到索引的映射緩存
                        device_name = device_info.get('name', f'Device {i}')
                        self.device_cache[device_name] = i
                        
                        if self.debug_mode:
                            print(f"NVDADeviceMonitor: 發現輸出設備 {i}: {device_name}")
                
                except Exception as e:
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 獲取設備 {i} 信息失敗: {e}")
            
            # 清理臨時實例
            if hasattr(temp_pyaudio, 'terminate'):
                temp_pyaudio.terminate()
            
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 設備列表刷新完成，找到 {len(self.pyaudio_device_list)} 個輸出設備")
            
            return True
            
        except Exception as e:
            print(f"NVDADeviceMonitor: 刷新設備列表失敗: {e}")
            return False
        
    def get_device_friendly_name(self, device_id):
        """根據設備ID獲取友好名稱"""
        try:
            if not device_id or device_id == "default":
                return "預設設備"
            
            # 嘗試從Windows設備管理器獲取友好名稱
            try:
                import winreg
                
                # 從GUID格式中提取設備信息
                if '{' in device_id and '}' in device_id:
                    # NVDA設備ID格式通常是 {GUID}.{GUID}
                    parts = device_id.replace('{', '').replace('}', '').split('.')
                    if len(parts) >= 2:
                        # 查找對應的PyAudio設備
                        for device_info in self.pyaudio_device_list:
                            device_name = device_info.get('name', '')
                            if any(part in device_name.lower() for part in ['realtek', 'audio', 'sound']):
                                return device_name
                
                # 如果找不到匹配的設備，返回簡化的ID
                return f"音頻設備 (ID結尾: ...{device_id[-8:]})"
                
            except Exception:
                pass
            
            # 降級方案：直接顯示設備ID的最後幾位
            if len(device_id) > 16:
                return f"音頻設備 (...{device_id[-8:]})"
            else:
                return f"音頻設備 ({device_id})"
            
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 獲取友好名稱失敗: {e}")
            return "未知設備"

    def old_convert_nvda_device_to_pyaudio_index(self, nvda_device_id):
        """將NVDA設備ID轉換為PyAudio設備索引"""
        try:
            if not nvda_device_id or nvda_device_id == "default":
                # 獲取默認輸出設備
                if self.pyaudio_instance_getter:
                    temp_pyaudio = self.pyaudio_instance_getter()
                    if temp_pyaudio:
                        try:
                            if hasattr(temp_pyaudio, 'get_default_output_device_info'):
                                default_info = temp_pyaudio.get_default_output_device_info()
                            else:
                                default_info = temp_pyaudio.pyaudio_instance.get_default_output_device_info() if temp_pyaudio.pyaudio_instance else None
                            
                            if default_info:
                                device_index = default_info.get('index', None)
                                if hasattr(temp_pyaudio, 'terminate'):
                                    temp_pyaudio.terminate()
                                return device_index
                        finally:
                            if hasattr(temp_pyaudio, 'terminate'):
                                temp_pyaudio.terminate()
                
                return None  # 使用PyAudio默認
            
            # 嘗試通過設備名稱匹配找到對應的PyAudio設備索引
            # 這裡可能需要更複雜的邏輯來匹配NVDA設備ID和PyAudio設備
            
            # 簡化方案：返回默認設備索引，讓PyAudio自動處理
            # 在實際情況下可能需要更複雜的設備ID解析
            
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 設備ID轉換 - NVDA: {nvda_device_id} -> PyAudio: 使用默認")
            
            return None  # None表示使用PyAudio的默認設備
            
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 設備ID轉換失敗: {e}")
            return None

    def old_convert_nvda_device_to_pyaudio_index(self, nvda_device_id):
        """將NVDA設備ID轉換為PyAudio設備索引 - 改進版本"""
        try:
            if not nvda_device_id or nvda_device_id == "default":
                return None  # 使用PyAudio默認設備
            
            # 嘗試通過Windows COM API獲取設備信息
            try:
                import comtypes
                from comtypes import GUID
                import comtypes.client
                
                # 解析NVDA設備ID中的GUID
                if '{' in nvda_device_id and '}' in nvda_device_id:
                    # NVDA設備ID格式：{device_guid}.{endpoint_guid}
                    parts = nvda_device_id.split('}.{')
                    if len(parts) == 2:
                        endpoint_guid = parts[1].replace('}', '')
                        
                        # 創建Windows音頻設備枚舉器
                        try:
                            # 通過COM接口獲取音頻設備信息
                            device_enumerator = comtypes.client.CreateObject(
                                "{BCDE0395-E52F-467C-8E3D-C4579291692E}"  # MMDeviceEnumerator CLSID
                            )
                            
                            # 枚舉音頻輸出設備
                            device_collection = device_enumerator.EnumAudioEndpoints(0, 1)  # eRender, DEVICE_STATE_ACTIVE
                            device_count = device_collection.GetCount()
                            
                            # 查找匹配的設備
                            for i in range(device_count):
                                device = device_collection.Item(i)
                                device_id = device.GetId()
                                
                                if endpoint_guid.lower() in device_id.lower():
                                    # 找到匹配的設備，返回對應的PyAudio索引
                                    # 這裡需要將Windows設備索引映射到PyAudio索引
                                    # 簡化實現：假設索引順序一致
                                    if self.debug_mode:
                                        print(f"NVDADeviceMonitor: 找到匹配設備，Windows索引: {i} -> PyAudio索引: {i}")
                                    return i
                        
                        except Exception as com_error:
                            if self.debug_mode:
                                print(f"NVDADeviceMonitor: COM接口查找設備失敗: {com_error}")
            
            except ImportError:
                if self.debug_mode:
                    print("NVDADeviceMonitor: comtypes不可用，無法使用Windows COM API")
            
            # 降級方案：嘗試通過設備名稱匹配（如果PyAudio提供了真實設備名稱）
            temp_pyaudio = self.pyaudio_instance_getter()
            if temp_pyaudio:
                try:
                    # 獲取所有設備信息並嘗試匹配
                    for i, device_info in enumerate(self.pyaudio_device_list):
                        device_name = device_info.get('name', '').lower()
                        # 這裡可以添加更複雜的名稱匹配邏輯
                        # 暫時跳過，因為當前設備名稱都是通用的
                        pass
                    
                    temp_pyaudio.terminate()
                except Exception as e:
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 降級匹配失敗: {e}")
                    if hasattr(temp_pyaudio, 'terminate'):
                        temp_pyaudio.terminate()
            
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 無法轉換設備ID，使用默認設備 - NVDA: {nvda_device_id}")
            
            return None  # 無法匹配，使用默認設備
            
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 設備ID轉換錯誤: {e}")
            return None

    def convert_nvda_device_to_pyaudio_index(self, nvda_device_id):
        """通過設備名稱關鍵詞映射 NVDA 設備到 PyAudio 索引"""
        try:
            if not nvda_device_id or nvda_device_id == "default":
                return None  # 使用默認設備
            
            # 根據你的日誌，建立設備關鍵詞映射
            # 當NVDA切換到包含這些GUID的設備時，映射到對應的PyAudio設備
            device_keyword_mappings = {
                # NVDA設備ID的部分 -> 設備名稱關鍵詞
                'da577682-b2de-4b80-8638-17620a6fb514': 'Synchronous Audio',  # SAR設備
                'ad6ebfcf-a3f6-4557-903a-ec8023915e4d': 'Realtek',  # Realtek設備
                # 可以根據需要添加更多映射
            }
            
            # 查找匹配的關鍵詞
            target_keyword = None
            for guid, keyword in device_keyword_mappings.items():
                if guid.lower() in nvda_device_id.lower():
                    target_keyword = keyword
                    break
            
            if not target_keyword:
                return None
            
            # 在PyAudio設備列表中查找匹配的設備
            for device_info in self.pyaudio_device_list:
                device_name = device_info.get('name', '')
                if target_keyword.lower() in device_name.lower():
                    device_index = device_info.get('index')
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 設備映射成功 - '{target_keyword}' -> 索引 {device_index} ({device_name})")
                    return device_index
            
            return None
            
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 設備映射錯誤: {e}")
            return None        
        
    def get_current_nvda_output_device_index(self):
        """獲取NVDA當前輸出設備對應的PyAudio設備索引"""
        try:
            current_device = self.get_current_device()
            return self.convert_nvda_device_to_pyaudio_index(current_device)
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 獲取當前設備索引失敗: {e}")
            return None

    def old_get_optimal_params_for_current_device(self):
        """為當前NVDA設備獲取最佳音頻參數"""
        try:
            device_index = self.get_current_nvda_output_device_index()
            
            if not self.pyaudio_instance_getter:
                return {'sample_rate': 48000, 'format': None, 'device_index': device_index}
            
            temp_pyaudio = self.pyaudio_instance_getter()
            if not temp_pyaudio:
                return {'sample_rate': 48000, 'format': None, 'device_index': device_index}
            
            try:
                # 獲取設備信息
                if device_index is not None:
                    if hasattr(temp_pyaudio, 'get_device_info_by_index'):
                        device_info = temp_pyaudio.get_device_info_by_index(device_index)
                    else:
                        device_info = temp_pyaudio.pyaudio_instance.get_device_info_by_index(device_index) if temp_pyaudio.pyaudio_instance else None
                else:
                    if hasattr(temp_pyaudio, 'get_default_output_device_info'):
                        device_info = temp_pyaudio.get_default_output_device_info()
                    else:
                        device_info = temp_pyaudio.pyaudio_instance.get_default_output_device_info() if temp_pyaudio.pyaudio_instance else None
                
                if device_info:
                    optimal_rate = int(device_info.get('defaultSampleRate', 48000))
                    device_name = device_info.get('name', 'Unknown Device')
                    
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 當前設備最佳參數 - 設備: {device_name}, 採樣率: {optimal_rate}Hz")
                    
                    # 測試支持的格式（簡化版本）
                    import _portaudio as pa
                    preferred_formats = [pa.paInt16, pa.paInt24, pa.paFloat32]
                    optimal_format = preferred_formats[0]  # 默認使用16位
                    
                    return {
                        'sample_rate': optimal_rate,
                        'format': optimal_format,
                        'device_index': device_index,
                        'device_name': device_name
                    }
            
            finally:
                if hasattr(temp_pyaudio, 'terminate'):
                    temp_pyaudio.terminate()
            
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 獲取設備最佳參數失敗: {e}")
        
        # 返回默認參數
        return {'sample_rate': 48000, 'format': None, 'device_index': device_index if 'device_index' in locals() else None}

    def start_monitoring(self):
        """啟動監聽"""
        if self.thread_running:
            return
            
        self.thread_running = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_worker,
            daemon=True
        )
        self.monitoring_thread.start()
        
        if self.debug_mode:
            print("NVDADeviceMonitor: 監聽線程已啟動")

    def get_optimal_params_for_current_device(self):
        """為當前NVDA設備獲取最佳音頻參數"""
        try:
            device_index = self.get_current_nvda_output_device_index()
            
            if not self.pyaudio_instance_getter:
                return {'sample_rate': 48000, 'format': None, 'device_index': device_index}
            
            temp_pyaudio = self.pyaudio_instance_getter()
            if not temp_pyaudio:
                return {'sample_rate': 48000, 'format': None, 'device_index': device_index}
            
            try:
                # 獲取設備信息 - 直接使用PyAudio實例方法
                if device_index is not None:
                    device_info = temp_pyaudio.get_device_info_by_index(device_index)
                else:
                    device_info = temp_pyaudio.get_default_output_device_info()
                
                if device_info:
                    optimal_rate = int(device_info.get('defaultSampleRate', 48000))
                    device_name = device_info.get('name', 'Unknown Device')
                    
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 當前設備最佳參數 - 設備: {device_name}, 採樣率: {optimal_rate}Hz")
                    
                    # 測試支持的格式（簡化版本）
                    import _portaudio as pa
                    preferred_formats = [pa.paInt16, pa.paInt24, pa.paFloat32]
                    optimal_format = preferred_formats[0]  # 默認使用16位
                    
                    return {
                        'sample_rate': optimal_rate,
                        'format': optimal_format,
                        'device_index': device_index,
                        'device_name': device_name
                    }
            
            finally:
                if hasattr(temp_pyaudio, 'terminate'):
                    temp_pyaudio.terminate()
            
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 獲取設備最佳參數失敗: {e}")
        
        # 返回默認參數
        return {'sample_rate': 48000, 'format': None, 'device_index': device_index if 'device_index' in locals() else None}    
    
    def stop_monitoring(self):
        """停止監聽"""
        if self.monitoring_thread and self.thread_running:
            self.thread_running = False
            self.monitoring_thread.join(timeout=2.0)
            
            if self.debug_mode:
                print("NVDADeviceMonitor: 監聽線程已停止")
    
    def _monitoring_worker(self):
        """監聽工作線程"""
        last_check = 0
        check_interval = 1.0
        rapid_check_count = 0
        
        while self.thread_running:
            try:
                current_time = time.time()
                
                if current_time - last_check > check_interval and self.monitoring_enabled:
                    if self._check_device_change():
                        rapid_check_count = 3  # 觸發快速檢查
                        check_interval = 0.3
                    elif rapid_check_count > 0:
                        rapid_check_count -= 1
                        check_interval = 0.3
                    else:
                        check_interval = 1.0
                        
                    last_check = current_time
                
                time.sleep(0.1)
                
            except Exception as e:
                if self.debug_mode:
                    print(f"NVDADeviceMonitor: 監聽錯誤 - {e}")
                time.sleep(1.0)
    
    def _check_device_change(self):
        """檢查設備變更"""
        if self.audio_config_section is None:
            return False
            
        try:
            current_device = self.audio_config_section.get("outputDevice", "default")
            
            if current_device != self.last_audio_device:
                if self.debug_mode:
                    print(f"NVDADeviceMonitor: 檢測到設備變更")
                    print(f"  之前: '{self.last_audio_device}'")
                    print(f"  當前: '{current_device}'")
                
                # 調用回調函數
                if self.on_device_change_callback:
                    try:
                        self.on_device_change_callback(self.last_audio_device, current_device)
                    except Exception as e:
                        print(f"NVDADeviceMonitor: 回調函數錯誤 - {e}")
                
                self.last_audio_device = current_device
                return True
                
            return False
            
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 檢查設備變更錯誤 - {e}")
            return False
    
    def get_current_device(self):
        """獲取當前設備配置"""
        if self.audio_config_section is None:
            return "default"
        return self.audio_config_section.get("outputDevice", "default")
    
    def enable_monitoring(self):
        """啟用監聽"""
        self.monitoring_enabled = True
    
    def disable_monitoring(self):
        """停用監聽"""
        self.monitoring_enabled = False