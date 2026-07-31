from .finance import analyze_finance  
from .productivity import analyze_productivity 
from .learning import analyze_learning   
from .behavior import analyze_behavior
try:
    from services.gemini_service import gemini_service
except ImportError:    
    from ..services.gemini_service import gemini_service

def safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except:
        return default

def _bounded_float(val, default=0.0, min_value=0.0, max_value=None):
    num = safe_float(val, default)
    if min_value is not None:
        num = max(min_value, num)
    if max_value is not None:
        num = min(max_value, num)
    return num

def normalize_profile_data(profile_data):
    source = profile_data if isinstance(profile_data, dict) else {}
    finance = dict(source.get("finance", {}) or {})
    productivity = dict(source.get("productivity", {}) or {})
    behavior = dict(source.get("behavior", {}) or {})
    learning = dict(source.get("learning", {}) or {})
    normalized = dict(source)

    finance["monthly_income"] = _bounded_float(finance.get("monthly_income", 0), 0, 0)
    finance["monthly_expenses"] = _bounded_float(finance.get("monthly_expenses", 0), 0, 0)
    finance["idle_cash"] = _bounded_float(finance.get("idle_cash", 0), 0, 0)
    productivity["deep_work_hours"] = _bounded_float(productivity.get("deep_work_hours", 0), 0, 0, 16)
    productivity["daily_screen_time_hours"] = _bounded_float(productivity.get("daily_screen_time_hours", 6), 6, 0, 24)
    behavior["sleep_hours_avg"] = _bounded_float(behavior.get("sleep_hours_avg", 8), 8, 0, 14)
    behavior["exercise_days_per_week"] = _bounded_float(behavior.get("exercise_days_per_week", 0), 0, 0, 7)
    behavior["workout_minutes_per_day"] = _bounded_float(behavior.get("workout_minutes_per_day", 0), 0, 0, 300)
    learning["hours_per_week"] = _bounded_float(learning.get("hours_per_week", 0), 0, 0, 80)
    learning["current_focus"] = str(learning.get("current_focus", "General") or "General").strip() or "General"

    normalized["finance"] = finance
    normalized["productivity"] = productivity
    normalized["behavior"] = behavior
    normalized["learning"] = learning
    return normalized

def _profile_has_financial_baseline(profile_data):
    finance = profile_data.get("finance", {}) if isinstance(profile_data, dict) else {}
    return any(safe_float(finance.get(key, 0)) > 0 for key in ["monthly_income", "monthly_expenses", "idle_cash"])

def _is_generic_question(q):
    generic_phrases = [
        "help", "what now", "what should i do", "what should i do next",
        "next steps", "next step", "what should i focus on", "what should i prioritize",
        "give me advice", "advise me", "plan", "make a plan"
    ]
    return len(q.strip()) < 35 or any(phrase in q for phrase in generic_phrases)

def run_multi_agent_system( profile_data ):  
    profile_data = normalize_profile_data(profile_data)
    finance = analyze_finance(profile_data.get('finance', {}))
    prod = analyze_productivity(profile_data.get('productivity', {}))
    learning  = analyze_learning(profile_data.get('learning', {})) 
    behavior = analyze_behavior(profile_data.get('behavior', {}), profile_data.get('productivity', {}))
    f_risk = finance['risk_score']
    b_risk  = behavior['burnout_risk_score']
    p_risk = (100 - prod['focus_score'])
    l_risk  = (100 - learning['consistency_score'])
    if f_risk > 80:
        instability = (f_risk * 0.6) + (b_risk * 0.2) + (p_risk * 0.1) + (l_risk * 0.1)
    else:
        instability = (f_risk * 0.4) + (b_risk * 0.25) + (p_risk * 0.2) + (l_risk * 0.15)
    if f_risk > 90 or b_risk > 90:
        instability += 10.0  
    instability = round(min(100.0, max(0.0, instability)), 1)
    explanations  = []    
    if f_risk > 60:
        explanations.append(f"Critical Cashflow Deficit: Spending is {finance.get('expense_ratio', 0)*100:.0f}% of income.")
    elif f_risk < 30:
        explanations.append("Financial Buffer: Strong savings and runway.")
    if b_risk > 60:
        explanations.append("Burnout Exposure: Sleep and recovery are dangerously low.")
    if p_risk > 50:
        explanations.append("Focus Leak: Deep work consistency is fragmented.")
    if l_risk > 60:
        explanations.append( "Learning Gap: Skill development is stalling." )
    return {
        "instability": instability,
        "explanations": explanations,
        "finance": finance,
        "productivity": prod,
        "learning": learning,
        "behavior": behavior
    }

def get_personality(agents):    
    f = agents['finance']['risk_score']
    b = agents['behavior']['burnout_risk_score']
    p  = agents['productivity']['focus_score']   
    if f > 80 and b > 60:
        return "Critical System Collapse Imminent"    
    if f > 70 and b < 40 and p > 60:
        return "Productive but Financially Fragile"
    if f > 70:
        return "Severe Cashflow Risk"
    if f < 30 and b > 60:
        return "Financially Safe but Bio-Fragile"
    if f < 30 and b < 30 and p > 70:
        return "Optimized High Performer"
    if f < 40 and p > 60:
        return "Balanced Growth Strategist"    
    if b > 70:
        return "Burnout Risk: Recovery Needed"
    return "Stable Operator"

import re as _re
import math 

def _extract_price_from_question(q):
    m = _re.search(r'\$\s*([\d,]+)', q)
    if m:  
        return float(m.group(1).replace(',', ''))
    m = _re.search(r'(\d+)\s*million', q)   
    if m:
        return float(m.group(1)) * 1_000_000
    m = _re.search(r'(\d+)\s*k\b', q)
    if m:
        return float(m.group(1)) * 1000
    m = _re.search(r'(\d{4,})', q)
    if m: 
        val = float(m.group(1))
        if val > 500:
            return val  
    return None

def _calc_monthly_payment(principal, annual_rate, years):
    if principal <= 0 or annual_rate <= 0 or years <= 0:
        return 0  
    r = annual_rate / 12 
    n = years * 12
    return principal * (r * (1 + r)**n) / ((1 + r)**n - 1)

def _is_cashflow_improvement_question(q):
    cash_terms = [
        "cash flow", "cashflow", "idle cash", "surplus", "runway", "reserve",
        "reserves", "savings rate", "save more", "saving more", "increase my cash",
        "increase cash", "more cash", "build cash", "grow cash", "extra cash"
    ]
    improve_terms = [
        "increase", "improve", "boost", "grow", "build", "optimize", "raise",
        "make more", "free up", "generate", "strengthen"
    ]
    return any(term in q for term in cash_terms) and (
        any(term in q for term in improve_terms) or q.strip().startswith("how")
    )

def _format_months_to_goal(goal, monthly_capacity):
    if goal <= 0:
        return "already funded"
    if monthly_capacity <= 0:
        return "blocked until monthly cash flow is positive"
    months = math.ceil(goal / monthly_capacity)
    return f"{months} month{'s' if months != 1 else ''}"

def _base_response_payload(decision, why, alternative, prediction, agents, f, b, monthly_net, runway):
    return {
        "decision": decision,
        "why": why,
        "alternative": alternative,
        "prediction": prediction,
        "risk_score": agents['instability'],
        "finance_agent": f,
        "productivity_agent": agents['productivity'],
        "learning_agent": agents['learning'],
        "behavior_agent": b,
        "personality_profile": get_personality(agents),
        "explanations": agents['explanations'],
        "reasoning": {
            "finance": f"Risk {f['risk_score']}/100. {f['status']}. Net: ${monthly_net:,.0f}/mo.",
            "productivity": f"Focus {agents['productivity']['focus_score']}/100. {agents['productivity']['trends']}.",
            "learning": f"Consistency {agents['learning']['consistency_score']}/100. Urgency: {agents['learning']['urgency']}.",
            "behavior": f"Burnout {b['burnout_risk_level']} ({b['burnout_risk_score']}/100). Energy: {b['energy_cycles']}."
        }
    }

def _contains_any(q, terms):
    return any(term in q for term in terms)

def _handle_safety_risk(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents):
    dangerous_terms = [
        "illegal", "fraud", "scam", "tax evasion", "steal", "theft", "fake documents",
        "lie on", "hide income", "all in", "yolo", "max out credit", "payday loan",
        "loan shark", "gamble rent", "skip rent", "stop paying rent", "quit without savings",
        "drop out", "stop medication", "ignore doctor", "sleep 3 hours", "no sleep"
    ]
    self_harm_terms = ["kill myself", "hurt myself", "end my life", "suicide", "self harm"]
    if _contains_any(q, self_harm_terms):
        return _base_response_payload(
            "STOP AND GET HELP",
            "This sounds like immediate personal safety territory, not a normal optimization decision. Your next move is to contact emergency services or a local crisis line now, and tell a trusted person nearby what is happening. Aurora should not coach you through anything that increases harm.",
            "Move away from anything you could use to hurt yourself, call emergency services if there is immediate danger, and send one direct message to someone you trust: 'I am not safe alone right now. Please call or come over.'",
            "SAFETY PRIORITY: The next 30 days only matter if you get through the next hour safely. Stabilize first; planning comes after.",
            agents, f, b, monthly_net, runway
        )
    if not _contains_any(q, dangerous_terms):
        return None
    if "quit" in q and runway >= 6 and monthly_net > 0:
        return None
    cashflow_text = f"${monthly_net:,.0f}/mo surplus" if monthly_net >= 0 else f"${abs(monthly_net):,.0f}/mo deficit"
    return _base_response_payload(
        "NO",
        f"This is too risky for your current system. Your financial runway is {runway:.1f} months, cash flow is a {cashflow_text}, and the request contains a high-risk signal. I will not recommend a move that can create legal, health, or financial damage.",
        f"Use the safe version: keep essentials paid, avoid debt traps or illegal shortcuts, and choose a reversible next step. If this is about money pressure, target ${max(300, abs(monthly_net) + 300):,.0f}/mo improvement through expense cuts, extra hours, or selling unused items before making the risky move.",
        generate_prediction_text(agents, monthly_net, runway),
        agents, f, b, monthly_net, runway
    )

