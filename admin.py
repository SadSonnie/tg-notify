"""
Admin functionality for Time Tracking Bot
"""

import os
from typing import List, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import db_manager

class AdminManager:
    def __init__(self):
        self.admin_user_id = int(os.getenv('ADMIN_USER_ID', 0))
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        env_admin = user_id == self.admin_user_id
        db_admin = self.is_db_admin(user_id)
        result = env_admin or db_admin
        return result
    
    def is_db_admin(self, user_id: int) -> bool:
        """Check if user is admin in database"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('SELECT is_admin FROM users WHERE user_id = %s', (user_id,))
            result = cursor.fetchone()
            return result and result[0]
    
    def get_admin_keyboard(self):
        """Get admin menu keyboard"""
        keyboard = [
            [
                InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
                InlineKeyboardButton("📋 Проекты", callback_data="admin_projects")
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
                InlineKeyboardButton("💾 Экспорт всех", callback_data="admin_export")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def get_all_users(self) -> List[Tuple]:
        """Get all users from database"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT 
                    u.user_id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    u.is_admin,
                    u.is_banned,
                    COUNT(te.id) as entries_count,
                    COALESCE(SUM(te.hours), 0) as total_hours
                FROM users u
                LEFT JOIN time_entries te ON u.user_id = te.user_id
                GROUP BY u.user_id, u.username, u.first_name, u.last_name, u.is_admin, u.is_banned
                ORDER BY total_hours DESC
            ''')
            return cursor.fetchall()
    
    def get_all_projects(self) -> List[Tuple]:
        """Get all projects from database"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT 
                    p.id,
                    p.name,
                    p.description,
                    p.is_active,
                    COUNT(te.id) as entries_count,
                    COALESCE(SUM(te.hours), 0) as total_hours
                FROM projects p
                LEFT JOIN time_entries te ON p.id = te.project_id
                GROUP BY p.id, p.name, p.description, p.is_active
                ORDER BY total_hours DESC
            ''')
            return cursor.fetchall()
    
    def add_project(self, name: str, description: str = None) -> bool:
        """Add new project"""
        try:
            with db_manager.get_cursor(dict_cursor=False) as cursor:
                cursor.execute(
                    'INSERT INTO projects (name, description) VALUES (%s, %s)',
                    (name, description)
                )
            return True
        except Exception:
            return False
    
    def toggle_project_status(self, project_id: int) -> bool:
        """Toggle project active status"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute(
                'UPDATE projects SET is_active = NOT is_active WHERE id = %s',
                (project_id,)
            )
            return cursor.rowcount > 0
    
    def delete_project(self, project_id: int) -> bool:
        """Delete project (only if no time entries)"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            # Check if project has time entries
            cursor.execute('SELECT COUNT(*) FROM time_entries WHERE project_id = %s', (project_id,))
            if cursor.fetchone()[0] > 0:
                return False
            
            cursor.execute('DELETE FROM projects WHERE id = %s', (project_id,))
            return cursor.rowcount > 0
    
    def toggle_user_admin(self, user_id: int) -> bool:
        """Toggle user admin status"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute(
                'UPDATE users SET is_admin = NOT is_admin WHERE user_id = %s',
                (user_id,)
            )
            return cursor.rowcount > 0
    
    def is_banned(self, user_id: int) -> bool:
        """Check if user is banned"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('SELECT is_banned FROM users WHERE user_id = %s', (user_id,))
            result = cursor.fetchone()
            return result and result[0]
    
    def ban_user(self, user_id: int) -> bool:
        """Ban user"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute(
                'UPDATE users SET is_banned = TRUE WHERE user_id = %s',
                (user_id,)
            )
            return cursor.rowcount > 0
    
    def unban_user(self, user_id: int) -> bool:
        """Unban user"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute(
                'UPDATE users SET is_banned = FALSE WHERE user_id = %s',
                (user_id,)
            )
            return cursor.rowcount > 0
    
    def get_users_keyboard(self, page: int = 0, page_size: int = 5):
        """Get users management keyboard"""
        users = self.get_all_users()
        total_pages = (len(users) - 1) // page_size + 1 if users else 1
        
        start_idx = page * page_size
        end_idx = start_idx + page_size
        page_users = users[start_idx:end_idx]
        
        keyboard = []
        
        for user_id, username, first_name, last_name, is_admin, is_banned, entries, hours in page_users:
            name = f"{first_name or ''} {last_name or ''}".strip()
            if not name:
                name = username or f"ID:{user_id}"
            
            admin_mark = "👑" if is_admin else ""
            ban_mark = "❌" if is_banned else ""
            button_text = f"{admin_mark}{ban_mark}{name} ({hours}ч)"
            
            keyboard.append([InlineKeyboardButton(
                button_text, callback_data=f"admin_user_{user_id}"
            )])
        
        # Navigation buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"admin_users_page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"admin_users_page_{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([
            InlineKeyboardButton("🔙 Админ меню", callback_data="admin_menu")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    def get_projects_keyboard(self, page: int = 0, page_size: int = 5):
        """Get projects management keyboard"""
        projects = self.get_all_projects()
        total_pages = (len(projects) - 1) // page_size + 1 if projects else 1
        
        start_idx = page * page_size
        end_idx = start_idx + page_size
        page_projects = projects[start_idx:end_idx]
        
        keyboard = []
        
        for proj_id, name, description, is_active, entries, hours in page_projects:
            status_mark = "✅" if is_active else "❌"
            button_text = f"{status_mark} {name} ({hours}ч)"
            
            keyboard.append([InlineKeyboardButton(
                button_text, callback_data=f"admin_project_{proj_id}"
            )])
        
        # Navigation buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"admin_projects_page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"admin_projects_page_{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([
            InlineKeyboardButton("➕ Добавить проект", callback_data="admin_add_project"),
            InlineKeyboardButton("🔙 Админ меню", callback_data="admin_menu")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    def get_user_detail_keyboard(self, user_id: int):
        """Get user detail management keyboard"""
        # Check if user is banned to show appropriate button
        is_banned = self.is_banned(user_id)
        
        keyboard = [
            [InlineKeyboardButton("👑 Переключить админа", callback_data=f"admin_toggle_user_{user_id}")],
            [InlineKeyboardButton("📊 Отчеты", callback_data=f"admin_user_reports_{user_id}")]
        ]
        
        # Add ban/unban button
        if is_banned:
            keyboard.append([InlineKeyboardButton("✅ Разбанить", callback_data=f"admin_unban_user_{user_id}")])
        else:
            keyboard.append([InlineKeyboardButton("🚫 Забанить", callback_data=f"admin_ban_user_{user_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_users")])
        
        return InlineKeyboardMarkup(keyboard)
    
    def get_project_detail_keyboard(self, project_id: int):
        """Get project detail management keyboard"""
        keyboard = [
            [InlineKeyboardButton("🔄 Переключить статус", callback_data=f"admin_toggle_project_{project_id}")],
            [InlineKeyboardButton("🗑 Удалить", callback_data=f"admin_delete_project_{project_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_projects")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def get_user_brief_info(self, user_id: int) -> str:
        """Get brief user information for management menu"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT u.username, u.first_name, u.last_name, u.is_admin, u.created_at,
                       COUNT(te.id) as total_entries,
                       COALESCE(SUM(te.hours), 0) as total_hours
                FROM users u
                LEFT JOIN time_entries te ON u.user_id = te.user_id
                WHERE u.user_id = %s
                GROUP BY u.user_id, u.username, u.first_name, u.last_name, u.is_admin, u.created_at
            ''', (user_id,))
            
            user_info = cursor.fetchone()
            if not user_info:
                return "❌ Пользователь не найден"
            
            username, first_name, last_name, is_admin, created_at, total_entries, total_hours = user_info
        
        name = f"{first_name or ''} {last_name or ''}".strip()
        if not name:
            name = username or f"ID:{user_id}"
        
        report = f"👤 Управление пользователем: {name}\n\n"
        report += f"🆔 ID: {user_id}\n"
        report += f"👑 Админ: {'Да' if is_admin else 'Нет'}\n"
        report += f"📊 Всего записей: {total_entries}\n"
        report += f"⏰ Всего часов: {total_hours}\n"
        report += f"📅 Регистрация: {created_at.strftime('%Y-%m-%d') if created_at else 'Неизвестно'}\n\n"
        report += "Выберите действие:"
        
        return report
    
    def get_user_stats(self, user_id: int) -> str:
        """Get detailed user statistics"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT username, first_name, last_name, is_admin, created_at
                FROM users WHERE user_id = %s
            ''', (user_id,))
            
            user_info = cursor.fetchone()
            if not user_info:
                return "❌ Пользователь не найден"
            
            username, first_name, last_name, is_admin, created_at = user_info
            
            # Get statistics
            cursor.execute('''
                SELECT 
                    COUNT(te.id) as total_entries,
                    SUM(te.hours) as total_hours,
                    MIN(te.date) as first_entry,
                    MAX(te.date) as last_entry
                FROM time_entries te
                WHERE te.user_id = %s
            ''', (user_id,))
            
            stats = cursor.fetchone()
            total_entries, total_hours, first_entry, last_entry = stats
            
            # Get project breakdown
            cursor.execute('''
                SELECT p.name, SUM(te.hours) as hours, COUNT(te.id) as entries
                FROM time_entries te
                JOIN projects p ON te.project_id = p.id
                WHERE te.user_id = %s
                GROUP BY p.id, p.name
                ORDER BY hours DESC
                LIMIT 5
            ''', (user_id,))
            
            top_projects = cursor.fetchall()
        
        name = f"{first_name or ''} {last_name or ''}".strip()
        if not name:
            name = username or f"ID:{user_id}"
        
        report = f"👤 Статистика пользователя: {name}\n\n"
        report += f"🆔 ID: {user_id}\n"
        report += f"👑 Админ: {'Да' if is_admin else 'Нет'}\n"
        report += f"📅 Регистрация: {created_at.strftime('%Y-%m-%d') if created_at else 'Неизвестно'}\n\n"
        
        if total_entries:
            report += f"📊 Всего записей: {total_entries}\n"
            report += f"⏰ Всего часов: {total_hours}\n"
            report += f"📅 Первая запись: {first_entry}\n"
            report += f"📅 Последняя запись: {last_entry}\n\n"
            
            if top_projects:
                report += "🏆 Топ проектов:\n"
                for project_name, hours, entries in top_projects:
                    report += f"   📋 {project_name}: {hours}ч ({entries} записей)\n"
        else:
            report += "❌ Записей времени нет"
        
        return report
    
    def get_project_stats(self, project_id: int) -> str:
        """Get detailed project statistics"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            # Get project info
            cursor.execute('''
                SELECT name, description, is_active, created_at
                FROM projects WHERE id = %s
            ''', (project_id,))
            
            project_info = cursor.fetchone()
            if not project_info:
                return "❌ Проект не найден"
            
            name, description, is_active, created_at = project_info
            
            # Get statistics
            cursor.execute('''
                SELECT 
                    COUNT(te.id) as total_entries,
                    SUM(te.hours) as total_hours,
                    COUNT(DISTINCT te.user_id) as users_count,
                    MIN(te.date) as first_entry,
                    MAX(te.date) as last_entry
                FROM time_entries te
                WHERE te.project_id = %s
            ''', (project_id,))
            
            stats = cursor.fetchone()
            total_entries, total_hours, users_count, first_entry, last_entry = stats
            
            # Get top contributors
            cursor.execute('''
                SELECT u.first_name, u.last_name, u.username, SUM(te.hours) as hours
                FROM time_entries te
                JOIN users u ON te.user_id = u.user_id
                WHERE te.project_id = %s
                GROUP BY u.user_id, u.first_name, u.last_name, u.username
                ORDER BY hours DESC
                LIMIT 5
            ''', (project_id,))
            
            top_users = cursor.fetchall()
        
        report = f"📋 Статистика проекта: {name}\n\n"
        report += f"🆔 ID: {project_id}\n"
        report += f"✅ Активен: {'Да' if is_active else 'Нет'}\n"
        report += f"📝 Описание: {description or 'Не указано'}\n"
        report += f"📅 Создан: {created_at.strftime('%Y-%m-%d') if created_at else 'Неизвестно'}\n\n"
        
        if total_entries:
            report += f"📊 Всего записей: {total_entries}\n"
            report += f"⏰ Всего часов: {total_hours}\n"
            report += f"👥 Участников: {users_count}\n"
            report += f"📅 Первая запись: {first_entry}\n"
            report += f"📅 Последняя запись: {last_entry}\n\n"
            
            if top_users:
                report += "🏆 Топ участников:\n"
                for first_name, last_name, username, hours in top_users:
                    user_name = f"{first_name or ''} {last_name or ''}".strip()
                    if not user_name:
                        user_name = username or "Неизвестный"
                    report += f"   👤 {user_name}: {hours}ч\n"
        else:
            report += "❌ Записей времени нет"
        
        return report
