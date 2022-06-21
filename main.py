import configure
import telebot
from telebot import types
import psycopg2
from car_info import CarInfo
from parcel_info import ParcelInfo
from offer_parcel import OfferParcel
import re
from geopy.geocoders import Nominatim
from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP

bot = telebot.TeleBot(configure.config["token"])
geolocator = Nominatim(user_agent="tudy-sudy")

db_connection = psycopg2.connect(configure.config["db_URI"], sslmode="require")
cursor = db_connection.cursor()

car_info_dict = {}
parcel_info_dict = {}
offer_dict = {}
current_car = {}

cars_type = {'sedan': 'Седан', 'SUV': 'Позашляховик', 'minivan': 'Мінівен', 'hatchback': 'Хетчбек',
             'universal': 'Універсал', 'coupe': 'Купе', 'passenger_van': 'Легковий фургон', 'pickup': 'Пікап',
             'other': 'Інше'}


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    id_user = message.from_user.id
    username = message.from_user.username

    cursor.execute(f'SELECT id FROM users WHERE id = {id_user}')
    result = cursor.fetchone()
    print(result)

    if not result:
        sql = 'INSERT INTO users(id, username) VALUES(%s, %s)'
        val = (id_user, username)
        cursor.execute(sql, val)
        db_connection.commit()
        print(cursor.rowcount, "record inserted.")

    bot.send_message(message.chat.id, f'Вітаємо, <b>{message.from_user.first_name}</b>',
                     reply_markup=main_markup(message.from_user.id), parse_mode="HTML")


@bot.callback_query_handler(func=DetailedTelegramCalendar.func())
def cal(call):
    result, key, step = DetailedTelegramCalendar().process(call.data)
    if not result and key:
        bot.edit_message_text(f"Select {LSTEP[step]}",
                              call.message.chat.id,
                              call.message.message_id,
                              reply_markup=key)
    elif result:
        bot.edit_message_text(f"Ви обрали дату: {result}",
                              call.message.chat.id,
                              call.message.message_id)

        parcel_info = parcel_info_dict[call.from_user.id]
        parcel_info.date = result

        msg = bot.send_message(call.message.chat.id, f'Як виглядає ваша посилка?\n📸Надішліть нам фото')
        bot.register_next_step_handler(msg, parcel_image)


@bot.message_handler(func=lambda message: True)
def callback(message):
    cursor.execute(f'SELECT phone FROM users WHERE id = {message.from_user.id}')
    phone = cursor.fetchone()[0]

    request_contact_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    request_contact_markup.add(types.KeyboardButton('Надіслати номер телефону 📲', request_contact=True))
    request_contact_markup.add(types.KeyboardButton('Назад🔙'))

    if message.text == "Опублікувати оголошення 💬":
        if not phone:
            msg = bot.send_message(message.chat.id, f'Перед тим як опублікувати оголошення, додайте свій номер '
                                                    f'телефону 📲',
                                   reply_markup=request_contact_markup)
            bot.register_next_step_handler(msg, add_phone_advertisement)
        else:
            msg = bot.send_message(message.chat.id, f'В якому місті знаходиться посилка?📦')
            bot.register_next_step_handler(msg, parcel_city_a)

    elif message.text == "Додати своє авто 🚘":
        print(get_number_of_cars(message.from_user.id))
        if not phone:
            msg = bot.send_message(message.chat.id, f'Перед тим як додати своє авто, додайте свій номер '
                                                    f'телефону 📲',
                                   reply_markup=request_contact_markup)
            bot.register_next_step_handler(msg, add_phone_car)
        else:
            msg = bot.send_message(message.chat.id, f'<b>Яка марка вашого авто?</b>', parse_mode='HTML')
            bot.register_next_step_handler(msg, car_brand_next_step)

    elif re.match("Моє авто \(\d🚘\)", message.text):
        inline_markup = types.InlineKeyboardMarkup()

        cursor.execute(f'SELECT id_car, car_brand, car_model FROM car_info WHERE id_owner = {message.from_user.id}')
        res = cursor.fetchall()

        for x in res:
            inline_markup.row(types.InlineKeyboardButton(f'{x[1]} {x[2]}', callback_data=str(x[0])))

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row(types.KeyboardButton('Додати своє авто 🚘'))
        markup.row(types.KeyboardButton('Назад🔙'))
        bot.send_message(message.chat.id, f'🔸🔹🔸🔹', reply_markup=markup)

        bot.send_message(message.chat.id, f'<b>Моє авто🚘</b>', reply_markup=inline_markup, parse_mode='HTML')

    elif message.text == 'Назад🔙':
        bot.send_message(message.chat.id, f'<b>Публікуй оголошення, додавай своє авто та заробляй гроші💰</b>',
                         reply_markup=main_markup(message.from_user.id),
                         parse_mode='HTML')

    elif message.text == 'Везти посилку📦':
        cursor.execute(f'SELECT id_car FROM car_info WHERE id_owner = {message.from_user.id}')
        result = cursor.fetchone()

        if not result:
            bot.send_message(message.chat.id, f'<b>Спочатку додайте авто🚘</b>', parse_mode='HTML')
            return

        bot.send_message(message.chat.id, f'<b>Оголошення:</b>', reply_markup=get_all_parcel(message.from_user.id),
                         parse_mode='HTML')

    elif message.text == 'Мої оголошення 💬':
        cursor.execute(f'SELECT * FROM parcel_info WHERE id_user = {message.from_user.id}')
        res = cursor.fetchall()

        if not res:
            bot.send_message(message.chat.id, f'<b>Тут поки пусто🗑</b>', parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, f'<b>Мої оголошення 💬</b>',
                             reply_markup=get_my_parcel_inline(message.from_user.id), parse_mode='HTML')

    elif message.text == '✅Мої поїздки':
        bot.send_message(message.chat.id, f'<b>Мої поїздки:</b>',
                         reply_markup=get_agree_parcel_inline(message.from_user.id), parse_mode='HTML')