def _handle_cashflow_improvement(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents):
    safe_income = max(income, 1)
    savings_rate = (monthly_net / safe_income) * 100
    three_month_target = expenses * 3
    six_month_target = expenses * 6
    three_month_gap = max(0, three_month_target - idle_cash)
    six_month_gap = max(0, six_month_target - idle_cash)
    trim_target = max(150, expenses * 0.05) if expenses > 0 else 150
    income_target = max(300, income * 0.05) if income > 0 else 500
    automated_transfer = max(0, monthly_net * 0.70)
    excess_cash_after_six_months = max(0, idle_cash - six_month_target)
    debt_hint = " If you have high-interest debt, redirect the first freed-up dollars there before investing."

    if monthly_net < 0:
        decision = "PROTECT CASH"
        why = (
            f"You are negative ${abs(monthly_net):,.0f}/mo: income is ${income:,.0f} and expenses are ${expenses:,.0f}. "
            f"The fastest cash-flow increase is not investing yet; it is closing that deficit, then creating a $500/mo surplus. "
            f"Target at least ${abs(monthly_net) + 500:,.0f}/mo of combined cuts or extra income."
        )
        alternative = (
            f"30-day plan: cut ${trim_target:,.0f}/mo from flexible spending in week 1, add ${income_target:,.0f}/mo from overtime, freelance, selling unused items, or a part-time shift by week 2, "
            f"and freeze new subscriptions or financed purchases. Once surplus turns positive, send 80% of it to cash reserves until you have ${three_month_target:,.0f} saved."
        )
    elif monthly_net == 0:
        decision = "CREATE SURPLUS"
        why = (
            f"You are breaking even at ${income:,.0f}/mo income and ${expenses:,.0f}/mo expenses. "
            "Your idle cash flow is zero, so every useful plan starts by opening a monthly gap between income and spending."
        )
        alternative = (
            f"Set a 30-day target of +${max(500, income * 0.10):,.0f}/mo: cut ${trim_target:,.0f}/mo, negotiate or add ${income_target:,.0f}/mo, "
            f"and automate the first transfer on payday. Keep the new surplus in cash until reserves reach ${three_month_target:,.0f}."
        )
    elif idle_cash < three_month_target:
        transfer = max(100, automated_transfer)
        decision = "BUILD CASH BUFFER"
        why = (
            f"You already have a ${monthly_net:,.0f}/mo surplus ({savings_rate:.1f}% savings rate), but idle cash is ${idle_cash:,.0f}, "
            f"which covers only {runway:.1f} months of expenses. Your best move is to convert the surplus into runway before chasing higher-risk returns."
        )
        alternative = (
            f"Automate ${transfer:,.0f}/mo to a high-yield savings account and use the remaining ${monthly_net - transfer:,.0f}/mo as flexible cash. "
            f"You will hit a 3-month reserve target of ${three_month_target:,.0f} in {_format_months_to_goal(three_month_gap, transfer)}. "
            f"To speed it up, cut ${trim_target:,.0f}/mo and add ${income_target:,.0f}/mo; that improves cash flow by about ${trim_target + income_target:,.0f}/mo."
        )
    else:
        investable_surplus = max(0, monthly_net * 0.50)
        decision = "OPTIMIZE SURPLUS"
        why = (
            f"You have a ${monthly_net:,.0f}/mo surplus ({savings_rate:.1f}% savings rate) and ${idle_cash:,.0f} in idle cash, "
            f"about {runway:.1f} months of runway. Keep 3-6 months liquid, then put excess monthly cash to work instead of letting it sit."
        )
        alternative = (
            f"Keep ${three_month_target:,.0f}-${six_month_target:,.0f} liquid in a high-yield savings account. "
            f"You currently have ${excess_cash_after_six_months:,.0f} above a 6-month reserve; that is the cash that can be redirected beyond emergency savings. "
            f"Route about ${investable_surplus:,.0f}/mo toward low-cost diversified investments or debt payoff and ${monthly_net - investable_surplus:,.0f}/mo toward near-term goals.{debt_hint}"
        )

    prediction = generate_prediction_text(agents, monthly_net, runway)
    return {
        "decision": decision,
        "why": why,
        "alternative": alternative,
        "prediction": prediction,
        "finance_agent": f,
        "productivity_agent": agents['productivity'],
        "learning_agent": agents['learning'],
        "behavior_agent": b,
        "personality_profile": get_personality(agents),
        "explanations": agents['explanations'],
        "reasoning": {
            "finance": f"Risk {f['risk_score']}/100. {f['status']}. Net: ${monthly_net:,.0f}/mo.",
            "productivity": f"Focus {agents['productivity']['focus_score']}/100. {agents['productivity']['trends']}.",
            "learning": f"Consistency {agents['learning']['consistency_score']}/100. Urgency: {agents['learning']['urgency']}.",
            "behavior": f"Burnout {b['burnout_risk_level']} ({b['burnout_risk_score']}/100). Energy: {b['energy_cycles']}."
        }
    }

def _is_next_steps_question(q):
    next_step_terms = [
        "next step", "next steps", "what should i do next", "what do i do next",
        "action plan", "game plan", "5-day", "five day", "focus on this week",
        "what should i focus on", "what should i prioritize"
    ]
    return any(term in q for term in next_step_terms) or bool(_re.search(r"\bthis week\b", q))

def _is_ambiguous_social_question(q):
    social_terms = ["go out", "weekend", "party", "friends", "trip", "vacation"]
    return any(term in q for term in social_terms) and not _is_weekend_planning_question(q) and "[user clarification]:" not in q

def _is_weekend_planning_question(q):
    planning_terms = ["what should i do", "what do i do", "plan my", "how should i spend"]
    return "weekend" in q and any(term in q for term in planning_terms) and "go out" not in q

def _is_relationship_question(q):
    terms = [
        "girlfriend", "boyfriend", "partner", "date", "dating", "relationship",
        "kid", "kids", "baby", "child", "children", "pregnant", "pregnancy"
    ]
    return any(term in q for term in terms)

def _handle_weekend_plan(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents, profile_data):
    focus = profile_data.get("learning", {}).get("current_focus", "your main goal")
    budget = max(50, min(monthly_net * 0.04 if monthly_net > 0 else 30, income * 0.02 if income > 0 else 75))
    if monthly_net < 0:
        decision = "LOW-COST RESET"
        why = f"This weekend should reduce pressure, not add it. You are running a ${abs(monthly_net):,.0f}/mo deficit, so the plan needs to protect cash while still giving you recovery."
        alternative = f"Use a 3-part weekend: one free social block, one 90-minute money cleanup, and one focused block on {focus}. Keep spending under ${budget:,.0f}."
    elif b['burnout_risk_score'] > 60:
        decision = "RECOVERY WEEKEND"
        why = f"Burnout risk is {b['burnout_risk_score']}/100, so the weekend should restore energy before it optimizes output."
        alternative = f"Do one social or fun block, one low-stimulus recovery block, and one light planning block. Keep spending near ${budget:,.0f} and protect sleep."
    else:
        decision = "BALANCED WEEKEND"
        why = f"With ${monthly_net:,.0f}/mo surplus, {runway:.1f} months runway, and stable recovery markers, you do not need to choose between being an adult and having a life."
        alternative = f"Use the weekend in thirds: one social/recovery block, one life admin block, and one 90-minute {focus} block. Keep discretionary spend around ${budget:,.0f} unless you intentionally budget more."
    return _base_response_payload(decision, why, alternative, generate_prediction_text(agents, monthly_net, runway), agents, f, b, monthly_net, runway)

def _handle_relationship_decision(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents, profile_data):
    if any(w in q for w in ["kid", "kids", "baby", "child", "children", "pregnant", "pregnancy"]):
        estimated_child_cost = 1500
        post_child_net = monthly_net - estimated_child_cost
        if monthly_net <= 0 or runway < 6:
            decision = "PREPARE FIRST"
            why = (
                f"A child is not a small reversible choice. Using a rough ${estimated_child_cost:,.0f}/mo child-cost placeholder, "
                f"your post-child cash flow would be ${post_child_net:,.0f}/mo and runway is {runway:.1f} months."
            )
            alternative = f"Before trying: confirm partner readiness, childcare support, health coverage, and build at least 6-12 months of expenses (${expenses * 6:,.0f}-${expenses * 12:,.0f})."
        elif post_child_net < max(500, income * 0.08):
            decision = "CAUTION"
            why = (
                f"You may be able to afford a child, but the margin gets thin after an estimated ${estimated_child_cost:,.0f}/mo in new costs. "
                f"Cash flow would fall from ${monthly_net:,.0f}/mo to about ${post_child_net:,.0f}/mo."
            )
            alternative = "Stress-test the budget for 90 days by saving the estimated child cost monthly, then decide with partner, support, housing, and health-care details included."
        else:
            decision = "PLAN DELIBERATELY"
            why = (
                f"Financially, you have room to plan: ${monthly_net:,.0f}/mo surplus and {runway:.1f} months runway. "
                "But having a child is a life-structure decision, not a generic optimization decision."
            )
            alternative = f"Run a 90-day readiness test: save ${estimated_child_cost:,.0f}/mo, discuss partner commitment, childcare, location, work flexibility, and emotional readiness before making it real."
        return _base_response_payload(decision, why, alternative, generate_prediction_text(agents, monthly_net, runway), agents, f, b, monthly_net, runway)

    if any(w in q for w in ["girlfriend", "boyfriend", "partner", "date", "dating", "relationship"]):
        if b['burnout_risk_score'] > 70:
            decision = "DATE SLOWLY"
            why = f"A relationship can be good for your life, but burnout risk is {b['burnout_risk_score']}/100. Do not add emotional intensity faster than your recovery can support."
            alternative = "Start with low-pressure dating and keep your sleep, work rhythm, and friendships intact. Avoid making the relationship your recovery system."
        elif monthly_net < 0:
            decision = "DATE LOW-COST"
            why = f"Being in a relationship is not only for rich people, but your ${abs(monthly_net):,.0f}/mo deficit means expensive dating would add stress."
            alternative = "Pursue connection, but keep dates low-cost, honest, and local while you repair cash flow."
        else:
            decision = "PURSUE CONNECTION"
            why = (
                f"Yes, if you want a girlfriend, pursue that like a grown person with a full life, not like a productivity side quest. "
                f"Your finances are stable (${monthly_net:,.0f}/mo surplus, {runway:.1f} months runway), so the key constraint is emotional availability and time."
            )
            alternative = "Make room for dating without letting it consume the system: one or two intentional social/date windows per week, keep deep work protected, and choose someone compatible with your actual life."
        return _base_response_payload(decision, why, alternative, generate_prediction_text(agents, monthly_net, runway), agents, f, b, monthly_net, runway)

    return None

