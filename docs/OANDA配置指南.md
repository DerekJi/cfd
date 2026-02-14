# OANDA API 配置步骤

## 📝 快速配置指南

### Step 1: 获取API密钥

1. 登录OANDA账户：https://www.oanda.com/
2. 进入API设置页面：https://www.oanda.com/account/tpa/personal_token
3. 点击 "Generate" 生成新的Personal Access Token
4. **复制并保存**这个Token（只显示一次！）

### Step 2: 创建配置文件

```bash
cd /d/source/cfd-backtest/backtest

# Windows
copy oanda_config_template.py oanda_config.py

# Linux/Mac
cp oanda_config_template.py oanda_config.py
```

### Step 3: 编辑配置文件

打开 `oanda_config.py`，填入你的信息：

```python
# API密钥（粘贴你刚才复制的Token）
OANDA_API_KEY = "b1a2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"

# 账户ID（可选，通常可以留空）
OANDA_ACCOUNT_ID = ""

# 环境类型
OANDA_ENVIRONMENT = "practice"  # 模拟账户用 "practice"，真实账户用 "live"

# 数据下载配置（可根据需要修改）
DOWNLOAD_CONFIG = {
    "instrument": "EUR_USD",
    "granularity": "M5",
    "start_date": "2024-01-01",
    "end_date": "2026-02-14",
}
```

### Step 4: 安装依赖

```bash
pip install oandapyV20
```

### Step 5: 下载数据

```bash
python download_oanda.py
# 选择选项 1（使用配置文件）
```

---

## 🚀 两种使用方式

### 方式A：使用配置文件（推荐）

**优点**：
- ✅ 安全：API密钥保存在本地文件
- ✅ 方便：配置一次，多次使用
- ✅ 可控：可以修改下载参数

**步骤**：
```bash
# 1. 创建并编辑配置文件（见上方 Step 2-3）

# 2. 运行下载脚本
python download_oanda.py
# 选择选项 1

# 3. 验证数据
python test_data.py

# 4. 运行回测
python run_backtest.py
```

---

### 方式B：交互式输入

**优点**：
- ✅ 快速：不需要创建配置文件
- ✅ 临时：适合一次性使用

**步骤**：
```bash
python download_oanda.py
# 选择选项 2
# 按提示输入API密钥和其他信息
```

---

## ⚙️ 配置说明

### API密钥格式
- 长度：64个字符
- 格式：字母数字混合
- 示例：`a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6a7b8c9d0e1f2g3h4i5j6k7l8m9n0o1p2`

### 环境类型
- **practice**：模拟账户（推荐用于回测）
  - 无风险
  - 免费使用
  - 数据相同
  
- **live**：真实账户
  - 需要真实资金账户
  - 谨慎使用

### 时间范围建议
| 范围 | 用途 | 下载时间 |
|------|------|---------|
| 1个月 | 快速测试 | ~1分钟 |
| 3个月 | 基础回测 | ~3分钟 |
| 6个月 | 充分验证 | ~6分钟 |
| 12个月 | 完整回测 | ~12分钟 |

---

## 🔒 安全提示

1. **从不公开分享API密钥**
2. **不要提交配置文件到Git**
   ```bash
   # .gitignore 中已包含
   oanda_config.py
   ```
3. **定期更新API密钥**
4. **使用practice账户进行测试**

---

## ❓ 常见问题

### Q1: API密钥在哪里找？
A: https://www.oanda.com/account/tpa/personal_token

### Q2: 需要账户ID吗？
A: 通常**不需要**，可以留空。只有特殊情况下才需要。

### Q3: practice和live账户的数据一样吗？
A: 是的，历史数据完全相同。推荐使用practice账户。

### Q4: 下载失败怎么办？
A: 检查：
- API密钥是否正确
- 网络连接是否正常
- 时间范围是否合理
- 是否安装了 oandapyV20

### Q5: 可以下载其他货币对吗？
A: 可以！修改配置中的 `instrument`：
- EUR_USD（欧元/美元）
- GBP_USD（英镑/美元）
- USD_JPY（美元/日元）
- 等等...

### Q6: 下载的数据保存在哪里？
A: `backtest/data/EURUSD_5m_2024-2026.csv`

---

## 📊 下载后的步骤

```bash
# 1. 验证数据质量
python test_data.py

# 2. 修改 run_backtest.py
# 将最后一行改为: run_backtest(use_sample_data=False)

# 3. 运行回测
python run_backtest.py

# 4. 查看结果
# 终端输出 + results/reports/ 目录
```

---

## 💡 提示

- 首次下载建议先下载1-3个月数据测试
- 确认工具正常后再下载完整数据集
- 可以随时重新下载覆盖旧数据
- 配置文件可以保存多个版本（用于不同货币对）

---

**需要帮助？** 查看错误提示或运行 `python download_oanda.py` 获取详细指导。
