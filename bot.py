#!/usr/bin/env python3
"""
Telegram Bot for Employee Time Tracking
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
import pandas as pd
import calendar
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from dotenv import load_dotenv
from database import db_manager
from reports import ReportsManager
from admin import AdminManager
from analytics import analytics_manager

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
SELECTING_PROJECT, ENTERING_HOURS, ENTERING_DESCRIPTION, SELECTING_DATE = range(4)

class TimeTrackingBot:
    def __init__(self):
        # Test database connection
        if not db_manager.test_connection():
            logger.error("Failed to connect to PostgreSQL database!")
            raise Exception("Database connection failed")
        
        db_manager.init_database()
        self.reports = ReportsManager()
        self.admin = AdminManager()
        

    
    def register_user(self, user_id: int, username: str = None, 
                     first_name: str = None, last_name: str = None):
        """Register or update user in database"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name
            ''', (user_id, username, first_name, last_name))
    
    def get_projects(self) -> list:
        """Get all active projects"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('SELECT id, name FROM projects WHERE is_active = TRUE ORDER BY name')
            return cursor.fetchall()
    
    def add_time_entry(self, user_id: int, project_id: int, hours: float, 
                      description: str = None, date: str = None):
        """Add time entry to database"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
            
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                INSERT INTO time_entries (user_id, project_id, hours, description, date)
                VALUES (%s, %s, %s, %s, %s)
            ''', (user_id, project_id, hours, description, date))
    
    def get_user_entries(self, user_id: int, limit: int = 10) -> list:
        """Get recent time entries for user"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT te.id, p.name, te.hours, te.description, te.date, te.created_at
                FROM time_entries te
                JOIN projects p ON te.project_id = p.id
                WHERE te.user_id = %s
                ORDER BY te.date DESC, te.created_at DESC
                LIMIT %s
            ''', (user_id, limit))
            return cursor.fetchall()
    
    def get_user_entries_paginated(self, user_id: int, limit: int = 5, offset: int = 0) -> list:
        """Get paginated time entries for user"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT te.id, p.name, te.hours, te.description, te.date, te.created_at
                FROM time_entries te
                JOIN projects p ON te.project_id = p.id
                WHERE te.user_id = %s
                ORDER BY te.date DESC, te.created_at DESC
                LIMIT %s OFFSET %s
            ''', (user_id, limit, offset))
            return cursor.fetchall()
    
    def delete_time_entry(self, entry_id: int, user_id: int) -> bool:
        """Delete time entry (only if belongs to user)"""
        try:
            with db_manager.get_cursor(dict_cursor=False) as cursor:
                cursor.execute(
                    'DELETE FROM time_entries WHERE id = %s AND user_id = %s',
                    (entry_id, user_id)
                )
                return cursor.rowcount > 0
        except Exception:
            return False

def generate_calendar(year: int, month: int) -> InlineKeyboardMarkup:
    """Generate calendar keyboard for date selection"""
    # Russian month names
    russian_months = [
        "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    
    # Get calendar data
    cal = calendar.monthcalendar(year, month)
    month_name = russian_months[month]
    
    keyboard = []
    
    # Header with month/year and navigation
    keyboard.append([
        InlineKeyboardButton("◀️", callback_data=f"cal_prev_{year}_{month}"),
        InlineKeyboardButton(f"{month_name} {year}", callback_data="cal_ignore"),
        InlineKeyboardButton("▶️", callback_data=f"cal_next_{year}_{month}")
    ])
    
    # Days of week header (Russian)
    keyboard.append([
        InlineKeyboardButton("Пн", callback_data="cal_ignore"),
        InlineKeyboardButton("Вт", callback_data="cal_ignore"),
        InlineKeyboardButton("Ср", callback_data="cal_ignore"),
        InlineKeyboardButton("Чт", callback_data="cal_ignore"),
        InlineKeyboardButton("Пт", callback_data="cal_ignore"),
        InlineKeyboardButton("Сб", callback_data="cal_ignore"),
        InlineKeyboardButton("Вс", callback_data="cal_ignore")
    ])
    
    # Calendar days
    today = datetime.now().date()
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
            else:
                date_obj = datetime(year, month, day).date()
                # Don't allow future dates
                if date_obj > today:
                    row.append(InlineKeyboardButton(f"({day})", callback_data="cal_ignore"))
                else:
                    row.append(InlineKeyboardButton(str(day), callback_data=f"cal_select_{year}_{month}_{day}"))
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)

# Initialize bot instance
bot_instance = TimeTrackingBot()

async def check_user_ban(user_id: int) -> bool:
    """Check if user is banned"""
    return bot_instance.admin.is_banned(user_id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    
    # Check if user is banned
    if await check_user_ban(user.id):
        await update.message.reply_text("🚫 Ваш аккаунт заблокирован. Обратитесь к администратору.")
        return
    
    bot_instance.register_user(
        user.id, user.username, user.first_name, user.last_name
    )
    
    # Create persistent reply keyboard
    keyboard = [
        [KeyboardButton("➕ Добавить часы"), KeyboardButton("📊 Мои записи")],
        [KeyboardButton("📈 Отчеты"), KeyboardButton("🗑 Удалить записи")]
    ]
    
    # Add admin button if user is admin
    if bot_instance.admin.is_admin(user.id):
        keyboard.append([KeyboardButton("👑 Админ")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    welcome_text = f"""
👋 Привет, {user.first_name}!

Это бот для учета рабочих часов. Выберите действие:

💡 Для просмотра справки используйте /help
    """
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Check if user is banned for most actions (except admin actions)
    if not query.data.startswith("admin_") and await check_user_ban(user_id):
        await query.answer("🚫 Ваш аккаунт заблокирован")
        await query.edit_message_text("🚫 Ваш аккаунт заблокирован. Обратитесь к администратору.")
        return
    
    await query.answer()
    
    if query.data == "add_hours":
        return await start_add_hours(update, context)
    elif query.data == "my_entries":
        return await show_my_entries(update, context)
    elif query.data == "reports":
        return await show_reports_menu(update, context)
    elif query.data == "help":
        return await show_help(update, context)
    elif query.data == "admin_menu":
        return await show_admin_menu(update, context)
    elif query.data.startswith("report_cal_"):
        return await handle_report_calendar(update, context)
    elif query.data.startswith("report_"):
        return await handle_report(update, context)
    elif query.data.startswith("admin_"):
        return await handle_admin(update, context)
    elif query.data == "export_csv":
        return await export_user_csv(update, context)
    elif query.data.startswith("project_"):
        return await select_project(update, context)
    elif query.data.startswith("hours_"):
        return await select_hours(update, context)
    elif query.data.startswith("date_"):
        return await select_date(update, context)
    elif query.data == "skip_description":
        return await skip_description(update, context)
    elif query.data == "back_to_main":
        return await back_to_main(update, context)
    elif query.data.startswith("delete_entry_from_page_"):
        return await confirm_delete_entry_from_page(update, context)
    elif query.data.startswith("confirm_delete_from_page_"):
        return await delete_entry_from_page(update, context)
    elif query.data.startswith("delete_entry_"):
        return await confirm_delete_entry(update, context)
    elif query.data.startswith("confirm_delete_"):
        return await delete_entry(update, context)
    elif query.data == "delete_menu":
        return await show_delete_menu(update, context)
    elif query.data.startswith("entries_page_"):
        return await handle_entries_pagination(update, context)
    elif query.data.startswith("delete_entries_page_"):
        return await show_delete_entries_from_page(update, context)
    elif query.data.startswith("confirm_delete_project_"):
        return await confirm_delete_project(update, context)
    elif query.data.startswith("final_delete_project_"):
        return await delete_project(update, context)
    elif query.data.startswith("cal_"):
        return await handle_calendar(update, context)

async def start_add_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the process of adding hours"""
    user_id = update.effective_user.id
    
    # Check if user is banned
    if await check_user_ban(user_id):
        text = "🚫 Ваш аккаунт заблокирован. Обратитесь к администратору."
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return ConversationHandler.END
    
    projects = bot_instance.get_projects()
    
    if not projects:
        text = "❌ Нет доступных проектов. Обратитесь к администратору."
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return ConversationHandler.END
    
    keyboard = []
    for project_id, project_name in projects:
        keyboard.append([InlineKeyboardButton(
            project_name, callback_data=f"project_{project_id}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "📋 Выберите проект:"
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
    
    return SELECTING_PROJECT

async def select_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle project selection"""
    query = update.callback_query
    project_id = int(query.data.split("_")[1])
    
    # Store selected project in context
    context.user_data['selected_project_id'] = project_id
    
    # Get project name for display
    with db_manager.get_cursor(dict_cursor=False) as cursor:
        cursor.execute('SELECT name FROM projects WHERE id = %s', (project_id,))
        project_name = cursor.fetchone()[0]
    
    context.user_data['selected_project_name'] = project_name
    
    # Show hours selection
    keyboard = [
        [
            InlineKeyboardButton("0.5ч", callback_data="hours_0.5"),
            InlineKeyboardButton("1ч", callback_data="hours_1"),
            InlineKeyboardButton("2ч", callback_data="hours_2"),
            InlineKeyboardButton("4ч", callback_data="hours_4")
        ],
        [InlineKeyboardButton("✏️ Ввести вручную", callback_data="hours_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"⏱ Проект: {project_name}\nСколько часов добавить?",
        reply_markup=reply_markup
    )
    
    return ENTERING_HOURS

async def select_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle hours selection"""
    query = update.callback_query
    
    if query.data == "hours_custom":
        await query.edit_message_text(
            f"⏱ Проект: {context.user_data['selected_project_name']}\n"
            "Введите количество часов (например: 1.5):"
        )
        return ENTERING_HOURS
    
    # Extract hours from callback data
    hours = float(query.data.split("_")[1])
    context.user_data['selected_hours'] = hours
    
    # Show description input
    keyboard = [
        [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_description")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"⏱ Проект: {context.user_data['selected_project_name']}\n"
        f"⏰ Часы: {hours}\n\n"
        "📝 Введите краткое описание задачи или нажмите 'Пропустить':",
        reply_markup=reply_markup
    )
    
    return ENTERING_DESCRIPTION

async def handle_hours_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual hours input"""
    try:
        hours = float(update.message.text.replace(',', '.'))
        if hours <= 0 or hours > 24:
            await update.message.reply_text(
                "❌ Некорректное количество часов. Введите число от 0.1 до 24:"
            )
            return ENTERING_HOURS
        
        context.user_data['selected_hours'] = hours
        
        # Show description input
        keyboard = [
            [InlineKeyboardButton("⏭ Пропустить", callback_data="skip_description")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"⏱ Проект: {context.user_data['selected_project_name']}\n"
            f"⏰ Часы: {hours}\n\n"
            "📝 Введите краткое описание задачи или нажмите 'Пропустить':",
            reply_markup=reply_markup
        )
        
        return ENTERING_DESCRIPTION
        
    except ValueError:
        await update.message.reply_text(
            "❌ Некорректный формат. Введите число (например: 1.5):"
        )
        return ENTERING_HOURS

async def handle_description_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle description input or admin project creation"""
    text = update.message.text.strip()
    
    # Check if this is admin project creation
    if context.user_data.get('admin_action') == 'add_project':
        if bot_instance.admin.is_admin(update.effective_user.id):
            success = bot_instance.admin.add_project(text)
            if success:
                await update.message.reply_text(f"✅ Проект '{text}' создан!")
                # Show projects menu again
                text_menu = "📋 Управление проектами:"
                reply_markup = bot_instance.admin.get_projects_keyboard()
                await update.message.reply_text(text_menu, reply_markup=reply_markup)
            else:
                await update.message.reply_text(f"❌ Проект '{text}' уже существует!")
        context.user_data.clear()
        return ConversationHandler.END
    
    # Regular description input
    context.user_data['description'] = text
    return await show_date_selection(update, context)

async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skip description input"""
    context.user_data['description'] = None
    return await show_date_selection(update, context)

async def show_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show date selection options"""
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data=f"date_{today.strftime('%Y-%m-%d')}")],
        [InlineKeyboardButton("📅 Вчера", callback_data=f"date_{yesterday.strftime('%Y-%m-%d')}")],
        [InlineKeyboardButton("🗓 Календарь", callback_data="date_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"⏱ Проект: {context.user_data['selected_project_name']}\n"
        f"⏰ Часы: {context.user_data['selected_hours']}\n"
        f"📝 Описание: {context.user_data.get('description', 'Не указано')}\n\n"
        "📅 Выберите дату:"
    )
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
    
    return SELECTING_DATE

async def handle_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle calendar navigation and date selection"""
    query = update.callback_query
    data = query.data
    
    if data == "cal_ignore":
        await query.answer()
        return
    
    if data.startswith("cal_prev_") or data.startswith("cal_next_"):
        # Navigate calendar
        parts = data.split("_")
        year = int(parts[2])
        month = int(parts[3])
        
        if data.startswith("cal_prev_"):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        else:  # cal_next_
            month += 1
            if month == 13:
                month = 1
                year += 1
        
        # Don't allow navigation too far back or forward
        current_date = datetime.now()
        if year < current_date.year - 1 or year > current_date.year:
            await query.answer("❌ Недоступный период")
            return
        
        calendar_markup = generate_calendar(year, month)
        text = (
            f"⏱ Проект: {context.user_data['selected_project_name']}\n"
            f"⏰ Часы: {context.user_data['selected_hours']}\n"
            f"📝 Описание: {context.user_data.get('description', 'Не указано')}\n\n"
            "📅 Выберите дату:"
        )
        await query.edit_message_text(text, reply_markup=calendar_markup)
        return SELECTING_DATE
    
    elif data.startswith("cal_select_"):
        # Date selected
        parts = data.split("_")
        year = int(parts[2])
        month = int(parts[3])
        day = int(parts[4])
        
        date_str = f"{year}-{month:02d}-{day:02d}"
        
        # Save time entry
        user_id = update.effective_user.id
        project_id = context.user_data['selected_project_id']
        hours = context.user_data['selected_hours']
        description = context.user_data.get('description')
        
        bot_instance.add_time_entry(user_id, project_id, hours, description, date_str)
        
        # Format date for display
        formatted_date = f"{day:02d}.{month:02d}.{year}"
        
        success_text = (
            "✅ Запись добавлена!\n\n"
            f"⏱ Проект: {context.user_data['selected_project_name']}\n"
            f"⏰ Часы: {hours}\n"
            f"📝 Описание: {description or 'Не указано'}\n"
            f"📅 Дата: {formatted_date}"
        )
        
        # Answer callback query and send simple message without inline buttons
        await query.answer()
        await query.message.reply_text(success_text)
        
        # Clear user data
        context.user_data.clear()
        
        return ConversationHandler.END

async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle date selection"""
    query = update.callback_query
    
    if query.data == "date_custom":
        # Show calendar instead of text input
        current_date = datetime.now()
        calendar_markup = generate_calendar(current_date.year, current_date.month)
        
        text = (
            f"⏱ Проект: {context.user_data['selected_project_name']}\n"
            f"⏰ Часы: {context.user_data['selected_hours']}\n"
            f"📝 Описание: {context.user_data.get('description', 'Не указано')}\n\n"
            "📅 Выберите дату:"
        )
        
        await query.edit_message_text(text, reply_markup=calendar_markup)
        return SELECTING_DATE
    
    # Extract date from callback data (today/yesterday)
    date_str = query.data.split("_", 1)[1]
    
    # Save time entry
    user_id = update.effective_user.id
    project_id = context.user_data['selected_project_id']
    hours = context.user_data['selected_hours']
    description = context.user_data.get('description')
    
    bot_instance.add_time_entry(user_id, project_id, hours, description, date_str)
    
    # Format date for display
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    formatted_date = date_obj.strftime('%d.%m.%Y')
    
    success_text = (
        "✅ Запись добавлена!\n\n"
        f"⏱ Проект: {context.user_data['selected_project_name']}\n"
        f"⏰ Часы: {hours}\n"
        f"📝 Описание: {description or 'Не указано'}\n"
        f"📅 Дата: {formatted_date}"
    )
    
    # Answer callback query and send simple message without inline buttons
    await query.answer()
    await query.message.reply_text(success_text)
    
    # Clear user data
    context.user_data.clear()
    
    return ConversationHandler.END

async def handle_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle manual date input (fallback - should use calendar instead)"""
    await update.message.reply_text(
        "📅 Пожалуйста, используйте кнопки выбора даты выше или нажмите '🗓 Календарь' для выбора конкретной даты."
    )
    return SELECTING_DATE

async def show_my_entries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's recent time entries with pagination"""
    user_id = update.effective_user.id
    page = 0  # Default to first page
    return await show_my_entries_page(update, context, page)

async def show_my_entries_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Show user's time entries for a specific page"""
    user_id = update.effective_user.id
    entries_per_page = 5
    offset = page * entries_per_page
    
    # Get total count of entries
    with db_manager.get_cursor(dict_cursor=False) as cursor:
        cursor.execute('SELECT COUNT(*) FROM time_entries WHERE user_id = %s', (user_id,))
        total_entries = cursor.fetchone()[0]
    
    # Get entries for current page
    entries = bot_instance.get_user_entries_paginated(user_id, entries_per_page, offset)
    
    if not entries:
        text = "📊 У вас пока нет записей о времени."
        keyboard = []
    else:
        # Calculate total pages
        total_pages = (total_entries + entries_per_page - 1) // entries_per_page
        
        text = f"📊 Ваши последние записи (страница {page + 1} из {total_pages}):\n\n"
        total_hours = 0
        
        for i, entry in enumerate(entries, 1):
            entry_id, project_name, hours, description, date, created_at = entry
            total_hours += hours
            
            # Format date - handle both string and date objects
            try:
                if hasattr(date, 'strftime'):
                    # date is already a datetime.date object from PostgreSQL
                    formatted_date = date.strftime('%d.%m.%Y')
                else:
                    # date is a string
                    date_obj = datetime.strptime(str(date), '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
            except (ValueError, AttributeError):
                # Fallback - convert to string first
                formatted_date = str(date)
            
            text += f"{offset + i}. 📋 {project_name}\n"
            text += f"   ⏰ {hours}ч | 📅 {formatted_date}\n"
            if description:
                text += f"   📝 {description}\n"
            text += "\n"
        
        text += f"📈 Всего часов на странице: {total_hours}ч"
        
        # Create navigation keyboard
        keyboard = []
        
        # Navigation row
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"entries_page_{page-1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Вперёд ▶️", callback_data=f"entries_page_{page+1}"))
        
        if nav_row:
            keyboard.append(nav_row)
        
        # Delete button
        keyboard.append([InlineKeyboardButton("🗑 Удалить запись", callback_data=f"delete_entries_page_{page}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    # Send message
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
        if reply_markup:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.callback_query.message.reply_text(text)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def show_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reports menu"""
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="report_today")],
        [InlineKeyboardButton("📊 Неделя", callback_data="report_week")],
        [InlineKeyboardButton("📅 Выбрать даты", callback_data="report_custom")],
        [InlineKeyboardButton("📋 По проектам", callback_data="report_projects")],
        [InlineKeyboardButton("📈 Недельная сводка", callback_data="report_weekly_summary")],
        [InlineKeyboardButton("🚀 Продуктивность", callback_data="report_productivity")],
        [InlineKeyboardButton("💾 Экспорт CSV", callback_data="export_csv")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "📈 Выберите тип отчета:"
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def show_user_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Show reports menu for a specific user (admin function)"""
    # Store the target user_id in context for subsequent report handlers
    context.user_data['admin_target_user_id'] = user_id
    
    # Get user info for display
    with db_manager.get_cursor(dict_cursor=False) as cursor:
        cursor.execute('SELECT first_name, last_name, username FROM users WHERE user_id = %s', (user_id,))
        user_info = cursor.fetchone()
        
    if user_info:
        first_name, last_name, username = user_info
        user_display = f"{first_name or ''} {last_name or ''}" or username or f"ID {user_id}"
    else:
        user_display = f"ID {user_id}"
    
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="report_today")],
        [InlineKeyboardButton("📊 Неделя", callback_data="report_week")],
        [InlineKeyboardButton("📅 Выбрать даты", callback_data="report_custom")],
        [InlineKeyboardButton("📋 По проектам", callback_data="report_projects")],
        [InlineKeyboardButton("📈 Недельная сводка", callback_data="report_weekly_summary")],
        [InlineKeyboardButton("🚀 Продуктивность", callback_data="report_productivity")],
        [InlineKeyboardButton("💾 Экспорт CSV", callback_data="export_csv")],
        [InlineKeyboardButton("🔙 К пользователю", callback_data=f"admin_user_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"📈 Отчеты для: {user_display}\n\nВыберите тип отчета:"
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def handle_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle report generation"""
    query = update.callback_query
    user_id = update.effective_user.id
    report_type = query.data.split("_")[1]
    
    # Check if this is an admin viewing another user's reports
    target_user_id = context.user_data.get('admin_target_user_id', user_id)
    
    if report_type == "today":
        report_text = bot_instance.reports.get_today_report(target_user_id)
    elif report_type == "week":
        report_text = bot_instance.reports.get_week_report(target_user_id)
    elif report_type == "projects":
        report_text = bot_instance.reports.get_projects_report(target_user_id)
    elif report_type == "weekly":
        if len(query.data.split("_")) > 2 and query.data.split("_")[2] == "summary":
            report_text = analytics_manager.get_weekly_summary(target_user_id)
        else:
            report_text = bot_instance.reports.get_week_report(target_user_id)
    elif report_type == "custom":
        return await show_custom_date_selection(update, context)
    elif report_type == "productivity":
        productivity_data = analytics_manager.get_user_productivity_trend(target_user_id)
        
        # Convert dictionary to readable text
        if productivity_data['trend'] == 'no_data':
            report_text = "📈 Недостаточно данных для анализа продуктивности."
        else:
            trend_emoji = {
                'increasing': '📈 Растет',
                'decreasing': '📉 Снижается',
                'stable': '📊 Стабильная',
                'insufficient_data': '❓ Недостаточно данных'
            }.get(productivity_data['trend'], '❓ Неопределенная')
            
            most_prod_date = productivity_data['most_productive_day']['date']
            if hasattr(most_prod_date, 'strftime'):
                most_prod_formatted = most_prod_date.strftime('%d.%m.%Y')
            else:
                most_prod_formatted = str(most_prod_date)
                
            least_prod_date = productivity_data['least_productive_day']['date']
            if hasattr(least_prod_date, 'strftime'):
                least_prod_formatted = least_prod_date.strftime('%d.%m.%Y')
            else:
                least_prod_formatted = str(least_prod_date)
            
            report_text = f"""🚀 Отчет по продуктивности (30 дней)

{trend_emoji}
📈 Среднее в день: {productivity_data['avg_daily_hours']}ч
📅 Рабочих дней: {productivity_data['total_days_worked']}

🏆 Макс продуктивность:
   📅 {most_prod_formatted}
   ⏰ {productivity_data['most_productive_day']['hours']}ч

📉 Мин продуктивность:
   📅 {least_prod_formatted}
   ⏰ {productivity_data['least_productive_day']['hours']}ч"""
    else:
        report_text = "❌ Неизвестный тип отчета"
    
    # Send report without inline buttons - use persistent reply keyboard for navigation
    await query.answer()
    await query.message.reply_text(report_text)

async def export_user_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export user's data to CSV"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Check if this is an admin viewing another user's data
    target_user_id = context.user_data.get('admin_target_user_id', user_id)
    
    try:
        csv_data = bot_instance.reports.export_to_csv(target_user_id)
        
        # Send CSV file
        filename = f"timetrack_{target_user_id}_{datetime.now().strftime('%Y%m%d')}.csv"
        caption = "📊 Ваши данные экспортированы в CSV" if target_user_id == user_id else f"📊 Данные пользователя {target_user_id} экспортированы в CSV"
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=csv_data,
            filename=filename,
            caption=caption
        )
        
        await query.answer("✅ CSV файл отправлен!")
        
    except Exception as e:
        await query.answer(f"❌ Ошибка экспорта: {str(e)}")

async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin menu"""
    user_id = update.effective_user.id
    
    if not bot_instance.admin.is_admin(user_id):
        text = "❌ Доступ запрещен"
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.answer(text)
        else:
            await update.message.reply_text(text)
        return
    
    text = "👑 Административная панель:"
    reply_markup = bot_instance.admin.get_admin_keyboard()
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin actions"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not bot_instance.admin.is_admin(user_id):
        await query.answer("❌ Доступ запрещен")
        return
    
    action_parts = query.data.split("_")
    action = "_".join(action_parts[1:])
    
    if action == "users":
        text = "👥 Управление пользователями:"
        reply_markup = bot_instance.admin.get_users_keyboard()
        await query.edit_message_text(text, reply_markup=reply_markup)
        
    elif action == "projects":
        text = "📋 Управление проектами:"
        reply_markup = bot_instance.admin.get_projects_keyboard()
        await query.edit_message_text(text, reply_markup=reply_markup)
        
    elif action.startswith("projects_page_"):
        page = int(action.split("_")[2])
        text = "📋 Управление проектами:"
        reply_markup = bot_instance.admin.get_projects_keyboard(page)
        await query.edit_message_text(text, reply_markup=reply_markup)
        
    elif action == "stats":
        text = "📊 Выберите тип отчета:"
        keyboard = [
            [InlineKeyboardButton("📈 Основная статистика", callback_data="admin_basic_stats")],
            [InlineKeyboardButton("🚀 Продуктивность команды", callback_data="admin_team_efficiency")],
            [InlineKeyboardButton("📅 Недельная сводка команды", callback_data="admin_team_weekly")],
            [InlineKeyboardButton("🔙 Админ меню", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
        
    elif action.startswith("user_stats_"):
        target_user_id = int(action.split("_")[2])
        # Show reports menu for the selected user
        return await show_user_reports_menu(update, context, target_user_id)
        
    elif action.startswith("user_reports_"):
        target_user_id = int(action.split("_")[2])
        # Show reports menu for the selected user
        return await show_user_reports_menu(update, context, target_user_id)
        
    elif action.startswith("user_"):
        target_user_id = int(action.split("_")[1])
        # Show brief user info instead of full stats
        brief_text = bot_instance.admin.get_user_brief_info(target_user_id)
        reply_markup = bot_instance.admin.get_user_detail_keyboard(target_user_id)
        await query.edit_message_text(brief_text, reply_markup=reply_markup)
        
    elif action.startswith("project_stats_"):
        project_id = int(action.split("_")[2])
        stats_text = bot_instance.admin.get_project_stats(project_id)
        reply_markup = bot_instance.admin.get_project_detail_keyboard(project_id)
        try:
            await query.edit_message_text(stats_text, reply_markup=reply_markup)
        except Exception:
            # If message can't be edited (same content), just answer the callback
            await query.answer("✅ Статистика уже отображается")
        
    elif action.startswith("project_") and action.split("_")[1].isdigit():
        project_id = int(action.split("_")[1])
        stats_text = bot_instance.admin.get_project_stats(project_id)
        reply_markup = bot_instance.admin.get_project_detail_keyboard(project_id)
        await query.edit_message_text(stats_text, reply_markup=reply_markup)
        
    elif action.startswith("toggle_user_"):
        target_user_id = int(action.split("_")[2])
        success = bot_instance.admin.toggle_user_admin(target_user_id)
        if success:
            await query.answer("✅ Статус администратора изменен")
        else:
            await query.answer("❌ Ошибка изменения статуса")
        # Refresh user stats
        brief_text = bot_instance.admin.get_user_brief_info(target_user_id)
        reply_markup = bot_instance.admin.get_user_detail_keyboard(target_user_id)
        await query.edit_message_text(brief_text, reply_markup=reply_markup)
        
    elif action.startswith("ban_user_"):
        target_user_id = int(action.split("_")[2])
        return await confirm_ban_user(update, context, target_user_id)
        
    elif action.startswith("confirm_ban_user_"):
        target_user_id = int(action.split("_")[3])
        success = bot_instance.admin.ban_user(target_user_id)
        if success:
            await query.answer("✅ Пользователь заблокирован!")
        else:
            await query.answer("❌ Ошибка блокировки")
        # Refresh user info
        brief_text = bot_instance.admin.get_user_brief_info(target_user_id)
        reply_markup = bot_instance.admin.get_user_detail_keyboard(target_user_id)
        await query.edit_message_text(brief_text, reply_markup=reply_markup)
        
    elif action.startswith("unban_user_"):
        target_user_id = int(action.split("_")[2])
        success = bot_instance.admin.unban_user(target_user_id)
        if success:
            await query.answer("✅ Пользователь разблокирован!")
        else:
            await query.answer("❌ Ошибка разблокировки")
        # Refresh user info
        brief_text = bot_instance.admin.get_user_brief_info(target_user_id)
        reply_markup = bot_instance.admin.get_user_detail_keyboard(target_user_id)
        await query.edit_message_text(brief_text, reply_markup=reply_markup)
        
    elif action.startswith("toggle_project_"):
        project_id = int(action.split("_")[2])
        success = bot_instance.admin.toggle_project_status(project_id)
        if success:
            await query.answer("✅ Статус проекта изменен")
        else:
            await query.answer("❌ Ошибка изменения статуса")
        # Refresh project stats
        stats_text = bot_instance.admin.get_project_stats(project_id)
        reply_markup = bot_instance.admin.get_project_detail_keyboard(project_id)
        await query.edit_message_text(stats_text, reply_markup=reply_markup)
        
    elif action.startswith("delete_project_"):
        project_id = int(action.split("_")[2])
        return await confirm_delete_project(update, context, project_id)
    
    elif action == "add_project":
        await query.edit_message_text(
            "➕ Введите название нового проекта:"
        )
        context.user_data['admin_action'] = 'add_project'
        return ENTERING_DESCRIPTION  # Reuse state for project name input
    
    elif action == "basic_stats":
        report_text = bot_instance.reports.get_admin_report()
        keyboard = [
            [InlineKeyboardButton("🔙 К статистике", callback_data="admin_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(report_text, reply_markup=reply_markup)
    
    elif action == "team_efficiency":
        report_text = analytics_manager.get_team_efficiency_report()
        keyboard = [
            [InlineKeyboardButton("🔙 К статистике", callback_data="admin_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(report_text, reply_markup=reply_markup)
    
    elif action == "project_health":
        report_text = analytics_manager.get_project_health_report()
        keyboard = [
            [InlineKeyboardButton("🔙 К статистике", callback_data="admin_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(report_text, reply_markup=reply_markup)
    
    elif action == "team_weekly":
        report_text = analytics_manager.get_weekly_summary()  # Team summary (no user_id)
        keyboard = [
            [InlineKeyboardButton("🔙 К статистике", callback_data="admin_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(report_text, reply_markup=reply_markup)
    
    else:
        await query.answer("❌ Неизвестное действие")

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    help_text = """
📝 **Как пользоваться ботом:**

➕ **Добавить часы** - записать время работы
• Выберите проект
• Укажите количество часов
• Добавьте описание (опционально)
• Выберите дату

📊 **Мои записи** - посмотреть последние записи

📈 **Отчеты** - статистика и экспорт
• Отчет за сегодня
• Отчет за неделю
• Отчет по проектам
• Экспорт в CSV

👑 **Админ** (только для администраторов)
• Управление пользователями
• Управление проектами
• Статистика системы

ℹ️ Используйте кнопки меню для навигации!
    """
    
    # Send help without inline buttons - use persistent reply keyboard for navigation
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(help_text)
    else:
        await update.message.reply_text(help_text)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages from reply keyboard"""
    user_id = update.effective_user.id
    
    # Check if user is banned
    if await check_user_ban(user_id):
        await update.message.reply_text("🚫 Ваш аккаунт заблокирован. Обратитесь к администратору.")
        return
    
    text = update.message.text
    
    # Check if this is admin project creation first
    if context.user_data.get('admin_action') == 'add_project':
        return await handle_description_input(update, context)
    
    if text == "➕ Добавить часы":
        return await start_add_hours(update, context)
    elif text == "📊 Мои записи":
        return await show_my_entries(update, context)
    elif text == "📈 Отчеты":
        return await show_reports_menu(update, context)
    elif text == "ℹ️ Помощь":
        return await show_help(update, context)
    elif text == "🗑 Удалить записи":
        return await show_delete_menu(update, context)
    elif text == "👑 Админ":
        if bot_instance.admin.is_admin(update.effective_user.id):
            return await show_admin_menu(update, context)
        else:
            await update.message.reply_text("❌ Доступ запрещен")
    else:
        # Unknown command
        await update.message.reply_text(
            "❓ Неизвестная команда. Используйте кнопки меню внизу экрана."
        )

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu"""
    context.user_data.clear()
    
    # Create persistent reply keyboard
    keyboard = [
        [KeyboardButton("➕ Добавить часы"), KeyboardButton("📊 Мои записи")],
        [KeyboardButton("📈 Отчеты"), KeyboardButton("🗑 Удалить записи")]
    ]
    
    # Add admin button if user is admin
    if bot_instance.admin.is_admin(update.effective_user.id):
        keyboard.append([KeyboardButton("👑 Админ")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    text = "🏠 Главное меню:"
    
    if hasattr(update, 'callback_query') and update.callback_query:
        # Answer callback query first
        await update.callback_query.answer()
        # Send new message instead of editing (can't change keyboard type)
        await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
    
    return ConversationHandler.END

async def show_delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show menu for deleting entries"""
    user_id = update.effective_user.id
    entries = bot_instance.get_user_entries(user_id, 10)
    
    if not entries:
        text = "🗑 У вас пока нет записей для удаления."
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text)
        else:
            await update.message.reply_text(text)
        return
    
    keyboard = []
    text = "🗑 Выберите запись для удаления:\n\n"
    
    for entry in entries:
        entry_id, project_name, hours, description, date, created_at = entry
        
        # Format date - handle both string and date objects
        try:
            if hasattr(date, 'strftime'):
                formatted_date = date.strftime('%d.%m.%Y')
            else:
                date_obj = datetime.strptime(str(date), '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
        except (ValueError, AttributeError):
            formatted_date = str(date)
        
        # Create button text
        button_text = f"📋 {project_name} - {hours}ч ({formatted_date})"
        if len(button_text) > 64:  # Telegram button text limit
            button_text = f"{project_name[:15]}... - {hours}ч ({formatted_date})"
        
        keyboard.append([InlineKeyboardButton(
            button_text, callback_data=f"delete_entry_{entry_id}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def confirm_delete_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm deletion of entry"""
    query = update.callback_query
    entry_id = int(query.data.split("_")[2])
    user_id = update.effective_user.id
    
    # Get entry details
    with db_manager.get_cursor(dict_cursor=False) as cursor:
        cursor.execute('''
            SELECT te.id, p.name, te.hours, te.description, te.date
            FROM time_entries te
            JOIN projects p ON te.project_id = p.id
            WHERE te.id = %s AND te.user_id = %s
        ''', (entry_id, user_id))
        
        entry = cursor.fetchone()
        if not entry:
            await query.answer("❌ Запись не найдена")
            return
    
    entry_id, project_name, hours, description, date = entry
    
    # Format date
    try:
        if hasattr(date, 'strftime'):
            formatted_date = date.strftime('%d.%m.%Y')
        else:
            date_obj = datetime.strptime(str(date), '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d.%m.%Y')
    except (ValueError, AttributeError):
        formatted_date = str(date)
    
    text = (
        f"⚠️ Подтвердите удаление:\n\n"
        f"⛱ Проект: {project_name}\n"
        f"⏰ Часы: {hours}\n"
        f"📝 Описание: {description or 'Не указано'}\n"
        f"📅 Дата: {formatted_date}"
    )
    
    keyboard = [
        [InlineKeyboardButton("❌ Удалить", callback_data=f"confirm_delete_{entry_id}")],
        [InlineKeyboardButton("🔙 Отмена", callback_data="delete_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def delete_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete the entry"""
    query = update.callback_query
    entry_id = int(query.data.split("_")[2])
    user_id = update.effective_user.id
    
    success = bot_instance.delete_time_entry(entry_id, user_id)
    
    if success:
        await query.answer("✅ Запись удалена!")
        await query.message.reply_text("✅ Запись успешно удалена!")
    else:
        await query.answer("❌ Ошибка удаления")
        await query.message.reply_text("❌ Ошибка при удалении записи.")

async def handle_entries_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination for entries"""
    query = update.callback_query
    page = int(query.data.split("_")[2])
    return await show_my_entries_page(update, context, page)

async def show_delete_entries_from_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show delete menu for entries from current page"""
    query = update.callback_query
    page = int(query.data.split("_")[3])  # delete_entries_page_X
    user_id = update.effective_user.id
    
    entries_per_page = 5
    offset = page * entries_per_page
    entries = bot_instance.get_user_entries_paginated(user_id, entries_per_page, offset)
    
    if not entries:
        await query.answer("❌ Нет записей для удаления")
        return
    
    text = "🗑 Выберите запись для удаления:\n\n"
    keyboard = []
    
    for i, entry in enumerate(entries, 1):
        entry_id, project_name, hours, description, date, created_at = entry
        
        # Format date - handle both string and date objects
        try:
            if hasattr(date, 'strftime'):
                formatted_date = date.strftime('%d.%m.%Y')
            else:
                date_obj = datetime.strptime(str(date), '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
        except (ValueError, AttributeError):
            formatted_date = str(date)
        
        # Create button text
        button_text = f"{offset + i}. 📋 {project_name} - {hours}ч ({formatted_date})"
        if len(button_text) > 64:  # Telegram button text limit
            button_text = f"{offset + i}. {project_name[:15]}... - {hours}ч ({formatted_date})"
        
        keyboard.append([InlineKeyboardButton(
            button_text, callback_data=f"delete_entry_from_page_{entry_id}_{page}"
        )])
    
    # Back button
    keyboard.append([InlineKeyboardButton(
        "🔙 Назад к записям", callback_data=f"entries_page_{page}"
    )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def confirm_delete_entry_from_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm deletion of entry from page"""
    query = update.callback_query
    data_parts = query.data.split("_")
    entry_id = int(data_parts[4])
    page = int(data_parts[5])
    user_id = update.effective_user.id
    
    # Get entry details
    with db_manager.get_cursor(dict_cursor=False) as cursor:
        cursor.execute('''
            SELECT te.id, p.name, te.hours, te.description, te.date
            FROM time_entries te
            JOIN projects p ON te.project_id = p.id
            WHERE te.id = %s AND te.user_id = %s
        ''', (entry_id, user_id))
        
        entry = cursor.fetchone()
        if not entry:
            await query.answer("❌ Запись не найдена")
            return
    
    entry_id, project_name, hours, description, date = entry
    
    # Format date
    try:
        if hasattr(date, 'strftime'):
            formatted_date = date.strftime('%d.%m.%Y')
        else:
            date_obj = datetime.strptime(str(date), '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d.%m.%Y')
    except (ValueError, AttributeError):
        formatted_date = str(date)
    
    text = (
        f"⚠️ Подтвердите удаление:\n\n"
        f"📋 Проект: {project_name}\n"
        f"⏰ Часы: {hours}\n"
        f"📝 Описание: {description or 'Не указано'}\n"
        f"📅 Дата: {formatted_date}"
    )
    
    keyboard = [
        [InlineKeyboardButton("❌ Удалить", callback_data=f"confirm_delete_from_page_{entry_id}_{page}")],
        [InlineKeyboardButton("🔙 Отмена", callback_data=f"delete_entries_page_{page}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def delete_entry_from_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete entry and return to page"""
    query = update.callback_query
    data_parts = query.data.split("_")
    entry_id = int(data_parts[4])
    page = int(data_parts[5])
    user_id = update.effective_user.id
    
    success = bot_instance.delete_time_entry(entry_id, user_id)
    
    if success:
        await query.answer("✅ Запись удалена!")
        # Return to the entries page
        return await show_my_entries_page(update, context, page)
    else:
        await query.answer("❌ Ошибка удаления")
        return await show_my_entries_page(update, context, page)

async def confirm_delete_project(update: Update, context: ContextTypes.DEFAULT_TYPE, project_id: int = None):
    """Confirm deletion of project"""
    query = update.callback_query
    
    if project_id is None:
        project_id = int(query.data.split("_")[3])
    
    user_id = update.effective_user.id
    
    if not bot_instance.admin.is_admin(user_id):
        await query.answer("❌ Доступ запрещен")
        return
    
    # Get project details
    with db_manager.get_cursor(dict_cursor=False) as cursor:
        cursor.execute('SELECT name FROM projects WHERE id = %s', (project_id,))
        result = cursor.fetchone()
        if not result:
            await query.answer("❌ Проект не найден")
            return
        
        project_name = result[0]
        
        # Check if project has time entries
        cursor.execute('SELECT COUNT(*) FROM time_entries WHERE project_id = %s', (project_id,))
        entry_count = cursor.fetchone()[0]
    
    if entry_count > 0:
        text = (
            f"⚠️ Внимание! Проект '{project_name}' содержит данные!\n\n"
            f"📊 По нему есть {entry_count} записей о времени.\n\n"
            "🔄 Рекомендуется деактивировать проект вместо удаления.\n"
            "❌ При удалении ВСЕ записи времени по проекту будут потеряны навсегда!"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Деактивировать (рекомендуется)", callback_data=f"admin_toggle_project_{project_id}")],
            [InlineKeyboardButton("❌ Всё равно удалить", callback_data=f"final_delete_project_{project_id}")],
            [InlineKeyboardButton("🔙 Отмена", callback_data=f"admin_project_{project_id}")]
        ]
    else:
        text = (
            f"⚠️ Подтвердите удаление проекта:\n\n"
            f"📋 Проект: {project_name}\n\n"
            "❌ Проект будет удалён навсегда!"
        )
        keyboard = [
            [InlineKeyboardButton("❌ Удалить", callback_data=f"final_delete_project_{project_id}")],
            [InlineKeyboardButton("🔙 Отмена", callback_data=f"admin_project_{project_id}")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def confirm_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None):
    """Confirm banning of user"""
    query = update.callback_query
    
    if user_id is None:
        user_id = int(query.data.split("_")[2])
    
    admin_id = update.effective_user.id
    
    if not bot_instance.admin.is_admin(admin_id):
        await query.answer("❌ Доступ запрещен")
        return
    
    # Get user details
    with db_manager.get_cursor(dict_cursor=False) as cursor:
        cursor.execute('SELECT first_name, last_name, username FROM users WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        if not result:
            await query.answer("❌ Пользователь не найден")
            return
        
        first_name, last_name, username = result
    
    name = f"{first_name or ''} {last_name or ''}".strip()
    if not name:
        name = username or f"ID {user_id}"
    
    text = (
        f"⚠️ Подтвердите блокировку пользователя:\n\n"
        f"👤 Пользователь: {name}\n\n"
        "🚫 Пользователь не сможет пользоваться ботом!"
    )
    
    keyboard = [
        [InlineKeyboardButton("❌ Забанить", callback_data=f"admin_confirm_ban_user_{user_id}")],
        [InlineKeyboardButton("🔙 Отмена", callback_data=f"admin_user_{user_id}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)

async def delete_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete the project (with force option)"""
    query = update.callback_query
    project_id = int(query.data.split("_")[3])
    user_id = update.effective_user.id
    
    if not bot_instance.admin.is_admin(user_id):
        await query.answer("❌ Доступ запрещен")
        return
    
    try:
        # Get project name for logging
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('SELECT name FROM projects WHERE id = %s', (project_id,))
            result = cursor.fetchone()
            project_name = result[0] if result else f"ID {project_id}"
            
            # Delete all time entries for this project first
            cursor.execute('DELETE FROM time_entries WHERE project_id = %s', (project_id,))
            deleted_entries = cursor.rowcount
            
            # Then delete the project
            cursor.execute('DELETE FROM projects WHERE id = %s', (project_id,))
            success = cursor.rowcount > 0
        
        if success:
            if deleted_entries > 0:
                await query.answer(f"✅ Проект удалён! ({deleted_entries} записей удалено)")
            else:
                await query.answer("✅ Проект удалён!")
            
            # Return to projects menu
            text = "📋 Управление проектами:"
            reply_markup = bot_instance.admin.get_projects_keyboard()
            await query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await query.answer("❌ Ошибка удаления")
            # Return to project details
            stats_text = bot_instance.admin.get_project_stats(project_id)
            reply_markup = bot_instance.admin.get_project_detail_keyboard(project_id)
            await query.edit_message_text(stats_text, reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Error deleting project {project_id}: {e}")
        await query.answer("❌ Ошибка удаления")
        # Return to project details
        try:
            stats_text = bot_instance.admin.get_project_stats(project_id)
            reply_markup = bot_instance.admin.get_project_detail_keyboard(project_id)
            await query.edit_message_text(stats_text, reply_markup=reply_markup)
        except:
            # If even returning to project details fails, go to projects list
            text = "📋 Управление проектами:"
            reply_markup = bot_instance.admin.get_projects_keyboard()
            await query.edit_message_text(text, reply_markup=reply_markup)

async def show_custom_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show custom date selection for reports"""
    query = update.callback_query
    
    text = "📅 Выберите период для отчета:\n\nСначала выберите дату НАЧАЛА периода:"
    
    current_date = datetime.now()
    calendar_markup = generate_report_calendar(current_date.year, current_date.month)
    
    await query.edit_message_text(text, reply_markup=calendar_markup)

def generate_report_calendar(year: int, month: int) -> InlineKeyboardMarkup:
    """Generate calendar keyboard for report date selection (allows future dates)"""
    # Russian month names
    russian_months = [
        "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    
    # Get calendar data
    cal = calendar.monthcalendar(year, month)
    month_name = russian_months[month]
    
    keyboard = []
    
    # Header with month/year and navigation
    keyboard.append([
        InlineKeyboardButton("◀️", callback_data=f"report_cal_prev_{year}_{month}"),
        InlineKeyboardButton(f"{month_name} {year}", callback_data="report_cal_ignore"),
        InlineKeyboardButton("▶️", callback_data=f"report_cal_next_{year}_{month}")
    ])
    
    # Days of week header (Russian)
    keyboard.append([
        InlineKeyboardButton("Пн", callback_data="report_cal_ignore"),
        InlineKeyboardButton("Вт", callback_data="report_cal_ignore"),
        InlineKeyboardButton("Ср", callback_data="report_cal_ignore"),
        InlineKeyboardButton("Чт", callback_data="report_cal_ignore"),
        InlineKeyboardButton("Пт", callback_data="report_cal_ignore"),
        InlineKeyboardButton("Сб", callback_data="report_cal_ignore"),
        InlineKeyboardButton("Вс", callback_data="report_cal_ignore")
    ])
    
    # Calendar days
    today = datetime.now().date()
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="report_cal_ignore"))
            else:
                date_obj = datetime(year, month, day).date()
                # Allow all dates including future ones for reports
                row.append(InlineKeyboardButton(str(day), callback_data=f"report_cal_select_{year}_{month}_{day}"))
        keyboard.append(row)
    
    # Back to reports menu button
    keyboard.append([
        InlineKeyboardButton("🔙 Назад к отчетам", callback_data="reports")
    ])
    
    return InlineKeyboardMarkup(keyboard)

async def handle_report_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle calendar navigation and date selection for reports"""
    query = update.callback_query
    data = query.data
    
    if data == "report_cal_ignore":
        await query.answer()
        return
    
    if data.startswith("report_cal_prev_") or data.startswith("report_cal_next_"):
        # Navigate calendar
        parts = data.split("_")
        year = int(parts[3])
        month = int(parts[4])
        
        if data.startswith("report_cal_prev_"):
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        else:  # report_cal_next_
            month += 1
            if month == 13:
                month = 1
                year += 1
        
        # Allow reasonable range for reports (2 years back, 1 year forward)
        current_date = datetime.now()
        if year < current_date.year - 2 or year > current_date.year + 1:
            await query.answer("❌ Недоступный период")
            return
        
        calendar_markup = generate_report_calendar(year, month)
        
        # Update text based on current selection state
        if context.user_data.get('report_start_date'):
            start_date = context.user_data['report_start_date']
            text = f"📅 Период для отчета:\n\nДата начала: {start_date}\n\nТеперь выберите дату ОКОНЧАНИЯ периода:"
        else:
            text = "📅 Выберите период для отчета:\n\nСначала выберите дату НАЧАЛА периода:"
        
        await query.edit_message_text(text, reply_markup=calendar_markup)
        return
    
    elif data.startswith("report_cal_select_"):
        # Date selected
        parts = data.split("_")
        year = int(parts[3])
        month = int(parts[4])
        day = int(parts[5])
        
        date_str = f"{year}-{month:02d}-{day:02d}"
        formatted_date = f"{day:02d}.{month:02d}.{year}"
        
        if not context.user_data.get('report_start_date'):
            # First date selection (start date)
            context.user_data['report_start_date'] = date_str
            context.user_data['report_start_date_formatted'] = formatted_date
            
            text = f"📅 Период для отчета:\n\nДата начала: {formatted_date}\n\nТеперь выберите дату ОКОНЧАНИЯ периода:"
            calendar_markup = generate_report_calendar(year, month)
            await query.edit_message_text(text, reply_markup=calendar_markup)
            
        else:
            # Second date selection (end date)
            start_date = context.user_data['report_start_date']
            start_date_formatted = context.user_data['report_start_date_formatted']
            
            # Validate date range
            try:
                start_obj = datetime.strptime(start_date, '%Y-%m-%d')
                end_obj = datetime.strptime(date_str, '%Y-%m-%d')
                
                if end_obj < start_obj:
                    await query.answer("❌ Дата окончания не может быть раньше даты начала!")
                    return
                
                # Check if period is not too long (max 365 days)
                if (end_obj - start_obj).days > 365:
                    await query.answer("❌ Период не может быть больше 365 дней!")
                    return
                    
            except ValueError:
                await query.answer("❌ Ошибка в датах")
                return
            
            # Generate custom period report
            user_id = update.effective_user.id
            # Check if this is an admin viewing another user's reports
            target_user_id = context.user_data.get('admin_target_user_id', user_id)
            report_text = bot_instance.reports.get_custom_period_report(target_user_id, start_date, date_str)
            
            # Clear user data
            context.user_data.pop('report_start_date', None)
            context.user_data.pop('report_start_date_formatted', None)
            
            # Send report
            await query.answer()
            await query.message.reply_text(report_text)

def main():
    """Start the bot"""
    # Get bot token from environment variable
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add conversation handler for adding hours
    add_hours_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_hours, pattern="^add_hours$"),
            MessageHandler(filters.Regex("^➕ Добавить часы$"), start_add_hours)
        ],
        states={
            SELECTING_PROJECT: [CallbackQueryHandler(select_project, pattern="^project_")],
            ENTERING_HOURS: [
                CallbackQueryHandler(select_hours, pattern="^hours_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_hours_input)
            ],
            ENTERING_DESCRIPTION: [
                CallbackQueryHandler(skip_description, pattern="^skip_description$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description_input)
            ],
            SELECTING_DATE: [
                CallbackQueryHandler(select_date, pattern="^date_"),
                CallbackQueryHandler(handle_calendar, pattern="^cal_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date_input)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$"),
            CommandHandler("start", start)
        ],
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", show_help))
    application.add_handler(add_hours_handler)  # ConversationHandler must be added before general MessageHandler
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