def _handle_next_steps(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents, profile_data):
    focus = profile_data.get("learning", {}).get("current_focus", "your main skill")
    learning_hours = safe_float(profile_data.get("learning", {}).get("hours_per_week", 5))
    deep_work = safe_float(profile_data.get("productivity", {}).get("deep_work_hours", 0))
    starter_buffer = max(1000, expenses * 3)
    six_month_buffer = expenses * 6
    savings_gap = max(0, starter_buffer - idle_cash)

    if monthly_net < 0:
        decision = "RESTORE CASH FLOW"
        why = (
            f"Your next step is not more studying yet; it is closing the ${abs(monthly_net):,.0f}/mo deficit. "
            f"Until income exceeds expenses, every other goal is being built on unstable ground."
        )
        alternative = (
            f"Today: cut or pause ${max(150, abs(monthly_net) * 0.25):,.0f}/mo in flexible spending. "
            f"This week: add or recover ${abs(monthly_net) + 500:,.0f}/mo so you reach a $500/mo surplus, then resume {focus} blocks."
        )
    elif runway < 3:
        transfer = max(250, min(monthly_net, savings_gap if savings_gap > 0 else monthly_net))
        decision = "BUILD 3-MONTH BUFFER"
        why = (
            f"Your profile is strong, but the next concrete move is turning your ${monthly_net:,.0f}/mo surplus into runway. "
            f"You have {runway:.1f} months saved; the first target is ${starter_buffer:,.0f} before adding new purchases or higher-risk investing."
        )
        alternative = (
            f"Next 5 days: automate ${transfer:,.0f} to savings, review one recurring expense, keep {max(learning_hours, 5):.0f} learning hours on {focus}, "
            f"protect {deep_work:.0f}h/day deep work, and reassess once cash reserves pass ${starter_buffer:,.0f}."
        )
    elif b['burnout_risk_score'] > 60:
        decision = "RECOVER THEN EXECUTE"
        why = (
            f"Your money is stable enough for action, but burnout risk is {b['burnout_risk_score']}/100. "
            "The next step should protect energy so your output does not collapse."
        )
        alternative = (
            f"For 5 days: hold deep work to two 90-minute blocks, add one recovery block daily, and keep {focus} learning at {max(3, learning_hours):.0f} hours/week."
        )
    else:
        decision = "EXECUTE THE SPRINT"
        why = (
            f"Your system is balanced at {inst}/100 instability, with ${monthly_net:,.0f}/mo surplus and {runway:.1f} months runway. "
            f"The best next step is a focused sprint: keep the financial surplus protected while advancing {focus}."
        )
        alternative = (
            f"Next 5 days: move 50-70% of surplus toward reserves until ${six_month_buffer:,.0f}, schedule {max(learning_hours, 5):.0f} learning hours, "
            "keep screen time from expanding, and use one weekly review to choose the next constraint."
        )

    return _base_response_payload(
        decision,
        why,
        alternative,
        generate_prediction_text(agents, monthly_net, runway),
        agents, f, b, monthly_net, runway
    )

def _ai_decision_needs_local_fallback(ai_data, question):
    if not ai_data:
        return True
    q = str(question or "").lower()
    decision = str(ai_data.get("decision", "") or "").upper()
    why = str(ai_data.get("why", "") or "").lower()
    vague_decisions = ["UNSURE", "NEED MORE INFO", "CLARIFICATION REQUIRED"]
    is_laptop_car_choice = (" or " in q or " vs " in q) and "laptop" in q and ("car" in q or "vehicle" in q)
    if _is_next_steps_question(q):
        combined = f"{ai_data.get('why', '')} {ai_data.get('alternative', '')}".lower()
        generic_next_step = decision in ["STUDY", "WORK", "LEARN", "FOCUS", "SAVE", "YES"]
        missing_plan_shape = not any(token in combined for token in ["day", "week", "next", "$", "buffer", "surplus", "runway"])
        if generic_next_step or missing_plan_shape:
            return True
    if _is_ambiguous_social_question(q) and decision in ["YES", "NO", "CAUTION", "GO OUT", "REST"]:
        return True
    if any(v in decision for v in vague_decisions) and (_is_cashflow_improvement_question(q) or is_laptop_car_choice):
        return True
    if _is_cashflow_improvement_question(q):
        weak_text = "need more detail" in why or "need more details" in why or "can you clarify" in why
        missing_math = "$" not in str(ai_data.get("why", "")) and "$" not in str(ai_data.get("alternative", ""))
        if weak_text or missing_math:
            return True
    if is_laptop_car_choice and ("laptop" not in why or "car" not in why):
        return True
    return False

def _handle_laptop_car_comparison(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents):
    laptop_cost = 1200
    car_cost = _extract_price_from_question(q) or 30000
    car_down = car_cost * 0.15
    car_monthly = _calc_monthly_payment(car_cost - car_down, 0.07, 5)
    remaining_after_car = monthly_net - car_monthly
    laptop_reserve_after = idle_cash - laptop_cost
    car_reserve_after = idle_cash - car_down
    car_is_needed = any(w in q for w in ["commute", "work", "job", "need a car", "transport", "transportation", "drive"])
    car_affordable = idle_cash >= car_down and remaining_after_car > 0
    starter_buffer = max(1000, expenses * 0.5)

    if monthly_net <= 0:
        decision = "NEITHER"
        why = (
            f"Do not buy either yet. Your monthly cash flow is negative ${abs(monthly_net):,.0f}/mo, so adding a laptop purchase or a car payment would weaken stability. "
            f"A car would likely need about ${car_down:,.0f} down and ${car_monthly:,.0f}/mo, while a practical laptop can be held near ${laptop_cost:,.0f}."
        )
        alt = f"Create at least $500/mo surplus first, then buy a laptop under ${laptop_cost:,.0f}. Revisit the car after 3 months of positive cash flow."
    elif idle_cash < laptop_cost and not car_is_needed:
        months_to_laptop = max(1, math.ceil(laptop_cost / max(1, monthly_net)))
        months_to_buffer = max(1, math.ceil(starter_buffer / max(1, monthly_net)))
        decision = "SAVE FIRST"
        why = (
            f"Do not buy either today. You have ${idle_cash:,.0f} idle cash, so a ${laptop_cost:,.0f} laptop is not covered by cash on hand yet. "
            f"Your ${monthly_net:,.0f}/mo surplus is strong, but runway is {runway:.1f} months right now. "
            "The laptop is still the better purchase than the car, but the timing should be after cash lands."
        )
        alt = (
            f"Save the first ${laptop_cost:,.0f} of surplus for the laptop in about {months_to_laptop} month{'s' if months_to_laptop != 1 else ''}, "
            f"then keep building a starter emergency buffer of ${starter_buffer:,.0f} in about {months_to_buffer} month{'s' if months_to_buffer != 1 else ''}. "
            f"Only consider the car if transportation becomes essential; otherwise avoid the estimated ${car_monthly:,.0f}/mo payment."
        )
    elif car_is_needed and not car_affordable:
        months_to_down = max(1, math.ceil(max(0, car_down - idle_cash) / max(1, monthly_net)))
        decision = "SAVE FIRST"
        why = (
            f"Transportation may be important, but you do not have the cash for the assumed ${car_down:,.0f} down payment yet. "
            f"With ${idle_cash:,.0f} idle cash and ${monthly_net:,.0f}/mo surplus, forcing the car now would create fragile runway."
        )
        alt = (
            f"Save for about {months_to_down} month{'s' if months_to_down != 1 else ''} before buying. In the meantime, use the cheapest reliable transport option available. "
            f"If you also need a laptop for work, cap it below ${laptop_cost:,.0f} and buy only after the first surplus deposit clears."
        )
    elif car_is_needed and car_affordable:
        decision = "BUY THE CAR"
        why = (
            f"If the car is required for work or reliable transportation, it wins. Assuming a ${car_cost:,.0f} car, you can cover a ${car_down:,.0f} down payment, "
            f"keep ${car_reserve_after:,.0f} in reserves, and the estimated ${car_monthly:,.0f}/mo payment still leaves ${remaining_after_car:,.0f}/mo surplus."
        )
        alt = f"Cap the vehicle around ${car_cost:,.0f}, keep the payment under ${monthly_net * 0.25:,.0f}/mo, and buy the laptop only if it stays under ${laptop_cost:,.0f} cash."
    else:
        decision = "BUY THE LAPTOP FIRST"
        car_cashflow_text = (
            f"would push monthly cash flow negative by ${abs(remaining_after_car):,.0f}/mo"
            if remaining_after_car < 0
            else f"reducing your surplus from ${monthly_net:,.0f}/mo to ${remaining_after_car:,.0f}/mo"
        )
        why = (
            f"Both are financially possible, but the laptop is the smarter default unless the car is truly required. A laptop at about ${laptop_cost:,.0f} leaves "
            f"${laptop_reserve_after:,.0f} in savings and no new monthly payment. The assumed ${car_cost:,.0f} car adds about ${car_monthly:,.0f}/mo in payments, "
            f"{car_cashflow_text}."
        )
        alt = (
            f"Buy a laptop under ${laptop_cost:,.0f}-${laptop_cost + 800:,.0f} now, then create a separate car fund. If transportation becomes necessary, "
            f"target a used car that keeps total payment, insurance, and maintenance under ${monthly_net * 0.25:,.0f}/mo."
        )

    return {
        "decision": decision,
        "why": why,
        "alternative": alt,
        "prediction": generate_prediction_text(agents, monthly_net, runway),
        "finance_agent": f,
        "productivity_agent": agents['productivity'],
        "learning_agent": agents['learning'],
        "behavior_agent": b,
        "personality_profile": get_personality(agents),
        "explanations": agents['explanations'],
        "reasoning": {
            "finance": f"Risk {f['risk_score']}/100. {f['status']}. Net: ${monthly_net:,.0f}/mo.",
            "productivity": f"Focus {agents['productivity']['focus_score']}/100. {agents['productivity']['trends']}.",
            "learning": f"Consistency {agents['learning']['consistency_score']}/100. Urgency: {agents['learning']['urgency']}.",
            "behavior": f"Burnout {b['burnout_risk_level']} ({b['burnout_risk_score']}/100). Energy: {b['energy_cycles']}."
        }
    }

