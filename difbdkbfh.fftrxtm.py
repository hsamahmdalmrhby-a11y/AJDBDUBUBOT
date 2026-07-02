import os
import re
import json
import sqlite3
import requests
import telebot
import yt_dlp
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import urlparse, quote
import time
from datetime import datetime, timedelta
import threading
import zipfile
import shutil

# ============================================
# 🔐 إعدادات الأمان والبيئة
# ============================================
BOT_TOKEN = "8833086519:AAFEZw7FPHJ6iJZc5tisB313iUO6jjjkWXU"
OWNER_ID = 8539408138
OWNER_USERNAME = "Mkdkdkd8484849"

bot = telebot.TeleBot(BOT_TOKEN)

# قاعدة بيانات SQLite
DB_FILE = "bot_database.db"

# ============================================
# 🗄️ نظام قاعدة البيانات المتطور
# ============================================

def init_database():
    """إنشاء قاعدة البيانات مع جميع الجداول"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # جدول المستخدمين
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        join_date TEXT,
        last_active TEXT,
        is_banned INTEGER DEFAULT 0,
        rank TEXT DEFAULT 'عضو',
        daily_reward_date TEXT,
        notifications INTEGER DEFAULT 1
    )''')
    
    # جدول القنوات الإجبارية
    c.execute('''CREATE TABLE IF NOT EXISTS channels (
        channel_id TEXT PRIMARY KEY,
        channel_title TEXT,
        added_date TEXT
    )''')
    
    # جدول الإحصائيات
    c.execute('''CREATE TABLE IF NOT EXISTS stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        media_type TEXT,
        platform TEXT,
        download_date TEXT,
        file_size INTEGER
    )''')
    
    # جدول المستخدمين المحظورين
    c.execute('''CREATE TABLE IF NOT EXISTS banned_users (
        user_id INTEGER PRIMARY KEY,
        ban_reason TEXT,
        ban_date TEXT
    )''')
    
    # جدول الطلبات اليومية
    c.execute('''CREATE TABLE IF NOT EXISTS daily_requests (
        user_id INTEGER,
        request_date TEXT,
        request_count INTEGER DEFAULT 1,
        PRIMARY KEY (user_id, request_date)
    )''')
    
    # جدول الملاحظات
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        feedback_text TEXT,
        feedback_date TEXT,
        status TEXT DEFAULT 'جديد'
    )''')
    
    # جدول التنبيهات
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        notification_text TEXT,
        notification_date TEXT,
        is_read INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    conn.close()

init_database()

# ============================================
# 📊 دوال إدارة قاعدة البيانات
# ============================================

def save_user(user_id, username=None, first_name=None, last_name=None):
    """حفظ المستخدم في قاعدة البيانات"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute('''INSERT OR IGNORE INTO users 
                     (user_id, username, first_name, last_name, join_date, last_active, rank)
                     VALUES (?, ?, ?, ?, ?, ?, 'عضو')''',
                  (user_id, username, first_name, last_name, now, now))
        
        c.execute('''UPDATE users SET last_active = ? WHERE user_id = ?''', (now, user_id))
        conn.commit()
        conn.close()
    except:
        pass

def update_user_rank(user_id):
    """تحديث مستوى المستخدم حسب عدد التحميلات"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM stats WHERE user_id = ?', (user_id,))
        downloads = c.fetchone()[0]
        
        if downloads >= 1000:
            rank = '👑 إمبراطوري'
        elif downloads >= 500:
            rank = '💎 ذهبي'
        elif downloads >= 100:
            rank = '⭐ مميز'
        else:
            rank = '👤 عضو'
        
        c.execute('UPDATE users SET rank = ? WHERE user_id = ?', (rank, user_id))
        conn.commit()
        conn.close()
        return rank
    except:
        return '👤 عضو'

def is_user_banned(user_id):
    """التحقق إذا كان المستخدم محظوراً"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT user_id FROM banned_users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def ban_user(user_id, reason="لا يوجد سبب"):
    """حظر مستخدم"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT OR IGNORE INTO banned_users (user_id, ban_reason, ban_date) VALUES (?, ?, ?)',
              (user_id, reason, now))
    conn.commit()
    conn.close()

def unban_user(user_id):
    """إلغاء حظر مستخدم"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def check_rate_limit(user_id, max_requests=30):
    """التحقق من عدد الطلبات لتجنب السبام"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    
    c.execute('''INSERT OR IGNORE INTO daily_requests (user_id, request_date, request_count)
                 VALUES (?, ?, 0)''', (user_id, today))
    
    c.execute('''UPDATE daily_requests SET request_count = request_count + 1
                 WHERE user_id = ? AND request_date = ?''', (user_id, today))
    
    c.execute('SELECT request_count FROM daily_requests WHERE user_id = ? AND request_date = ?',
              (user_id, today))
    count = c.fetchone()[0]
    conn.commit()
    conn.close()
    
    return count <= max_requests

def get_remaining_requests(user_id):
    """الحصول على عدد الطلبات المتبقية"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute('SELECT request_count FROM daily_requests WHERE user_id = ? AND request_date = ?',
              (user_id, today))
    result = c.fetchone()
    conn.close()
    if result:
        return max(0, 30 - result[0])
    return 30

def get_users_count():
    """عدد المستخدمين الكلي"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    count = c.fetchone()[0]
    conn.close()
    return count

def get_active_users_today():
    """عدد المستخدمين النشطين اليوم"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute('SELECT COUNT(DISTINCT user_id) FROM stats WHERE download_date LIKE ?', (f"{today}%",))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_total_downloads():
    """إجمالي التحميلات"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM stats')
    count = c.fetchone()[0]
    conn.close()
    return count

def increment_download_stats(user_id, media_type, platform="unknown", file_size=0):
    """تسجيل عملية تحميل"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO stats (user_id, media_type, platform, download_date, file_size)
                 VALUES (?, ?, ?, ?, ?)''',
              (user_id, media_type, platform, now, file_size))
    conn.commit()
    conn.close()
    update_user_rank(user_id)

