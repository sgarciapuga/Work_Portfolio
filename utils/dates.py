from datetime import datetime, timedelta

def is_month_end(date):
    return (date + timedelta(days=1)).month != date.month

def today():
    return datetime.today().strftime("%Y-%m-%d")
    
# add this alias so existing imports keep working
today_str = today