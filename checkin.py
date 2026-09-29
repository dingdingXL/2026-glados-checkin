#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
2026 GLaDOS 自动签到 (积分增强版)

功能：
- 全自动签到
- 精准获取当前积分 (Points)
- PushPlus 微信推送（包含积分、剩余天数、签到结果）
- 智能多域名切换 (优先 www.glados.vip)
- 签到 token 自动跟随实际域名，避免跨域名无效签到
- 支持 Cookie-Editor 导出格式
"""

import requests
import json
import os
import sys
import time
from datetime import datetime

# Fix Windows Unicode Output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# ================= 配置 =================

# 域名优先级：www.glados.vip 第一（2026 新版 API）
DOMAINS = [
    "https://www.glados.vip",
    "https://glados.vip",
    "https://glados.cloud",
    "https://glados.rocks",
    "https://glados.network",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36 Edg/149.0.0.0',
    'Content-Type': 'application/json;charset=UTF-8',
    'Accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'sec-ch-ua': '"Microsoft Edge";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'priority': 'u=1, i',
}

# ================= 工具函数 =================

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def extract_cookie(raw: str):
    """提取 Cookie，支持 Cookie-Editor 冒号格式"""
    if not raw: return None
    raw = raw.strip()
    
    # Cookie-Editor 格式 (koa:sess=xxx; koa:sess.sig=yyy)
    if 'koa:sess=' in raw or 'koa:sess.sig=' in raw:
        return raw
        
    # JSON
    if raw.startswith('{'):
        try:
            return 'koa:sess=' + json.loads(raw).get('token')
        except: pass
        
    # JWT Token
    if raw.count('.') == 2 and '=' not in raw and len(raw) > 50:
        return 'koa:sess=' + raw
        
    # Standard
    return raw

def get_cookies():
    raw = os.environ.get("GLADOS_COOKIE", "")
    if not raw:
        log("❌ 未配置 GLADOS_COOKIE")
        return []
    
    # Split by enter or &
    sep = '\n' if '\n' in raw else '&'
    return [extract_cookie(c) for c in raw.split(sep) if c.strip()]

# ================= 核心逻辑 =================

class GLaDOS:
    def __init__(self, cookie):
        self.cookie = cookie
        self.domain = DOMAINS[0]
        self.email = "?"
        self.left_days = "?"
        self.system_date = ""
        self.points = "?"
        self.points_change = "?"
        self.exchange_info = ""
        self.plan = "?"
        self.today_gain = None
        self.streak = None
        
    def req(self, method, path, data=None, data_fn=None):
        """带自动域名切换的请求

        data_fn: 可调用对象，接收当前域名并返回请求体。
                 用于那些 body 内容必须与域名保持一致的接口（如签到 token）。
        """
        last_err = None
        for d in DOMAINS:
            try:
                url = f"{d}{path}"
                h = HEADERS.copy()
                h['Cookie'] = self.cookie
                h['Origin'] = d
                h['Referer'] = f"{d}/console/checkin"

                payload = data_fn(d) if data_fn else data

                if method == 'GET':
                    resp = requests.get(url, headers=h, timeout=10)
                else:
                    resp = requests.post(url, headers=h, json=payload, timeout=10)

                if resp.status_code == 200:
                    self.domain = d  # Remember working domain
                    return resp.json()
                else:
                    last_err = f"HTTP {resp.status_code}"
            except Exception as e:
                last_err = e
                log(f"⚠️ {d} 请求失败: {e}")
                continue
        if last_err:
            log(f"⚠️ {path} 所有域名均失败，最后错误: {last_err}")
        return None

    def get_status(self):
        """获取状态：天数、邮箱"""
        res = self.req('GET', '/api/user/status')
        if res and 'data' in res:
            d = res['data']
            self.email = d.get('email', 'Unknown')
            self.left_days = str(d.get('leftDays', '?')).split('.')[0]
            self.system_date = str(d.get('system_date') or '')[:10]
            return True
        return False

    def get_points(self):
        """获取积分、变化历史、兑换计划"""
        res = self.req('GET', '/api/user/points')
        if res and 'points' in res:
            # 当前积分
            self.points = str(res.get('points', '0')).split('.')[0]
            
            # 最近一次积分变化
            history = res.get('history', []) or []
            if history:
                last = history[0]
                change = str(last.get('change', '0')).split('.')[0]
                if not change.startswith('-'):
                    change = '+' + change
                self.points_change = change

                # 若最近一条流水就是今天，则视为今日签到收益
                today = self.system_date or datetime.now().strftime('%Y-%m-%d')
                if str(last.get('detail', ''))[:10] == today:
                    try:
                        self.today_gain = int(float(last.get('change', 0)))
                    except (TypeError, ValueError):
                        self.today_gain = None
            
            # 兑换计划
            plans = res.get('plans', {}) or {}
            try:
                pts = int(self.points)
            except (TypeError, ValueError):
                pts = 0
            exchange_lines = []
            for plan_id, plan_data in plans.items():
                need = plan_data.get('points', 0)
                days = plan_data.get('days', 0)
                if pts >= need:
                    exchange_lines.append(f"✅ {need}分→{days}天 (可兑换)")
                else:
                    exchange_lines.append(f"❌ {need}分→{days}天 (差{need - pts}分)")
            self.exchange_info = "<br>".join(exchange_lines)
            return True
        return False

    @staticmethod
    def token_of(domain):
        """签到 token 必须与请求域名完全一致（含 www. 前缀）"""
        return domain.replace('https://', '').replace('http://', '').strip('/')

    def checkin(self):
        """执行签到：token 跟随实际命中的域名，避免跨域名导致无效签到"""
        res = self.req(
            'POST',
            '/api/user/checkin',
            data_fn=lambda d: {'token': self.token_of(d)},
        )
        if res:
            # 新版 API 会返回连续签到天数（points 字段恒为 0，不代表今日收益）
            self.streak = res.get('streak')
        return res

    # 失败文案特征：新版 API 失败时返回 "please checkin via https://..."
    FAIL_HINTS = ('please checkin', 'unauthorized', 'invalid', 'expired', 'error', 'fail')

    @classmethod
    def is_success(cls, res):
        """判断签到结果

        注意：GLaDOS 各接口的 code 语义并不统一（签到成功 code=1，状态接口成功 code=0），
        所以这里只依据 message 文案判断，不能依赖 code：
        - 成功: "Today's observation logged. Return tomorrow for more points."
        - 成功: "Checkin Repeats! Please Try Tomorrow"（今日已签）
        - 失败: "please checkin via https://..."
        """
        if not res:
            return False
        msg = f"{res.get('message', '')}{res.get('msg', '')}".strip().lower()
        if not msg:
            return False
        return not any(hint in msg for hint in cls.FAIL_HINTS)

# ================= 主程序 =================

def pushplus(token, title, content):
    if not token: return
    try:
        url = "http://www.pushplus.plus/send"
        requests.get(url, params={'token': token, 'title': title, 'content': content, 'template': 'html'}, timeout=5)
        log("✅ PushPlus 推送成功")
    except:
        log("❌ PushPlus 推送失败")

def telegram_push(token, chat_id, title, content):
    if not token or not chat_id: return
    try:
        import re
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        # Convert HTML to be Telegram-compatible
        text = f"<b>{title}</b>\n\n{content}"
        
        # 1. Block elements replacements (handle tags with attributes)
        text = text.replace("<br>", "\n")
        # Handle H3 tags
        text = re.sub(r"<h3[^>]*>", "<b>", text)
        text = text.replace("</h3>", "</b>\n")
        
        # 2. Paragraph and Div tags
        text = re.sub(r"<(div|p)[^>]*>", "", text)
        text = re.sub(r"</(div|p)>", "\n", text)
        
        # 3. Span and small tags
        text = re.sub(r"<(span|small)[^>]*>", "", text)
        text = re.sub(r"</(span|small)>", "", text)
        
        # 4. Final cleaning: Strip all HTML tags EXCEPT the ones supported by Telegram: b, i, u, s, a, code, pre
        text = re.sub(r"<(?!\/?(b|i|u|s|a|code|pre)\b)[^>]+>", "", text)
        
        # 5. Dedent each line to fix alignment issues caused by HTML template indentation
        lines = [line.strip() for line in text.split('\n')]
        text = "\n".join(lines)
        
        # 6. Collapse multiple newlines
        text = re.sub(r"\n\s*\n", "\n\n", text).strip()
        
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        log(f"发送内容: {data}")
        resp=requests.post(url, json=data, timeout=5)
        if resp.status_code != 200:
            log(f"❌ Telegram 推送失败: {resp.json()}")
            return
        log("✅ Telegram 推送成功")
    except Exception as e:
        log(f"❌ Telegram 推送失败: {e}")

def main():
    log("🚀 2026 GLaDOS Checkin Starting...")
    cookies = get_cookies()
    if not cookies: sys.exit(1)
    
    results = []
    success_cnt = 0
    
    for i, cookie in enumerate(cookies, 1):
        g = GLaDOS(cookie)
        
        # 1. Checkin
        res = g.checkin()
        msg = res.get('message', 'Failure') if res else "Network Error"
        
        # 2. Get Info (Refresh data)
        g.get_status()
        g.get_points()
        
        # 3. Log
        ok = g.is_success(res)
        status_icon = "✅" if ok else "⚠️"
        gain_txt = f" | 今日+{g.today_gain}" if g.today_gain is not None else ""
        log(f"{status_icon} 用户: {g.email} | 积分: {g.points} | 天数: {g.left_days}{gain_txt} | 结果: {msg}")

        if ok: success_cnt += 1

        # 连续签到天数
        streak_html = ""
        if g.streak:
            streak_html = f'<p style="margin:8px 0; color:#000; font-size:16px;"><b>连续签到:</b> <span style="font-weight:bold;">{g.streak} 天</span></p>'
        # 今日获得积分
        gain_html = ""
        if g.today_gain is not None and g.today_gain > 0:
            gain_html = f'<p style="margin:8px 0; color:#000; font-size:16px;"><b>今日获得:</b> <span style="color:#e74c3c; font-weight:bold;">+{g.today_gain} 积分</span></p>'

        # 4. Result Formatting
        results.append(f"""
