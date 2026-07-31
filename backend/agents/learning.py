def safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except:
        return default

def analyze_learning(data):
    focus = str(data.get("current_focus", "General"))
    hours = safe_float(data.get("hours_per_week", 0))
    consistency_score = min(100.0, max(0.0, (hours / 10) * 100))
    urgency = "High" if hours < 3 else "Moderate" if hours < 7 else "Low"
    skill_gaps = []
    if consistency_score < 50:
        skill_gaps.append(f"Falling behind in {focus}")
    return {
        "consistency_score": round(consistency_score, 1),
        "urgency": urgency,
        "skill_gaps": skill_gaps,
        "learning_path": [f"Commit {max(1.0, 10.0 - hours)} more hours per week to {focus}"]
    }