def get_agree_parcel_inline(id_user):
    inline_markup = types.InlineKeyboardMarkup()

    cursor.execute(f'SELECT parcel_info.date_parcel, parcel_info.city_a, parcel_info.city_b, parcel_info.id_parcel '
                   f'FROM parcel_info JOIN car_info ON '
                   f'parcel_info.id_car = car_info.id_car WHERE car_info.id_owner = {id_user}')
    res = cursor.fetchall()

    for x in res:
        if x[1] == x[2]:
            inline_markup.row(types.InlineKeyboardButton(f'{x[0]} {x[1]}', callback_data=f'parcel-agree-{x[3]}'))
        else:
            inline_markup.row(types.InlineKeyboardButton(f'{x[0]} {x[1]} - {x[2]}',
                                                         callback_data=f'parcel-agree-{x[3]}'))

    return inline_markup


@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    owner_id = call.from_user.id

    cursor.execute(f'SELECT id_car FROM car_info WHERE id_owner = {call.from_user.id}')
    cars_id = cursor.fetchall()

    if call.data in cars_type:
        # noinspection PyBroadException
        try:
            car_info = car_info_dict[call.from_user.id]
            car_info.car_type = cars_type[call.data]

            msg = bot.send_message(call.message.chat.id, f'<b>Якого кольору ваше авто?</b>', parse_mode='HTML')
            bot.register_next_step_handler(msg, car_color_next_step)
        except Exception as e:
            print(e)
            bot.reply_to(call.message, "Щось пішло не так...")

    elif call.data in str(cars_id):
        send_car_info_call(call)

    elif re.match("brand-\d+", call.data):
        message = call.data
        car_id = message.split('-')[-1]
        current_car[owner_id] = car_id

        msg = bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                    text=f'<b>Яка марка вашого авто?</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, change_brand)

    elif re.match("model-\d+", call.data):
        set_current_car(call)

        msg = bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                    text=f'<b>Яка модель вашого авто?</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, change_model)

    elif re.match("color-\d+", call.data):
        set_current_car(call)

        msg = bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                    text=f'<b>Якого кольору ваше авто?</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, change_color)

    elif re.match("year-\d", call.data):
        set_current_car(call)
        msg = bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                    text=f'<b>У якому році випустили вашу машину?</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, change_year)

    elif re.match("number-\d+", call.data):
        set_current_car(call)
        msg = bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                    text=f'<b>Який номерний знак авто?</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, change_number)

    elif re.match("description-\d+", call.data):
        set_current_car(call)
        msg = bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                    text=f'<b>Додайте короткий опис вашого авто.</b> Ваш опис допоможе комусь '
                                         f'обрати саме ваше авто для перевезення вантажу.\n(Наприклад, вкажіть '
                                         f'максимальну вагу вантажу, яку можете взяти з собою, розміри '
                                         f'багажника чи розміри буди, якщо авто грузове і тд.)',
                                    parse_mode='HTML')
        bot.register_next_step_handler(msg, change_description)

    elif re.match("type-\d+", call.data):
        set_current_car(call)

        inline_markup = types.InlineKeyboardMarkup()
        inline_markup.row(types.InlineKeyboardButton('Седан', callback_data='change-sedan'),
                          types.InlineKeyboardButton('Позашляховик / Кросовер', callback_data='change-SUV'))
        inline_markup.row(types.InlineKeyboardButton('Мінівен', callback_data='change-minivan'),
                          types.InlineKeyboardButton('Хетчбек', callback_data='change-hatchback'))
        inline_markup.row(types.InlineKeyboardButton('Універсал', callback_data='change-universal'),
                          types.InlineKeyboardButton('Купе', callback_data='change-coupe'))
        inline_markup.row(types.InlineKeyboardButton('Легковий фургон', callback_data='change-passenger_van'),
                          types.InlineKeyboardButton('Пікап', callback_data='change-pickup'))
        inline_markup.row(types.InlineKeyboardButton('Інше', callback_data='change-other'))

        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text=f'<b>Який тип кузова у вашого авто?</b>', reply_markup=inline_markup,
                              parse_mode='HTML')

    elif re.match("change-\w+", call.data):
        message = call.data
        car_type = message.split('-')[-1]
        sql = f'UPDATE car_info SET car_type = \'{cars_type[car_type]}\' WHERE id_car = {current_car[owner_id]}'
        cursor.execute(sql)
        db_connection.commit()

        print(cursor.rowcount, "record(s) affected")

        bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                              text=f'<b>Інформація по вашій машині:</b>\n❗Натисність на поле, щоб змінити його значення',
                              reply_markup=get_car_inline_delete(current_car[owner_id]), parse_mode='HTML')

    elif re.match("delete-\d+", call.data):
        set_current_car(call)

        sql = f'DELETE FROM car_info WHERE id_car = {current_car[owner_id]}'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) deleted")

        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f'<b>Авто успішно видалено</b>',
                              parse_mode='HTML')

        bot.send_message(call.message.chat.id, f'❌🚘',
                         reply_markup=main_markup(owner_id), parse_mode='HTML')

    elif re.match(f"{owner_id}-\w+", call.data):
        parcel_info = parcel_info_dict[call.from_user.id]

        if parcel_info.city_b is not None:
            return

        bot.clear_step_handler(call.message)

        message = call.data
        city_b = message.split('-')[-1]

        parcel_info = parcel_info_dict[owner_id]
        parcel_info.city_b = city_b

        msg = bot.send_message(call.message.chat.id, f'📍Введіть адресу за якою потрібно доставити вашу посилку')
        bot.register_next_step_handler(msg, parcel_address_b)

    elif re.match(f"my-parcel-\d+", call.data):
        id_parcel = get_id(call.data)

        bot.send_photo(chat_id=chat_id, photo=get_photo_parcel(int(id_parcel)), caption=get_caption_parcel(id_parcel),
                       reply_markup=get_parcel_inline(id_parcel))

    elif re.match(f"delete-parcel-\d+", call.data):
        id_parcel = get_id(call.data)

        sql = f'DELETE FROM parcel_info WHERE id_parcel = {int(id_parcel)};'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) deleted")

        chat_id = call.message.chat.id
        message_id = call.message.message_id

        bot.delete_message(chat_id=chat_id, message_id=message_id)

        cursor.execute(f'SELECT * FROM parcel_info WHERE id_user = {call.from_user.id}')
        res = cursor.fetchall()

        if not res:
            bot.send_message(chat_id, f'<b>Тут поки пусто🗑</b>', parse_mode='HTML')
        else:
            bot.send_message(chat_id, f'<b>Мої оголошення 💬</b>',
                             reply_markup=get_my_parcel_inline(call.from_user.id), parse_mode='HTML')

    elif re.match(f"parcel-\d+", call.data):
        id_parcel = get_id(call.data)

        inline_markup, desc = get_parcel_info_inline(id_parcel)

        bot.send_photo(chat_id=chat_id, photo=get_photo_parcel(int(id_parcel)), caption=desc,
                       reply_markup=inline_markup)

    elif re.match(f'parcel-address_a-\d+', call.data):
        id_parcel = get_id(call.data)

        cursor.execute(f'SELECT city_a, address_a, lon_a, lat_a FROM parcel_info WHERE id_parcel = {int(id_parcel)}')
        res = cursor.fetchone()

        bot.send_venue(chat_id=chat_id, latitude=res[3], longitude=res[2], address=f'{res[1]}, {res[0]}',
                       title=f'Адреса за якою потрібно забрати посилку\n')

    elif re.match(f'parcel-address_b-\d+', call.data):
        id_parcel = get_id(call.data)

        cursor.execute(f'SELECT city_b, address_b, lon_b, lat_b FROM parcel_info WHERE id_parcel = {int(id_parcel)}')
        res = cursor.fetchone()

        bot.send_venue(chat_id=chat_id, latitude=res[3], longitude=res[2], address=f'{res[1]}, {res[0]}',
                       title=f'Адреса за якою потрібно доставити посилку\n')

    elif re.match(f'take-parcel-\d+', call.data):
        id_parcel = get_id(call.data)

        offer = OfferParcel(id_parcel)
        offer_dict[call.from_user.id] = offer
        bot.send_message(chat_id, f'<b>На якій машині повезеш?</b>', reply_markup=get_my_car_inline(call.from_user.id),
                         parse_mode='HTML')

    elif re.match(f'parcel-car-\d+', call.data):
        id_car = get_id(call.data)

        offer = offer_dict[call.from_user.id]
        offer.id_car = id_car

        sql = 'INSERT INTO offer_parcel(id_parcel, id_car) VALUES(%s, %s)'
        val = (offer.id_parcel, offer.id_car)
        cursor.execute(sql, val)
        db_connection.commit()
        print(cursor.rowcount, "record inserted.")

        bot.send_message(chat_id, f'<b>Чудово!</b>\nТепер очікуйте підтвердження від замовника', parse_mode='HTML')

        bot.send_message(get_user_from_parcel(offer.id_parcel), '🥳Хтось хоче перевезти вашу посилку.\n'
                                                                'Зайдіть в розділ Мої оголошення 💬 та '
                                                                'підтвердіть запит')

        del offer_dict[call.from_user.id]

    elif re.match(f'offer-\d+-\d+', call.data):
        print(call.data)
        id_parcel = get_id_parcel(call.data)

        id_car = get_id(call.data)

        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton('Погодити', callback_data=f'offer-yes-{id_parcel}-{id_car}'))
        markup.row(types.InlineKeyboardButton('Відмовити', callback_data=f'offer-no-{id_parcel}-{id_car}'))

        bot.send_message(chat_id=chat_id, text=get_car_text(id_car), reply_markup=markup, parse_mode='HTML')

    elif re.match(f'offer-no-\d+-\d+', call.data):
        id_parcel = get_id_parcel(call.data)
        id_car = get_id(call.data)

        sql = f'DELETE FROM offer_parcel WHERE id_parcel = {int(id_parcel)} AND id_car = {int(id_car)};'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) deleted")

        chat_id = call.message.chat.id
        message_id = call.message.message_id

        bot.delete_message(chat_id, message_id)
        bot.send_photo(chat_id=chat_id, photo=get_photo_parcel(int(id_parcel)), caption=get_caption_parcel(id_parcel),
                       reply_markup=get_parcel_inline(id_parcel))

    elif re.match(f'offer-yes-\d+-\d+', call.data):
        id_parcel = get_id_parcel(call.data)
        id_car = get_id(call.data)

        sql = f'UPDATE parcel_info SET id_car = {int(id_car)}, ' \
              f'status = \'Машину знайдено, очікуйте прибуття посилки\' WHERE id_parcel = {int(id_parcel)};'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) affected")

        sql = f'DELETE FROM offer_parcel WHERE id_parcel = {int(id_parcel)} ;'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) deleted")

        chat_id = call.message.chat.id
        message_id = call.message.message_id

        bot.delete_message(chat_id, message_id)
        bot.send_photo(chat_id=chat_id, photo=get_photo_parcel(int(id_parcel)), caption=get_caption_parcel(id_parcel),
                       reply_markup=get_parcel_inline(id_parcel))

        cursor.execute(f'SELECT id_owner FROM car_info WHERE car_info.id_car = {id_car};')
        id_user = cursor.fetchone()[0]

        bot.send_message(chat_id=id_user,
                         text='Вашу заявку схвалено! Ви везете посилку. Перейдіть в розділ ✅Мої поїздки')

    elif re.match(f'get-info-\d+', call.data):
        id_car = get_id(call.data)

        cursor.execute(f'SELECT users.username, users.phone FROM users '
                       f'JOIN car_info ON car_info.id_owner = users.id WHERE car_info.id_car = {id_car};')
        user = cursor.fetchone()

        info = get_car_text(id_car) + f'\n<b>👤Власник авто</b>\n\t\t\t📲Номер телефону: +{user[1]}\n' \
                                      f'\t\t\t✍️Telegram: @{user[0]}'
        bot.send_message(chat_id=chat_id, text=info, parse_mode='HTML')

    elif re.match(f'parcel-done-\d+', call.data):
        id_parcel = get_id(call.data)

        sql = f'UPDATE parcel_info SET status = \'Посилку доставлено!\' WHERE id_parcel = {int(id_parcel)};'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) affected")

        cursor.execute(f'SELECT * FROM parcel_info JOIN car_info ON '
                       f'parcel_info.id_car = car_info.id_car WHERE car_info.id_owner = {call.from_user.id}')
        res = cursor.fetchone()

        inline_markup = types.InlineKeyboardMarkup()

        inline_markup.row(types.InlineKeyboardButton(f'📍Від: {res[1]}, {res[2]}',
                                                     callback_data=f'parcel-address_a-{int(res[0])}'))
        inline_markup.row(types.InlineKeyboardButton(f'📍До: {res[5]}, {res[6]}',
                                                     callback_data=f'parcel-address_b-{int(res[0])}'))

        chat_id = call.message.chat.id
        message_id = call.message.message_id

        bot.delete_message(chat_id=chat_id, message_id=message_id)
        bot.send_photo(chat_id=call.message.chat.id, photo=get_photo_parcel(int(int(res[0]))),
                       caption=f'🗓Дата: {res[9]}\n💰Ціна: {res[11]}\n💬Коментар: {res[12]}\n'
                               f'❗️Статус: {res[14]}', reply_markup=inline_markup)

        bot.send_message(chat_id=res[13], text='Вашу посилку доставлено')

    elif re.match(f'parcel-agree-\d+', call.data):
        cursor.execute(f'SELECT * FROM parcel_info JOIN car_info ON '
                               f'parcel_info.id_car = car_info.id_car WHERE car_info.id_owner = {call.from_user.id}')
        res = cursor.fetchone()

        inline_markup = types.InlineKeyboardMarkup()

        inline_markup.row(types.InlineKeyboardButton(f'📍Від: {res[1]}, {res[2]}',
                                                     callback_data=f'parcel-address_a-{int(res[0])}'))
        inline_markup.row(types.InlineKeyboardButton(f'📍До: {res[5]}, {res[6]}',
                                                     callback_data=f'parcel-address_b-{int(res[0])}'))

        if res[14] == "Посилку доставлено!":
            bot.send_photo(chat_id=call.message.chat.id, photo=get_photo_parcel(int(int(res[0]))),
                           caption=f'🗓Дата: {res[9]}\n💰Ціна: {res[11]}\n💬Коментар: {res[12]}\n'
                                   f'❗️Статус: {res[14]}',
                           reply_markup=inline_markup)
        else:
            inline_markup.row(types.InlineKeyboardButton(f'✅Відмітити як виконане',
                                                         callback_data=f'parcel-done-{int(res[0])}'))

            bot.send_photo(chat_id=call.message.chat.id, photo=get_photo_parcel(int(int(res[0]))),
                           caption=f'🗓Дата: {res[9]}\n💰Ціна: {res[11]}\n💬Коментар: {res[12]}',
                           reply_markup=inline_markup)

    else:
        pass


