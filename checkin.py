"""
Doc2X 自动登录与每日签到脚本
- 签到成功：自动触发飞书自定义机器人 Webhook 通知
- 签到失败：自动发送邮件到指定邮箱进行告警提醒
支持多账号批量执行、额度查询与变动对比、手机号掩码隐私保护及 GitHub Actions 定时执行。
"""

import os
import re
import sys
import json
import time
import random
import base64
import hmac
import hashlib
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Tuple, Optional
import requests

# API 配置
API_BASE_URL = "https://v2c.doc2x.noedgeai.com/v2"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Origin": "https://doc2x.noedgeai.com",
    "Referer": "https://doc2x.noedgeai.com/parse",
    "Content-Type": "application/json",
    "x-doc2x-api-version": "2025-06-04",
    "x-doc2x-error-format": "v2",
    "Doc2x-Web-Version": "1.5.70",
}


def mask_phone(phone: str) -> str:
    """掩码手机号以保护隐私，例如 138****0001"""
    if not phone:
        return "未知账号"
    phone_str = str(phone).strip()
    if len(phone_str) >= 7:
        return f"{phone_str[:3]}****{phone_str[-4:]}"
    return f"{phone_str[:2]}***"


class Doc2XClient:
    """Doc2X API 客户端"""

    def __init__(self, phone: str, password: str):
        self.phone = str(phone).strip()
        self.password = str(password).strip()
        self.masked_phone = mask_phone(self.phone)
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.user_info: Dict = {}

    def login(self) -> Tuple[bool, str]:
        """密码登录，获取 access_token"""
        url = f"{API_BASE_URL}/user/login/password"
        payload = {
            "phone": self.phone,
            "password": self.password,
            "loginType": "password",
        }
        try:
            resp = self.session.post(url, json=payload, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and data.get("code") == "success":
                token_data = data.get("data", {})
                self.access_token = token_data.get("access_token")
                self.refresh_token = token_data.get("refresh_token")
                self.session.headers["Authorization"] = f"Bearer {self.access_token}"
                return True, "登录成功"
            else:
                msg = data.get("msg") or data.get("message") or resp.text
                return False, f"登录失败: {msg}"
        except Exception as e:
            return False, f"登录网络异常: {str(e)}"

    def get_profile(self) -> Tuple[bool, Dict]:
        """获取用户基本信息"""
        url = f"{API_BASE_URL}/user/profile"
        try:
            resp = self.session.get(url, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and data.get("code") == "success":
                self.user_info = data.get("data", {})
                return True, self.user_info
            return False, {}
        except Exception:
            return False, {}

    def get_quota(self) -> Optional[int]:
        """获取当前可用解析额度（页数）"""
        url = f"{API_BASE_URL}/user/quota"
        try:
            resp = self.session.get(url, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and data.get("code") == "success":
                return data.get("data", {}).get("available_pages")
            return None
        except Exception:
            return None

    def get_checkin_status(self) -> Tuple[bool, List[str]]:
        """获取当月已签到日期列表"""
        url = f"{API_BASE_URL}/user/checkin/status"
        try:
            resp = self.session.get(url, timeout=15)
            data = resp.json()
            if resp.status_code == 200 and data.get("code") == "success":
                dates = data.get("data", {}).get("checkin_dates", [])
                return True, dates
            return False, []
        except Exception:
            return False, []

    def checkin(self) -> Tuple[bool, str, int]:
        """
        执行每日签到
        返回: (是否成功, 提示消息, 状态类型: 0失败, 1成功, 2已签到)
        """
        url = f"{API_BASE_URL}/user/checkin"
        try:
            resp = self.session.post(url, json={}, timeout=15)
            data = resp.json()
            # 200 表示签到成功
            if resp.status_code == 200 and data.get("code") == "success":
                count = data.get("data", {}).get("count", 1)
                return True, f"签到成功！当月已连续/累计签到 {count} 次", 1
            # 409 或 code 为 user_checkin_exist 表示今日已签过
            elif resp.status_code == 409 or data.get("code") == "user_checkin_exist":
                msg = data.get("msg") or "今天已经签到了"
                return True, f"今日无需重复签到 ({msg})", 2
            else:
                msg = data.get("msg") or data.get("message") or resp.text
                return False, f"签到失败: {msg}", 0
        except Exception as e:
            return False, f"签到异常: {str(e)}", 0

    def run(self) -> Dict:
        """执行单个账号的完整签到工作流"""
        print(f"\n==========================================")
        print(f"👉 开始处理账号: {self.masked_phone}")
        print(f"==========================================")

        result = {
            "account": self.masked_phone,
            "username": "未知",
            "wechat_bound": False,
            "status": "失败",
            "is_success": False,
            "message": "",
            "quota_before": None,
            "quota_after": None,
            "quota_added": 0,
            "checkin_count": 0,
        }

        # 1. 登录
        ok, msg = self.login()
        if not ok:
            print(f"❌ {self.masked_phone} {msg}")
            result["message"] = msg
            return result

        print(f"✅ {self.masked_phone} 登录成功！")

        # 2. 获取用户信息
        _, profile = self.get_profile()
        username = profile.get("username", "无昵称")
        wechat_bound = profile.get("wechat_bound", False)
        result["username"] = username
        result["wechat_bound"] = wechat_bound
        print(f"👤 用户昵称: {username} | 微信绑定状态: {'已绑定 (签到享15页奖励)' if wechat_bound else '未绑定 (签到享8页奖励)'}")

        # 3. 签到前额度
        quota_before = self.get_quota()
        result["quota_before"] = quota_before
        print(f"📊 签到前可用额度: {quota_before if quota_before is not None else '未知'} 页")

        # 4. 查询本月历史签到记录
        _, checkin_dates = self.get_checkin_status()
        result["checkin_count"] = len(checkin_dates)
        print(f"📅 本月已签到天数: {len(checkin_dates)} 天")

        # 5. 执行签到
        checkin_ok, checkin_msg, status_type = self.checkin()
        print(f"{'✅' if checkin_ok else '❌'} {checkin_msg}")
        result["message"] = checkin_msg

        if status_type in (1, 2):
            result["is_success"] = True
            result["status"] = "签到成功" if status_type == 1 else "今日已签到"
        else:
            result["is_success"] = False
            result["status"] = "签到失败"

        # 6. 签到后额度
        quota_after = self.get_quota()
        result["quota_after"] = quota_after
        if quota_before is not None and quota_after is not None:
            added = quota_after - quota_before
            result["quota_added"] = added
            if added > 0:
                print(f"🎉 成功获取额度: +{added} 页 | 当前总额度: {quota_after} 页")
            else:
                print(f"📊 当前总额度: {quota_after} 页")
        elif quota_after is not None:
            print(f"📊 当前总额度: {quota_after} 页")

        return result


def parse_accounts() -> List[Tuple[str, str]]:
    """
    解析账号密码列表，支持多种环境变量配置格式：
    1. DOC2X_ACCOUNTS:
       - 多行格式:
         13800000001:password123
         13800000002:password456
       - 分号/逗号分隔格式:
         13800000001:password123;13800000002:password456
       - 分隔符支持冒号(:)、四横杠(----)、竖线(|)或空格
       - JSON 数组格式:
         [{"phone": "13800000001", "password": "password123"}, ...]
    2. 单账号兼容配置:
       DOC2X_PHONE 和 DOC2X_PASSWORD (或 DOC2X_USERNAME / DOC2X_PWD)
    """
    accounts = []
    raw_accounts = os.environ.get("DOC2X_ACCOUNTS", "").strip()

    if raw_accounts:
        if raw_accounts.startswith("[") and raw_accounts.endswith("]"):
            try:
                data = json.loads(raw_accounts)
                for item in data:
                    p = item.get("phone") or item.get("username") or item.get("account")
                    pwd = item.get("password") or item.get("pwd")
                    if p and pwd:
                        accounts.append((str(p).strip(), str(pwd).strip()))
            except Exception as e:
                print(f"⚠️ JSON 格式解析失败，回退到文本解析: {e}")

        if not accounts:
            lines = re.split(r"[\r\n;,]+", raw_accounts)
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = None
                if "----" in line:
                    parts = line.split("----", 1)
                elif ":" in line:
                    parts = line.split(":", 1)
                elif "|" in line:
                    parts = line.split("|", 1)
                elif " " in line:
                    parts = re.split(r"\s+", line, 1)

                if parts and len(parts) == 2:
                    p, pwd = parts[0].strip(), parts[1].strip()
                    if p and pwd:
                        accounts.append((p, pwd))

    if not accounts:
        single_phone = os.environ.get("DOC2X_PHONE") or os.environ.get("DOC2X_USERNAME")
        single_pwd = os.environ.get("DOC2X_PASSWORD") or os.environ.get("DOC2X_PWD")
        if single_phone and single_pwd:
            accounts.append((single_phone.strip(), single_pwd.strip()))

    return accounts


def gen_feishu_sign(secret: str, timestamp: int) -> str:
    """计算飞书自定义机器人的签名"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_feishu_webhook(success_results: List[Dict]):
    """
    【签到成功通道】向飞书 Webhook 机器人发送成功通知
    """
    feishu_webhook = os.environ.get("FEISHU_WEBHOOK_URL") or os.environ.get("FEISHU_WEBHOOK_KEY")
    if not feishu_webhook:
        print("ℹ️ 未配置飞书 Webhook (FEISHU_WEBHOOK_URL)，跳过飞书推送。")
        return

    url = feishu_webhook.strip()
    if not url.startswith("http"):
        url = f"https://open.feishu.cn/open-apis/bot/v2/hook/{url}"

    current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    content_lines = [
        f"🎉 Doc2X 每日签到成功通知",
        f"⏰ 执行时间: {current_time}",
        "------------------------------------"
    ]
    for r in success_results:
        quota_str = f"{r['quota_after']} 页" if r['quota_after'] is not None else "未知"
        gain_str = f"+{r['quota_added']} 页" if r['quota_added'] > 0 else "0"
        wx_str = "已绑定微信" if r['wechat_bound'] else "未绑定微信"
        content_lines.append(
            f"👤 账号: {r['account']} ({r['username']})\n"
            f"📌 状态: {r['status']}\n"
            f"📊 额度: {quota_str} (本次增加: {gain_str})\n"
            f"💡 详情: {r['message']} ({wx_str})\n"
        )

    text_body = "\n".join(content_lines).strip()
    payload = {
        "msg_type": "text",
        "content": {
            "text": text_body
        }
    }

    feishu_secret = os.environ.get("FEISHU_SECRET")
    if feishu_secret:
        ts = int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = gen_feishu_sign(feishu_secret, ts)

    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"📢 飞书机器人推送结果: {resp.text}")
    except Exception as e:
        print(f"⚠️ 飞书机器人推送失败: {e}")


def send_email_alert(failed_results: List[Dict]):
    """
    【签到失败通道】发送邮件告警提醒
    """
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS") or os.environ.get("SMTP_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL") or os.environ.get("TO_EMAIL") or smtp_user

    if not (smtp_user and smtp_pass and receiver_email):
        print("⚠️ 检测到签到失败，但未完整配置邮箱报警环境变量 (SMTP_USER, SMTP_PASS, RECEIVER_EMAIL)！无法发送告警邮件。")
        return

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port_raw = os.environ.get("SMTP_PORT", "465")
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        smtp_port = 465

    # 智能推断常用 SMTP 服务器
    if not smtp_host:
        u_lower = smtp_user.lower()
        if "@qq.com" in u_lower:
            smtp_host = "smtp.qq.com"
        elif "@163.com" in u_lower:
            smtp_host = "smtp.163.com"
        elif "@126.com" in u_lower:
            smtp_host = "smtp.126.com"
        elif "@gmail.com" in u_lower:
            smtp_host = "smtp.gmail.com"
        elif "@feishu.cn" in u_lower:
            smtp_host = "smtp.feishu.cn"
        elif "@foxmail.com" in u_lower:
            smtp_host = "smtp.qq.com"
        elif "@outlook.com" in u_lower or "@hotmail.com" in u_lower:
            smtp_host = "smtp-mail.outlook.com"
        else:
            smtp_host = "smtp.qq.com"

    current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    subject = f"🚨【警报】Doc2X 签到失败提醒 - {len(failed_results)}个账号异常 ({current_time})"

    # 构建 HTML 邮件内容
    rows_html = ""
    for r in failed_results:
        rows_html += f"""
        <tr style="border-bottom: 1px solid #ddd;">
            <td style="padding: 10px; font-weight: bold; color: #d9534f;">{r['account']}</td>
            <td style="padding: 10px;">{r['username']}</td>
            <td style="padding: 10px; color: #d9534f; font-weight: bold;">{r['status']}</td>
            <td style="padding: 10px; color: #666;">{r['message']}</td>
        </tr>
        """

    html_content = f"""
    <html>
    <body style="font-family: Arial, 'Microsoft YaHei', sans-serif; background-color: #f9f9f9; padding: 20px;">
        <div style="max-width: 650px; margin: 0 auto; background-color: #fff; border-radius: 8px; padding: 25px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); border-left: 5px solid #d9534f;">
            <h2 style="color: #d9534f; margin-top: 0;">🚨 Doc2X 每日签到失败通知</h2>
            <p style="color: #555; font-size: 14px;">您的 Doc2X 账号在今日定时签到过程中发生异常，详情如下：</p>
            <p style="color: #888; font-size: 12px;">执行时间：{current_time}</p>
            
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px;">
                <thead>
                    <tr style="background-color: #f2dede; color: #a94442; text-align: left;">
                        <th style="padding: 10px;">账号</th>
                        <th style="padding: 10px;">昵称</th>
                        <th style="padding: 10px;">状态</th>
                        <th style="padding: 10px;">失败原因</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
            
            <div style="background-color: #fff3cd; color: #856404; padding: 12px; border-radius: 4px; font-size: 13px;">
                <strong>💡 建议排查方向：</strong><br/>
                1. 检查账号密码是否已变更，或在 GitHub Secrets (DOC2X_ACCOUNTS) 中核对格式。<br/>
                2. 访问 <a href="https://doc2x.noedgeai.com" target="_blank">Doc2X 官网</a> 检查账号是否正常或需手机验证码。<br/>
            </div>
            
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;"/>
            <p style="font-size: 12px; color: #999; text-align: center;">此邮件由 GitHub Actions 自动化脚本触发发送，请勿直接回复。</p>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = Header(f"Doc2X Checkin Alert <{smtp_user}>", "utf-8")
    msg["To"] = Header(receiver_email, "utf-8")
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            try:
                server.starttls()
            except Exception:
                pass

        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [receiver_email], msg.as_string())
        server.quit()
        print(f"📧 失败报警邮件发送成功！已成功发送至: {receiver_email}")
    except Exception as e:
        print(f"⚠️ 报警邮件发送失败: {e}")


def write_github_summary(results: List[Dict]):
    """写入 GitHub Actions Job Summary"""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return
    try:
        current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        markdown = f"## 📅 Doc2X 每日签到结果\n\n"
        markdown += f"> 执行时间: {current_time}\n\n"
        markdown += "| 账号 | 昵称 | 微信绑定 | 签到状态 | 当前额度 | 本次增加 | 详情 |\n"
        markdown += "| :--- | :--- | :---: | :---: | :---: | :---: | :--- |\n"
        for r in results:
            wx = "✅ 已绑定" if r["wechat_bound"] else "❌ 未绑定"
            status_style = f"**{r['status']}**" if r["is_success"] else f"<span style='color:red;'>**{r['status']}**</span>"
            added = f"+{r['quota_added']} 页" if r['quota_added'] > 0 else "0"
            quota = f"{r['quota_after']} 页" if r['quota_after'] is not None else "未知"
            markdown += f"| `{r['account']}` | {r['username']} | {wx} | {status_style} | {quota} | {added} | {r['message']} |\n"

        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(markdown)
        print("📝 GitHub Action Summary 写入成功！")
    except Exception as e:
        print(f"⚠️ 写入 GitHub Action Summary 失败: {e}")


def main():
    print("=" * 50)
    print("🚀 Doc2X 每日自动签到程序启动")
    print(f"⏰ 当前时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
    print("=" * 50)

    accounts = parse_accounts()
    if not accounts:
        print("\n❌ 未配置任何 Doc2X 账号！")
        print("请在 GitHub 仓库中配置 Secret: DOC2X_ACCOUNTS")
        print("格式示例（每行一个账号密码，冒号分隔）：")
        print("13800000001:password123")
        sys.exit(1)

    print(f"📦 共检测到 {len(accounts)} 个账号，开始依次签到...")

    results = []
    success_list = []
    failed_list = []

    for idx, (phone, password) in enumerate(accounts, start=1):
        client = Doc2XClient(phone, password)
        res = client.run()
        results.append(res)

        if res["is_success"]:
            success_list.append(res)
        else:
            failed_list.append(res)

        # 多账号之间随机等待 3~8 秒，避免过快被风控
        if idx < len(accounts):
            sleep_sec = random.randint(3, 8)
            print(f"⏳ 等待 {sleep_sec} 秒后处理下一个账号...")
            time.sleep(sleep_sec)

    # 汇总输出
    print("\n" + "=" * 50)
    print("📋 签到任务执行汇总")
    print("=" * 50)

    for r in results:
        quota_str = f"{r['quota_after']} 页" if r['quota_after'] is not None else "未知"
        gain_str = f"+{r['quota_added']}" if r['quota_added'] > 0 else "0"
        tag = "✅" if r["is_success"] else "❌"
        print(f"{tag} 【{r['account']}】({r['username']}) - {r['status']} | 额度: {quota_str} (本次 {gain_str}) | {r['message']}")

    # 1. 写入 GitHub Actions Job Summary
    write_github_summary(results)

    # 2. 条件分流推送：
    # 成功账号 -> 发送飞书 Webhook
    if success_list:
        print(f"\n📨 检测到 {len(success_list)} 个账号签到成功，正在触发【飞书 Webhook】推送...")
        send_feishu_webhook(success_list)
    else:
        print("\nℹ️ 无签到成功账号，跳过飞书推送。")

    # 失败账号 -> 发送邮件告警提醒
    if failed_list:
        print(f"\n🚨 检测到 {len(failed_list)} 个账号签到失败，正在触发【邮件告警】推送...")
        send_email_alert(failed_list)
    else:
        print("\n✨ 所有账号均执行成功，无需发送失败报警邮件。")

    print("\n✨ 所有流程处理完毕！")

    fail_on_error = os.environ.get("FAIL_ON_ERROR", "false").lower() == "true"
    if failed_list and fail_on_error:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
