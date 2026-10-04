# Doc2X 每日自动签到 (GitHub Actions)

[![Doc2X 每日自动签到](https://github.com/leisure462/doc2x/actions/workflows/daily_checkin.yml/badge.svg)](https://github.com/leisure462/doc2x/actions/workflows/daily_checkin.yml)

本项目为 [Doc2X (noedgeai.com)](https://doc2x.noedgeai.com) 的每日全自动签到脚本，基于 GitHub Actions 实现零服务器部署，每天定时自动登录、签到并领取解析额度（绑定微信每日 15 页，未绑定每日 8 页）。

---

## ✨ 核心特性

- **分流精准通知**：
  - **签到成功**：自动触发 **飞书自定义机器人 Webhook** 发送签到成功与额度变动通知。
  - **签到失败**：自动向指定 **邮箱** 发送告警邮件，详细汇报失败账号与原因，提醒及时处理。
- **多账号支持**：支持配置一个或多个账号密码，自动批量执行。
- **定时自动化**：每天北京时间上午 09:15 定时执行（Doc2X 刷新时间为 08:00）。
- **额度统计**：自动查询并对比签到前后的可用解析页数、本月签到天数。
- **隐私保护**：运行日志中对手机号做脱敏掩码处理（如 `138****0001`），密码绝不上屏。
- **支持手动运行**：支持在 GitHub Actions 页面一键点击 `Run workflow` 立即测试。
- **可视报告**：自动生成 GitHub Actions Job Summary 结果汇总表格。

---

## 🚀 快速上手配置指南

所有配置项均在 GitHub 仓库中通过 **Secrets** 维护，无需修改任何代码。

打开你的 GitHub 仓库页面：`https://github.com/leisure462/doc2x`  
点击仓库上方的 **Settings** -> 左侧菜单选择 **Secrets and variables** -> **Actions** -> 点击 **New repository secret** 添加。

---

### 第一步：配置账号密码（必填）

- **Secret 名称**: `DOC2X_ACCOUNTS`
- **Secret 内容**: 你的账号密码，支持多账号（每行一个）：

```text
13800000001:password123
13800000002:password456
```

> 💡 **分隔符说明**：
> 账号与密码之间支持冒号 `:`、四个横杠 `----`、竖线 `|` 或 空格。

---

### 第二步：配置成功通知（飞书 Webhook 机器人）

当签到成功（或今日已签到）时，脚本会向飞书群机器人发送通知卡片。

1. 在飞书群聊中点击右上角 **设置** -> **群机器人** -> **添加机器人** -> 选择 **自定义机器人**。
2. 复制生成的 **Webhook 地址**。如果开启了“签名校验”，同时复制 **Secret（密钥）**。
3. 在 GitHub Secrets 中添加：

| Secret 变量名 | 是否必填 | 说明 |
| :--- | :---: | :--- |
| `FEISHU_WEBHOOK_URL` | **推荐** | 飞书机器人 Webhook 完整地址，如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx` |
| `FEISHU_SECRET` | 可选 | 飞书机器人的签名密钥（开启了安全设置中的“签名校验”时填写，未开启可留空） |

---

### 第三步：配置失败报警（发送告警邮件）

当某个账号登录失败、接口报错或签到异常时，脚本会自动发送邮件到你的邮箱。

在 GitHub Secrets 中添加以下邮箱配置（以常用的 QQ 邮箱或 163 邮箱为例）：

| Secret 变量名 | 是否必填 | 说明与示例 |
| :--- | :---: | :--- |
| `SMTP_USER` | **必填** | 发件人邮箱账号，例如 `your_qq_number@qq.com` |
| `SMTP_PASS` | **必填** | 发件人邮箱**授权码 / 密码**（非邮箱登录密码，见下方说明） |
| `RECEIVER_EMAIL` | 可选 | 接收告警邮件的目标邮箱（不填则默认发给自己 `SMTP_USER`） |
| `SMTP_HOST` | 可选 | SMTP 服务器地址（脚本会自动根据发件人推断：QQ 邮箱默认 `smtp.qq.com`，163 邮箱默认 `smtp.163.com`） |
| `SMTP_PORT` | 可选 | SMTP 端口，默认 `465` (SSL) |

> 💡 **如何获取邮箱授权码（以 QQ 邮箱为例）**：
> 1. 网页登录 QQ 邮箱 -> 点击顶部「设置」->「账号与安全」。
> 2. 向下滚动找到「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务」。
> 3. 开启「POP3/SMTP服务」，按照提示发送短信即可获得一串 16 位的**授权码**，填入 `SMTP_PASS` 即可。

---

### 第四步：测试运行

1. 点击仓库上方的 **Actions** 标签页。
2. 在左侧列表中点击 **Doc2X 每日自动签到**。
3. 点击右侧的 **Run workflow** 下拉按钮，点击绿色的 **Run workflow** 按钮启动测试。
4. 几秒钟后即可在运行日志与 Job Summary 中查看签到结果。

---

## ⏰ 定时签到时间

在 `.github/workflows/daily_checkin.yml` 中配置的 cron 为：
```yaml
- cron: '15 1 * * *'
```
即 **UTC 时间 01:15**，换算为 **北京时间 09:15**。Doc2X 每日签到额度的刷新时间为北京时间 08:00，因此 09:15 执行既避开了整点拥堵，又能准时获取当日额度。

---

## 🛡️ 本地运行与调试

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置环境变量测试
# Windows (PowerShell):
$env:DOC2X_ACCOUNTS="13800000001:password123"
$env:FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
python checkin.py

# Linux / macOS:
export DOC2X_ACCOUNTS="13800000001:password123"
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
python checkin.py
```

---

## ⚠️ 免责声明

1. 本项目仅供个人学习研究交流使用，请勿用于任何商业或非法用途。
2. 请妥善保管好个人账号密码，务必通过 GitHub Secrets 存放，切勿直接提交到公开代码中。
