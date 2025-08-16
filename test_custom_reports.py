#!/usr/bin/env python3
"""
Test script for custom period reports
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv()

from database import db_manager
from reports import ReportsManager

def test_custom_period_report():
    """Test custom period report functionality"""
    print("🧪 Testing Custom Period Report...")
    
    # Initialize reports manager
    reports = ReportsManager()
    
    # Test with a fake user ID (assuming user exists)
    test_user_id = 1
    
    # Test different date ranges
    test_cases = [
        {
            "name": "Last Week",
            "start": (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
            "end": datetime.now().strftime('%Y-%m-%d')
        },
        {
            "name": "Last Month", 
            "start": (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
            "end": datetime.now().strftime('%Y-%m-%d')
        },
        {
            "name": "Single Day",
            "start": datetime.now().strftime('%Y-%m-%d'),
            "end": datetime.now().strftime('%Y-%m-%d')
        }
    ]
    
    for case in test_cases:
        print(f"\n📊 Testing: {case['name']}")
        print(f"   Period: {case['start']} to {case['end']}")
        
        try:
            report = reports.get_custom_period_report(
                test_user_id, 
                case['start'], 
                case['end']
            )
            print(f"✅ Report generated successfully")
            print(f"📝 Report preview:")
            print("-" * 50)
            # Show first few lines of report
            lines = report.split('\n')
            for line in lines[:5]:
                print(f"   {line}")
            if len(lines) > 5:
                print(f"   ... ({len(lines) - 5} more lines)")
            print("-" * 50)
            
        except Exception as e:
            print(f"❌ Error generating report: {e}")
    
    print("\n🎉 Custom period report test completed!")

def test_calendar_generation():
    """Test calendar generation for reports"""
    print("\n🗓 Testing Report Calendar Generation...")
    
    # Import the calendar function
    from bot import generate_report_calendar
    
    current_date = datetime.now()
    
    try:
        calendar_markup = generate_report_calendar(current_date.year, current_date.month)
        print(f"✅ Calendar generated for {current_date.strftime('%B %Y')}")
        print(f"📱 Inline keyboard has {len(calendar_markup.inline_keyboard)} rows")
        
        # Check that we have proper structure
        expected_rows = ["Navigation", "Week header", "Week 1", "Week 2", "Week 3", "Week 4", "Week 5/6", "Back button"]
        actual_rows = len(calendar_markup.inline_keyboard)
        
        if actual_rows >= 5:  # At least navigation + week header + 3 weeks + back button
            print(f"✅ Calendar structure looks correct ({actual_rows} rows)")
        else:
            print(f"⚠️ Calendar structure might be incomplete ({actual_rows} rows)")
            
    except Exception as e:
        print(f"❌ Error generating calendar: {e}")

if __name__ == "__main__":
    print("🚀 Starting Custom Reports Test Suite")
    
    # Test database connection first
    if not db_manager.test_connection():
        print("❌ Database connection failed!")
        exit(1)
    
    print("✅ Database connection successful")
    
    # Run tests
    test_custom_period_report()
    test_calendar_generation()
    
    print("\n✨ All tests completed!")
