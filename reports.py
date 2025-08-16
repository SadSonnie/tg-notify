"""
Reports module for Time Tracking Bot
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any
import io
from database import db_manager

class ReportsManager:
    def __init__(self):
        pass
    
    def get_today_report(self, user_id: int) -> str:
        """Generate today's report for user"""
        today = datetime.now().strftime('%Y-%m-%d')
        
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT p.name, te.hours, te.description
                FROM time_entries te
                JOIN projects p ON te.project_id = p.id
                WHERE te.user_id = %s AND te.date = %s
                ORDER BY te.created_at
            ''', (user_id, today))
            
            entries = cursor.fetchall()
        
        if not entries:
            return f"📅 Сегодня ({datetime.now().strftime('%d.%m.%Y')})\n\n❌ Записей не найдено"
        
        total_hours = sum(float(entry[1]) for entry in entries)
        
        report = f"📅 Сегодня ({datetime.now().strftime('%d.%m.%Y')})\n\n"
        
        for project, hours, description in entries:
            hours = float(hours)
            report += f"📋 {project}: {hours}ч\n"
            if description:
                report += f"   📝 {description}\n"
            report += "\n"
        
        report += f"📊 Всего за день: {total_hours}ч"
        return report
    
    def get_week_report(self, user_id: int) -> str:
        """Generate week report for user"""
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT te.date, p.name, te.hours, te.description
                FROM time_entries te
                JOIN projects p ON te.project_id = p.id
                WHERE te.user_id = %s AND te.date BETWEEN %s AND %s
                ORDER BY te.date, te.created_at
            ''', (user_id, week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')))
            
            entries = cursor.fetchall()
        
        if not entries:
            return f"📊 Неделя ({week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m.%Y')})\n\n❌ Записей не найдено"
        
        # Group by date
        daily_totals = {}
        project_totals = {}
        total_week_hours = 0
        
        for date, project, hours, description in entries:
            hours = float(hours)  # Convert Decimal to float
            
            if isinstance(date, str):
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m')
            else:
                # date is already a datetime.date object from PostgreSQL
                formatted_date = date.strftime('%d.%m')
            
            if formatted_date not in daily_totals:
                daily_totals[formatted_date] = 0
            daily_totals[formatted_date] += hours
            
            if project not in project_totals:
                project_totals[project] = 0
            project_totals[project] += hours
            
            total_week_hours += hours
        
        report = f"📊 Неделя ({week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m.%Y')})\n\n"
        
        # Daily breakdown
        report += "📅 По дням:\n"
        for date, hours in sorted(daily_totals.items()):
            report += f"   {date}: {hours}ч\n"
        
        report += "\n📋 По проектам:\n"
        for project, hours in sorted(project_totals.items(), key=lambda x: x[1], reverse=True):
            report += f"   {project}: {hours}ч\n"
        
        report += f"\n📈 Всего за неделю: {total_week_hours}ч"
        return report
    
    def get_projects_report(self, user_id: int) -> str:
        """Generate projects report for user (last 30 days)"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT p.name, SUM(te.hours) as total_hours, COUNT(te.id) as entries_count
                FROM time_entries te
                JOIN projects p ON te.project_id = p.id
                WHERE te.user_id = %s AND te.date BETWEEN %s AND %s
                GROUP BY p.id, p.name
                ORDER BY total_hours DESC
            ''', (user_id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
            
            projects = cursor.fetchall()
        
        if not projects:
            return f"📋 Проекты (последние 30 дней)\n\n❌ Записей не найдено"
        
        total_hours = sum(float(project[1]) for project in projects)
        
        report = f"📋 Проекты (последние 30 дней)\n\n"
        
        for project_name, hours, entries_count in projects:
            hours = float(hours)  # Convert Decimal to float
            percentage = (hours / total_hours * 100) if total_hours > 0 else 0
            report += f"📊 {project_name}\n"
            report += f"   ⏰ {hours}ч ({percentage:.1f}%)\n"
            report += f"   📝 {entries_count} записей\n\n"
        
        report += f"📈 Всего: {float(total_hours)}ч"
        return report
    
    def get_custom_period_report(self, user_id: int, start_date: str, end_date: str) -> str:
        """Generate report for custom date period"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT te.date, p.name, te.hours, te.description
                FROM time_entries te
                JOIN projects p ON te.project_id = p.id
                WHERE te.user_id = %s AND te.date BETWEEN %s AND %s
                ORDER BY te.date, te.created_at
            ''', (user_id, start_date, end_date))
            
            entries = cursor.fetchall()
        
        # Format dates for display
        try:
            start_obj = datetime.strptime(start_date, '%Y-%m-%d')
            end_obj = datetime.strptime(end_date, '%Y-%m-%d')
            period_str = f"{start_obj.strftime('%d.%m.%Y')} - {end_obj.strftime('%d.%m.%Y')}"
        except ValueError:
            period_str = f"{start_date} - {end_date}"
        
        if not entries:
            return f"📊 Отчет за период ({period_str})\n\n❌ Записей не найдено"
        
        # Group by date and project
        daily_totals = {}
        project_totals = {}
        total_hours = 0
        
        for date, project, hours, description in entries:
            hours = float(hours)  # Convert Decimal to float
            
            # Format date for display
            if isinstance(date, str):
                date_obj = datetime.strptime(date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            else:
                # date is already a datetime.date object from PostgreSQL
                formatted_date = date.strftime('%d.%m.%Y')
            
            if formatted_date not in daily_totals:
                daily_totals[formatted_date] = 0
            daily_totals[formatted_date] += hours
            
            if project not in project_totals:
                project_totals[project] = 0
            project_totals[project] += hours
            
            total_hours += hours
        
        report = f"📊 Отчет за период ({period_str})\n\n"
        
        # Daily breakdown (only show if period is <= 31 days to avoid too long reports)
        days_count = len(daily_totals)
        if days_count <= 31:
            report += "📅 По дням:\n"
            for date, hours in sorted(daily_totals.items(), key=lambda x: datetime.strptime(x[0], '%d.%m.%Y')):
                report += f"   {date}: {hours}ч\n"
            report += "\n"
        
        # Project breakdown
        report += "📋 По проектам:\n"
        for project, hours in sorted(project_totals.items(), key=lambda x: x[1], reverse=True):
            percentage = (hours / total_hours * 100) if total_hours > 0 else 0
            report += f"   {project}: {hours}ч ({percentage:.1f}%)\n"
        
        # Calculate average per day
        avg_per_day = total_hours / days_count if days_count > 0 else 0
        
        report += f"\n📈 Всего: {total_hours}ч"
        report += f"\n📊 Рабочих дней: {days_count}"
        report += f"\n⚡ Среднее за день: {avg_per_day:.1f}ч"
        
        return report
    
    def export_to_csv(self, user_id: int, days: int = 30) -> io.BytesIO:
        """Export user's time entries to CSV"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        with db_manager.get_connection() as conn:
            query = '''
                SELECT 
                    te.date as "Дата",
                    p.name as "Проект",
                    te.hours as "Часы",
                    te.description as "Описание",
                    te.created_at as "Создано"
                FROM time_entries te
                JOIN projects p ON te.project_id = p.id
                WHERE te.user_id = %s AND te.date BETWEEN %s AND %s
                ORDER BY te.date DESC, te.created_at DESC
            '''
            
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(user_id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
            )
        
        # Convert date format
        df['Дата'] = pd.to_datetime(df['Дата']).dt.strftime('%d.%m.%Y')
        df['Создано'] = pd.to_datetime(df['Создано']).dt.strftime('%d.%m.%Y %H:%M')
        
        # Create CSV in memory
        output = io.BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        output.seek(0)
        
        return output
    
    def get_admin_report(self) -> str:
        """Generate admin report with all users' statistics"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            # Get total statistics
            cursor.execute('''
                SELECT 
                    COUNT(DISTINCT u.user_id) as users_count,
                    COUNT(DISTINCT p.id) as projects_count,
                    COUNT(te.id) as total_entries,
                    SUM(te.hours) as total_hours
                FROM users u
                LEFT JOIN time_entries te ON u.user_id = te.user_id
                LEFT JOIN projects p ON te.project_id = p.id
            ''')
            
            stats = cursor.fetchone()
            users_count, projects_count, total_entries, total_hours = stats
            
            # Get top users by hours (last 30 days)
            cursor.execute('''
                SELECT 
                    u.first_name,
                    u.last_name,
                    u.username,
                    SUM(te.hours) as total_hours
                FROM users u
                JOIN time_entries te ON u.user_id = te.user_id
                WHERE te.date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY u.user_id, u.first_name, u.last_name, u.username
                ORDER BY total_hours DESC
                LIMIT 10
            ''')
            
            top_users = cursor.fetchall()
            
            # Get top projects by hours (last 30 days)
            cursor.execute('''
                SELECT 
                    p.name,
                    SUM(te.hours) as total_hours,
                    COUNT(DISTINCT te.user_id) as users_count
                FROM projects p
                JOIN time_entries te ON p.id = te.project_id
                WHERE te.date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY p.id, p.name
                ORDER BY total_hours DESC
                LIMIT 10
            ''')
            
            top_projects = cursor.fetchall()
        
        report = "👑 Административный отчет\n\n"
        report += "📊 Общая статистика:\n"
        report += f"   👥 Пользователей: {users_count or 0}\n"
        report += f"   📋 Проектов: {projects_count or 0}\n"
        report += f"   📝 Записей: {total_entries or 0}\n"
        report += f"   ⏰ Часов: {float(total_hours or 0)}\n\n"
        
        if top_users:
            report += "🏆 Топ пользователей (30 дней):\n"
            for i, (first_name, last_name, username, hours) in enumerate(top_users, 1):
                name = f"{first_name or ''} {last_name or ''}".strip()
                if not name:
                    name = username or "Неизвестный"
                report += f"   {i}. {name}: {float(hours)}ч\n"
            report += "\n"
        
        if top_projects:
            report += "📈 Топ проектов (30 дней):\n"
            for i, (project_name, hours, users_count) in enumerate(top_projects, 1):
                report += f"   {i}. {project_name}: {float(hours)}ч ({users_count} польз.)\n"
        
        return report
