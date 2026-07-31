def safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except:
        return default

def analyze_productivity(data):
    screen_time = safe_float(data.get("daily_screen_time_hours", 24))
    deep_work = safe_float(data.get("deep_work_hours", 0))
    if screen_time <= 0:
        focus_score = 100.0
    else:
        focus_score = min(100.0, max(0.0, (deep_work / screen_time) * 100 * 2))
    distractions = []
    if screen_time - deep_work > 5:
        distractions.append("High non-productive screen time.")
    return {
        "focus_score": round(focus_score, 1),
        "deep_work_ratio": round(deep_work / max(1, screen_time), 2),
        "distractions": distractions,
        "trends": "Optimal deep work" if focus_score > 70 else "High distraction risk"
    }
