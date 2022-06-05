from flask import Flask

import configure
import telebot
from telebot import types
import logging
import psycopg2
from flask import Flask, request

bot = telebot.TeleBot(configure.config["token"])

db_connection = psycopg2.connect(configure.config["db_URI"], sslmode="require")
db_cursor = db_connection.cursor()


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('Опублікувати оголошення 💬')
    btn2 = types.KeyboardButton('Додати своє авто 🚘')
    markup.row(btn1)
    markup.row(btn2)

    bot.send_message(message.chat.id, f'Вітаємо, <b>{message.from_user.first_name}</b>', reply_markup=markup,
                     parse_mode="HTML")


@bot.message_handler(func=lambda message: True)
def callback(message):
    if message.text == "Опублікувати оголошення 💬":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(types.KeyboardButton('Надіслати номер телефону 📲', request_contact=True))
        msg = bot.send_message(message.chat.id, f'Перед тим як опублікувати оголошення, додайте свій номер телефону 📲',
                               reply_markup=markup)

    elif message.text == "Додати своє авто 🚘":
        pass


bot.polling(none_stop=True, interval=0)