<div style="border:2px solid #333; padding:15px; margin-bottom:15px; border-radius:10px; background:#fff;">
    <h3 style="margin:0 0 15px 0; color:#333; border-bottom:2px solid #333; padding-bottom:8px;">👤 {g.email}</h3>
    <p style="margin:8px 0; color:#000; font-size:16px;"><b>当前积分:</b> <span style="color:#e74c3c; font-size:22px; font-weight:bold;">{g.points}</span> <span style="color:#27ae60; font-weight:bold;">({g.points_change})</span></p>
    {gain_html}
    <p style="margin:8px 0; color:#000; font-size:16px;"><b>剩余天数:</b> <span style="font-weight:bold;">{g.left_days} 天</span></p>
    {streak_html}
    <p style="margin:8px 0; color:#000; font-size:16px;"><b>签到结果:</b> {msg}</p>
    <div style="margin-top:15px; padding:12px; background:#f0f0f0; border-radius:8px; border:1px solid #ccc;">
        <p style="margin:0 0 8px 0; color:#333; font-weight:bold; font-size:15px;">🎁 兑换选项:</p>
        <p style="margin:0; color:#000; font-size:14px; line-height:1.8;">
{g.exchange_info}</p>
    </div>
</div>
""")

    # Push
    push_level = os.environ.get("PUSH_LEVEL", "all").lower()
    
    if push_level == "fail_only" and success_cnt == len(cookies):
        log("⏭️ 根据 PUSH_LEVEL=fail_only 设置，所有账号签到成功，跳过推送")
        return

    ptoken = os.environ.get("PUSHPLUS_TOKEN")
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if ptoken or (tg_token and tg_chat_id):
        title = f"GLaDOS签到: 成功{success_cnt}/{len(cookies)}"
        content = "".join(results)
        content += f"<br><small>时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small>"
        
        if ptoken:
            pushplus(ptoken, title, content)
        if tg_token and tg_chat_id:
            telegram_push(tg_token, tg_chat_id, title, content)

if __name__ == '__main__':
    main()