def _infer_general_question_context(q):
    cost = _extract_price_from_question(q) or 0
    domains = []
    domain_terms = {
        "money": ["money", "cost", "pay", "buy", "rent", "loan", "debt", "invest", "save", "budget", "expensive", "$"],
        "career": ["job", "career", "boss", "work", "promotion", "salary", "business", "client", "interview", "quit"],
        "learning": ["learn", "study", "course", "school", "college", "degree", "exam", "skill", "certification"],
        "health": ["health", "sleep", "doctor", "therapy", "medicine", "surgery", "diet", "gym", "mental"],
        "relationship": ["friend", "family", "girlfriend", "boyfriend", "partner", "dating", "marry", "marriage", "break up", "social"],
        "home": ["move", "relocate", "apartment", "house", "roommate", "city", "country"],
        "time": ["week", "month", "year", "today", "tomorrow", "weekend", "night", "schedule", "routine"],
    }
    for domain, terms in domain_terms.items():
        if any(term in q for term in terms):
            domains.append(domain)

    high_commitment_terms = [
        "kid", "child", "baby", "marry", "marriage", "divorce", "move", "relocate",
        "quit", "drop out", "loan", "debt", "lease", "contract", "mortgage", "surgery",
        "tattoo", "degree", "business", "cofounder", "adopt", "dog", "cat", "pet"
    ]
    high_commitment = any(term in q for term in high_commitment_terms)
    time_heavy = any(term in q for term in ["multi day", "all week", "every day", "year", "years", "semester", "full time"])
    low_reversible = any(term in q for term in ["try", "test", "experiment", "one time", "today", "tonight", "call", "text", "message", "ask", "talk"])
    asks_how = q.startswith("how") or " how do i " in q or "how should" in q
    asks_choice = " or " in q or " vs " in q
    asks_decision = any(q.startswith(prefix) for prefix in ["should", "can i", "do i", "is it", "would it"])

    return {
        "cost": cost,
        "domains": domains or ["general life"],
        "high_commitment": high_commitment or time_heavy,
        "low_reversible": low_reversible and not high_commitment,
        "asks_how": asks_how,
        "asks_choice": asks_choice,
        "asks_decision": asks_decision,
    }

def _binding_constraint(agents, monthly_net, runway):
    f = agents['finance']
    b = agents['behavior']
    focus_score = agents['productivity']['focus_score']
    learning_score = agents['learning']['consistency_score']
    if monthly_net < 0:
        return "cash flow", f"you are short ${abs(monthly_net):,.0f}/mo"
    if runway < 3:
        return "runway", f"cash runway is {runway:.1f} months"
    if b['burnout_risk_score'] > 60:
        return "recovery", f"burnout risk is {b['burnout_risk_score']}/100"
    if focus_score < 45:
        return "attention", f"focus score is {focus_score}/100"
    if learning_score < 40:
        return "skill momentum", f"learning consistency is {learning_score}/100"
    if f['risk_score'] < 30 and b['burnout_risk_score'] < 35:
        return "intentionality", "your baseline is strong, so the decision should fit your values and long-term direction"
    return "stability", f"instability is {agents['instability']}/100"

def _handle_open_ended_general(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents, profile_data):
    account = profile_data.get("account", {}) if isinstance(profile_data, dict) else {}
    goal = account.get("primary_goal") or "long-term stability"
    focus = profile_data.get("learning", {}).get("current_focus", "your main focus")
    ctx = _infer_general_question_context(q)
    constraint, constraint_text = _binding_constraint(agents, monthly_net, runway)
    cost = ctx["cost"]
    cost_text = f" The question appears to involve about ${cost:,.0f}." if cost else ""
    domains = ", ".join(ctx["domains"][:3])

    if ctx["asks_how"]:
        decision = "BUILD A PLAN"
        why = (
            f"This is a {domains} question, so Aurora should answer it as a plan, not force it into study/work/rest. "
            f"The binding constraint is {constraint}: {constraint_text}.{cost_text}"
        )
        alternative = (
            f"Use a 3-step plan: define the outcome, choose the smallest reversible next action, then check it against money, time, energy, and {goal}. "
            f"For the next 7 days, protect ${max(0, monthly_net):,.0f}/mo surplus, keep recovery stable, and reserve one focused block for {focus}."
        )
    elif ctx["high_commitment"] and "[user clarification]:" not in q and cost == 0:
        decision = "NEED MORE CONTEXT"
        why = (
            f"This sounds like a high-commitment {domains} decision. I can reason about it, but a responsible answer needs the missing variables: "
            f"cost, timeline, reversibility, who else is affected, and what happens if it goes badly. Your current binding constraint is {constraint}: {constraint_text}."
        )
        alternative = "Safe default: do not sign, quit, move, finance, commit, or permanently change your life structure until those variables are explicit. Do the smallest reversible test first."
    elif monthly_net < 0 and (cost > 0 or "money" in ctx["domains"]):
        decision = "NO UNTIL STABLE"
        why = f"This may be reasonable in another profile, but not while cash flow is negative by ${abs(monthly_net):,.0f}/mo.{cost_text}"
        alternative = f"First create at least $500/mo surplus. If you still want it then, cap the first version under ${max(30, income * 0.01):,.0f} and avoid recurring obligations."
    elif cost and cost > max(idle_cash * 0.20, monthly_net * 2):
        decision = "CAUTION"
        why = (
            f"The issue is not whether the idea is allowed; it is sizing. ${cost:,.0f} is large relative to your monthly surplus of ${monthly_net:,.0f}, "
            f"even with {runway:.1f} months runway."
        )
        alternative = f"Shrink it, delay it, or fund it from a separate goal bucket. Keep at least ${expenses * 6:,.0f} liquid and avoid turning a one-time desire into recurring drag."
    elif ctx["low_reversible"]:
        decision = "TEST IT"
        why = (
            f"This looks reversible, so the right move is a controlled test rather than overthinking. "
            f"Your binding constraint is {constraint}: {constraint_text}."
        )
        alternative = "Try the smallest version once, set a time or money cap in advance, then review whether it improved your life system or just added noise."
    elif b['burnout_risk_score'] > 60 and any(d in ctx["domains"] for d in ["career", "learning", "time", "general life"]):
        decision = "REDUCE LOAD"
        why = f"This may be a good idea later, but burnout risk is {b['burnout_risk_score']}/100. Adding load now can reduce output instead of increasing it."
        alternative = "Choose the lower-friction version for 72 hours. Protect sleep first, then revisit once energy is stable."
    else:
        alignment_target = goal if any(d in ctx["domains"] for d in ["career", "learning", "money"]) else "your values and real-life priorities"
        decision = "PROCEED WITH CONDITIONS"
        why = (
            f"I do not need a custom rule for this exact question. Treated as a {domains} decision, it is acceptable if it is reversible, aligned with {alignment_target}, "
            f"and does not damage the current constraint: {constraint_text}."
        )
        alternative = (
            f"Use the adult filter: what is the cost, time commitment, reversibility, downside, and effect on people involved? "
            f"If those are acceptable, take the next small step; if any are unclear or permanent, ask Aurora with those details."
        )

    return _base_response_payload(decision, why, alternative, generate_prediction_text(agents, monthly_net, runway), agents, f, b, monthly_net, runway)

def _handle_adaptive_general(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents, profile_data):
    account = profile_data.get("account", {}) if isinstance(profile_data, dict) else {}
    goal = account.get("primary_goal") or profile_data.get("account", {}).get("primary_goal", "long-term stability")
    challenge = account.get("current_challenge") or "time, money, or energy allocation"
    focus = profile_data.get("learning", {}).get("current_focus", "your current skill focus")
    focus_score = agents['productivity']['focus_score']
    learning_score = agents['learning']['consistency_score']
    burnout_score = b['burnout_risk_score']
    vague_without_object = [
        "should i do it", "should i go for it", "is this good", "is this a good idea",
        "what do you think", "should i say yes", "should i say no"
    ]

    if any(phrase in q for phrase in vague_without_object) and "[user clarification]:" not in q:
        cashflow_text = f"${monthly_net:,.0f}/mo surplus" if monthly_net >= 0 else f"${abs(monthly_net):,.0f}/mo deficit"
        return _base_response_payload(
            "NEED MORE INFO",
            (
                f"I can make this decision, but I need the actual option first. Your current baseline is a {cashflow_text}, "
                f"{runway:.1f} months runway, burnout risk {burnout_score}/100, and goal '{goal}'. What exactly are you considering, what does it cost, and when would it happen?"
            ),
            "Safe default until you clarify: do not commit money, debt, sleep loss, legal risk, or a long-term obligation. If it is small, reversible, and aligned with your goal, hold it as a maybe.",
            generate_prediction_text(agents, monthly_net, runway),
            agents, f, b, monthly_net, runway
        )

    return _handle_open_ended_general(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents, profile_data)

