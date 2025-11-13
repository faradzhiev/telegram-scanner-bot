import os
import logging
import requests
import time
import json
from datetime import datetime
from threading import Thread
import sqlite3
from flask import Flask, request

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8354006848:AAEQZbIAGty2IN0a9FOrIdIiwgtEoyrY7FE')
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

class TelegramScannerBot:
    def __init__(self):
        self.active_chats = set()
        self.init_database()
        self.load_active_chats()
        self.start_monitoring()
        logging.info("✅ Бот запущен на Render!")

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

    def save_user_chat(self, chat_id, username, first_name):
        conn = sqlite3.connect('/tmp/signals.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO user_chats 
            (chat_id, username, first_name, registered_at)
            VALUES (?, ?, ?, datetime('now'))
        ''', (chat_id, username, first_name))
        conn.commit()
        conn.close()
        self.active_chats.add(chat_id)

    def send_message(self, chat_id, text):
        url = f"{BASE_URL}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        try:
            requests.post(url, data=data, timeout=10)
        except:
            pass

    def broadcast_signal(self, message):
        for chat_id in self.active_chats:
            self.send_message(chat_id, message)
            time.sleep(0.1)

    def scan_demo_signals(self):
        """Демо-сигналы для теста"""
        signals = []
        
        # OI сигнал
        signals.append({
            'type': 'oi',
            'symbol': 'BTCUSDT',
            'exchange': 'ByBit',
            'change': 7.24,
            'amount': 0.81
        })
        
        # Pump long сигнал
        signals.append({
            'type': 'pump',
            'symbol': 'ETHUSDT', 
            'exchange': 'Binance',
            'change': 2.1,
            'signal_type': 'long'
        })
        
        # Liquidation сигнал
        signals.append({
            'type': 'liquidation',
            'symbol': 'SOL',
            'exchange': 'ByBit', 
            'amount': 34140
        })
        
        return signals

    def format_signal(self, signal):
        if signal['type'] == 'oi':
            return (
                f"<b>📊 ОТКРЫТЫЙ ИНТЕРЕС – 15м – {signal['symbol']} {signal['exchange']}</b>\n"
                f"📈 <b>ОИ вырос на {signal['change']}%</b>\n"
                f"Объем: {signal['amount']} млн. $\n"
                f"<i>{datetime.now().strftime('%H:%M')}</i>"
            )
        elif signal['type'] == 'pump':
            signal_type = "ЛОНГ" if signal['signal_type'] == 'long' else "ШОРТ"
            return (
                f"<b>🚀 ПАМП СКРИНЕР – 1м – {signal['symbol']} {signal['exchange']}</b>\n"
                f"<b>{signal_type}:</b> {signal['change']}%\n"
                f"<i>{datetime.now().strftime('%H:%M')}</i>"
            )
        elif signal['type'] == 'liquidation':
            return (
                f"<b>💥 ЛИКВИДАЦИЯ – 5м – {signal['symbol']} {signal['exchange']}</b>\n"
                f"${signal['amount']:,}\n"
                f"<i>{datetime.now().strftime('%H:%M')}</i>"
            )

    def start_monitoring(self):
        def monitor():
            while True:
                try:
                    signals = self.scan_demo_signals()
                    for signal in signals:
                        message = self.format_signal(signal)
                        self.broadcast_signal(message)
                        time.sleep(1)
                    time.sleep(60)  # Проверка каждую минуту
                except Exception as e:
                    logging.error(f"Ошибка: {e}")
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
                "✅ Запущено на Render\n"
                "✅ Автоматический мониторинг\n"
                "✅ OI + Pump + Liquidation\n\n"
                "<i>Сигналы приходят автоматически!</i>"
            )
            self.send_message(chat_id, welcome)
            
        elif text == '/status':
            status = f"<b>Статус:</b> 🟢 Работает\n<b>Пользователей:</b> {len(self.active_chats)}"
            self.send_message(chat_id, status)

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
    <h1>🤖 Scanner Bot</h1>
    <p>Работает на Render!</p>
    <p>Пользователей: {len(bot.active_chats)}</p>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)