def get_id_parcel(message):
    mes = message
    return mes.split('-')[-2]


def get_user_from_parcel(id_parcel):
    cursor.execute(f'SELECT id_user FROM parcel_info WHERE id_parcel = {int(id_parcel)}')
    return cursor.fetchone()[0]


def get_my_car_inline(id_owner):
    inline_markup = types.InlineKeyboardMarkup()

    cursor.execute(f'SELECT id_car, car_brand, car_model FROM car_info WHERE id_owner = {id_owner}')
    res = cursor.fetchall()

    for x in res:
        inline_markup.row(types.InlineKeyboardButton(f'{x[1]} {x[2]}', callback_data=f'parcel-car-{x[0]}'))

    return inline_markup


def get_id(message):
    mes = message
    return mes.split('-')[-1]


def get_parcel_info_inline(id_parcel):
    inline_markup = types.InlineKeyboardMarkup()

    cursor.execute(f'SELECT * FROM parcel_info WHERE id_parcel = {int(id_parcel)}')
    res = cursor.fetchone()

    description = res[12]

    inline_markup.row(types.InlineKeyboardButton(f'📍Від: {res[1]}, {res[2]}',
                                                 callback_data=f'parcel-address_a-{id_parcel}'))
    inline_markup.row(types.InlineKeyboardButton(f'📍До: {res[5]}, {res[6]}',
                                                 callback_data=f'parcel-address_b-{id_parcel}'))
    inline_markup.row(types.InlineKeyboardButton(f'🗓Дата: {res[9]}', callback_data=f'.'))
    inline_markup.row(types.InlineKeyboardButton(f'💰Ціна: {res[11]}', callback_data=f'parcel-price-{id_parcel}'))
    inline_markup.row(types.InlineKeyboardButton(f'✅Можу завезти', callback_data=f'take-parcel-{id_parcel}'))

    return inline_markup, description