def save_channel(channel_id, channel_title="غير معروف"):
    """حفظ قناة إجبارية مع إشعار جميع المستخدمين"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT OR IGNORE INTO channels (channel_id, channel_title, added_date) VALUES (?, ?, ?)',
              (channel_id, channel_title, now))
    conn.commit()
    conn.close()
    
    # إشعار جميع المستخدمين بالقناة الجديدة
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT user_id FROM users')
        users = c.fetchall()
        conn.close()
        
        for user_id in users:
            try:
                bot.send_message(
                    user_id[0],
                    f"📢 **تم إضافة قناة جديدة للاشتراك الإجباري!**\n\n"
                    f"🔹 القناة: `{channel_title}`\n"
                    f"🔹 يرجى الاشتراك فيها لمواصلة استخدام البوت.\n\n"
                    f"💡 أرسل أي كلمة أو رابط وسيظهر لك طلب الاشتراك."
                )
                time.sleep(0.05)
            except:
                pass
    except:
        pass

def get_channels():
    """الحصول على قائمة القنوات الإجبارية"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT channel_id FROM channels')
    channels = [row[0] for row in c.fetchall()]
    conn.close()
    return channels

def clear_channels():
    """تصفير القنوات الإجبارية"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM channels')
    conn.commit()
    conn.close()

def get_user_rank(user_id):
    """الحصول على مستوى المستخدم"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT rank FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else '👤 عضو'