def _handle_purchase_decision(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents):
    extracted_price = _extract_price_from_question(q)
    follow_ups = []
    if "house" in q or "home" in q or "condo" in q or "apartment" in q:
        item_type = "house"  
        cost = extracted_price or 400000   
        down_pct = 0.20
        rate = 0.06
        term_years = 25
        if not extracted_price:
            follow_ups.append(f"I'm assuming a home price of ${cost:,.0f} as a placeholder; update the price and location for a sharper answer.")
        follow_ups.append("If you have a co-signer or existing home equity, the down payment requirement may change.")
    elif "car" in q or "vehicle" in q:
        item_type  = "car"
        cost  = extracted_price or 30000
        down_pct  = 0.15
        rate = 0.07
        term_years  = 5
        if not extracted_price:
            follow_ups.append(f"I'm assuming a vehicle cost of ${cost:,.0f}; update the price and whether it is new or used for a sharper answer.")
    elif "laptop" in q or "computer" in q or "macbook" in q or "pc" in q:
        item_type  = "laptop"
        cost = extracted_price or 1200
        down_pct  = 1.0
        rate = 0   
        term_years = 0
        if not extracted_price:
            follow_ups.append(f"I'm assuming ~${cost:,.0f} for a quality laptop; update the price and model for a sharper answer.")
    elif "phone" in q or "iphone" in q:
        item_type  = "phone"
        cost = extracted_price or 1100
        down_pct  = 1.0
        rate  = 0
        term_years = 0   
        if not extracted_price:
            follow_ups.append(f"I'm assuming ~${cost:,.0f} for a flagship phone; update the price for a sharper answer.")
    else:
        item_type = "purchase"  
        cost = extracted_price or 5000
        down_pct  = 1.0 
        rate = 0
        term_years = 0    
        if not extracted_price:
            follow_ups.append(f"I'm assuming a cost of ${cost:,.0f}; update the actual amount for a sharper answer.")
    down_payment = cost * down_pct
    loan_amount  = cost - down_payment
    monthly_payment = _calc_monthly_payment(loan_amount, rate, term_years) if loan_amount > 0 else 0
    can_afford_down = idle_cash >= down_payment
    shortfall = max(0, down_payment - idle_cash)    
    remaining_surplus = monthly_net - monthly_payment
    can_afford_monthly  = remaining_surplus > 0 and monthly_net > 0
    if monthly_net > 0 and shortfall > 0:
        months_to_save = math.ceil(shortfall / monthly_net)   
    else:
        months_to_save = None   
    follow_up_text  = " ".join(follow_ups) if follow_ups else ""
    decision = "CAUTION"
    if expenses >= income:
        decision = "NO"
        why = (f"You're spending ${expenses:,.0f}/mo on ${income:,.0f}/mo income — "
               f"a monthly deficit of ${abs(monthly_net):,.0f}. You cannot take on any {item_type} payments. "
               f"{follow_up_text}" )  
        target_expense = income * 0.7
        alt = (f"Step 1: Cut expenses from ${expenses:,.0f} to ${target_expense:,.0f}/mo to create a ${income - target_expense:,.0f}/mo surplus. "
               f"Step 2: Save that surplus for {math.ceil(down_payment / max(1, income - target_expense))} months to reach the ${down_payment:,.0f} down payment. "
               f"Step 3: Only then revisit this {item_type}.")
    elif not can_afford_down and item_type in ["laptop", "phone", "purchase"]:
        decision = "SAVE FIRST" if monthly_net > 0 else ("NO" if idle_cash < cost * 0.5 else "CAUTION")
        why  = (f"This {item_type} costs ~${cost:,.0f}. You have ${idle_cash:,.0f} in savings. "
               f"{'Buying this would wipe out your reserves.' if idle_cash > 0 else 'You have no savings to cover this today.'} "
               f"{follow_up_text}")
        if monthly_net > 0:
            months_to_buy = max(1, math.ceil(cost / max(1, monthly_net)))
            alt = (f"Save first, then buy. At your current ${monthly_net:,.0f}/mo surplus, you can cover the ${cost:,.0f} in about {months_to_buy} month{'s' if months_to_buy != 1 else ''}. "
                   f"After that, keep building toward a starter emergency buffer of ${max(1000, expenses * 0.5):,.0f}. "
                   f"Consider a refurbished model for ${int(cost * 0.6):,} to reach the goal faster.")
        else:
            alt = f"You need to create positive cashflow first. Cut ${int(abs(monthly_net) + 200):,}/mo in expenses, then save for {math.ceil(cost / 200)} months."
    elif not can_afford_down:
        decision = "NO"
        pct_covered = (idle_cash / down_payment * 100) if down_payment > 0 else 0  
        why = (f"A ${cost:,.0f} {item_type} requires a {down_pct*100:.0f}% down payment of ${down_payment:,.0f}. "
               f"You have ${idle_cash:,.0f} ({pct_covered:.0f}% of what's needed). " 
               f"{'Even with a mortgage, ' if item_type == 'house' else ''}"
               f"the monthly payment would be ${monthly_payment:,.0f}/mo at {rate*100:.1f}% over {term_years} years. "   
               f"{follow_up_text}")
        if months_to_save:
            alt  = (f"Save ${monthly_net:,.0f}/month (your current surplus) for {months_to_save} months to accumulate the ${down_payment:,.0f} down payment. "
                   f"After that, your monthly {item_type} payment of ${monthly_payment:,.0f} would leave ${remaining_surplus:,.0f}/mo surplus — "
                   f"{'viable but tight.' if remaining_surplus < income * 0.1 else 'manageable.'} "
                   f"Consider a {item_type} under ${int(idle_cash / down_pct):,} to buy now with your current savings.")
        else:
            alt  = f"Create positive cashflow first by reducing expenses by ${int(abs(monthly_net) + 500):,}/mo. Then begin saving toward the ${down_payment:,.0f} down payment."
    elif not can_afford_monthly:   
        decision = "CAUTION"    
        max_affordable = monthly_net * 0.35
        max_house = max_affordable / max(0.001, _calc_monthly_payment(1, rate, term_years)) if rate > 0 else monthly_net * 100
        why = (f"You can cover the ${down_payment:,.0f} down payment, but the monthly payment of ${monthly_payment:,.0f} "
               f"exceeds your ${monthly_net:,.0f}/mo surplus. This would push you into deficit. "
               f"{follow_up_text}")    
        alt = (f"The max {item_type} you can afford with your ${monthly_net:,.0f}/mo surplus is ~${max_house:,.0f} "
               f"(keeping payments under 35% of income at ${max_affordable:,.0f}/mo). "
               f"Increase income by ${monthly_payment - monthly_net:,.0f}/mo to afford the ${cost:,.0f} target.")
    else:
        emergency_after = idle_cash - down_payment 
        months_emergency  = emergency_after / expenses if expenses > 0 else 99  
        why = (f"With ${idle_cash:,.0f} in savings, you can cover the ${down_payment:,.0f} down payment for this {item_type} "
               f"and still have ${emergency_after:,.0f} in reserves ({months_emergency:.1f} months of expenses). "
               f"Monthly payments of ${monthly_payment:,.0f} leave you ${remaining_surplus:,.0f}/mo surplus. "
               f"{follow_up_text}")  
        if months_emergency < 3:
            alt = (f"CAUTION: After the down payment, you'll only have {months_emergency:.1f} months of emergency reserves. "
                   f"Save an additional ${int( expenses * 3 - emergency_after ):,} before purchasing to maintain a safe buffer." )
        else:
            alt = f"Proceed, but maintain ${int(expenses * 6):,} emergency fund. Lock in the best rate available and consider accelerated payments if surplus allows."
            
    # Only default to YES/CAUTION if it wasn't already hard-rejected as NO
    if decision not in ["NO", "PROTECT CASH", "NEITHER", "SAVE FIRST"]:
        decision = "YES" if remaining_surplus > expenses * 0.2 else "CAUTION"
        
    prediction = generate_prediction_text(agents, monthly_net, runway)  
    return {    
        "decision": decision,
        "why": why,
        "alternative": alt,
        "prediction": prediction,

        "finance_agent": f,
        "productivity_agent": agents['productivity'],
        "learning_agent": agents['learning'],
        "behavior_agent": agents['behavior'],   
        "personality_profile": get_personality(agents),
        "explanations": agents['explanations'],
        "reasoning": {
            "finance": f"Risk {f['risk_score']}/100. {f['status']}. Net: ${monthly_net:,.0f}/mo.",   
            "productivity": f"Focus {agents['productivity']['focus_score']}/100. {agents['productivity']['trends']}.",
            "learning": f"Consistency {agents['learning']['consistency_score']}/100. Urgency: {agents['learning']['urgency']}.",
            "behavior": f"Burnout {b['burnout_risk_level']} ({b['burnout_risk_score']}/100). Energy: {b['energy_cycles']}."
        }
    }