def get_car_text(id_car):
    cursor.execute(f'SELECT * FROM car_info WHERE id_car = {id_car}')
    car_data = cursor.fetchone()

    return f'<b>🚘Інформація про авто</b>\n' \
           f'\t\t\tМарка: {car_data[1]}\n' \
           f'\t\t\tМодель: {car_data[2]}\n' \
           f'\t\t\tТип кузова: {car_data[3]}\n' \
           f'\t\t\tКолір: {car_data[4]}\n' \
           f'\t\t\tРік випуску: {car_data[5]}\n' \
           f'\t\t\tНомерний знак: {car_data[6]}\n' \
           f'\t\t\tКороткий опис: {car_data[7]}'


def get_parcel_inline(id_parcel):
    inline_markup = types.InlineKeyboardMarkup()

    inline_markup.row(types.InlineKeyboardButton(f'❌Видалити оголошення❌', callback_data=f'delete-parcel-{id_parcel}'))

    cursor.execute(f'SELECT id_car FROM parcel_info WHERE id_parcel = {int(id_parcel)}')
    id_car = cursor.fetchone()[0]

    cursor.execute(f'SELECT * FROM offer_parcel WHERE id_parcel = {int(id_parcel)}')
    res = cursor.fetchall()

    if id_car:
        inline_markup.row(types.InlineKeyboardButton(f'⬇️Вашу посилку відвезе⬇️', callback_data='.'))
        res = get_car_info(id_car)

        inline_markup.row(types.InlineKeyboardButton(f'{res[1]} {res[2]}',
                                                     callback_data=f'get-info-{res[0]}'))

    elif res:
        inline_markup.row(types.InlineKeyboardButton(f'⬇️Вашу посилку можуть відвезти⬇️', callback_data='.'))
        for car in res:
            car_info = get_car_info(car[1])

            inline_markup.row(types.InlineKeyboardButton(f'{car_info[1]} {car_info[2]}',
                                                         callback_data=f'offer-{id_parcel}-{car[1]}'))

    return inline_markup


