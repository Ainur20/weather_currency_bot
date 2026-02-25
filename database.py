# database.py
import sqlite3
import logging
from typing import Optional, Dict, Any

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Имя файла базы данных
DB_NAME = 'weather_bot.db'


def get_connection():
    """Создаёт и возвращает соединение с базой данных."""
    try:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Позволяет обращаться к колонкам по имени
        return conn
    except sqlite3.Error as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return None


def init_db():
    """Инициализирует базу данных и создаёт необходимые таблицы."""
    conn = get_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()

        # Таблица для хранения запросов погоды
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weather_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                city TEXT NOT NULL,
                temperature REAL,
                description TEXT,
                request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица для хранения запросов курсов валют
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS currency_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                currency_code TEXT NOT NULL,
                rate REAL,
                request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        logger.info("База данных инициализирована успешно")
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка при создании таблиц: {e}")
        return False
    finally:
        if conn:
            conn.close()


def save_weather_request(user_id: int, username: Optional[str], city: str,
                         temperature: float, description: str) -> bool:
    """Сохраняет запрос погоды в базу данных."""
    if not city or temperature is None:
        logger.warning("Попытка сохранить некорректные данные погоды")
        return False

    conn = get_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO weather_requests (user_id, username, city, temperature, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, city, temperature, description))

        conn.commit()
        logger.info(f"Сохранён запрос погоды: user_id={user_id}, city={city}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении запроса погоды: {e}")
        return False
    finally:
        if conn:
            conn.close()


def save_currency_request(user_id: int, username: Optional[str],
                          currency_code: str, rate: float) -> bool:
    """Сохраняет запрос курса валюты в базу данных."""
    if not currency_code or rate is None:
        logger.warning("Попытка сохранить некорректные данные валюты")
        return False

    conn = get_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO currency_requests (user_id, username, currency_code, rate)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, currency_code, rate))

        conn.commit()
        logger.info(f"Сохранён запрос валюты: user_id={user_id}, currency={currency_code}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении запроса валюты: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_user_stats(user_id: int) -> Dict[str, Any]:
    """Возвращает статистику по пользователю."""
    conn = get_connection()
    if conn is None:
        return {}

    try:
        cursor = conn.cursor()

        # Статистика по погоде
        cursor.execute('''
            SELECT COUNT(*) as weather_count, 
                   AVG(temperature) as avg_temp
            FROM weather_requests 
            WHERE user_id = ?
        ''', (user_id,))
        weather_stats = cursor.fetchone()

        # Статистика по валютам
        cursor.execute('''
            SELECT COUNT(*) as currency_count,
                   GROUP_CONCAT(DISTINCT currency_code) as currencies
            FROM currency_requests 
            WHERE user_id = ?
        ''', (user_id,))
        currency_stats = cursor.fetchone()

        return {
            'weather_requests': weather_stats[0] if weather_stats else 0,
            'avg_temperature': round(weather_stats[1], 1) if weather_stats and weather_stats[1] else None,
            'currency_requests': currency_stats[0] if currency_stats else 0,
            'currencies_used': currency_stats[1].split(',') if currency_stats and currency_stats[1] else []
        }
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        return {}
    finally:
        if conn:
            conn.close()
