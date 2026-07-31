def safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except: return default

def analyze_finance(data):
    income = safe_float(data.get("monthly_income", 5000.0))
    expenses = safe_float(data.get("monthly_expenses", 4000.0))
    idle_cash = safe_float(data.get("idle_cash", 0.0))
    monthly_net = income - expenses
    if income > 0:
        expense_ratio = expenses / income
        if expense_ratio <= 0.5:
            savings_score = 90 + ((0.5 - expense_ratio) * 20)
        elif expense_ratio <= 0.8:
            savings_score = 60 + ((0.8 - expense_ratio) * 100)
        elif expense_ratio <= 1.0:
            savings_score = 30 + ((1.0 - expense_ratio) * 150)
        else:
            savings_score = max(0.0, 30.0 - ((expense_ratio - 1.0) * 10))
    else:
        savings_score = 0.0
        expense_ratio = 5.0
    runway_months = (idle_cash / expenses) if expenses > 0 else 12.0
    if runway_months >= 12:
        runway_score = 100.0
    elif runway_months >= 6:
        runway_score = 80 + (runway_months - 6) * 3.3
    else:
        runway_score = (runway_months / 6.0) * 80
    health_score = (savings_score * 0.6) + (runway_score * 0.4)
    health_score = min(100.0, max(0.0, health_score))
    risk_score = round(100.0 - health_score, 1)
    if risk_score > 70:
        status = "Critical Financial Instability"
        reason = f"Severe monthly deficit (${abs(monthly_net):,}) and critically low runway ({runway_months:.1f} months)."
    elif risk_score > 40:
        status = "Financial Friction"
        reason = f"Tight margins. Spending represents {expense_ratio*100:.0f}% of total income."
    else:
        status = "Financially Optimized"
        reason = f"Strong savings rate with {runway_months:.1f} months of liquidity buffer."
    return {
        "risk_score": risk_score,
        "status": status,
        "reason": reason,
        "monthly_net": monthly_net,
        "savings_rate": round((monthly_net / income * 100), 1) if income > 0 else -100.0,
        "cash_runway_months": round(runway_months, 1),
        "expense_ratio": round(expense_ratio, 2)
    }