def get_car_info(id_car):
    cursor.execute(f'SELECT id_car, car_brand, car_model FROM car_info WHERE id_car = {id_car}')
    return cursor.fetchone()


def get_caption_parcel(id_parcel):
    cursor.execute(f'SELECT * FROM parcel_info WHERE id_parcel = {id_parcel}')
    res = cursor.fetchone()

    return f'📍{res[2]}, {res[1]}\n' \
           f'📍{res[6]}, {res[5]}\n' \
           f'🗓Дата: {res[9]}\n' \
           f'💸Ваша ціна: {res[11]} UAH\n' \
           f'📝Ваш опис: {res[12]}\n' \
           f'СТАТУС: {res[14]}'


def get_photo_parcel(id_parcel):
    cursor.execute(f'SELECT photo FROM parcel_info WHERE id_parcel = {id_parcel}')
    return cursor.fetchone()[0]


def get_all_parcel(id_user):
    inline_markup = types.InlineKeyboardMarkup()

    cursor.execute(f'SELECT date_parcel, city_a, city_b, id_parcel FROM parcel_info WHERE id_car IS NULL AND '
                   f'id_user <> {id_user} ')

    res = cursor.fetchall()

    for x in res:
        if x[1] == x[2]:
            inline_markup.row(types.InlineKeyboardButton(f'{x[0]} {x[1]}', callback_data=f'parcel-{x[3]}'))
        else:
            inline_markup.row(types.InlineKeyboardButton(f'{x[0]} {x[1]} - {x[2]}', callback_data=f'parcel-{x[3]}'))

    return inline_markup


def get_my_parcel_inline(id_user):
    inline_markup = types.InlineKeyboardMarkup()

    cursor.execute(f'SELECT date_parcel, city_a, city_b, id_parcel FROM parcel_info '
                   f'WHERE id_user = {id_user}')
    res = cursor.fetchall()

    for x in res:
        if x[1] == x[2]:
            inline_markup.row(types.InlineKeyboardButton(f'{x[0]} {x[1]}', callback_data=f'my-parcel-{x[3]}'))
        else:
            inline_markup.row(types.InlineKeyboardButton(f'{x[0]} {x[1]} - {x[2]}', callback_data=f'my-parcel-{x[3]}'))

    return inline_markup


def get_country(address):
    country = address.split(',')[-1]
    return country


