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
        """刷新PyAudio設備列表並建立緩存 - 參考ooo.py改進"""
        try:
            if not self.pyaudio_instance_getter:
                return False
            
            # 獲取PyAudio實例（臨時）
            temp_pyaudio = self.pyaudio_instance_getter()
            if not temp_pyaudio:
                return False
            
            self.pyaudio_device_list = []
            self.device_cache.clear()
            
            # 檢查是否有Host API信息
            if hasattr(temp_pyaudio, 'host_apis') and hasattr(temp_pyaudio, 'preferred_host_api'):
                # 使用Host API優先級掃描
                self.scan_devices_by_host_api_priority(temp_pyaudio)
            else:
                # 降級到簡單掃描
                self.scan_devices_simple(temp_pyaudio)
            
            temp_pyaudio.terminate()
            
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 設備列表刷新完成，找到 {len(self.pyaudio_device_list)} 個輸出設備")
            
            return True
            
        except Exception as e:
            print(f"NVDADeviceMonitor: 刷新設備列表失敗: {e}")
            return False

    def scan_devices_by_host_api_priority(self, temp_pyaudio):
        """按Host API優先級掃描設備 - 參考ooo.py"""
        try:
            # 構建Host API優先級列表
            host_api_priority = []
            
            # 首選API優先
            if temp_pyaudio.preferred_host_api:
                host_api_priority.append(temp_pyaudio.preferred_host_api['index'])
            
            # 其他API (WASAPI, DirectSound優先)
            for api_index, api_data in temp_pyaudio.host_apis.items():
                api_name = api_data['name'].lower()
                if api_index not in host_api_priority:
                    if 'wasapi' in api_name:
                        host_api_priority.insert(0, api_index)  # WASAPI最優先
                    elif 'directsound' in api_name:
                        host_api_priority.insert(-1 if len(host_api_priority) > 0 else 0, api_index)
                    else:
                        host_api_priority.append(api_index)
            
            if self.debug_mode:
                api_names = [temp_pyaudio.host_apis[i]['name'] for i in host_api_priority]
                print(f"NVDADeviceMonitor: 設備掃描順序: {api_names}")
            
            # 按優先級掃描設備
            for api_index in host_api_priority:
                api_name = temp_pyaudio.host_apis[api_index]['name']
                if self.debug_mode:
                    print(f"NVDADeviceMonitor: 掃描 {api_name} (Host API {api_index})")
                
                devices = temp_pyaudio.get_devices_by_host_api(api_index)
                
                for device in devices:
                    global_index = device.get('global_index', -1)
                    max_output_channels = device.get('maxOutputChannels', 0)
                    
                    if max_output_channels > 0:  # 只要輸出設備
                        device_info = temp_pyaudio.get_device_info_by_index(global_index)
                        if device_info:
                            # 添加優先級信息
                            device_info['host_api_priority'] = len(host_api_priority) - host_api_priority.index(api_index)
                            
                            self.pyaudio_device_list.append(device_info)
                            self.device_cache[device_info['name']] = global_index
                            
                            if self.debug_mode:
                                print(f"NVDADeviceMonitor: ✓ 設備 {global_index}: {device_info['name']} ({api_name})")
                        
        except Exception as e:
            print(f"NVDADeviceMonitor: Host API優先級掃描失敗: {e}")
            self.scan_devices_simple(temp_pyaudio)

    def scan_devices_simple(self, temp_pyaudio):
        """簡單設備掃描 - 降級方案"""
        try:
            import _portaudio as pa
            device_count = pa.get_device_count()
            
            for i in range(device_count):
                device_info = temp_pyaudio.get_device_info_by_index(i)
                if device_info and device_info.get('maxOutputChannels', 0) > 0:
                    self.pyaudio_device_list.append(device_info)
                    self.device_cache[device_info['name']] = i
                    
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 設備 {i}: {device_info['name']}")
                        
        except Exception as e:
            print(f"NVDADeviceMonitor: 簡單掃描失敗: {e}")
        
    def get_device_friendly_name(self, device_id):
        """根據設備ID獲取友好名稱 - 動態查找"""
        try:
            if not device_id or device_id == "default":
                return "預設設備"
            
            # 嘗試通過動態映射找到對應的PyAudio設備
            mapped_index = self.convert_nvda_device_to_pyaudio_index(device_id)
            
            if mapped_index is not None:
                # 找到了映射索引，查找對應的設備名稱
                for device_info in self.pyaudio_device_list:
                    if device_info.get('index') == mapped_index:
                        return device_info.get('name', f'設備 {mapped_index}')
            
            # 如果沒找到映射，嘗試從設備ID推斷類型
            device_id_lower = device_id.lower()
            
            # 根據GUID特徵推斷設備類型
            if 'realtek' in device_id_lower or '3487e654' in device_id_lower:
                # 查找任何Realtek設備作為候選
                for device_info in self.pyaudio_device_list:
                    device_name = device_info.get('name', '').lower()
                    if 'realtek' in device_name and ('digital' in device_name or 'spdif' in device_name):
                        return device_info.get('name', 'Realtek Digital Output')
                return "Realtek Digital Output (推斷)"
                
            elif 'universal' in device_id_lower or 'ad6ebfcf' in device_id_lower:
                # 查找任何Universal Audio設備作為候選
                for device_info in self.pyaudio_device_list:
                    device_name = device_info.get('name', '').lower()
                    if 'universal audio' in device_name:
                        return device_info.get('name', 'Universal Audio設備')
                return "喇叭 (Universal Audio Thunderbolt WDM)"
                
            elif 'nvidia' in device_id_lower:
                # 查找任何NVIDIA設備作為候選
                for device_info in self.pyaudio_device_list:
                    device_name = device_info.get('name', '').lower()
                    if 'nvidia' in device_name:
                        return device_info.get('name', 'NVIDIA音頻設備')
                return "NVIDIA音頻設備 (推斷)"
            
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
        """智能映射NVDA設備到PyAudio索引 - 參考ooo.py改進"""
        if not nvda_device_id or nvda_device_id == "default":
            return None  # 使用默認設備
        
        try:
            # 第一步：嘗試GUID特徵匹配
            mapped_index = self.try_guid_mapping(nvda_device_id)
            if mapped_index is not None:
                return mapped_index
            
            # 第二步：嘗試名稱模式匹配
            mapped_index = self.try_name_pattern_mapping(nvda_device_id)
            if mapped_index is not None:
                return mapped_index
            
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 無法映射設備 {nvda_device_id}，使用默認")
            
            return None  # 找不到就用默認
            
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 設備映射錯誤: {e}")
            return None

    def try_guid_mapping(self, nvda_device_id):
        """嘗試通過GUID映射 - 動態映射系統"""
        try:
            if not nvda_device_id or nvda_device_id == "default":
                return None
            
            # 提取GUID部分進行匹配
            guid_parts = []
            if '{' in nvda_device_id and '}' in nvda_device_id:
                # 提取所有GUID
                import re
                guids = re.findall(r'\{[^}]+\}', nvda_device_id)
                for guid in guids:
                    guid_clean = guid.replace('{', '').replace('}', '')
                    guid_parts.append(guid_clean.lower())
            
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 提取到的GUID部分: {guid_parts}")
            
            # 動態查找設備映射
            best_match = None
            best_priority = -1
            
            for device in self.pyaudio_device_list:
                device_name = device['name'].lower()
                device_index = device['index']
                host_api_priority = device.get('host_api_priority', 0)
                
                # 檢查設備名稱是否與某些GUID相關聯
                # 我們不硬編碼GUID，而是通過設備名稱特徵匹配
                matched = False
                
                # Realtek設備檢測
                if 'realtek' in device_name and ('digital' in device_name or 'spdif' in device_name):
                    matched = True
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 找到Realtek設備候選: {device['name']}")
                
                # Universal Audio設備檢測
                elif 'universal audio' in device_name and 'thunderbolt' in device_name:
                    matched = True
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 找到Universal Audio設備候選: {device['name']}")
                
                # NVIDIA設備檢測
                elif 'nvidia' in device_name and 'high definition' in device_name:
                    matched = True
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 找到NVIDIA設備候選: {device['name']}")
                
                # 通用音頻設備檢測
                elif any(keyword in device_name for keyword in ['speakers', 'headphones', 'audio', 'sound']):
                    matched = True
                    if self.debug_mode:
                        print(f"NVDADeviceMonitor: 找到通用音頻設備候選: {device['name']}")
                
                # 如果匹配且優先級更高，更新最佳匹配
                if matched and host_api_priority > best_priority:
                    best_match = device
                    best_priority = host_api_priority
            
            if best_match:
                if self.debug_mode:
                    host_api = best_match.get('host_api_name', 'Unknown')
                    print(f"NVDADeviceMonitor: *** 動態GUID映射成功: {best_match['name']} (索引:{best_match['index']}, API:{host_api}) ***")
                return best_match['index']
            
            if self.debug_mode:
                print("NVDADeviceMonitor: 動態GUID映射未找到匹配設備")
            
            return None
            
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 動態GUID映射失敗: {e}")
            return None

    def try_name_pattern_mapping(self, nvda_device_id):
        """嘗試通過名稱模式映射 - 動態映射系統"""
        try:
            if not nvda_device_id or nvda_device_id == "default":
                return None
            
            # 從NVDA設備ID中嘗試推斷設備類型
            device_type_hints = []
            nvda_id_lower = nvda_device_id.lower()
            
            # 分析GUID來推斷設備類型
            if 'realtek' in nvda_id_lower or '3487e654' in nvda_id_lower:
                device_type_hints.append('realtek')
            if 'universal' in nvda_id_lower or 'ad6ebfcf' in nvda_id_lower:
                device_type_hints.append('universal_audio')
            if 'nvidia' in nvda_id_lower:
                device_type_hints.append('nvidia')
            
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 設備類型推斷: {device_type_hints}")
            
            # 根據推斷的設備類型尋找最佳匹配
            best_match = None
            best_score = 0
            
            for device in sorted(self.pyaudio_device_list, 
                               key=lambda d: d.get('host_api_priority', 0), reverse=True):
                device_name = device['name'].lower()
                host_api = device.get('host_api_name', '').lower()
                match_score = 0
                
                # 計算匹配分數
                if 'realtek' in device_type_hints:
                    if 'realtek' in device_name:
                        match_score += 10
                        if 'digital' in device_name or 'spdif' in device_name:
                            match_score += 5
                
                if 'universal_audio' in device_type_hints:
                    if 'universal audio' in device_name:
                        match_score += 10
                        if 'thunderbolt' in device_name:
                            match_score += 5
                
                if 'nvidia' in device_type_hints:
                    if 'nvidia' in device_name:
                        match_score += 10
                        if 'high definition' in device_name:
                            match_score += 5
                
                # Host API優先級獎勵
                if 'wasapi' in host_api:
                    match_score += 3
                elif 'directsound' in host_api:
                    match_score += 2
                elif 'mme' in host_api:
                    match_score += 1
                
                # 如果沒有特定類型提示，給通用音頻設備一些分數
                if not device_type_hints:
                    if any(keyword in device_name for keyword in ['speakers', 'headphones', 'audio', 'sound']):
                        match_score += 3
                
                if match_score > best_score:
                    best_match = device
                    best_score = match_score
            
            if best_match and best_score > 0:
                if self.debug_mode:
                    host_api = best_match.get('host_api_name', 'Unknown')
                    print(f"NVDADeviceMonitor: *** 動態名稱映射成功: {best_match['name']} (分數:{best_score}, API:{host_api}) ***")
                return best_match['index']
            
            if self.debug_mode:
                print("NVDADeviceMonitor: 動態名稱映射未找到匹配設備")
            
            return None
            
        except Exception as e:
            if self.debug_mode:
                print(f"NVDADeviceMonitor: 動態名稱映射失敗: {e}")
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