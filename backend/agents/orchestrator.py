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

def run_multi_agent_system( profile_data ):  
    finance = analyze_finance(profile_data.get('finance', {}))
    prod = analyze_productivity(profile_data.get('productivity', {}))
    learning  = analyze_learning(profile_data.get('learning', {})) 
    behavior = analyze_behavior(profile_data.get('behavior', {}))
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
            follow_ups.append(f"I'm assuming a home price of ${cost:,.0f} (national average). What is the actual price and location?")
        follow_ups.append("Do you have a co-signer or existing home equity to reduce the down payment requirement?")
    elif "car" in q or "vehicle" in q:
        item_type  = "car"
        cost  = extracted_price or 30000
        down_pct  = 0.15
        rate = 0.07
        term_years  = 5
        if not extracted_price:
            follow_ups.append(f"I'm assuming a vehicle cost of ${cost:,.0f}. What's the actual price? New or used?")
    elif "laptop" in q or "computer" in q or "macbook" in q or "pc" in q:
        item_type  = "laptop"
        cost = extracted_price or 1200
        down_pct  = 1.0
        rate = 0   
        term_years = 0
        if not extracted_price:
            follow_ups.append(f"I'm assuming ~${cost:,.0f} for a quality laptop. What's the actual price and model?")
    elif "phone" in q or "iphone" in q:
        item_type  = "phone"
        cost = extracted_price or 1100
        down_pct  = 1.0
        rate  = 0
        term_years = 0   
        if not extracted_price:
            follow_ups.append(f"I'm assuming ~${cost:,.0f} for a flagship phone. What's the actual price?")
    else:
        item_type = "purchase"  
        cost = extracted_price or 5000
        down_pct  = 1.0 
        rate = 0
        term_years = 0    
        if not extracted_price:
            follow_ups.append(f"I'm assuming a cost of ${cost:,.0f}. What's the actual amount?")
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
        decision = "NO" if idle_cash < cost * 0.5 else "CAUTION"
        why  = (f"This {item_type} costs ~${cost:,.0f}. You have ${idle_cash:,.0f} in savings. "
               f"{'Buying this would wipe out your reserves.' if idle_cash > 0 else 'You have no savings to cover this.'} "
               f"{follow_up_text}")
        if monthly_net > 0:
            alt = (f"Save ${min(monthly_net, cost / 3):,.0f}/month for {math.ceil(cost / max(1, min(monthly_net, cost / 3)))} months. "
                   f"You'll have ${cost:,.0f} saved by month {math.ceil(cost / max(1, monthly_net))} at your current surplus rate. "
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
        decision  = "YES" if remaining_surplus > expenses * 0.2 else "CAUTION"
        emergency_after = idle_cash - down_payment 
        months_emergency  = emergency_after / expenses if expenses > 0 else 99  
        why = (f"With ${idle_cash:,.0f} in savings, you can cover the ${down_payment:,.0f} down payment "
               f"and still have ${emergency_after:,.0f} in reserves ({months_emergency:.1f} months of expenses). "
               f"Monthly payments of ${monthly_payment:,.0f} leave you ${remaining_surplus:,.0f}/mo surplus. "
               f"{follow_up_text}")  
        if months_emergency < 3:
            alt = (f"CAUTION: After the down payment, you'll only have {months_emergency:.1f} months of emergency reserves. "
                   f"Save an additional ${int( expenses * 3 - emergency_after ):,} before purchasing to maintain a safe buffer." )
        else:
            alt = f"Proceed, but maintain ${int(expenses * 6):,} emergency fund. Lock in the best rate available and consider accelerated payments if surplus allows."
    prediction = generate_prediction_text(agents, monthly_net, runway)  
    return {    
        "decision": decision,
        "why": why,
        "alternative": alt,
        "prediction": prediction,
        "life_instability_index": inst,
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
    q = str(question or "").lower()
    f = agents['finance']
    b = agents['behavior']
    inst = agents['instability']
    income = safe_float(profile_data.get('finance', {}).get('monthly_income', 0))
    expenses = safe_float(profile_data.get('finance', {}).get('monthly_expenses', 0))
    idle_cash = safe_float(profile_data.get('finance', {}).get('idle_cash', 0))
    monthly_net = income - expenses
    runway = round(idle_cash / expenses, 1) if expenses > 0 else 99.0

    decisions = []
    whys = []
    alts = []

    # 1. Purchase intent
    if any(w in q for w in ["buy", "house", "car", "purchase", "spend", "laptop", "phone"]):
        res = _handle_purchase_decision(q, income, expenses, idle_cash, monthly_net, runway, f, b, inst, agents)
        decisions.append(res['decision'])
        whys.append(res['why'])
        alts.append(res['alternative'])

    # 2. Social/Discretionary intent
    if any(w in q for w in ["go out", "got out", "out", "friends", "weekend", "vacation", "trip", "party", "social", "relax", "break", "rest"]):
        if expenses >= income and idle_cash < expenses:
            decisions.append("NO")
            whys.append(f"Your cashflow is negative (${monthly_net:,.0f}/mo). Discretionary spending will accelerate financial instability.")
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
    if any(w in q for w in ["focus", "study", "learn", "learning", "work", "prioritize", "week", "exam", "course"]):
        is_choice = " or " in q or " vs " in q
        is_open = "what" in q or "how" in q
        if f['risk_score'] > 60:
            decisions.append("EARN" if (is_choice or is_open) else "COURSE CORRECTION")
            whys.append(f"Financial pressure (risk {f['risk_score']}/100) is your #1 bottleneck. Focus energy on income generation and expense reduction.")
            alts.append(f"Dedicate 2 hours/day to income-generating activities until monthly surplus exceeds ${max(500, income * 0.15):,.0f}.")
        elif b['burnout_risk_score'] > 60:
            decisions.append("REST" if (is_choice or is_open) else "CAUTION")
            whys.append(f"Burnout risk is {b['burnout_risk_score']}/100. Pushing harder will reduce output. Prioritize recovery first.")
            alts.append("Implement 90-minute deep work blocks with 30-minute recovery cycles.")
        else:
            if agents['productivity']['focus_score'] > 80 and b['burnout_risk_score'] < 30 and f['risk_score'] < 30:
                decisions.append("REST" if (is_choice or is_open) else "YES")
                whys.append(f"Your system is highly optimized (instability {inst}/100) and you've put in the work. You have earned a break. Go out and enjoy yourself.")
                alts.append("Use this time to completely disconnect from work and recharge.")
            else:
                decisions.append("STUDY" if (is_choice or is_open) else "YES")
                whys.append(f"Your system is balanced (instability {inst}/100). Lean into deep work — you have the biological and financial runway for it.")
                alts.append(f"Target {min(8, agents['productivity']['focus_score'] / 10 + 2):.0f} hours of deep work this week.")

    # 4. Final Aggregation
    if not decisions:
        if inst > 70:
            final_decision = "CAUTION"
            final_why = f"Your life instability is {inst}/100. Before making any decisions, stabilize your primary risk factors."
            final_alt = "Address the highest-risk pillar first: " + ("finances" if f['risk_score'] > b['burnout_risk_score'] else "burnout recovery") + "."
        elif inst > 40:
            final_decision = "PROCEED WITH AWARENESS"
            final_why = f"Moderate instability ({inst}/100). Consider how this decision affects your weakest areas."
            final_alt = "Evaluate the financial and energy cost of this choice before committing."
        else:
            final_decision = "UNSURE"
            final_why = f"Your metrics are healthy (instability {inst}/100), but I need more details to evaluate this specific request. Can you clarify?"
            final_alt = "Please try rephrasing your question or adding specific constraints like price or time."
    else:
        # Prioritize specific choices (e.g., STUDY, SLEEP) over generic YES/NO
        specific_choices = [d for d in decisions if d not in ["YES", "NO", "CAUTION", "COURSE CORRECTION"]]
        if specific_choices:
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

    prediction = generate_prediction_text(agents, monthly_net, runway)
    return {
        "decision": final_decision,
        "why": final_why,
        "alternative": final_alt,
        "prediction": prediction,
        "life_instability_index": inst,
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
    if f_risk > 80: 
        if runway < 1:
            return f"CRITICAL: At current burn rate (${abs(monthly_net):,.0f}/mo deficit), you will be insolvent within {max(1, int(runway * 30))} days. Immediate intervention required."   
        return f"WARNING: ${abs(monthly_net):,.0f}/mo deficit gives you {runway:.1f} months of runway. Without correction, financial collapse is inevitable."
    elif f_risk > 50:
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
    plan = []
    if f_risk > 60:
        cut_target = max(100, int(expenses * 0.15))
        plan.append(f"Day 1: Audit all expenses — identify ${cut_target:,} in monthly cuts.")
        plan.append(f"Day 2: Cancel non-essential subscriptions and freeze discretionary spending.")
        plan.append(f"Day 3: Explore side income — target ${max(200, int(expenses - income)):,}/mo additional revenue.")
    else:
        plan.append(f"Day 1: Review investment opportunities for your ${int(income - expenses):,}/mo surplus.")
        plan.append("Day 2: Optimize tax strategy and automate savings transfers.")  
        plan.append("Day 3: Allocate 2 hours to high-leverage skill development.")
    if b_risk > 50:
        plan.append("Day 4: Implement sleep hygiene protocol — 8hr target, no screens 1hr before bed.")
    else:
        plan.append( "Day 4: Scale deep work sessions to 4+ focused hours." )  
    plan.append("Day 5: Full system review — reassess all metrics and adjust 30-day targets.")
    return plan

def generate_decision(question, profile_data):    
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
    ai_data = gemini_service.get_strategic_decision( agent_summary, question )
    if ai_data:
        return {
            "decision": ai_data.get("decision", "CAUTION"),
            "why": ai_data.get("why", "Based on multi-agent synthesis."),  
            "alternative": ai_data.get( "alternative", "Review core bottlenecks." ),
            "prediction": ai_data.get("prediction", generate_prediction_text(agents, monthly_net, runway)),
            "life_instability_index": agents['instability'],
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
    agents = run_multi_agent_system(profile_data)    
    income = safe_float(profile_data.get('finance', {}).get('monthly_income', 0))
    expenses = safe_float(profile_data.get('finance', {}).get('monthly_expenses', 0))
    idle_cash = safe_float(profile_data.get('finance', {}).get('idle_cash', 0))
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
    ai_data  = gemini_service.get_full_analysis(agent_summary)
    if ai_data: 
        return {
            "life_summary": f"Life Instability: {agents['instability']}/100.",
            "risk_score": agents['instability'],
            "finance_agent": agents['finance'],  
            "productivity_agent": agents['productivity'],  
            "learning_agent": agents['learning'],
            "behavior_agent": agents['behavior'],
            "simulation_30_day": ai_data.get("simulation", generate_simulation_text(agents, profile_data)),
            "optimization_plan": ai_data.get("plan", generate_plan(agents, profile_data)),
            "personality_profile": ai_data.get( "personality_profile", get_personality( agents ) ),    
            "explanations": agents['explanations']
        }   
    return {
        "life_summary": f"Life Instability: {agents['instability']}/100.",
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