def parcel_city_a(message):
    try:
        location = geolocator.geocode(message.text)

        if get_country(location.address) != ' Україна':
            msg = bot.reply_to(message, "Введіть місто / населений пункт в межах України 🇺🇦")
            bot.register_next_step_handler(msg, parcel_city_a)
            return

        parcel_info = ParcelInfo(message.text)
        parcel_info_dict[message.from_user.id] = parcel_info

        msg = bot.send_message(message.chat.id, f'📍Введіть адресу за якою потрібно забрати вашу посилку')
        bot.register_next_step_handler(msg, parcel_address_a)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Ми не знайшли такого міста / населеного пункта...")


def parcel_address_a(message):
    try:
        id_user = message.from_user.id

        location = geolocator.geocode(message.text)

        parcel_info = parcel_info_dict[message.from_user.id]
        parcel_info.address_a = message.text

        coords = geolocator.geocode(f'{parcel_info.address_a}, {parcel_info.city_a}')
        parcel_info.lon_a = coords.longitude
        parcel_info.lat_a = coords.latitude

        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton(f'{parcel_info.city_a}', callback_data=f'{id_user}-{parcel_info.city_a}'))

        msg = bot.send_message(message.chat.id, f'В яке місто потрібно доставити вашу посилку?', reply_markup=markup)
        bot.register_next_step_handler(msg, parcel_city_b)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось ми не знайшли такої адреси...")


def parcel_city_b(message):
    try:
        location = geolocator.geocode(message.text)

        if get_country(location.address) != ' Україна':
            msg = bot.reply_to(message, "Введіть місто / населений пункт в межах України 🇺🇦")
            bot.register_next_step_handler(msg, parcel_city_a)
            return

        parcel_info = parcel_info_dict[message.from_user.id]
        parcel_info.city_b = message.text

        msg = bot.send_message(message.chat.id, f'📍Введіть адресу за якою потрібно доставити вашу посилку')
        bot.register_next_step_handler(msg, parcel_address_b)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Ми не знайшли такого міста / населеного пункта...")


def parcel_address_b(message):
    try:
        location = geolocator.geocode(message.text)
        print(location.address)

        parcel_info = parcel_info_dict[message.from_user.id]
        parcel_info.address_b = message.text

        coords = geolocator.geocode(f'{parcel_info.address_b}, {parcel_info.city_b}')
        parcel_info.lon_b = coords.longitude
        parcel_info.lat_b = coords.latitude

        bot.send_message(message.chat.id, f'🗓Коли потрібно доставити?')

        calendar, step = DetailedTelegramCalendar().build()
        bot.send_message(message.chat.id,
                         f"Select {LSTEP[step]}",
                         reply_markup=calendar)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось ми не знайшли такої адреси...")


def parcel_image(message):
    try:
        if message.content_type == 'photo':
            file_info = bot.get_file(message.photo[len(message.photo) - 1].file_id)

            parcel_info = parcel_info_dict[message.from_user.id]
            parcel_info.photo = file_info.file_id

            msg = bot.send_message(message.chat.id, f'🤑<b>Скільки ви заплатите за доставку?</b>\n'
                                                    f'Вказуйте ціну в гривнях!', parse_mode='HTML')
            bot.register_next_step_handler(msg, parcel_price)
        else:
            msg = bot.reply_to(message, "Треба надіслати фото...")
            bot.register_next_step_handler(msg, parcel_image)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


def parcel_price(message):
    try:
        price = message.text
        if not price.isdigit() or int(price) < 0:
            msg = bot.reply_to(message, f'<b>Ви ввели недопустиме значення. Спробуйте ще раз</b>', parse_mode='HTML')
            bot.register_next_step_handler(msg, parcel_price)
            return

        parcel_info = parcel_info_dict[message.from_user.id]
        parcel_info.price = price

        msg = bot.send_message(message.chat.id, f'<b>Додайте короткий опис вашої посилки</b>\n'
                                                f'(Наприклад, укажіть вагу посилки, її розміри. '
                                                f'Якщо вона хрупка, обов\'язково вкажіть це)', parse_mode='HTML')
        bot.register_next_step_handler(msg, parcel_description)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


def parcel_description(message):
    try:
        id_user = message.from_user.id

        parcel_info = parcel_info_dict[message.from_user.id]
        parcel_info.description = message.text

        sql = 'INSERT INTO parcel_info(city_a, address_a, lon_a, lat_a, city_b, address_b, lon_b, lat_b, ' \
              'date_parcel, photo, price, description, id_user, status) ' \
              'VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'
        val = (parcel_info.city_a, parcel_info.address_a, parcel_info.lon_a, parcel_info.lat_a, parcel_info.city_b,
               parcel_info.address_b, parcel_info.lon_b, parcel_info.lat_b, parcel_info.date, parcel_info.photo,
               parcel_info.price, parcel_info.description, id_user, parcel_info.status)
        cursor.execute(sql, val)
        db_connection.commit()

        print(cursor.rowcount, "record inserted.")

        del parcel_info_dict[message.from_user.id]

        bot.send_message(message.chat.id, f'<b>🥳Ви опублікували нове оголошення</b>\n'
                                          f'Очікуйте поки хтось прийме його⏳', parse_mode='HTML')
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


def send_car_info_call(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    return bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                 text=f'<b>Інформація по вашій машині:</b>\n'
                                      f'❗Натисність на поле, щоб змінити його значення',
                                 reply_markup=get_car_inline_delete(int(call.data)), parse_mode='HTML')


def change_description(message):
    try:
        sql = f'UPDATE car_info SET car_description = \'{message.text}\' ' \
              f'WHERE id_car = {current_car[message.from_user.id]};'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) affected")
        send_car_info(message)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


