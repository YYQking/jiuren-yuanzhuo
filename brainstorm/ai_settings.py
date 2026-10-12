"""Local AI settings; Windows protects the key for the current user."""
import base64
import ctypes
from ctypes import wintypes
from dataclasses import replace
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout


def endpoint_url(base_url):
    value = base_url.strip().rstrip('/')
    parsed = urlsplit(value)
    if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('请输入有效的接口地址')
    if parsed.scheme == 'http' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('远程接口必须使用 HTTPS')
    return value if value.endswith('/chat/completions') else value + '/chat/completions'


def protect_key(value, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    incoming = Blob(len(value), buffer)
    outgoing = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise OSError('无法访问本机加密密钥')
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel = ctypes.WinDLL('kernel32')
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(outgoing.data)


class AISettingsStore:
    def __init__(self, path=None):
        if path:
            self.path = Path(path)
        else:
            base = os.environ.get('LOCALAPPDATA') or os.environ.get('USERPROFILE') or os.getcwd()
            self.path = Path(base) / '九人圆桌' / 'ai-settings.json'

    def load(self, config):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            endpoint_url(data['base_url'])
            key = protect_key(base64.b64decode(data['protected_key']), True).decode('utf-8') if data.get('protected_key') else ''
            return replace(config, llm_provider='openai', llm_base_url=data['base_url'], llm_model=data['model'], llm_api_key=key, allow_llm=data.get('enabled') is True)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return config

    def save(self, config):
        endpoint_url(config.llm_base_url)
        data = {'base_url': config.llm_base_url, 'model': config.llm_model, 'enabled': config.allow_llm,
                'protected_key': base64.b64encode(protect_key(config.llm_api_key.encode('utf-8'))).decode('ascii') if config.llm_api_key else ''}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, self.path)


class AISettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle('AI 设置 · OpenAI 兼容接口')
        self.resize(540, 420)
        self.config = config
        root = QVBoxLayout(self)
        note = QLabel('支持 OpenAI 格式的服务。设置用于下一次讨论；密钥仅在本机加密保存。')
        note.setWordWrap(True)
        root.addWidget(note)
        self.enabled = QCheckBox('启用 AI 讨论（会调用所填服务）')
        self.enabled.setChecked(config.allow_llm)
        root.addWidget(self.enabled)
        self.address = QLineEdit(config.llm_base_url)
        self.model = QLineEdit(config.llm_model if config.llm_provider == 'openai' else '')
        self.model.setPlaceholderText('填写服务商提供的模型名称')
        self.key = QLineEdit(config.llm_api_key if config.llm_provider == 'openai' else '')
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        for label, widget in [('接口地址（例如 https://api.openai.com/v1）', self.address), ('模型名称', self.model), ('API Key', self.key)]:
            root.addWidget(QLabel(label))
            root.addWidget(widget)
        self.status = QLabel('未测试连接；保存配置不代表服务请求成功。')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _save(self):
        try:
            endpoint_url(self.address.text())
            if self.enabled.isChecked() and (not self.model.text().strip() or not self.key.text().strip()):
                raise ValueError('启用 AI 时需要模型名称和 API Key')
            self.result_config = replace(self.config, llm_provider='openai', llm_base_url=self.address.text().strip().rstrip('/'),
                llm_model=self.model.text().strip(), llm_api_key=self.key.text().strip(), allow_llm=self.enabled.isChecked())
            AISettingsStore().save(self.result_config)
            self.accept()
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
