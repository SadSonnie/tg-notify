"""
Analytics module for Time Tracking Bot
Provides advanced analytics and insights
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import pandas as pd
from database import db_manager

class AnalyticsManager:
    def __init__(self):
        pass
    
    def get_user_productivity_trend(self, user_id: int, days: int = 30) -> Dict:
        """Get user productivity trend over specified days"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT 
                    date,
                    SUM(hours) as daily_hours,
                    COUNT(*) as entries_count
                FROM time_entries 
                WHERE user_id = %s AND date BETWEEN %s AND %s
                GROUP BY date
                ORDER BY date
            ''', (user_id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
            
            data = cursor.fetchall()
        
        if not data:
            return {
                'trend': 'no_data',
                'avg_daily_hours': 0,
                'total_days_worked': 0,
                'most_productive_day': None,
                'least_productive_day': None
            }
        
        daily_hours = [float(row[1]) for row in data]
        dates = [row[0] for row in data]
        
        avg_hours = sum(daily_hours) / len(daily_hours)
        max_hours_idx = daily_hours.index(max(daily_hours))
        min_hours_idx = daily_hours.index(min(daily_hours))
        
        # Simple trend calculation
        if len(daily_hours) >= 7:
            first_week_avg = sum(daily_hours[:7]) / 7
            last_week_avg = sum(daily_hours[-7:]) / 7
            if last_week_avg > first_week_avg * 1.1:
                trend = 'increasing'
            elif last_week_avg < first_week_avg * 0.9:
                trend = 'decreasing'
            else:
                trend = 'stable'
        else:
            trend = 'insufficient_data'
        
        return {
            'trend': trend,
            'avg_daily_hours': round(avg_hours, 2),
            'total_days_worked': len(data),
            'most_productive_day': {
                'date': dates[max_hours_idx],
                'hours': daily_hours[max_hours_idx]
            },
            'least_productive_day': {
                'date': dates[min_hours_idx],
                'hours': daily_hours[min_hours_idx]
            }
        }
    
    def get_team_efficiency_report(self) -> str:
        """Generate team efficiency report"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            # Get data for last 30 days
            cursor.execute('''
                SELECT 
                    u.first_name,
                    u.last_name,
                    u.username,
                    COUNT(te.id) as total_entries,
                    SUM(te.hours) as total_hours,
                    AVG(te.hours) as avg_entry_hours,
                    COUNT(DISTINCT te.date) as active_days
                FROM users u
                LEFT JOIN time_entries te ON u.user_id = te.user_id 
                    AND te.date >= CURRENT_DATE - INTERVAL '30 days'
                GROUP BY u.user_id, u.first_name, u.last_name, u.username
                HAVING SUM(te.hours) > 0
                ORDER BY total_hours DESC
                LIMIT 10
            ''')
            
            team_data = cursor.fetchall()
        
        if not team_data:
            return "📊 Нет данных за последние 30 дней"
        
        report = "📈 Отчет по эффективности команды (30 дней)\n\n"
        
        total_team_hours = sum(float(row[4] or 0) for row in team_data)
        
        for i, (first_name, last_name, username, entries, hours, avg_hours, active_days) in enumerate(team_data, 1):
            name = f"{first_name or ''} {last_name or ''}".strip()
            if not name:
                name = username or f"Пользователь #{i}"
            
            # Convert Decimal to float
            hours = float(hours or 0)
            avg_hours = float(avg_hours or 0)
            
            efficiency_score = hours / (active_days or 1)  # Hours per active day
            percentage = (hours / total_team_hours * 100) if total_team_hours > 0 else 0
            
            report += f"{i}. {name}\n"
            report += f"   📊 {hours:.1f}ч ({percentage:.1f}% команды)\n"
            report += f"   📅 {active_days} дней активности\n"
            report += f"   ⚡ {efficiency_score:.1f}ч/день\n"
            report += f"   📝 {entries} записей\n\n"
        
        report += f"👥 Общая продуктивность: {total_team_hours:.1f}ч"
        return report
    
    def get_project_health_report(self) -> str:
        """Generate project health report"""
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            cursor.execute('''
                SELECT 
                    p.name,
                    p.is_active,
                    COUNT(te.id) as total_entries,
                    SUM(te.hours) as total_hours,
                    COUNT(DISTINCT te.user_id) as unique_users,
                    COUNT(DISTINCT te.date) as active_days,
                    MAX(te.date) as last_activity,
                    MIN(te.date) as first_activity
                FROM projects p
                LEFT JOIN time_entries te ON p.id = te.project_id
                WHERE te.id IS NOT NULL
                GROUP BY p.id, p.name, p.is_active
                ORDER BY total_hours DESC
            ''')
            
            projects_data = cursor.fetchall()
        
        if not projects_data:
            return "📋 Нет данных по проектам"
        
        report = "🏗 Отчет о состоянии проектов\n\n"
        
        for name, is_active, entries, hours, users, active_days, last_activity, first_activity in projects_data:
            status = "🟢 Активен" if is_active else "🔴 Неактивен"
            
            # Convert Decimal to float
            hours = float(hours or 0)
            
            # Calculate project health score
            days_since_last = (datetime.now().date() - last_activity).days if last_activity else 999
            
            if days_since_last <= 3:
                health = "🟢 Отличное"
            elif days_since_last <= 7:
                health = "🟡 Хорошее"
            elif days_since_last <= 14:
                health = "🟠 Требует внимания"
            else:
                health = "🔴 Критическое"
            
            report += f"📋 **{name}**\n"
            report += f"   {status} | Здоровье: {health}\n"
            report += f"   ⏰ {hours:.1f}ч за все время\n"
            report += f"   👥 {users} участников\n"
            report += f"   📅 Последняя активность: {last_activity}\n"
            report += f"   📊 {entries} записей за {active_days} дней\n\n"
        
        return report
    
    def get_weekly_summary(self, user_id: int = None) -> str:
        """Get weekly summary for user or all users"""
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        with db_manager.get_cursor(dict_cursor=False) as cursor:
            if user_id:
                cursor.execute('''
                    SELECT 
                        EXTRACT(DOW FROM te.date) as day_of_week,
                        te.date,
                        SUM(te.hours) as hours,
                        COUNT(te.id) as entries,
                        STRING_AGG(DISTINCT p.name, ', ') as projects
                    FROM time_entries te
                    JOIN projects p ON te.project_id = p.id
                    WHERE te.user_id = %s AND te.date BETWEEN %s AND %s
                    GROUP BY te.date, EXTRACT(DOW FROM te.date)
                    ORDER BY te.date
                ''', (user_id, week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')))
                
                user_clause = f"для вас"
            else:
                cursor.execute('''
                    SELECT 
                        EXTRACT(DOW FROM te.date) as day_of_week,
                        te.date,
                        SUM(te.hours) as hours,
                        COUNT(te.id) as entries,
                        COUNT(DISTINCT te.user_id) as users
                    FROM time_entries te
                    WHERE te.date BETWEEN %s AND %s
                    GROUP BY te.date, EXTRACT(DOW FROM te.date)
                    ORDER BY te.date
                ''', (week_start.strftime('%Y-%m-%d'), week_end.strftime('%Y-%m-%d')))
                
                user_clause = f"для команды"
            
            week_data = cursor.fetchall()
        
        if not week_data:
            return f"📅 Нет данных за эту неделю {user_clause}"
        
        days_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        total_hours = sum(float(row[2] or 0) for row in week_data)
        total_entries = sum(row[3] for row in week_data)
        
        report = f"📅 Недельная сводка {user_clause}\n"
        report += f"({week_start.strftime('%d.%m')} - {week_end.strftime('%d.%m.%Y')})\n\n"
        
        # Create daily breakdown
        daily_hours = {int(row[0]): float(row[2] or 0) for row in week_data}
        
        for day_num in range(7):  # Monday = 1, Sunday = 0
            dow = 1 if day_num == 0 else day_num + 1  # Adjust for PostgreSQL DOW
            if day_num == 6:  # Sunday
                dow = 0
                
            hours = daily_hours.get(dow, 0)
            day_name = days_names[day_num]
            
            if hours > 0:
                report += f"{day_name}: {hours}ч ✅\n"
            else:
                report += f"{day_name}: 0ч ⭕\n"
        
        report += f"\n📊 Итого: {total_hours}ч ({total_entries} записей)"
        
        if not user_id and week_data:
            avg_daily = float(total_hours) / len(week_data)
            report += f"\n📈 Среднее за день: {avg_daily:.1f}ч"
        
        return report

# Global analytics manager instance
analytics_manager = AnalyticsManager()