def change_number(message):
    try:
        sql = f'UPDATE car_info SET car_number = \'{message.text}\' WHERE id_car = {current_car[message.from_user.id]};'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) affected")
        send_car_info(message)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


def change_year(message):
    try:
        car_year = message.text
        if not car_year.isdigit() or int(message.text) > 2022 or int(message.text) < 1975:
            msg = bot.reply_to(message, f'<b>Ви ввели недопустиме значення. Спробуйте ще раз</b>', parse_mode='HTML')
            bot.register_next_step_handler(msg, change_year)
            return

        sql = f'UPDATE car_info SET car_year = {int(message.text)} WHERE id_car = {current_car[message.from_user.id]};'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) affected")

        send_car_info(message)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


def change_color(message):
    try:
        sql = f'UPDATE car_info SET car_color = \'{message.text}\' WHERE id_car = {current_car[message.from_user.id]};'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) affected")

        send_car_info(message)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


# noinspection PyBroadException
def change_model(message):
    try:
        sql = f'UPDATE car_info SET car_model = \'{message.text}\' WHERE id_car = {current_car[message.from_user.id]};'
        cursor.execute(sql)
        db_connection.commit()
        print(cursor.rowcount, "record(s) affected")

        send_car_info(message)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


# noinspection PyBroadException
def change_brand(message):
    try:
        sql = f'UPDATE car_info SET car_brand = \'{message.text}\' WHERE id_car = {current_car[message.from_user.id]};'
        cursor.execute(sql)
        db_connection.commit()

        print(cursor.rowcount, "record(s) affected")

        send_car_info(message)

    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


def send_car_info(message):
    return bot.send_message(message.chat.id,
                            f'<b>Інформація по вашій машині:</b>\n❗Натисність на поле, щоб змінити його значення',
                            reply_markup=get_car_inline_delete(current_car[message.from_user.id]), parse_mode='HTML')


def set_current_car(call):
    message = call.data
    car_id = message.split('-')[-1]
    current_car[call.from_user.id] = car_id


def get_car_inline(id_car):
    cursor.execute(f'SELECT * FROM car_info WHERE id_car = {id_car}')
    car_data = cursor.fetchone()

    inline_markup = types.InlineKeyboardMarkup()

    inline_markup.row(types.InlineKeyboardButton(f'Марка: {car_data[1]}', callback_data=f'brand-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Модель: {car_data[2]}', callback_data=f'model-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Тип кузова: {car_data[3]}', callback_data=f'type-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Колір: {car_data[4]}', callback_data=f'color-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Рік випуску: {car_data[5]}', callback_data=f'year-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Номерний знак: {car_data[6]}',
                                                 callback_data=f'number-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Короткий опис: {car_data[7]}',
                                                 callback_data=f'description-{car_data[0]}'))

    return inline_markup


def get_car_inline_delete(id_car):
    cursor.execute(f'SELECT * FROM car_info WHERE id_car = {id_car}')
    car_data = cursor.fetchone()

    inline_markup = types.InlineKeyboardMarkup()

    inline_markup.row(types.InlineKeyboardButton(f'Марка: {car_data[1]}', callback_data=f'brand-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Модель: {car_data[2]}', callback_data=f'model-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Тип кузова: {car_data[3]}', callback_data=f'type-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Колір: {car_data[4]}', callback_data=f'color-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Рік випуску: {car_data[5]}', callback_data=f'year-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Номерний знак: {car_data[6]}',
                                                 callback_data=f'number-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'Короткий опис: {car_data[7]}',
                                                 callback_data=f'description-{car_data[0]}'))
    inline_markup.row(types.InlineKeyboardButton(f'❌Видалити авто❌',
                                                 callback_data=f'delete-{car_data[0]}'))

    return inline_markup


