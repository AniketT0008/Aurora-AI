def safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except:
        return default

def analyze_behavior(data):
    sleep = safe_float(data.get("sleep_hours_avg", 8))
    exercise = safe_float(data.get("exercise_days_per_week", 0))
    workout_mins = safe_float(data.get("workout_minutes_per_day", 0))
    habit_notes = str(data.get("daily_habits_notes", "") or "")
    sleep_deficit = max(0.0, 8.0 - sleep)
    activity_gap = max(0.0, 30.0 - workout_mins) / 30.0
    notes_lower = habit_notes.lower()
    note_penalty = 0.0
    if any(k in notes_lower for k in ["stress", "tired", "burnout", "anxious", "overwhelmed"]):
        note_penalty += 5.0
    if any(k in notes_lower for k in ["sick", "ill", "pain", "hospital"]):
        note_penalty += 10.0
    note_bonus = 0.0
    if any(k in notes_lower for k in ["meditation", "walk", "water", "yoga", "nature", "quiet"]):
        note_bonus += 5.0
    if "2l" in notes_lower or "3l" in notes_lower:
        note_bonus += 2.0
    burnout_risk = (sleep_deficit / 4.0) * 35 + (max(0.0, 3.0 - exercise) / 3.0) * 25 + activity_gap * 15 + note_penalty - note_bonus
    burnout_risk = min(100.0, max(0.0, burnout_risk))
    habits = []
    if sleep < 6: habits.append("Severe sleep deprivation")
    if exercise < 2: habits.append("Sedentary lifestyle")
    if workout_mins < 20: habits.append("Low daily movement")
    if habit_notes and ("stress" in habit_notes.lower() or "tired" in habit_notes.lower()):
        habits.append("Self-reported stress pattern")
    energy_cycles = "Highly Volatile" if burnout_risk > 60 else "Stable"
    return {
        "burnout_risk_score": round(burnout_risk, 1),
        "burnout_risk_level": "High" if burnout_risk > 60 else "Moderate" if burnout_risk > 30 else "Low",
        "habits": habits,
        "energy_cycles": energy_cycles,
        "workout_minutes_per_day": workout_mins
    }
