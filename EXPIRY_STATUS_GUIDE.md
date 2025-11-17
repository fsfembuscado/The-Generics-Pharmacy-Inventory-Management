# Expiry Status Color Guide

## Visual Reference

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXPIRY STATUS INDICATORS                      │
└─────────────────────────────────────────────────────────────────┘

🟢 GOOD (Green)
   ┌─────────────┐
   │ ● Good      │  Background: #388e3c (Green)
   └─────────────┘  Text: White
   
   Condition: Expires in MORE than 6 months
   Action: Continue normal sales
   Priority: Low
   

🟡 NEAR EXPIRY (Orange/Yellow)
   ┌──────────────────┐
   │ ● Near Expiry    │  Background: #ffa000 (Orange)
   └──────────────────┘  Text: White
   
   Condition: Expires in 6 months or LESS (≤ 180 days)
   Action: Prioritize selling, consider discounts
   Priority: High
   

🔴 EXPIRED (Red)
   ┌─────────────┐
   │ ● Expired   │  Background: #d32f2f (Red)
   └─────────────┘  Text: White
   
   Condition: Past expiry date
   Action: Remove from inventory immediately
   Priority: Critical


═══════════════════════════════════════════════════════════════════

TIMELINE EXAMPLE:

Today: Nov 17, 2025

│<──────── EXPIRED ────────>│<───── NEAR EXPIRY ──────>│<─── GOOD ───>
│                           │                          │              │
│    Before Today           │  Today to May 16, 2026   │  After May   │
│    (Past dates)           │  (Next 6 months)         │  16, 2026    │
│                           │                          │              │
│    🔴 Red                 │  🟡 Orange               │  🟢 Green    │


═══════════════════════════════════════════════════════════════════

EXAMPLES:

1. Medicine expires on Oct 18, 2025 (30 days ago)
   Status: 🔴 Expired
   Display: Red badge "● Expired"

2. Medicine expires on Dec 15, 2025 (28 days from now)
   Status: 🟡 Near Expiry
   Display: Orange badge "● Near Expiry"

3. Medicine expires on Apr 16, 2026 (5 months from now)
   Status: 🟡 Near Expiry
   Display: Orange badge "● Near Expiry"

4. Medicine expires on May 16, 2026 (exactly 6 months)
   Status: 🟡 Near Expiry
   Display: Orange badge "● Near Expiry"

5. Medicine expires on Jul 15, 2026 (8 months from now)
   Status: 🟢 Good
   Display: Green badge "● Good"


═══════════════════════════════════════════════════════════════════

WHERE TO SEE STATUS:

1. EXPIRATION MONITOR PAGE
   URL: /expiration-monitor/
   - Shows all batches with expiry dates
   - Filterable by status (All, Expired, Expiring Soon)
   - Allows removal of expired/near-expiry items

2. ACTUAL INVENTORY PAGE
   URL: /actual-inventory/
   - Shows store shelf inventory
   - Displays both stock level AND expiry status
   - Format:
     Stock Status (● Low Stock / ● Medium / ● In Stock)
     Expiry Status (badge)


═══════════════════════════════════════════════════════════════════

NOTIFICATION SYSTEM:

When medicines reach "Near Expiry" status:
- Automatic notifications are generated
- Alert appears in notification badge (sidebar)
- Title: "Near Expiry Alert: [Medicine Name]"
- Managers and staff receive notifications

When medicines become "Expired":
- Critical alerts generated
- Requires immediate action
- "Remove" button available in Expiration Monitor


═══════════════════════════════════════════════════════════════════

TECHNICAL DETAILS:

CSS Classes:
- .status-badge: Base styling for all badges
- .status-good: Green badge styling
- .status-near-expiry: Orange badge styling
- .status-expired: Red badge styling

Django Template Logic:
{% if batch.expiry_date < today %}
    <span class="status-badge status-expired">● Expired</span>
{% elif batch.expiry_date <= six_months_from_now %}
    <span class="status-badge status-near-expiry">● Near Expiry</span>
{% else %}
    <span class="status-badge status-good">● Good</span>
{% endif %}

Context Variables:
- today: Current date (date.today())
- six_months_from_now: today + timedelta(days=180)


═══════════════════════════════════════════════════════════════════

BUSINESS RULES:

6-Month Threshold Rationale:
✓ Industry standard for pharmacy inventory management
✓ Sufficient time to move stock through promotions
✓ Prevents last-minute fire sales
✓ Reduces waste from expired products
✓ Improves cash flow through better turnover

Recommended Actions by Status:

GOOD (Green):
- No special action needed
- Continue regular sales
- Monitor expiry date

NEAR EXPIRY (Orange):
- Move to prominent shelf location
- Consider promotional pricing
- Notify purchasing to reduce future orders
- Prioritize in FIFO dispensing

EXPIRED (Red):
- IMMEDIATE removal from sales floor
- Document removal reason
- Record in stock movement history
- Dispose according to regulations
- Contact supplier if under warranty
```
