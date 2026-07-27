# ReversibleMosaic

Android 本地单图可逆视觉混淆工具。项目以 [需求规格](requirements_product_v1.md) 和 [开发计划](development_plan.md) 为准。

> 本产品提供可逆视觉混淆，不是密码学加密。分享代码不提供机密性、真实性或抗穷举保证。

## 当前状态

项目处于阶段 0/1：工程基线、V1 算法与安全图片链路开发。

## 本地开发

要求 Python 3.11–3.13。Windows 当前项目虚拟环境为 Python 3.11。

```bash
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

Android 构建将在 WSL2 内使用 Buildozer/python-for-android，工具版本会在可行性探针后冻结。

## 隐私边界

- 图片仅在本机处理。
- 不申请网络权限。
- 不保存图片历史、最近 URI 或分享代码。
- 分享代码不会写入 PNG 元数据、文件名、日志或分享文字。
