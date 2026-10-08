const TelegramBot = require('node-telegram-bot-api');
const express = require('express');

// Ваш уникальный токен бота
const token = '8806421764:AAHB4im5Wf54ACw1KqlLT58qiIKE-QCiDEU';
const bot = new TelegramBot(token, {polling: true});

// Настраиваем сервер для раздачи HTML файлов из папки public
const app = express();
app.use(express.static('public')); 

// ВНИМАНИЕ: Сюда нужно вставить ссылку, которую выдаст Replit в правом верхнем углу (Webview)
// Она должна начинаться с https:// и заканчиваться на .replit.app
const webAppUrl = 'https://ВАШ-REPLIT-URL.replit.app'; 

// Логика бота при команде /start
bot.onText(/\/start/, (msg) => {
  const chatId = msg.chat.id;
  
  // Отправляем сообщение с кнопкой Web App
  bot.sendMessage(chatId, 'Привет, lMrVoltl! ⚡ Добро пожаловать в VOLTAGE LAB.\nЖми кнопку ниже, чтобы запустить симуляции.', {
    reply_markup: {
      inline_keyboard: [
        [{ text: 'Открыть лабораторию', web_app: { url: webAppUrl } }]
      ]
    }
  });
});

// Запускаем сервер
app.listen(3000, () => {
  console.log('Сервер VOLTAGE LAB успешно запущен на порту 3000!');
});