def generate_deterministic_decision(question, agents, profile_data):
    profile_data = normalize_profile_data(profile_data)
    full_q = str(question or "").lower()
    q = full_q
    clarification = ""
    if "[user clarification]:" in full_q:
        parts = full_q.split("[user clarification]:")
        q = f"{parts[0].strip()} {parts[1].strip()}"
        clarification = parts[1].strip()

    # Context Awareness: If current question is short/numeric, pull context from history
    context_q = q
    should_use_history_context = (
        (len(q) < 20 or q.replace("$","").replace(",","").replace(".","").strip().isdigit())
        and not _is_next_steps_question(q)
        and not _is_generic_question(q)
        and not q.strip().endswith("?")
    )
    if should_use_history_context:
        for msg in reversed(profile_data.get("history", [])):
            if msg["role"] == "user":
                prev = msg["content"].lower()
                if any(w in prev for w in ["buy", "house", "car", "purchase", "spend", "laptop", "phone", "job", "career", "invest", "social", "focus", "study", "work", "learn", "cash flow", "cashflow", "idle cash", "surplus", "savings", "runway"]):
                    context_q = f"{prev} {q}"
                    break
    
    # Use context_q for intent detection
    q = context_q

    f = agents['finance']
    b = agents['behavior']
    inst = agents['instability']
    income = safe_float(profile_data.get('finance', {}).get('monthly_income', 0))
    expenses = safe_float(profile_data.get('finance', {}).get('monthly_expenses', 0))
    idle_cash = safe_float(profile_data.get('finance', {}).get('idle_cash', 0))
    monthly_net = income - expenses
    runway = round(idle_cash / expenses, 1) if expenses > 0 else 99.0

    if not _profile_has_financial_baseline(profile_data) and _is_generic_question(q):
        return _base_response_payload(
            "NEED PROFILE DATA",
            (
                "I can adapt to almost any profile, but this one has no usable financial baseline yet. "
                "For a generic question, the responsible next step is to collect the minimum inputs before giving a confident plan."
            ),
            "Enter monthly income, monthly expenses, idle cash, sleep, deep work, screen time, and learning focus. Until then: avoid irreversible spending, protect sleep, and choose one small reversible action.",
            generate_prediction_text(agents, monthly_net, runway),
            agents, f, b, monthly_net, runway
        )

    safety = _handle_safety_risk(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents)
    if safety:
        return safety

    # Fallback Decision Layer: Deterministic Rules (Multi-Agent Logic)
    decisions = []
    whys = []
    alts = []

    # 0. Cash-flow / idle-cash improvement intent
    if _is_cashflow_improvement_question(q):
        res = _handle_cashflow_improvement(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents)
        decisions.append(res['decision'])
        whys.append(res['why'])
        alts.append(res['alternative'])

    # 0b. Explicit purchase comparison intent
    is_choice_question = " or " in q or " vs " in q
    if is_choice_question and "laptop" in q and ("car" in q or "vehicle" in q):
        res = _handle_laptop_car_comparison(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents)
        decisions.append(res['decision'])
        whys.append(res['why'])
        alts.append(res['alternative'])

    # 0c. Next-step / weekly planning intent
    if _is_next_steps_question(q) and not is_choice_question:
        res = _handle_next_steps(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents, profile_data)
        decisions.append(res['decision'])
        whys.append(res['why'])
        alts.append(res['alternative'])

    # 0d. Adult-life relationship / family intent
    relationship = _handle_relationship_decision(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents, profile_data)
    if relationship:
        decisions.append(relationship['decision'])
        whys.append(relationship['why'])
        alts.append(relationship['alternative'])

    # 0e. Open weekend planning intent
    if _is_weekend_planning_question(q):
        res = _handle_weekend_plan(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents, profile_data)
        decisions.append(res['decision'])
        whys.append(res['why'])
        alts.append(res['alternative'])

    # 1. Purchase intent
    if any(w in q for w in ["buy", "house", "car", "purchase", "spend", "laptop", "phone"]) and not (is_choice_question and "laptop" in q and ("car" in q or "vehicle" in q)):
        res = _handle_purchase_decision(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents)
        decisions.append(res['decision'])
        whys.append(res['why'])
        alts.append(res['alternative'])

    # 2. Social/Discretionary/Leisure intent
    social_keywords = ["go out", "going out", "went out", "got out", "friends", "weekend", "vacation", "trip", "party", "social", "relax", "break", "rest"]
    if any(w in q for w in social_keywords) and not _is_weekend_planning_question(q):
        # 2a. Mental Health / Human Balance Priority
        # If user explicitly confirms a long time since last break, override everything else
        if clarification and any(w in clarification.lower() for w in ["year", "month", "long", "never", "while", "ago"]):
            decisions.append("GO OUT")
            whys.append("Mental health and human connection are non-negotiable for long-term productivity. Since it has been a very long time since your last engagement, the biological and psychological benefit of this break outweighs any marginal work progress.")
            alts.append("Commit fully to the break. Turn off notifications and reconnect. Use Monday for a high-intensity recovery-fueled deep work session.")
        elif clarification:
            clarified_cost = _extract_price_from_question(clarification) or _extract_price_from_question(q) or 0
            budget_cap = max(50, min(monthly_net * 0.05 if monthly_net > 0 else 50, income * 0.02 if income > 0 else 100))
            late_night = any(w in clarification.lower() for w in ["all night", "late", "3am", "4am", "5am", "no sleep"])
            has_obligation = any(w in clarification.lower() for w in ["exam", "work", "shift", "meeting", "deadline", "early"])
            if monthly_net <= 0 and clarified_cost > 0:
                decisions.append("NO")
                whys.append(f"With ${abs(monthly_net):,.0f}/mo cash-flow pressure, a paid night out is not the responsible move right now.")
                alts.append("Choose the free version: see people, keep it local, and do not add spending until cash flow is positive.")
            elif clarified_cost > max(budget_cap * 2, monthly_net * 0.10):
                decisions.append("CAUTION")
                whys.append(f"The social benefit is real, but ${clarified_cost:,.0f} is high relative to the safe recovery budget of about ${budget_cap:,.0f}.")
                alts.append(f"Go only if you reduce the plan near ${budget_cap:,.0f}, avoid debt, and keep the next day intact.")
            elif late_night and has_obligation:
                decisions.append("NO")
                whys.append("The cost is not the main issue; the timing is. Going out late before an obligation would trade recovery for avoidable performance drag.")
                alts.append("Reschedule or leave early enough to protect sleep. Make the social plan shorter, cheaper, and earlier.")
            else:
                decisions.append("YES")
                whys.append(f"Given the clarification, this looks like a reasonable recovery choice. Keep it near ${max(clarified_cost, budget_cap):,.0f} or less and protect sleep.")
                alts.append("Enjoy it deliberately, then return to the weekly plan without adding extra spending or lost sleep.")
        elif not clarification and any(w in q for w in ["go out", "weekend", "party", "friends", "trip", "vacation"]):
            budget = max(50, min(monthly_net * 0.05 if monthly_net > 0 else 50, income * 0.02 if income > 0 else 100))
            decisions.append("NEED MORE INFO")
            baseline_text = (
                f"cash flow is negative by ${abs(monthly_net):,.0f}/mo, so spending has to be tightly capped"
                if monthly_net < 0
                else "your baseline is healthy enough to allow recovery"
            )
            whys.append(
                f"I can make the call, but this depends on the version of 'go out.' Right now {baseline_text}, "
                f"but I need the missing constraint: expected spend, how late it runs, and whether you have a major obligation the next day."
            )
            alts.append(f"Safe default: go only if you cap spending near ${budget:,.0f}, avoid debt, and protect sleep. If it is expensive or wipes out tomorrow, choose a lower-cost plan.")
        
        elif expenses >= income and idle_cash < expenses:
            decisions.append("NO")
            whys.append(f"Your cashflow is negative by ${abs(monthly_net):,.0f}/mo. Discretionary spending will accelerate financial instability.")
            alts.append("Plan a free alternative: home cooking with friends, outdoor activities, or skill-building time.")
        elif b['burnout_risk_score'] > 70:
            budget = max(50, income * 0.02)
            decisions.append("YES")
            whys.append(f"Your burnout risk is {b['burnout_risk_score']}/100. Social recovery and mental breaks are critical for sustainability.")
            alts.append(f"Keep the budget under ${budget:,.0f} to protect cash position.")
        elif f['risk_score'] > 60:
            budget = max(30, income * 0.01)
            decisions.append("CAUTION")
            whys.append(f"Financial risk is elevated at {f['risk_score']}/100. Going out is fine if you cap spending at ${budget:,.0f}.")
            alts.append("Set a hard spending cap before going out.")
        else:
            decisions.append("YES")
            whys.append(f"Your finances are stable (risk {f['risk_score']}/100) and burnout risk is manageable. Enjoy responsibly.")
            alts.append("Use this as active recovery to maintain productivity momentum.")

    # 3. Focus/Productivity intent
    # Keep social/leisure questions focused on the actual decision.
    is_primarily_social = any(w in q for w in social_keywords)
    if any(w in q for w in ["focus", "study", "learn", "learning", "work", "prioritize", "week", "exam", "course"]) and not _is_next_steps_question(q) and not is_primarily_social:
        is_choice = " or " in q or " vs " in q
        is_open = "what" in q or "how" in q
        if runway < 1 and monthly_net > 0 and (is_open or "week" in q or "focus" in q):
            target_buffer = max(1000, expenses * 0.5)
            decisions.append("BUILD BUFFER")
            whys.append(
                f"Your focus this week should be building the first cash buffer while maintaining career momentum. "
                f"You have a strong ${monthly_net:,.0f}/mo surplus, but ${idle_cash:,.0f} idle cash means {runway:.1f} months of runway. "
                "That makes the next paycheck a stability event, not investment money."
            )
            alts.append(
                f"Route the first ${target_buffer:,.0f} of surplus into savings, then protect your Career Growth track with 5-7 focused learning hours and your existing deep-work routine. "
                "Do not add new purchases until the starter buffer exists."
            )
        elif f['risk_score'] > 60:
            decisions.append("EARN" if (is_choice or is_open) else "COURSE CORRECTION")
            whys.append(f"Financial pressure (risk {f['risk_score']}/100) is your #1 bottleneck. Focus energy on income generation and expense reduction.")
            alts.append(f"Dedicate 2 hours/day to income-generating activities until monthly surplus exceeds ${max(500, income * 0.15):,.0f}.")
        elif b['burnout_risk_score'] > 60:
            decisions.append("REST" if (is_choice or is_open) else "CAUTION")
            whys.append(f"Burnout risk is {b['burnout_risk_score']}/100. Pushing harder will reduce output. Prioritize recovery first.")
            alts.append("Implement 90-minute deep work blocks with 30-minute recovery cycles.")
        else:
            if agents['productivity']['focus_score'] > 80 and b['burnout_risk_score'] < 30 and f['risk_score'] < 30:
                if clarification:
                    if any(w in clarification for w in ["long", "while", "never", "month", "week", "days", "yes", "ago"]):
                        decisions.append("REST")
                        whys.append("You confirmed it has been a long time since your last break. Even with optimal metrics, proactive recovery is the only way to sustain this 'High Performer' state long-term.")
                        alts.append("Take the weekend off or schedule a 'low-stimulus' day immediately.")
                    else:
                        decisions.append("STUDY")
                        whys.append("Since you are well-rested and your system is optimized, you are in a rare 'Flow State' window. This is the best time for aggressive learning.")
                        alts.append("Target a 4-hour deep work block today to maximize this momentum.")
                else:
                    decisions.append("UNSURE")
                    whys.append(f"Your system is highly optimized (instability {inst}/100), but before I decide: when was the last time you took a real break?")
                    alts.append("If it's been a while, you should REST. If you just had a break, keep the momentum and STUDY/WORK.")
            else:
                decisions.append("STUDY" if (is_choice or is_open) else "YES")
                whys.append(f"Your system is balanced (instability {inst}/100). Lean into deep work while protecting your current cash position.")
                alts.append(f"Target {max(5, safe_float(profile_data.get('learning', {}).get('hours_per_week', 5))):.0f} learning hours this week and keep daily deep work consistent.")

    # 4. Investment intent
    if any(w in q for w in ["invest", "startup", "stock", "crypto", "bonds", "portfolio", "savings", "loan", "debt", "pay off"]):
        if expenses >= income:
            decisions.append("NO")
            whys.append(f"You're running a ${abs(monthly_net):,.0f}/mo deficit. Any investment or debt strategy must wait until you fix your cashflow.")
            alts.append(f"Cut expenses by ${int(abs(monthly_net) + 200):,}/mo first. Once surplus is positive, direct 50% to debt payoff and 50% to emergency fund.")
        elif idle_cash < expenses * 3:
            decisions.append("CAUTION")
            whys.append(f"Your emergency fund (${idle_cash:,.0f}) covers only {runway:.1f} months. Standard advice is 3-6 months before investing.")
            alts.append(f"Build savings to ${int(expenses * 3):,} first (about {max(1, int((expenses * 3 - idle_cash) / max(1, monthly_net)))} months), then invest surplus.")
        else:
            max_invest = min(idle_cash * 0.3, monthly_net * 6)
            decisions.append("YES" if max_invest > 1000 else "CAUTION")
            whys.append(f"With ${idle_cash:,.0f} in reserves ({runway:.1f} months runway) and ${monthly_net:,.0f}/mo surplus, you have room for calculated risk.")
            alts.append(f"Max investable amount: ${max_invest:,.0f} (30% of reserves). Never invest emergency funds.")

    # 5. Career/Job intent
    if any(w in q for w in ["quit", "job", "career", "fired", "salary", "pay cut", "promotion", "business"]):
        if "quit" in q or "start a business" in q:
            months_covered = runway
            if months_covered < 6:
                decisions.append("NO")
                whys.append(f"You only have {months_covered:.1f} months of runway. Quitting without 6+ months of expenses saved is high-risk.")
                alts.append(f"Save ${int(expenses * 6 - idle_cash):,} more before making the leap. That's {max(1, int((expenses * 6 - idle_cash) / max(1, monthly_net)))} months away.")
            else:
                decisions.append("CAUTION")
                whys.append(f"You have {months_covered:.1f} months of runway — enough for a calculated transition, but not unlimited.")
                alts.append(f"Start the business as a side project while employed. Quit only when it generates ${int(expenses * 0.5):,}/mo (50% of expenses).")
        elif "fired" in q or "lost" in q:
            decisions.append("PROTECT CASH")
            whys.append(f"Immediate priority: your ${idle_cash:,.0f} must last as long as possible. Cut all non-essential spending below ${int(expenses * 0.6):,}/mo.")
            alts.append(f"Emergency budget: ${int(expenses * 0.6):,}/mo buys you {idle_cash / max(1, expenses * 0.6):.0f} months. Apply to 5+ jobs/day starting now.")
        elif "pay cut" in q:
            price = _extract_price_from_question(q) or income * 0.15
            if price > income: # Assume annual
                price = price / 12
            new_income = income - price
            new_net = new_income - expenses
            if new_net < 0:
                decisions.append("NO")
                whys.append(f"A ${price:,.0f} pay cut drops your income to ${new_income:,.0f}/mo, creating a ${abs(new_net):,.0f}/mo deficit.")
            else:
                decisions.append("CAUTION" if new_net < expenses * 0.1 else "YES")
                whys.append(f"A ${price:,.0f} pay cut leaves you with ${new_net:,.0f}/mo surplus. {'Tight but survivable.' if new_net < expenses * 0.1 else 'Manageable with discipline.'}")
            alts.append(f"Negotiate: counter with ${int(price * 0.5):,} less and request equity/remote work to offset the difference.")
        else:
            # General job/career question (e.g., "should I find another job?")
            if f['risk_score'] > 60:
                decisions.append("SEARCH")
                whys.append(f"Your current financial risk is high ({f['risk_score']}/100) due to thin margins. A new job with higher compensation is your fastest path to stability.")
                alts.append("Update your resume and target roles with at least a 15-20% salary increase while staying in your current role.")
            elif b['burnout_risk_score'] > 60:
                decisions.append("STAY & STABILIZE")
                whys.append(f"Burnout risk is high ({b['burnout_risk_score']}/100). The stress of a job search and starting a new role may trigger systemic failure right now.")
                alts.append("Focus on recovery for 30 days before initiating any major career transitions.")
            else:
                decisions.append("YES")
                whys.append("Your life system is stable. Exploring new career opportunities is recommended for long-term growth and market-value testing.")
                alts.append("Initiate passive searching. Only jump for a role that offers significant equity or leadership growth.")

    # 6. Health/Wellness intent
    if any(w in q for w in ["gym", "trainer", "health", "therapy", "doctor", "baby", "pregnant", "child", "kid"]):
        if not relationship and ("baby" in q or "child" in q or "kid" in q):
            baby_cost = 1500
            new_expenses = expenses + baby_cost
            if income < new_expenses:
                decisions.append("NO")
                whys.append(f"A baby adds ~${baby_cost:,}/mo in expenses. Your income of ${income:,.0f}/mo wouldn't cover ${new_expenses:,.0f}/mo total expenses.")
                alts.append(f"Target: increase income to ${int(new_expenses * 1.2):,}/mo and save ${int(baby_cost * 12):,} baby fund before trying.")
            elif idle_cash < 10000:
                decisions.append("CAUTION")
                whys.append(f"Financially possible (${income - new_expenses:,.0f}/mo surplus after baby costs), but your ${idle_cash:,.0f} savings is thin for medical/unexpected costs.")
                alts.append(f"Build savings to $15,000+ (about {max(1, int((15000 - idle_cash) / max(1, monthly_net)))} months) then reassess.")
            else:
                decisions.append("YES")
                whys.append(f"With ${monthly_net:,.0f}/mo surplus and ${idle_cash:,.0f} in savings, you can absorb ~${baby_cost:,}/mo baby costs while maintaining ${income - new_expenses:,.0f}/mo surplus.")
                alts.append("Start a dedicated baby fund and review health insurance coverage immediately.")
        elif "gym" in q or "trainer" in q:
            gym_cost = 150
            if "trainer" in q:
                gym_cost = 400
            if monthly_net < gym_cost:
                decisions.append("CAUTION")
                if monthly_net < 0:
                    whys.append(f"A gym/trainer combo (~${gym_cost}/mo) is not the next paid upgrade because you already have a ${abs(monthly_net):,.0f}/mo deficit.")
                else:
                    whys.append(f"A gym/trainer combo (~${gym_cost}/mo) would consume most of your ${monthly_net:,.0f}/mo surplus.")
                alts.append(f"Start with bodyweight exercises (free) or a budget gym ($30/mo). Upgrade when surplus exceeds ${gym_cost * 3}/mo.")
            else:
                decisions.append("YES")
                whys.append(f"${gym_cost}/mo is {gym_cost/income*100:.1f}% of income — affordable. Your burnout risk is {b['burnout_risk_score']}/100, exercise investment pays dividends.")
                alts.append(f"Lock in a 3-month commitment first. If consistent, upgrade to trainer.")

    # 7. Weakness/diagnostic intent
    if any(w in q for w in ["weakness", "problem", "wrong", "fix", "improve", "optimize", "biggest"]):
        pillars = [
            ("finances", f['risk_score'], f"Risk {f['risk_score']}/100 — {'critical deficit' if expenses > income else 'tight margins' if f['risk_score'] > 50 else 'stable'}"),
            ("burnout", b['burnout_risk_score'], f"Burnout risk {b['burnout_risk_score']}/100 — sleep/exercise gaps"),
            ("focus", 100 - agents['productivity']['focus_score'], f"Focus {agents['productivity']['focus_score']}/100 — deep work ratio"),
            ("learning", 100 - agents['learning']['consistency_score'], f"Learning consistency {agents['learning']['consistency_score']}/100"),
        ]
        worst = max(pillars, key=lambda x: x[1])
        decisions.append(worst[0].upper())
        whys.append(f"Your biggest vulnerability is {worst[0]}: {worst[2]}. This is dragging your overall instability to {inst}/100.")
        alts.append(f"Dedicate 70% of optimization effort to {worst[0]} for the next 2 weeks. The other pillars can coast temporarily.")
    if not decisions:
        return _handle_adaptive_general(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents, profile_data)
    else:
        # Prioritize specific choices over generic YES/NO
        specific_choices = [d for d in decisions if d not in ["YES", "NO", "CAUTION", "COURSE CORRECTION", "UNSURE"]]
        if "UNSURE" in decisions and not specific_choices:
            final_decision = "UNSURE"
        elif specific_choices:
            final_decision = specific_choices[0]
        elif "NO" in decisions:
            final_decision = "NO"
        elif "COURSE CORRECTION" in decisions:
            final_decision = "COURSE CORRECTION"
        elif "CAUTION" in decisions:
            final_decision = "CAUTION"
        else:
            final_decision = decisions[0]
        
        final_why = " ".join(whys)
        final_alt = " ".join(alts)

        # Global Follow-up Detection: If Aurora asks a question, the verdict must be UNSURE
        if "?" in final_why and final_decision not in ["UNSURE", "NEED MORE INFO", "CLARIFICATION REQUIRED"] and not any(w in q for w in ["buy", "purchase", "spend", "car", "house", "laptop", "phone"]):
            final_decision = "UNSURE"

    prediction = generate_prediction_text(agents, monthly_net, runway)
    return {
        "decision": final_decision,
        "why": final_why,
        "alternative": final_alt,
        "prediction": prediction,
        "risk_score": inst,
        "finance_agent": f,
        "productivity_agent": agents['productivity'],
        "learning_agent": agents['learning'],
        "behavior_agent": b,
        "personality_profile": get_personality(agents),
        "explanations": agents['explanations'],
        "reasoning": {
            "finance": f"Risk {f['risk_score']}/100. {f['status']}. Net: ${monthly_net:,.0f}/mo.",
            "productivity": f"Focus {agents['productivity']['focus_score']}/100. {agents['productivity']['trends']}.",
            "learning": f"Consistency {agents['learning']['consistency_score']}/100. Urgency: {agents['learning']['urgency']}.",
            "behavior": f"Burnout {b['burnout_risk_level']} ({b['burnout_risk_score']}/100). Energy: {b['energy_cycles']}."
        }
    }