# noinspection PyBroadException
def car_brand_next_step(message):
    try:
        car_info = CarInfo(message.text)
        car_info_dict[message.from_user.id] = car_info

        msg = bot.send_message(message.chat.id, f'<b>Яка модель вашого авто?</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, car_model_next_step)
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


# noinspection PyBroadException
def car_model_next_step(message):
    try:
        car_info = car_info_dict[message.from_user.id]
        car_info.car_model = message.text

        bot.send_message(message.chat.id, f'<b>Який тип кузова у вашого авто?</b>', reply_markup=get_type_inline(),
                         parse_mode='HTML')
        # bot.register_next_step_handler(msg, car_type_next_step)
    except Exception as e:
        bot.reply_to(message, "Щось пішло не так...")


def get_type_inline():
    inline_markup = types.InlineKeyboardMarkup()

    inline_markup.row(types.InlineKeyboardButton('Седан', callback_data='sedan'),
                      types.InlineKeyboardButton('Позашляховик / Кросовер', callback_data='SUV'))
    inline_markup.row(types.InlineKeyboardButton('Мінівен', callback_data='minivan'),
                      types.InlineKeyboardButton('Хетчбек', callback_data='hatchback'))
    inline_markup.row(types.InlineKeyboardButton('Універсал', callback_data='universal'),
                      types.InlineKeyboardButton('Купе', callback_data='coupe'))
    inline_markup.row(types.InlineKeyboardButton('Легковий фургон', callback_data='passenger_van'),
                      types.InlineKeyboardButton('Пікап', callback_data='pickup'))
    inline_markup.row(types.InlineKeyboardButton('Інше', callback_data='other'))

    return inline_markup


# noinspection PyBroadException
def car_type_next_step(message):
    try:
        car_info = car_info_dict[message.from_user.id]
        car_info.car_type = message.text

        msg = bot.send_message(message.chat.id, f'<b>Якого кольору ваше авто?</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, car_color_next_step)
    except Exception as e:
        bot.reply_to(message, "Щось пішло не так...")


# noinspection PyBroadException
def car_color_next_step(message):
    try:
        car_info = car_info_dict[message.from_user.id]
        car_info.car_color = message.text

        msg = bot.send_message(message.chat.id, f'<b>У якому році випустили вашу машину?</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, car_year_next_step)
    except Exception as e:
        bot.reply_to(message, "Щось пішло не так...")


# noinspection PyBroadException
def car_year_next_step(message):
    try:
        car_year = message.text

        if not car_year.isdigit() or int(message.text) > 2022 or int(message.text) < 1975:
            msg = bot.reply_to(message, f'<b>Ви ввели недопустиме значення. Спробуйте ще раз</b>', parse_mode='HTML')
            bot.register_next_step_handler(msg, car_year_next_step)
            return

        car_info = car_info_dict[message.from_user.id]
        car_info.car_year = car_year

        msg = bot.send_message(message.chat.id, f'<b>Який номерний знак авто?</b>', parse_mode='HTML')
        bot.register_next_step_handler(msg, car_number_next_step)
    except Exception as e:
        bot.reply_to(message, "Щось пішло не так...")


# noinspection PyBroadException
def car_number_next_step(message):
    try:
        car_info = car_info_dict[message.from_user.id]
        car_info.car_number = message.text

        msg = bot.send_message(message.chat.id, f'<b>Додайте короткий опис вашого авто.</b> Ваш опис допоможе комусь '
                                                f'обрати саме ваше авто для перевезення вантажу.\n(Наприклад, вкажіть '
                                                f'максимальну вагу вантажу, яку можете взяти з собою, розміри '
                                                f'багажника чи розміри буди, якщо авто грузове і тд.)',
                               parse_mode='HTML')
        bot.register_next_step_handler(msg, car_description_next_step)
    except Exception as e:
        bot.reply_to(message, "Щось пішло не так...")


# noinspection PyBroadException
def car_description_next_step(message):
    try:
        id_owner = message.from_user.id
        car_info = car_info_dict[id_owner]
        car_info.car_description = message.text

        sql = 'INSERT INTO car_info(car_brand, car_model, car_type, car_color, car_year, car_number, car_description,' \
              ' id_owner) VALUES(%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_car'
        val = (car_info.car_brand, car_info.car_model, car_info.car_type, car_info.car_color, car_info.car_year,
               car_info.car_number, car_info.car_description, id_owner)
        cursor.execute(sql, val)

        car_info.id_car = cursor.fetchone()[0]

        db_connection.commit()

        print(cursor.rowcount, "record inserted.")

        del car_info_dict[message.from_user.id]

        bot.send_message(message.chat.id, f'Тепер <b>{car_info.car_brand} {car_info.car_model}</b> може приймати '
                                          f'оголошення🥳', reply_markup=main_markup(message.from_user.id),
                         parse_mode="HTML")
    except Exception as e:
        print(e)
        bot.reply_to(message, "Щось пішло не так...")


# noinspection PyBroadException
def add_phone_car(message):
    try:
        if message.content_type == "contact":
            id_user = message.from_user.id
            phone = message.contact.phone_number

            sql = f'UPDATE users SET phone = {phone} WHERE id = {id_user};'
            cursor.execute(sql)
            db_connection.commit()

            msg = bot.send_message(message.chat.id, f'<b>Яка марка вашого авто?</b>', reply_markup=main_markup(id_user),
                                   parse_mode='HTML')
            bot.register_next_step_handler(msg, car_brand_next_step)

        else:
            bot.send_message(message.chat.id, f'Щось пішло не так! Спробуйте ще раз...',
                             reply_markup=main_markup(message.from_user.id), parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, "Щось пішло не так...")


def add_phone_advertisement(message):
    if message.content_type == "contact":
        id_user = message.from_user.id
        phone = message.contact.phone_number

        sql = f'UPDATE users SET phone = {phone} WHERE id = {id_user};'
        cursor.execute(sql)
        db_connection.commit()

        msg = bot.send_message(message.chat.id, f'В якому місті знаходиться посилка?📦',
                               reply_markup=main_markup(id_user))
        bot.register_next_step_handler(msg, parcel_city_a)
    else:
        bot.send_message(message.chat.id, f'Щось пішло не так! Спробуйте ще раз...',
                         reply_markup=main_markup(message.from_user.id), parse_mode="HTML")


def main_markup(id_owner):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    btn1 = types.KeyboardButton('Везти посилку📦')
    btn2 = types.KeyboardButton('Опублікувати оголошення 💬')
    btn3 = types.KeyboardButton('Мої оголошення 💬')
    btn4 = types.KeyboardButton('✅Мої поїздки')

    if get_number_of_cars(id_owner) > 0:
        btn5 = types.KeyboardButton(f'Моє авто ({get_number_of_cars(id_owner)}🚘)')
    else:
        btn5 = types.KeyboardButton('Додати своє авто 🚘')

    markup.row(btn1)
    markup.row(btn2, btn3)
    markup.row(btn4)
    markup.row(btn5)

    return markup


def get_number_of_cars(id_owner):
    cursor.execute(f'SELECT COUNT(*) FROM car_info WHERE id_owner = {id_owner};')
    count = cursor.fetchone()[0]
    return count


bot.polling(none_stop=True, interval=0)
