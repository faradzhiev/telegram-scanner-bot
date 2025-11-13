import os
import logging
import requests
import time
import json
from datetime import datetime, timedelta
from threading import Thread
import sqlite3
from flask import Flask, request
import hashlib

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8354006848:AAEQZbIAGty2IN0a9FOrIdIiwgtEoyrY7FE')
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

class TelegramScannerBot:
    def __init__(self):
        self.active_chats = set()
        self.sent_signals = {}  # Для защиты от дублирования
        self.settings = {
            'oi_min_change': 5.0,      # Минимальное изменение OI %
            'oi_min_volume': 0.5,      # Минимальный объем в млн $
            'pump_min_change': 1.5,    # Минимальное изменение пампов %
            'cooldown_minutes': 10,    # Кду между одинаковыми сигналами
        }
        self.init_database()
        self.load_active_chats()
        self.start_monitoring()
        logging.info("✅ Бот запущен с улучшениями!")

    def init_database(self):
        conn = sqlite3.connect('/tmp/signals.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_chats (
                chat_id TEXT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                registered_at DATETIME
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                chat_id TEXT PRIMARY KEY,
                oi_min_change REAL DEFAULT 5.0,
                oi_min_volume REAL DEFAULT 0.5,
                pump_min_change REAL DEFAULT 1.5,
                cooldown_minutes INTEGER DEFAULT 10
            )
        ''')
        conn.commit()
        conn.close()

    def load_active_chats(self):
        try:
            conn = sqlite3.connect('/tmp/signals.db')
            cursor = conn.cursor()
            cursor.execute('SELECT chat_id FROM user_chats')
            for (chat_id,) in cursor.fetchall():
                self.active_chats.add(chat_id)
            conn.close()
        except:
            pass

    def get_user_settings(self, chat_id):
        try:
            conn = sqlite3.connect('/tmp/signals.db')
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_settings WHERE chat_id = ?', (chat_id,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return {
                    'oi_min_change': result[1],
                    'oi_min_volume': result[2],
                    'pump_min_change': result[3],
                    'cooldown_minutes': result[4]
                }
        except:
            pass
        return self.settings.copy()

    def save_user_settings(self, chat_id, settings):
        try:
            conn = sqlite3.connect('/tmp/signals.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO user_settings 
                (chat_id, oi_min_change, oi_min_volume, pump_min_change, cooldown_minutes)
                VALUES (?, ?, ?, ?, ?)
            ''', (chat_id, settings['oi_min_change'], settings['oi_min_volume'], 
                  settings['pump_min_change'], settings['cooldown_minutes']))
            conn.commit()
            conn.close()
        except:
            pass

    def save_user_chat(self, chat_id, username, first_name):
        conn = sqlite3.connect('/tmp/signals.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_chats 
            (chat_id, username, first_name, registered_at)
            VALUES (?, ?, ?, datetime('now'))
        ''', (chat_id, username, first_name))
        
        # Создаем настройки по умолчанию для нового пользователя
        cursor.execute('''
            INSERT OR IGNORE INTO user_settings 
            (chat_id, oi_min_change, oi_min_volume, pump_min_change, cooldown_minutes)
            VALUES (?, ?, ?, ?, ?)
        ''', (chat_id, 5.0, 0.5, 1.5, 10))
        
        conn.commit()
        conn.close()
        self.active_chats.add(chat_id)

    def send_message(self, chat_id, text):
        url = f"{BASE_URL}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False
        }
        try:
            requests.post(url, data=data, timeout=10)
        except:
            pass

    def broadcast_signal(self, message, signal_hash):
        """Рассылка сигнала с проверкой дублирования"""
        if self.is_duplicate_signal(signal_hash):
            logging.info(f"⏭️ Пропущен дубликат сигнала: {signal_hash}")
            return False
            
        for chat_id in self.active_chats:
            user_settings = self.get_user_settings(chat_id)
            self.send_message(chat_id, message)
            time.sleep(0.1)
        
        self.record_signal(signal_hash)
        return True

    def is_duplicate_signal(self, signal_hash):
        """Проверка на дублирование сигнала"""
        now = datetime.now()
        if signal_hash in self.sent_signals:
            last_sent = self.sent_signals[signal_hash]
            cooldown = timedelta(minutes=self.settings['cooldown_minutes'])
            if now - last_sent < cooldown:
                return True
        return False

    def record_signal(self, signal_hash):
        """Запись отправленного сигнала"""
        self.sent_signals[signal_hash] = datetime.now()
        
        # Очистка старых записей (старше 24 часов)
        cutoff_time = datetime.now() - timedelta(hours=24)
        self.sent_signals = {k: v for k, v in self.sent_signals.items() if v > cutoff_time}

    def create_signal_hash(self, signal):
        """Создание хеша для идентификации сигнала"""
        signal_str = f"{signal['type']}_{signal['symbol']}_{signal['exchange']}_{signal.get('change', 0)}_{signal.get('amount', 0)}"
        return hashlib.md5(signal_str.encode()).hexdigest()

    def scan_demo_signals(self):
        """Демо-сигналы только OI и Pump"""
        signals = []
        
        # OI сигналы
        signals.append({
            'type': 'oi',
            'symbol': 'BTC',
            'exchange': 'ByBit',
            'change': 7.24,
            'amount': 0.81
        })
        
        signals.append({
            'type': 'oi',
            'symbol': 'ETH',
            'exchange': 'Binance', 
            'change': 4.32,
            'amount': 0.56
        })
        
        # Pump сигналы
        signals.append({
            'type': 'pump',
            'symbol': 'SOL',
            'exchange': 'ByBit',
            'change': 2.1,
            'signal_type': 'long'
        })
        
        signals.append({
            'type': 'pump', 
            'symbol': 'ADA',
            'exchange': 'Binance',
            'change': -1.8,
            'signal_type': 'short'
        })
        
        return signals

    def format_signal(self, signal):
        """Форматирование сигнала с ссылками"""
        timestamp = datetime.now().strftime('%H:%M')
        symbol = signal['symbol']
        
        # Ссылки на CoinGlass
        coinglass_url = f"https://coinglass.com/top-long-short?symbol={symbol}"
        
        if signal['type'] == 'oi':
            return (
                f"<b>📊 ОТКРЫТЫЙ ИНТЕРЕС – 15м</b>\n"
                f"▪️ Монета: <a href='{coinglass_url}'>{symbol}</a>\n"
                f"▪️ Биржа: {signal['exchange']}\n"
                f"▪️ <b>ОИ вырос на {signal['change']}%</b>\n"
                f"▪️ Объем: {signal['amount']} млн. $\n"
                f"<i>🕒 {timestamp}</i>"
            )
        elif signal['type'] == 'pump':
            signal_type = "🟢 ЛОНГ" if signal['signal_type'] == 'long' else "🔴 ШОРТ"
            change_icon = "📈" if signal['signal_type'] == 'long' else "📉"
            return (
                f"<b>🚀 ПАМП СКРИНЕР – 1м</b>\n"
                f"▪️ Монета: <a href='{coinglass_url}'>{symbol}</a>\n" 
                f"▪️ Биржа: {signal['exchange']}\n"
                f"▪️ {signal_type}: {change_icon} {abs(signal['change'])}%\n"
                f"<i>🕒 {timestamp}</i>"
            )

    def start_monitoring(self):
        def monitor():
            while True:
                try:
                    signals = self.scan_demo_signals()
                    for signal in signals:
                        message = self.format_signal(signal)
                        signal_hash = self.create_signal_hash(signal)
                        
                        if self.broadcast_signal(message, signal_hash):
                            logging.info(f"📢 Отправлен сигнал: {signal['type']} {signal['symbol']}")
                            time.sleep(2)
                    
                    time.sleep(60)  # Проверка каждую минуту
                    
                except Exception as e:
                    logging.error(f"Ошибка мониторинга: {e}")
                    time.sleep(30)
        
        Thread(target=monitor, daemon=True).start()

    def process_message(self, message):
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        username = message.get('from', {}).get('username', '')
        first_name = message.get('from', {}).get('first_name', '')
        
        if text == '/start':
            self.save_user_chat(chat_id, username, first_name)
            welcome = (
                "🚀 <b>UNIFIED SCANNER</b>\n\n"
                "📊 <b>Доступные скринеры:</b>\n"
                "• Открытый интерес (OI Scanner)\n" 
                "• Пампы (Pump Scanner)\n\n"
                "⚙️ <b>Команды:</b>\n"
                "/settings - Настройки параметров\n"
                "/status - Статус бота\n\n"
                "<i>Сигналы приходят автоматически!</i>"
            )
            self.send_message(chat_id, welcome)
            
        elif text == '/status':
            status = (
                f"<b>📊 Статус системы</b>\n"
                f"• Пользователей: {len(self.active_chats)}\n"
                f"• Активные скринеры: 2\n"
                f"• Время: {datetime.now().strftime('%H:%M:%S')}\n"
                f"• Режим: Демонстрационный"
            )
            self.send_message(chat_id, status)
            
        elif text == '/settings':
            user_settings = self.get_user_settings(chat_id)
            settings_msg = (
                f"<b>⚙️ Настройки параметров</b>\n\n"
                f"📊 <b>OI Scanner:</b>\n"
                f"• Мин. изменение: {user_settings['oi_min_change']}%\n"
                f"• Мин. объем: {user_settings['oi_min_volume']}M $\n\n"
                f"🚀 <b>Pump Scanner:</b>\n" 
                f"• Мин. изменение: {user_settings['pump_min_change']}%\n\n"
                f"⏰ <b>Общие:</b>\n"
                f"• Кду дубликатов: {user_settings['cooldown_minutes']} мин\n\n"
                f"<i>Для изменения настроек используйте цифровые команды</i>"
            )
            
            # Клавиатура для быстрых настроек
            keyboard = {
                'inline_keyboard': [
                    [{'text': '📊 OI мин. %', 'callback_data': 'set_oi_change'}],
                    [{'text': '🚀 Pump мин. %', 'callback_data': 'set_pump_change'}],
                    [{'text': '⏰ Время кду', 'callback_data': 'set_cooldown'}]
                ]
            }
            
            url = f"{BASE_URL}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': settings_msg,
                'parse_mode': 'HTML',
                'reply_markup': json.dumps(keyboard)
            }
            try:
                requests.post(url, data=data, timeout=10)
            except:
                pass

# Создаем бота
bot = TelegramScannerBot()

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    if 'message' in update:
        bot.process_message(update['message'])
    return 'OK'

@app.route('/')
def home():
    return f'''
    <h1>🤖 Unified Scanner Bot</h1>
    <p>✅ Работает на Render</p>
    <p>📊 Активных пользователей: {len(bot.active_chats)}</p>
    <p>🚀 Скринеры: OI + Pump</p>
    <p>⚙️ Версия: 2.0 с улучшениями</p>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)