def generate_prediction_text(agents, monthly_net, runway):
    f_risk = agents['finance']['risk_score']
    if monthly_net < 0 and f_risk <= 80:
        return f"DEFICIT: You are short ${abs(monthly_net):,.0f}/mo despite {runway:.1f} months runway. Stop new purchases and restore positive cash flow before optimizing."
    if f_risk > 80: 
        if runway < 1:
            return f"CRITICAL: At current burn rate (${abs(monthly_net):,.0f}/mo deficit), you will be insolvent within {max(1, int(runway * 30))} days. Immediate intervention required."   
        return f"WARNING: ${abs(monthly_net):,.0f}/mo deficit gives you {runway:.1f} months of runway. Without correction, financial collapse is inevitable."
    elif runway < 1 and monthly_net > 0:
        return f"BUFFER NEEDED: You have a strong ${monthly_net:,.0f}/mo surplus, but only {runway:.1f} months of cash runway. First priority is building at least a starter emergency fund before new purchases or investing."
    elif f_risk > 50:
        if monthly_net < 0:
            return f"FRICTION: You are running a ${abs(monthly_net):,.0f}/mo deficit. Stop new purchases, reduce expenses, and restore positive cash flow before building reserves."
        return f"FRICTION: Tight margins with ${monthly_net:,.0f}/mo surplus. One unexpected expense could push you into deficit. Build a 3-month buffer."
    elif f_risk > 30:
        return f"STABLE: ${monthly_net:,.0f}/mo surplus with {runway:.1f} months runway. Continue accumulating reserves and optimizing spending."
    else:
        return f"OPTIMIZED: Strong ${monthly_net:,.0f}/mo surplus with {runway:.1f}+ months runway. Consider strategic investments or accelerating skill development."