def save_feedback(user_id, feedback_text):
    """حفظ ملاحظة"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO feedback (user_id, feedback_text, feedback_date)
                 VALUES (?, ?, ?)''', (user_id, feedback_text, now))
    conn.commit()
    conn.close()

def get_feedback_list():
    """الحصول على قائمة الملاحظات"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT id, user_id, feedback_text, feedback_date, status 
                 FROM feedback WHERE status = 'جديد'
                 ORDER BY feedback_date DESC LIMIT 20''')
    results = c.fetchall()
    conn.close()
    return results

def get_daily_reward(user_id):
    """التحقق من المكافأة اليومية"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute('SELECT daily_reward_date FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0] == today:
        return False
    return True

def update_daily_reward(user_id):
    """تحديث تاريخ المكافأة اليومية"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute('UPDATE users SET daily_reward_date = ? WHERE user_id = ?', (today, user_id))
    conn.commit()
    conn.close()

# ============================================
# 💬 ذاكرة الجلسات المؤقتة
# ============================================
user_sessions = {}
user_queues = {}
user_processing = {}

# ============================================
# 📢 القنوات الإجبارية والتحقق المتقدم
# ============================================

def check_all_subscriptions(chat_id):
    """التحقق من اشتراك المستخدم في جميع القنوات الإجبارية - نسخة متطورة"""
    
    # المطور لا يخضع للاشتراك الإجباري
    if chat_id == OWNER_ID:
        return []
    
    # التحقق من الحظر
    if is_user_banned(chat_id):
        return ["banned"]
    
    # جلب قائمة القنوات الإجبارية
    channels = get_channels()
    
    # إذا لم توجد قنوات إجبارية، نسمح بالاستخدام
    if not channels:
        return []
    
    unsubscribed_channels = []
    
    for ch_id in channels:
        try:
            # محاولة جلب معلومات العضو من القناة
            member = bot.get_chat_member(ch_id, chat_id)
            
            # التحقق من حالة العضوية الفعلية
            if member.status not in ["member", "administrator", "creator"]:
                raise Exception("غير مشترك")
            
            # التحقق الإضافي: التأكد من أن المستخدم ليس بوتاً
            if member.user.is_bot:
                raise Exception("بوت")
                
        except Exception as e:
            # المستخدم غير مشترك أو حدث خطأ
            try:
                # محاولة الحصول على رابط دعوة للقناة
                invite_link = bot.export_chat_invite_link(ch_id)
                chat_info = bot.get_chat(ch_id)
                unsubscribed_channels.append({
                    "title": chat_info.title,
                    "url": invite_link,
                    "id": ch_id
                })
            except Exception as invite_error:
                # إذا لم نتمكن من جلب الرابط، نضيف القناة بدون رابط
                unsubscribed_channels.append({
                    "title": f"قناة {ch_id}",
                    "url": None,
                    "id": ch_id
                })
    
    return unsubscribed_channels

def send_dynamic_join_request(chat_id, unsub_list, message_id=None):
    """إرسال طلب الاشتراك بالقنوات مع أزرار ملونة - نسخة متطورة"""
    
    if unsub_list == ["banned"]:
        bot.send_message(chat_id, "⛔ **أنت محظور من استخدام البوت!**\nللتواصل مع المطور: @Mkdkdkd8484849")
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    
    # إضافة أزرار القنوات
    for ch in unsub_list:
        button_text = f"📢 اشترك في {ch['title']}"
        if ch.get('url'):
            markup.add(InlineKeyboardButton(button_text, url=ch['url'], style="primary"))
        else:
            # إذا لم يكن هناك رابط، نرسل معرف القناة
            markup.add(InlineKeyboardButton(button_text, callback_data=f"channel_info_{ch['id']}", style="primary"))
    
    # زر التحقق من الاشتراك - أخضر
    markup.add(InlineKeyboardButton(
        "✅ تحقق من الاشتراك",
        callback_data="check_sub",
        style="success"
    ))
    
    msg_text = (
        "⚠️ **عذراً! يجب الانضمام إلى القنوات أولاً.**\n\n"
        "📌 اشترك في القنوات التالية، ثم اضغط على زر التحقق 👇\n"
        "🔍 **البوت سيتأكد من عضويتك فعلياً.**\n\n"
        f"📊 عدد القنوات المطلوبة: `{len(unsub_list)}`"
    )
    
    if message_id:
        bot.send_message(chat_id, msg_text, parse_mode="Markdown", 
                        reply_markup=markup, reply_to_message_id=message_id)
    else:
        bot.send_message(chat_id, msg_text, parse_mode="Markdown", 
                        reply_markup=markup)

# ============================================
# 🔍 محرك البحث المتطور
# ============================================

def process_search_download(chat_id, query, media_type, reply_to_id=None):
    """معالجة البحث عن ميديا مع إخفاء المصدر تماماً"""
    
    try:
        # التحقق من الاشتراك الإجباري أولاً
        unsub_list = check_all_subscriptions(chat_id)
        if unsub_list:
            send_dynamic_join_request(chat_id, unsub_list)
            return
        
        # التحقق من حد الطلبات
        if not check_rate_limit(chat_id):
            remaining = get_remaining_requests(chat_id)
            bot.send_message(chat_id, f"⛔ **تم تجاوز حد الطلبات اليومي!**\nالطلبات المتبقية: {remaining}")
            return
        
        status_msg = bot.send_message(chat_id, "⏳ **جاري البحث والتجهيز...**", parse_mode="Markdown")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        
        encoded_query = quote(query)
        found = False
        
        if media_type == "image":
            sources = [
                f"https://www.flickr.com/search/?text={encoded_query}&sort=relevance",
                f"https://unsplash.com/s/photos/{encoded_query}",
                f"https://www.pexels.com/search/{encoded_query}/"
            ]
            
            for source_url in sources:
                try:
                    response = requests.get(source_url, headers=headers, timeout=15)
                    patterns = [
                        r'https://live\.staticflickr\.com/[0-9]+/[0-9]+_[a-zA-Z0-9]+_[b|c|z]\.jpg',
                        r'https://images\.unsplash\.com/[^"\']+',
                        r'https://images\.pexels\.com/[^"\']+'
                    ]
                    
                    for pattern in patterns:
                        matches = re.findall(pattern, response.text)
                        if matches:
                            clean_url = matches[0].split("?")[0]
                            if "flickr" in clean_url:
                                clean_url = clean_url.replace("_z.jpg", "_b.jpg")
                            
                            bot.send_photo(chat_id, clean_url, 
                                         caption="🖼️ **تم تجهيز الصورة بنجاح!**",
                                         reply_to_message_id=reply_to_id if reply_to_id else None)
                            bot.delete_message(chat_id, status_msg.message_id)
                            increment_download_stats(chat_id, "image")
                            found = True
                            break
                    if found:
                        break
                except:
                    continue
            
            if not found:
                bot.edit_message_text("❌ **لم نتمكن من العثور على صورة مناسبة.**", 
                                    chat_id, status_msg.message_id)
            return
        
        elif media_type in ["video", "audio"]:
            if not os.path.exists("downloads"):
                os.makedirs("downloads")
            
            ydl_opts = {
                "outtmpl": f"downloads/{chat_id}_search_%(id)s.%(ext)s",
                "quiet": True,
                "no_warnings": True,
                "max_filesize": 50 * 1024 * 1024,
                "geo_bypass": True,
                "http_headers": headers,
                "extract_flat": False,
                "ignoreerrors": True,
                "no_color": True
            }
            
            if media_type == "audio":
                ydl_opts["format"] = "bestaudio/best"
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192"
                }]
            else:
                ydl_opts["format"] = "best[ext=mp4]/best"
            
            search_engines = [
                f"ytsearch1:{query}",
                f"ytsearch1:{query} audio",
                f"ytsearch1:{query} video"
            ]
            
            for search_term in search_engines:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(search_term, download=True)
                        
                        if info and 'entries' in info and len(info['entries']) > 0:
                            video_info = info['entries'][0]
                            filename = ydl.prepare_filename(video_info)
                            
                            if media_type == "audio":
                                base, _ = os.path.splitext(filename)
                                if os.path.exists(base + ".mp3"):
                                    filename = base + ".mp3"
                            
                            if not os.path.exists(filename):
                                base, _ = os.path.splitext(filename)
                                for ext in [".mp4", ".mp3", ".mkv", ".webm", ".m4a"]:
                                    if os.path.exists(base + ext):
                                        filename = base + ext
                                        break
                            
                            if os.path.exists(filename):
                                file_size = os.path.getsize(filename)
                                with open(filename, "rb") as file_to_send:
                                    if media_type == "audio":
                                        bot.send_audio(chat_id, file_to_send,
                                                     caption="🎵 **تم تجهيز الملف الصوتي بنجاح!**",
                                                     reply_to_message_id=reply_to_id if reply_to_id else None,
                                                     timeout=120)
                                    else:
                                        bot.send_video(chat_id, file_to_send,
                                                     caption="🎬 **تم تجهيز الفيديو بنجاح!**",
                                                     reply_to_message_id=reply_to_id if reply_to_id else None,
                                                     timeout=120,
                                                     supports_streaming=True)
                                
                                os.remove(filename)
                                bot.delete_message(chat_id, status_msg.message_id)
                                increment_download_stats(chat_id, media_type, "search", file_size)
                                found = True
                                break
                except Exception as e:
                    print(f"Search engine error: {e}")
                    continue
            
            if not found:
                bot.edit_message_text("❌ **لم نتمكن من العثور على محتوى مناسب.**",
                                    chat_id, status_msg.message_id)
    
    except Exception as e:
        print(f"Search error: {e}")
        try:
            bot.edit_message_text("❌ **حدث خطأ أثناء البحث، يرجى المحاولة مرة أخرى.**",
                                chat_id, status_msg.message_id)
        except:
            bot.send_message(chat_id, "❌ **حدث خطأ أثناء البحث، يرجى المحاولة مرة أخرى.**")

# ============================================
# 🔗 تنزيل الروابط المتطور
# ============================================

def clean_and_fix_url(url):
    """تنظيف الرابط وإصلاحه"""
    if "instagram.com" in url and "?" in url:
        url = url.split("?")[0]
    if "x.com" in url:
        url = url.replace("x.com", "twitter.com")
    for param in ["?utm_", "&utm_", "?fbclid", "&fbclid"]:
        if param in url:
            url = url.split(param)[0]
    return url

def download_media_processor(url, chat_id, reply_to_id, media_type, quality=None, platform="unknown"):
    """معالجة تحميل الوسائط"""
    
    try:
        # التحقق من الاشتراك الإجباري أولاً
        unsub_list = check_all_subscriptions(chat_id)
        if unsub_list:
            send_dynamic_join_request(chat_id, unsub_list)
            return False
        
        # التحقق من حد الطلبات
        if not check_rate_limit(chat_id):
            remaining = get_remaining_requests(chat_id)
            bot.send_message(chat_id, f"⛔ **تم تجاوز حد الطلبات اليومي!**\nالطلبات المتبقية: {remaining}")
            return False
        
        status_msg = bot.send_message(chat_id, "⏳ **جاري التحميل والتجهيز...**", parse_mode="Markdown")
        
        if not os.path.exists("downloads"):
            os.makedirs("downloads")
        
        ydl_opts = {
            "outtmpl": f"downloads/{chat_id}_%(id)s.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            },
            "socket_timeout": 30,
            "retries": 10,
            "fragment_retries": 10,
            "ignoreerrors": True,
            "no_color": True,
            "extract_flat": False
        }
        
        if media_type == "audio":
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192"
            }]
        else:
            if quality == "1080p":
                ydl_opts["format"] = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"
            elif quality == "720p":
                ydl_opts["format"] = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
            elif quality == "480p":
                ydl_opts["format"] = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"
            elif quality == "360p":
                ydl_opts["format"] = "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best"
            else:
                ydl_opts["format"] = "best[ext=mp4]/best"
        
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    url = clean_and_fix_url(url)
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    
                    if media_type == "audio":
                        base, _ = os.path.splitext(filename)
                        if os.path.exists(base + ".mp3"):
                            filename = base + ".mp3"
                    
                    if not os.path.exists(filename):
                        base, _ = os.path.splitext(filename)
                        for ext in [".mp4", ".mp3", ".mkv", ".webm", ".m4a", ".mp4a"]:
                            if os.path.exists(base + ext):
                                filename = base + ext
                                break
                    
                    if os.path.exists(filename):
                        file_size = os.path.getsize(filename)
                        with open(filename, "rb") as file_to_send:
                            if media_type == "audio":
                                bot.send_audio(chat_id, file_to_send,
                                             caption="🎵 **تم تحميل الصوت بنجاح** ✨",
                                             reply_to_message_id=reply_to_id,
                                             timeout=180)
                            else:
                                quality_text = f"بجودة {quality}" if quality else "تلقائية"
                                bot.send_video(chat_id, file_to_send,
                                             caption=f"🎬 **تم تحميل الفيديو {quality_text}** ✨",
                                             reply_to_message_id=reply_to_id,
                                             timeout=180,
                                             supports_streaming=True)
                        
                        os.remove(filename)
                        bot.delete_message(chat_id, status_msg.message_id)
                        increment_download_stats(chat_id, media_type, platform, file_size)
                        return True
                    else:
                        raise Exception("الملف غير موجود")
            
            except Exception as e:
                print(f"Download attempt {attempt + 1} failed: {e}")
                if attempt == max_attempts - 1:
                    bot.edit_message_text("❌ **فشل التحميل، تأكد من صلاحية الرابط.**",
                                        chat_id, status_msg.message_id)
                    return False
                else:
                    time.sleep(2)
                    continue
        
        return False
    
    except Exception as e:
        print(f"Download error: {e}")
        bot.send_message(chat_id, "❌ **حدث خطأ أثناء التحميل، حاول مرة أخرى.**")
        return False

# ============================================
# 🎨 واجهات الأزرار المتطورة
# ============================================

def show_word_options(message, text_query):
    """عرض أزرار اختيار نوع الميديا"""
    markup = InlineKeyboardMarkup(row_width=2)
    session_id = str(message.message_id)
    user_sessions[f"word_{message.chat.id}_{session_id}"] = text_query
    
    markup.add(
        InlineKeyboardButton("🎵 صوت", callback_data=f"wtype_audio_{session_id}", style="primary"),
        InlineKeyboardButton("🎬 فيديو", callback_data=f"wtype_video_{session_id}", style="success"),
        InlineKeyboardButton("🖼️ صورة", callback_data=f"wtype_image_{session_id}", style="danger")
    )
    
    bot.reply_to(message, "📥 **اختر نوع المحتوى من الأزرار التالية:**", reply_markup=markup)

def show_link_platforms(message, url):
    """عرض أزرار المنصات السبعة"""
    markup = InlineKeyboardMarkup(row_width=2)
    session_id = str(message.message_id)
    user_sessions[f"link_{message.chat.id}_{session_id}"] = url
    
    markup.add(
        InlineKeyboardButton("🔵 فيسبوك", callback_data=f"plat_fb_{session_id}", style="primary"),
        InlineKeyboardButton("⚫ تيك توك", callback_data=f"plat_tt_{session_id}", style="primary")
    )
    markup.add(
        InlineKeyboardButton("🐦 تويتر", callback_data=f"plat_tw_{session_id}", style="primary"),
        InlineKeyboardButton("💬 ماسنجر", callback_data=f"plat_ms_{session_id}", style="primary")
    )
    markup.add(
        InlineKeyboardButton("🟣 انستغرام", callback_data=f"plat_ig_{session_id}", style="primary"),
        InlineKeyboardButton("🔴 يوتيوب", callback_data=f"plat_yt_{session_id}", style="danger")
    )
    markup.add(
        InlineKeyboardButton("📌 Pinterest", callback_data=f"plat_pin_{session_id}", style="primary")
    )
    
    bot.reply_to(message, "📱 **اختر المنصة المطلوبة للتحميل:**", reply_markup=markup)

def show_service_type_options(chat_id, session_id, platform_name):
    """سؤال المستخدم: فيديو أم صوت"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎬 فيديو", callback_data=f"srv_video_{platform_name}_{session_id}", style="success"),
        InlineKeyboardButton("🎵 صوت", callback_data=f"srv_audio_{platform_name}_{session_id}", style="primary")
    )
    bot.send_message(chat_id, "🎥 **اختر نوع التحميل:**", reply_markup=markup)

def show_quality_options(chat_id, session_id, platform_name):
    """عرض جودات الفيديو"""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("1080p 🔥", callback_data=f"qual_1080p_{platform_name}_{session_id}", style="danger"),
        InlineKeyboardButton("720p ✨", callback_data=f"qual_720p_{platform_name}_{session_id}", style="success")
    )
    markup.add(
        InlineKeyboardButton("480p ⚡", callback_data=f"qual_480p_{platform_name}_{session_id}", style="primary"),
        InlineKeyboardButton("360p 📉", callback_data=f"qual_360p_{platform_name}_{session_id}", style="primary")
    )
    bot.send_message(chat_id, "⚙️ **اختر الجودة المناسبة:**", reply_markup=markup)

# ============================================
# 🎛️ معالج الأحداث والـ Callbacks
# ============================================

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    if is_user_banned(chat_id):
        bot.answer_callback_query(call.id, "⛔ أنت محظور!", show_alert=True)
        return
    
    # معلومات القناة
    if call.data.startswith("channel_info_"):
        channel_id = call.data.replace("channel_info_", "")
        bot.answer_callback_query(call.id, f"🔍 معرف القناة: {channel_id}\nابحث عن القناة يدوياً واشترك فيها.", show_alert=True)
        return
    
    # معالجة أزرار الكلمات
    if call.data.startswith("wtype_"):
        parts = call.data.split("_")
        media_type = parts[1]
        session_id = parts[2]
        session_key = f"word_{chat_id}_{session_id}"
        
        if session_key in user_sessions:
            query_text = user_sessions[session_key]
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
            process_search_download(chat_id, query_text, media_type, int(session_id))
            del user_sessions[session_key]
        else:
            bot.answer_callback_query(call.id, "❌ انتهت صلاحية الجلسة.", show_alert=True)
        return
    
    # معالجة اختيار المنصة
    if call.data.startswith("plat_"):
        parts = call.data.split("_")
        platform_name = parts[1]
        session_id = parts[2]
        
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass
        show_service_type_options(chat_id, session_id, platform_name)
        bot.answer_callback_query(call.id, "✅ تم اختيار المنصة")
        return
    
    # معالجة اختيار نوع الخدمة
    if call.data.startswith("srv_"):
        parts = call.data.split("_")
        media_type = parts[1]
        platform_name = parts[2]
        session_id = parts[3]
        
        session_key = f"link_{chat_id}_{session_id}"
        if session_key not in user_sessions:
            bot.answer_callback_query(call.id, "❌ حدث خطأ في الجلسة.", show_alert=True)
            return
        
        url = user_sessions[session_key]
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass
        
        platform_names = {
            "fb": "Facebook", "tt": "TikTok", "tw": "Twitter",
            "ms": "Messenger", "ig": "Instagram", "yt": "YouTube", "pin": "Pinterest"
        }
        platform_full = platform_names.get(platform_name, "unknown")
        
        if media_type == "audio":
            download_media_processor(url, chat_id, int(session_id), "audio", platform=platform_full)
            del user_sessions[session_key]
        else:
            show_quality_options(chat_id, session_id, platform_name)
        return
    
    # معالجة جودات الفيديو
    if call.data.startswith("qual_"):
        parts = call.data.split("_")
        quality_val = parts[1]
        platform_name = parts[2]
        session_id = parts[3]
        
        session_key = f"link_{chat_id}_{session_id}"
        if session_key in user_sessions:
            url = user_sessions[session_key]
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
            
            platform_names = {
                "fb": "Facebook", "tt": "TikTok", "tw": "Twitter",
                "ms": "Messenger", "ig": "Instagram", "yt": "YouTube", "pin": "Pinterest"
            }
            platform_full = platform_names.get(platform_name, "unknown")
            
            download_media_processor(url, chat_id, int(session_id), "video", quality=quality_val, platform=platform_full)
            del user_sessions[session_key]
        else:
            bot.answer_callback_query(call.id, "❌ انتهت الجلسة.")
        return
    
    # ✅ التحقق من الاشتراك - نسخة متطورة
    if call.data == "check_sub":
        # إعلام المستخدم بالتحقق
        bot.answer_callback_query(call.id, "🔍 جاري التحقق من اشتراكك...", show_alert=False)
        
        # التحقق الفعلي من الاشتراك
        unsub_list = check_all_subscriptions(chat_id)
        
        if not unsub_list:
            # ✅ تم الاشتراك بنجاح
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
            bot.send_message(
                chat_id, 
                "🎉 **تم التفعيل بنجاح! أهلاً بك في البوت.**\n\n"
                "✅ أنت الآن مشترك في جميع القنوات المطلوبة.\n\n"
                "💡 أرسل كلمة للبحث أو رابط للتحميل."
            )
        else:
            # ❌ لا زال غير مشترك في بعض القنوات
            markup = InlineKeyboardMarkup(row_width=2)
            
            for ch in unsub_list:
                button_text = f"📢 اشترك في {ch['title']}"
                if ch.get('url'):
                    markup.add(InlineKeyboardButton(button_text, url=ch['url'], style="primary"))
                else:
                    markup.add(InlineKeyboardButton(button_text, callback_data=f"channel_info_{ch['id']}", style="primary"))
            
            markup.add(InlineKeyboardButton(
                "✅ تحقق من الاشتراك",
                callback_data="check_sub",
                style="success"
            ))
            
            msg_text = (
                "⚠️ **لا زلت غير مشترك في جميع القنوات!**\n\n"
                "📌 اشترك في القنوات التالية، ثم اضغط على زر التحقق 👇\n"
                f"📊 عدد القنوات المتبقية: `{len(unsub_list)}`"
            )
            
            try:
                bot.edit_message_text(msg_text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
            except:
                bot.send_message(chat_id, msg_text, parse_mode="Markdown", reply_markup=markup)
            
            bot.answer_callback_query(call.id, f"❌ لم تشترك في {len(unsub_list)} قنوات بعد!", show_alert=True)
        return
    
    # لوحة التحكم
    if call.data == "broadcast_msg":
        if chat_id != OWNER_ID:
            bot.answer_callback_query(call.id, "⛔ غير مصرح", show_alert=True)
            return
        msg = bot.send_message(OWNER_ID, "✍️ **أرسل رسالة الإذاعة:**\nلإلغاء الأمر أرسل `/cancel`")
        bot.register_next_step_handler(msg, start_broadcasting)
        bot.answer_callback_query(call.id, "✅ جاهز للإذاعة")
        return
    
    if call.data == "clear_ch":
        if chat_id != OWNER_ID:
            bot.answer_callback_query(call.id, "⛔ غير مصرح", show_alert=True)
            return
        clear_channels()
        bot.answer_callback_query(call.id, "✅ تم تصفير القنوات!", show_alert=True)
        admin_panel(call.message)
        return
    
    if call.data == "stats_advanced":
        if chat_id != OWNER_ID:
            bot.answer_callback_query(call.id, "⛔ غير مصرح", show_alert=True)
            return
        
        total_users = get_users_count()
        active_today = get_active_users_today()
        total_downloads = get_total_downloads()
        channels_count = len(get_channels())
        
        stats_text = (
            "📊 **الإحصائيات المتقدمة**\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"👥 إجمالي المستخدمين: `{total_users}`\n"
            f"🟢 النشاط اليومي: `{active_today}`\n"
            f"📥 إجمالي التحميلات: `{total_downloads}`\n"
            f"📈 متوسط التحميل: `{round(total_downloads/max(1,total_users), 1)}`\n"
            f"📢 القنوات الإجبارية: `{channels_count}`"
        )
        bot.edit_message_text(stats_text, chat_id, message_id, parse_mode="Markdown")
        return
    
    if call.data == "feedback_list":
        if chat_id != OWNER_ID:
            bot.answer_callback_query(call.id, "⛔ غير مصرح", show_alert=True)
            return
        
        feedbacks = get_feedback_list()
        if not feedbacks:
            bot.send_message(chat_id, "📭 **لا توجد ملاحظات جديدة.**")
            return
        
        text = "📋 **قائمة الملاحظات الجديدة:**\n━━━━━━━━━━━━━━━━━━━\n"
        for fb in feedbacks[:10]:
            text += f"🆔 معرف: `{fb[0]}` | مستخدم: `{fb[1]}`\n📝 {fb[2][:50]}...\n📅 {fb[3]}\n━━━━━━━━━━━━━━━━━━━\n"
        
        bot.send_message(chat_id, text, parse_mode="Markdown")
        return
    
    # معلومات البوت
    if call.data == "about_bot":
        about_text = (
            "⚡ **البوت الإمبراطوري المتطور** ⚡\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📥 **البحث الذكي:**\n"
            "• أرسل أي كلمة ← تظهر خيارات (صوت، فيديو، صورة)\n\n"
            "🔗 **تحميل الروابط:**\n"
            "• يدعم 7 منصات مختلفة\n"
            "• 4 جودات للفيديو (1080p - 720p - 480p - 360p)\n\n"
            "📢 **الاشتراك الإجباري:**\n"
            "• يجب الاشتراك في القنوات المطلوبة\n"
            "• زر التحقق يتأكد من عضويتك\n\n"
            "🎁 **المكافآت اليومية:**\n"
            "• استخدم `/daily` للحصول على مكافأة\n\n"
            "📝 **الملاحظات:**\n"
            "• أرسل `/feedback` لاقتراحك\n\n"
            "👑 **المستويات:**\n"
            f"• مستواك الحالي: `{get_user_rank(chat_id)}`\n\n"
            f"👨‍💻 **المطور:** @{OWNER_USERNAME}"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬅️ رجوع", callback_data="back_to_main", style="primary"))
        bot.edit_message_text(about_text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
        return
    
    # الرجوع للقائمة الرئيسية
    if call.data == "back_to_main":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("👨‍💻 المطور", url=f"https://t.me/{OWNER_USERNAME}", style="primary"),
            InlineKeyboardButton("ℹ️ الميزات", callback_data="about_bot", style="success")
        )
        if chat_id == OWNER_ID:
            markup.add(
                InlineKeyboardButton("📊 إحصائيات", callback_data="stats_advanced", style="primary"),
                InlineKeyboardButton("📋 الملاحظات", callback_data="feedback_list", style="primary")
            )
        
        welcome = (
            "👑 **مرحباً بك في البوت الإمبراطوري المتطور!**\n\n"
            "💡 **طريقة الاستخدام:**\n"
            "✍️ أرسل أي **كلمة** للبحث عن محتوى\n"
            "🔗 أرسل أي **رابط** للتحميل من المنصات\n\n"
            "📢 **الاشتراك الإجباري:**\n"
            "• إذا طلب منك الاشتراك، اشترك ثم اضغط تحقق\n\n"
            "🎁 استخدم `/daily` للمكافأة اليومية\n"
            "📝 استخدم `/feedback` لإرسال اقتراح\n\n"
            f"👑 مستواك: `{get_user_rank(chat_id)}`"
        )
        bot.edit_message_text(welcome, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
        return

# ============================================
# 📨 الأوامر الأساسية
# ============================================

@bot.message_handler(commands=["start"])
def send_welcome(message):
    user = message.from_user
    save_user(user.id, user.username, user.first_name, user.last_name)
    
    if is_user_banned(user.id):
        bot.send_message(user.id, "⛔ **أنت محظور من استخدام البوت!**")
        return
    
    # التحقق من الاشتراك الإجباري
    unsub_list = check_all_subscriptions(user.id)
    if unsub_list:
        send_dynamic_join_request(user.id, unsub_list)
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👨‍💻 المطور", url=f"https://t.me/{OWNER_USERNAME}", style="primary"),
        InlineKeyboardButton("ℹ️ الميزات", callback_data="about_bot", style="success")
    )
    if user.id == OWNER_ID:
        markup.add(
            InlineKeyboardButton("📊 إحصائيات", callback_data="stats_advanced", style="primary"),
            InlineKeyboardButton("📋 الملاحظات", callback_data="feedback_list", style="primary")
        )
    
    welcome_text = (
        f"👑 **مرحباً بك {user.first_name} في البوت الإمبراطوري!**\n\n"
        "✨ **المميزات:**\n"
        "• 🔍 البحث الذكي (صور - فيديوهات - صوتيات)\n"
        "• 📥 تحميل من 7 منصات مختلفة\n"
        "• 🎯 4 جودات للفيديو\n"
        "• 📢 الاشتراك الإجباري مع تحقق فوري\n"
        "• 🎁 مكافآت يومية\n"
        "• 📝 نظام الملاحظات\n"
        "• 👑 مستويات حسب التحميلات\n\n"
        f"👑 مستواك: `{get_user_rank(user.id)}`"
    )
    
    bot.send_message(user.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=["daily"])
def daily_reward(message):
    """المكافأة اليومية"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if is_user_banned(user_id):
        return
    
    if get_daily_reward(user_id):
        update_daily_reward(user_id)
        reward_text = (
            "🎁 **تهانينا! حصلت على مكافأتك اليومية!**\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "✅ تم إضافة **5 طلبات إضافية** اليوم.\n"
            "🔹 أصبح حدك اليومي: 35 طلب.\n\n"
            "💡 عد غداً للحصول على مكافأة جديدة!"
        )
        bot.reply_to(message, reward_text, parse_mode="Markdown")
    else:
        remaining = get_remaining_requests(user_id)
        bot.reply_to(message, f"⏳ **لقد حصلت على مكافأتك اليومية بالفعل!**\n📊 الطلبات المتبقية: `{remaining}`")

@bot.message_handler(commands=["feedback"])
def feedback_command(message):
    """إرسال ملاحظة"""
    msg = bot.reply_to(message, "✍️ **أرسل ملاحظتك الآن:**\nلإلغاء الأمر أرسل `/cancel`")
    bot.register_next_step_handler(msg, process_feedback)

def process_feedback(message):
    if message.text == "/cancel":
        bot.reply_to(message, "❌ تم إلغاء الإرسال.")
        return
    
    save_feedback(message.from_user.id, message.text)
    bot.reply_to(message, "✅ **تم استلام ملاحظتك بنجاح!**\nشكراً لك. 🙏")

@bot.message_handler(commands=["rank"])
def rank_command(message):
    """عرض مستوى المستخدم"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    rank = get_user_rank(user_id)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM stats WHERE user_id = ?', (user_id,))
    downloads = c.fetchone()[0]
    conn.close()
    
    if "إمبراطوري" in rank:
        next_rank = "👑 أنت في أعلى مستوى!"
        remaining = 0
    elif "ذهبي" in rank:
        next_rank = "👑 إمبراطوري"
        remaining = 1000 - downloads
    elif "مميز" in rank:
        next_rank = "💎 ذهبي"
        remaining = 500 - downloads
    else:
        next_rank = "⭐ مميز"
        remaining = 100 - downloads
    
    rank_text = (
        "👑 **مستواك في البوت**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📌 المستوى الحالي: `{rank}`\n"
        f"📥 عدد التحميلات: `{downloads}`\n"
        f"🎯 المستوى التالي: `{next_rank}`\n"
        f"📊 التحميلات المتبقية: `{max(0, remaining)}`"
    )
    bot.reply_to(message, rank_text, parse_mode="Markdown")

@bot.message_handler(commands=["admin"])
def admin_panel(message):
    if message.chat.id != OWNER_ID:
        return
    
    total_users = get_users_count()
    active_today = get_active_users_today()
    total_downloads = get_total_downloads()
    channels_count = len(get_channels())
    remaining = get_remaining_requests(message.chat.id)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📢 إذاعة جماعية", callback_data="broadcast_msg", style="success"),
        InlineKeyboardButton("🗑️ تعطيل القنوات", callback_data="clear_ch", style="danger")
    )
    markup.add(
        InlineKeyboardButton("📊 إحصائيات", callback_data="stats_advanced", style="primary"),
        InlineKeyboardButton("📋 الملاحظات", callback_data="feedback_list", style="primary")
    )
    
    admin_text = (
        "👑 **لوحة التحكم الإمبراطورية**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"👥 المستخدمين: `{total_users}`\n"
        f"🟢 النشاط اليومي: `{active_today}`\n"
        f"📥 التحميلات: `{total_downloads}`\n"
        f"📢 القنوات: `{channels_count}`\n"
        f"📊 طلباتك المتبقية: `{remaining}`\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔧 **أدوات التحكم:**"
    )
    
    bot.reply_to(message, admin_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=["ban"])
def ban_command(message):
    if message.chat.id != OWNER_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ استخدم: `/ban معرف_المستخدم`")
            return
        
        user_id = int(parts[1])
        reason = " ".join(parts[2:]) if len(parts) > 2 else "لا يوجد سبب"
        
        ban_user(user_id, reason)
        bot.reply_to(message, f"✅ تم حظر المستخدم `{user_id}`")
        try:
            bot.send_message(user_id, f"⛔ **تم حظرك من البوت!**\nالسبب: {reason}")
        except:
            pass
    except:
        bot.reply_to(message, "❌ معرف المستخدم غير صالح.")

@bot.message_handler(commands=["unban"])
def unban_command(message):
    if message.chat.id != OWNER_ID:
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ استخدم: `/unban معرف_المستخدم`")
            return
        
        user_id = int(parts[1])
        unban_user(user_id)
        bot.reply_to(message, f"✅ تم إلغاء حظر المستخدم `{user_id}`")
    except:
        bot.reply_to(message, "❌ معرف المستخدم غير صالح.")

@bot.message_handler(commands=["stats"])
def stats_command(message):
    if message.chat.id != OWNER_ID:
        return
    
    total_users = get_users_count()
    active_today = get_active_users_today()
    total_downloads = get_total_downloads()
    
    stats_text = (
        "📊 **إحصائيات البوت**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"👥 إجمالي المستخدمين: `{total_users}`\n"
        f"🟢 النشاط اليومي: `{active_today}`\n"
        f"📥 إجمالي التحميلات: `{total_downloads}`\n"
        f"📈 متوسط التحميل: `{round(total_downloads/max(1,total_users), 1)}`"
    )
    bot.reply_to(message, stats_text, parse_mode="Markdown")

@bot.message_handler(commands=["cancel"])
def cancel_command(message):
    if message.chat.id != OWNER_ID:
        return
    bot.reply_to(message, "❌ تم إلغاء العملية.")

def start_broadcasting(message):
    if message.text == "/cancel":
        bot.reply_to(message, "❌ تم إلغاء الإذاعة.")
        return
    
    users = []
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT user_id FROM users')
    users = [row[0] for row in c.fetchall()]
    conn.close()
    
    if not users:
        bot.reply_to(message, "❌ لا يوجد مستخدمين.")
        return
    
    progress = bot.send_message(OWNER_ID, f"⏳ جاري النشر لـ `{len(users)}` مستخدم...", parse_mode="Markdown")
    success = 0
    failed = 0
    
    for u_id in users:
        try:
            bot.copy_message(int(u_id), message.chat.id, message.message_id)
            success += 1
            time.sleep(0.05)
        except:
            failed += 1
    
    result_text = (
        f"✅ **تم النشر بنجاح!**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📤 تم الإرسال لـ: `{success}` مستخدم\n"
        f"❌ فشل الإرسال لـ: `{failed}` مستخدم"
    )
    bot.edit_message_text(result_text, OWNER_ID, progress.message_id, parse_mode="Markdown")

@bot.my_chat_member_handler()
def detect_channel_add(update):
    """اكتشاف إضافة البوت كادمن في قناة - مع تفعيل الاشتراك الإجباري تلقائياً"""
    if update.chat.type == "channel" and update.new_chat_member.status in ["administrator", "creator"]:
        try:
            # التحقق من أن المطور موجود في القناة
            owner_status = bot.get_chat_member(update.chat.id, OWNER_ID).status
            if owner_status in ["creator", "administrator"]:
                chat_info = bot.get_chat(update.chat.id)
                save_channel(update.chat.id, chat_info.title)
                
                # إشعار للمطور
                bot.send_message(
                    OWNER_ID,
                    f"✅ **تم تفعيل الاشتراك الإجباري لقناة جديدة!**\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"📢 اسم القناة: `{chat_info.title}`\n"
                    f"🆔 معرف القناة: `{update.chat.id}`\n"
                    f"🔒 سيتم تفعيل الاشتراك الإجباري فوراً لجميع المستخدمين."
                )
                
                # إشعار للمستخدمين النشطين
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute('SELECT user_id FROM users WHERE last_active > datetime("now", "-1 day")')
                    active_users = c.fetchall()
                    conn.close()
                    
                    for user_id in active_users:
                        try:
                            bot.send_message(
                                user_id[0],
                                f"📢 **تم إضافة قناة جديدة للاشتراك الإجباري!**\n"
                                f"📌 يرجى الاشتراك في `{chat_info.title}` لمواصلة استخدام البوت.\n"
                                f"💡 أرسل أي كلمة أو رابط وسيظهر لك طلب الاشتراك."
                            )
                            time.sleep(0.1)
                        except:
                            pass
                except:
                    pass
        except Exception as e:
            print(f"Error detecting channel add: {e}")

# ============================================
# 🧠 المعالج المركزي للرسائل
# ============================================

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user = message.from_user
    chat_id = message.chat.id
    
    if message.chat.type in ["group", "supergroup", "channel"]:
        return
    
    save_user(user.id, user.username, user.first_name, user.last_name)
    
    if is_user_banned(user.id):
        bot.send_message(chat_id, "⛔ **أنت محظور من استخدام البوت!**")
        return
    
    if not message.text:
        return
    
    text = message.text.strip()
    
    # ✅ التحقق من الاشتراك الإجباري أولاً وقبل كل شيء
    unsub_list = check_all_subscriptions(chat_id)
    if unsub_list:
        send_dynamic_join_request(chat_id, unsub_list, message.message_id)
        return
    
    if text.lower().startswith("vless://"):
        try:
            parsed = urlparse(text)
            result = (
                "🔑 **مفتاح VLESS المستخرج**\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 UUID: `{parsed.username}`\n"
                f"🌐 Host: `{parsed.hostname}`\n"
                f"🔌 Port: `{parsed.port}`"
            )
            bot.reply_to(message, result, parse_mode="Markdown")
        except:
            bot.reply_to(message, "❌ بنية رابط vless غير مدعومة.")
        return
    
    if text.startswith("http://") or text.startswith("https://"):
        cleaned_url = clean_and_fix_url(text)
        show_link_platforms(message, cleaned_url)
    else:
        show_word_options(message, text)

# ============================================
# 🚀 تشغيل البوت
# ============================================

def clean_temp_files():
    while True:
        try:
            if os.path.exists("downloads"):
                for file in os.listdir("downloads"):
                    file_path = os.path.join("downloads", file)
                    try:
                        if os.path.isfile(file_path):
                            file_age = time.time() - os.path.getctime(file_path)
                            if file_age > 3600:
                                os.remove(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path, ignore_errors=True)
                    except:
                        pass
        except:
            pass
        time.sleep(3600)

cleanup_thread = threading.Thread(target=clean_temp_files, daemon=True)
cleanup_thread.start()

print("=" * 60)
print("👑 تم إطلاق البوت الإمبراطوري المتطور بنجاح 100%!")
print("📊 نظام التشغيل: SQLite Database")
print("🎨 دعم الأزرار الملونة: style (primary, success, danger)")
print("🛡️ نظام الحماية: Rate Limiting (30 طلب/يوم)")
print("📢 نظام الاشتراك الإجباري: متطور مع تحقق فوري")
print("🎁 نظام المكافآت اليومية: Daily Rewards")
print("📝 نظام الملاحظات: Feedback System")
print("👑 نظام المستويات: Ranks حسب التحميلات")
print("🔒 الخصوصية: جميع المصادر مخفية تماماً")
print("=" * 60)

bot.infinity_polling(allowed_updates=["message", "callback_query", "my_chat_member", "channel_post"])
