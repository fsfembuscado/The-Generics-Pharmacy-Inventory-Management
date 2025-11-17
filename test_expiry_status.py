"""
Test script to verify expiry status logic
This script demonstrates the expiry status color indicators:
- Red (Expired): Past expiry date
- Yellow/Orange (Near Expiry): Within 6 months of expiry
- Green (Good): More than 6 months until expiry
"""

from datetime import date, timedelta

def get_expiry_status(expiry_date):
    """
    Determine expiry status based on expiry date
    Returns: tuple (status_name, color_indicator)
    """
    today = date.today()
    six_months_from_now = today + timedelta(days=180)
    
    if expiry_date < today:
        return ("Expired", "Red")
    elif expiry_date <= six_months_from_now:
        return ("Near Expiry", "Yellow/Orange")
    else:
        return ("Good", "Green")

# Test cases
print("Expiry Status Test Cases")
print("=" * 60)

today = date.today()
print(f"Today's date: {today.strftime('%B %d, %Y')}")
print()

# Test Case 1: Already expired
expired_date = today - timedelta(days=30)
status, color = get_expiry_status(expired_date)
print(f"1. Expired 30 days ago ({expired_date.strftime('%b %d, %Y')})")
print(f"   Status: {status} - Color: {color}")
print()

# Test Case 2: Expires in 5 months (within 6 month threshold)
near_expiry_date = today + timedelta(days=150)
status, color = get_expiry_status(near_expiry_date)
print(f"2. Expires in ~5 months ({near_expiry_date.strftime('%b %d, %Y')})")
print(f"   Status: {status} - Color: {color}")
print()

# Test Case 3: Expires exactly in 6 months
six_months_date = today + timedelta(days=180)
status, color = get_expiry_status(six_months_date)
print(f"3. Expires in exactly 6 months ({six_months_date.strftime('%b %d, %Y')})")
print(f"   Status: {status} - Color: {color}")
print()

# Test Case 4: Expires in 8 months (more than 6 months - good status)
good_date = today + timedelta(days=240)
status, color = get_expiry_status(good_date)
print(f"4. Expires in ~8 months ({good_date.strftime('%b %d, %Y')})")
print(f"   Status: {status} - Color: {color}")
print()

# Test Case 5: Expires tomorrow (within 6 months - near expiry)
tomorrow = today + timedelta(days=1)
status, color = get_expiry_status(tomorrow)
print(f"5. Expires tomorrow ({tomorrow.strftime('%b %d, %Y')})")
print(f"   Status: {status} - Color: {color}")
print()

print("=" * 60)
print("Summary:")
print("- Expired (Red): Medicine has passed its expiry date")
print("- Near Expiry (Yellow): Medicine expires within 6 months")
print("- Good (Green): Medicine expires in more than 6 months")
