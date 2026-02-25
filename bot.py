# bot.py
import telebot
import requests
import json
import logging
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import init_db, save_weather_request, save_currency_request, get_user_stats
from config import BOT_TOKEN, OPENWEATHER_API_KEY

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создаём бота
bot = telebot.TeleBot(BOT_TOKEN)

# Константы для API
CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"  # API Центробанка
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = """
    👋 Привет! Я бот-помощник.
    Я умею показывать курс валют и погоду.
    """
    bot.reply_to(message, welcome_text)


@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """Доступные команды:
    /course — курс доллара и евро
    /weather <город> — погода в указанном городе
    /help — эта подсказка

    Например: /weather Moscow"""
    bot.reply_to(message, help_text)


def get_currency_rate(currency_code="USD"):
    """
    Получает курс валюты от ЦБ РФ.
    currency_code — код валюты: USD, EUR, GBP и т.д.
    Возвращает словарь с данными или None в случае ошибки.
    """
    try:
        # Делаем запрос к API
        response = requests.get(CBR_URL, timeout=10)

        # Проверяем, что запрос успешен (код 200)
        if response.status_code != 200:
            logger.error(f"Ошибка API ЦБ: статус {response.status_code}")
            return None

        # Превращаем JSON в словарь Python
        data = response.json()

        # Проверяем, есть ли нужная валюта в ответе
        if "Valute" not in data or currency_code not in data["Valute"]:
            logger.warning(f"Валюта {currency_code} не найдена")
            return None

        # Достаём данные о валюте
        currency_data = data["Valute"][currency_code]

        # Возвращаем только то, что нам нужно
        return {
            "name": currency_data["Name"],
            "value": currency_data["Value"],
            "previous": currency_data["Previous"],
            "date": data["Date"][:10]  # Обрезаем время, оставляем дату
        }

    except requests.exceptions.Timeout:
        logger.error("Таймаут при запросе к ЦБ")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Ошибка подключения к ЦБ")
        return None
    except json.JSONDecodeError:
        logger.error("Ошибка парсинга JSON от ЦБ")
        return None
    except Exception as e:
        logger.exception(f"Неизвестная ошибка: {e}")
        return None


@bot.message_handler(commands=['course'])
def course_menu(message):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🇺🇸 Доллар", callback_data="course_USD"),
        InlineKeyboardButton("🇪🇺 Евро", callback_data="course_EUR")
    )
    markup.row(
        InlineKeyboardButton("🇬🇧 Фунт", callback_data="course_GBP"),
        InlineKeyboardButton("🇯🇵 Иена", callback_data="course_JPY")
    )
    markup.row(
        InlineKeyboardButton("🇨🇳 Юань", callback_data="course_CNY"),
        InlineKeyboardButton("🇨🇭 Франк", callback_data="course_CHF")
    )

    bot.reply_to(
        message,
        "Выбери валюту:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('course_'))
def handle_course_callback(call):
    currency_code = call.data.split('_')[1]
    bot.answer_callback_query(call.id)
    bot.send_chat_action(call.message.chat.id, 'typing')
    currency = get_currency_rate(currency_code)

    if not currency:
        bot.edit_message_text(
            "😔 Не удалось получить курс.",
            call.message.chat.id,
            call.message.message_id
        )
        return

    text = f"""
    💰 *Курс {currency['name']} на {currency['date']}*

    {currency['value']:.2f} ₽
    Изменение: {currency['value'] - currency['previous']:+.2f} ₽
    """

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )

    # Сохраняем запрос в базу данных
    save_currency_request(
        call.from_user.id,
        call.from_user.username,
        currency_code,
        currency['value']
    )

def get_weather(city):
    """Получает погоду для указанного города."""
    try:
        params = {
            'q': city,
            'appid': OPENWEATHER_API_KEY,
            'units': 'metric',
            'lang': 'ru'
        }

        response = requests.get(WEATHER_URL, params=params, timeout=10)

        if response.status_code == 404:
            logger.warning(f"Город {city} не найден")
            return None

        if response.status_code != 200:
            logger.error(f"Ошибка OpenWeatherMap: статус {response.status_code}")
            return None

        data = response.json()

        # Добавляем проверку на наличие всех нужных полей
        if 'main' not in data or 'weather' not in data:
            logger.error("Неполный ответ от API")
            return None

        weather = {
            'city': data.get('name', city),
            'temp': data['main'].get('temp'),
            'feels_like': data['main'].get('feels_like'),
            'description': data['weather'][0].get('description', 'неизвестно'),
            'humidity': data['main'].get('humidity', 0),
            'wind': data.get('wind', {}).get('speed', 0),
            'pressure': data['main'].get('pressure', 0)
        }

        return weather

    except requests.exceptions.Timeout:
        logger.error("Таймаут при запросе к OpenWeatherMap")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("Ошибка подключения к OpenWeatherMap")
        return None
    except Exception as e:
        logger.exception(f"Неизвестная ошибка в get_weather: {e}")
        return None


@bot.message_handler(commands=['weather'])
def send_weather(message):
    bot.send_chat_action(message.chat.id, 'typing')

    command_parts = message.text.split(maxsplit=1)

    if len(command_parts) < 2:
        bot.reply_to(
            message,
            "🌍 Укажи город после команды.\n"
            "Например: /weather Moscow"
        )
        return

    city = command_parts[1].strip()
    weather = get_weather(city)

    if not weather:
        bot.reply_to(
            message,
            f"😔 Не удалось найти город '{city}' или получить данные о погоде.\n"
            "Проверь название и попробуй снова."
        )
        return

    text = f"""
    🌍 *Погода в {weather['city']}*

    🌡 Температура: {weather['temp']:.1f}°C
    🤔 Ощущается как: {weather['feels_like']:.1f}°C
    ☁️ {weather['description'].capitalize()}
    💧 Влажность: {weather['humidity']}%
    💨 Ветер: {weather['wind']} м/с
    🎚 Давление: {weather['pressure']} гПа
    """

    bot.reply_to(message, text, parse_mode='Markdown')

    # Сохраняем запрос в базу данных
    save_weather_request(
        message.from_user.id,
        message.from_user.username,
        weather['city'],
        weather['temp'],
        weather['description']
    )


# Добавьте команду для просмотра статистики
@bot.message_handler(commands=['stats'])
def send_stats(message):
    stats = get_user_stats(message.from_user.id)
    if not stats:
        bot.reply_to(message, "Статистика недоступна.")
        return

    text = f"""
    📊 *Ваша статистика:*

    🌤 Запросов погоды: {stats['weather_requests']}
    💰 Запросов курсов: {stats['currency_requests']}
    """

    if stats['avg_temperature'] is not None:
        text += f"🌡 Средняя температура: {stats['avg_temperature']}°C\n"

    if stats['currencies_used']:
        text += f"💱 Валюты: {', '.join(stats['currencies_used'])}"

    bot.reply_to(message, text, parse_mode='Markdown')


# Инициализация базы данных при запуске
if __name__ == "__main__":
    logger.info("🤖 Бот запускается...")
    if not init_db():
        logger.error("❌ Не удалось инициализировать базу данных!")
        exit(1)
    bot.infinity_polling(none_stop=True)