def generate_simulation_text( agents, profile_data ):
    income  = safe_float(profile_data.get('finance', {}).get('monthly_income', 0))
    expenses = safe_float(profile_data.get('finance', {}).get('monthly_expenses', 0))  
    idle_cash  = safe_float(profile_data.get('finance', {}).get('idle_cash', 0))
    monthly_net = income - expenses
    f_risk = agents['finance']['risk_score']
    b_risk  = agents['behavior']['burnout_risk_score']
    parts = []
    if monthly_net < 0:   
        days_to_zero = int(idle_cash / (abs(monthly_net) / 30)) if monthly_net != 0 else 999
        parts.append(f"FINANCIAL ALERT: At your current deficit of ${abs(monthly_net):,.0f}/month, your ${idle_cash:,.0f} reserves will be exhausted in approximately {days_to_zero} days.")
        parts.append(f"By Day 15, you'll have burned through ~${int(abs(monthly_net) / 2):,}. By Day 30, your liquid position drops to ${max(0, int(idle_cash + monthly_net)):,}.")
        if abs(monthly_net) > income * 0.3:
            parts.append("This trajectory is unsustainable. Without immediate expense cuts of 30%+, you face cascading financial failure.")
    elif monthly_net > 0:
        monthly_savings  = monthly_net
        parts.append(f"GROWTH TRAJECTORY: Your ${monthly_savings:,.0f}/month surplus will add ${int(monthly_savings):,} to reserves over 30 days, bringing your total to ${int(idle_cash + monthly_savings):,}.")
        safe_income = max(1.0, income)
        if income > 0 and monthly_savings > income * 0.2:
            parts.append(f"Your {monthly_savings/safe_income*100:.0f}% savings rate is excellent. At this pace, you'll build a 6-month emergency fund in {max(1, int((expenses * 6 - idle_cash) / monthly_savings))} months.")
        elif income > 0:
            parts.append(f"Your savings rate of {monthly_savings/safe_income*100:.0f}% is moderate. Consider reducing discretionary spending to accelerate wealth building.")
        else:
            parts.append(f"You are successfully building reserves at ${monthly_savings:,.0f}/month. Maintain this discipline to expand your financial runway.")
    else:    
        parts.append("BREAKEVEN: You're spending exactly what you earn. No growth, no decline. One unexpected expense will push you into deficit.")
    if b_risk > 60:
        parts.append(f"BURNOUT WARNING: Biological stress indicators are at {b_risk}/100. Without recovery intervention (sleep, exercise), expect productivity decline of 20-40% within 2 weeks.")
    elif b_risk < 30:
        parts.append("RECOVERY OPTIMAL: Strong biological markers support sustained high performance over the next 30 days.")
    return " ".join(parts)

def generate_plan(agents, profile_data):
    f_risk = agents['finance']['risk_score']   
    b_risk = agents['behavior']['burnout_risk_score']
    income = safe_float(profile_data.get('finance', {}).get('monthly_income', 0))    
    expenses  = safe_float(profile_data.get('finance', {}).get('monthly_expenses', 0))
    idle_cash = safe_float(profile_data.get('finance', {}).get('idle_cash', 0))
    monthly_net = income - expenses
    plan = []
    if monthly_net > 0 and idle_cash < max(1000, expenses * 0.5):
        starter = max(1000, int(expenses * 0.5))
        plan.append(f"Day 1: Move the first ${min(int(monthly_net), starter):,} of surplus into savings; starter buffer target is ${starter:,}.")
        plan.append("Day 2: Freeze new purchases until that starter buffer exists.")
        plan.append("Day 3: Keep career-growth learning on schedule with one focused block.")
    elif f_risk > 60:
        cut_target = max(100, int(expenses * 0.15))
        plan.append(f"Day 1: Audit all expenses — identify ${cut_target:,} in monthly cuts.")
        plan.append(f"Day 2: Cancel non-essential subscriptions and freeze discretionary spending.")
        plan.append(f"Day 3: Explore side income — target ${max(200, int(expenses - income)):,}/mo additional revenue.")
    else:
        plan.append(f"Day 1: Review investment opportunities for your ${int(monthly_net):,}/mo surplus.")
        plan.append("Day 2: Optimize tax strategy and automate savings transfers.")  
        plan.append("Day 3: Allocate 2 hours to high-leverage skill development.")
    if b_risk > 50:
        plan.append("Day 4: Implement sleep hygiene protocol — 8hr target, no screens 1hr before bed.")
    else:
        plan.append( "Day 4: Scale deep work sessions to 4+ focused hours." )  
    plan.append("Day 5: Full system review — reassess all metrics and adjust 30-day targets.")
    return plan

def generate_decision(question, profile_data):    
    profile_data = normalize_profile_data(profile_data)
    agents = run_multi_agent_system(profile_data)
    income = safe_float(profile_data.get('finance', {}).get('monthly_income', 0))
    expenses = safe_float(profile_data.get('finance', {}).get('monthly_expenses', 0))
    idle_cash  = safe_float(profile_data.get('finance', {}).get('idle_cash', 0))  
    monthly_net = income - expenses
    runway = round(idle_cash / expenses, 1) if expenses > 0 else 99.0
    agent_summary = {
        "instability": agents['instability'],
        "finance": {
            "status": agents['finance']['status'],
            "income": int(income),
            "expenses": int(expenses),
            "idle_cash": int(idle_cash),
            "monthly_net": int(monthly_net),
            "runway_months": runway,
            "savings_rate": agents['finance'].get('savings_rate', 0)
        },
        "behavior": {
            "burnout_risk_score": agents['behavior']['burnout_risk_score'],
            "burnout_risk_level": agents['behavior']['burnout_risk_level'],
            "sleep_hours": safe_float(profile_data.get('behavior', {}).get('sleep_hours_avg', 8)),
            "energy_cycles": agents['behavior']['energy_cycles']
        },
        "productivity": {
            "focus_score": agents['productivity']['focus_score'],
            "deep_work_hours": safe_float(profile_data.get('productivity', {}).get('deep_work_hours', 0)),
            "screen_time": safe_float(profile_data.get('productivity', {}).get('daily_screen_time_hours', 6))
        },
        "learning": {
            "consistency_score": agents['learning']['consistency_score'],
            "hours_per_week": safe_float(profile_data.get('learning', {}).get('hours_per_week', 0)),
            "focus": profile_data.get('learning', {}).get('current_focus', 'General')
        }
    }
    q_lower = str(question or "").lower()
    if (
        (_is_generic_question(q_lower) and not _profile_has_financial_baseline(profile_data))
        or _is_next_steps_question(q_lower)
        or _is_ambiguous_social_question(q_lower)
        or _is_weekend_planning_question(q_lower)
        or _is_relationship_question(q_lower)
    ):
        return generate_deterministic_decision(question, agents, profile_data)
    ai_data = gemini_service.get_strategic_decision( agent_summary, question )
    if ai_data and not _ai_decision_needs_local_fallback(ai_data, question):
        return {
            "decision": ai_data.get("decision", "CAUTION"),
            "why": ai_data.get("why", "Based on multi-agent synthesis."),  
            "alternative": ai_data.get( "alternative", "Review core bottlenecks." ),
            "prediction": ai_data.get("prediction", generate_prediction_text(agents, monthly_net, runway)),
            "risk_score": agents['instability'],
            "finance_agent": agents['finance'],
            "productivity_agent": agents['productivity'],
            "learning_agent": agents['learning'],
            "behavior_agent": agents['behavior'], 
            "personality_profile": get_personality(agents),   
            "explanations": agents['explanations'],  
            "reasoning": {
                "finance": f"Risk {agents['finance']['risk_score']}/100. {agents['finance']['status']}. Net: ${monthly_net:,.0f}/mo.",
                "productivity": f"Focus {agents['productivity']['focus_score']}/100. {agents['productivity']['trends']}.",   
                "learning": f"Consistency {agents['learning']['consistency_score']}/100. Urgency: {agents['learning']['urgency']}.",
                "behavior": f"Burnout {agents['behavior']['burnout_risk_level']} ({agents['behavior']['burnout_risk_score']}/100). Energy: {agents['behavior']['energy_cycles']}."
            }
        }
    return generate_deterministic_decision(question, agents, profile_data)

def run_full_analysis(profile_data):
    profile_data = normalize_profile_data(profile_data)
    agents = run_multi_agent_system(profile_data)    
    income = safe_float(profile_data.get('finance', {}).get('monthly_income', 0))
    expenses = safe_float(profile_data.get('finance', {}).get('monthly_expenses', 0))
    idle_cash = safe_float(profile_data.get('finance', {}).get('idle_cash', 0))
    monthly_net = income - expenses
    runway = round(idle_cash / expenses, 1) if expenses > 0 else 99.0
    agent_summary = {
        "instability": agents['instability'],
        "finance": agents['finance']['status'],
        "monthly_net": int(monthly_net),
        "runway": runway,   
        "savings_rate": agents['finance'].get('savings_rate', 0),
        "behavior": agents['behavior']['burnout_risk_level'],
        "productivity": agents['productivity']['focus_score']
    }
    ai_data  = gemini_service.get_full_analysis(agent_summary)
    if ai_data: 
        return {
            "life_summary": "System analysis complete.",
            "risk_score": agents['instability'],
            "finance_agent": agents['finance'],  
            "productivity_agent": agents['productivity'],  
            "learning_agent": agents['learning'],
            "behavior_agent": agents['behavior'],
            "simulation_30_day": ai_data.get("simulation", generate_simulation_text(agents, profile_data)),
            "optimization_plan": ai_data.get("plan") if ai_data.get("plan") else generate_plan(agents, profile_data),
            "personality_profile": ai_data.get( "personality_profile", get_personality( agents ) ),    
            "explanations": agents['explanations']
        }   
    return {
        "life_summary": "System analysis complete.",
        "risk_score": agents['instability'],
        "finance_agent": agents['finance'],
        "productivity_agent": agents['productivity'],
        "learning_agent": agents['learning'],
        "behavior_agent": agents['behavior'],
        "simulation_30_day": generate_simulation_text(agents, profile_data),
        "optimization_plan": generate_plan(agents, profile_data),  
        "personality_profile": get_personality(agents),   
        "explanations": agents['explanations']
    }
