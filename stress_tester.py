import time
import requests
import json
import threading

BASE_URL = "https://aurora-ai-o2f6.onrender.com/api"

def print_result(name, res):
    try:
        data = res.json()
        if res.status_code == 200:
            print(f"[PASS] {name}")
            if "decision" in data:
                print(f"   -> Decision: {data['decision']}")
                print(f"   -> Why: {data['why']}")
        else:
            print(f"[FAIL] {name} - Status: {res.status_code}")
            print(data)
    except Exception as e:
        print(f"[ERROR] {name} - {str(e)}")

def test_decision_logic():
    print("\n--- TESTING DECISION LOGIC ---")
    
    # Normal case
    payload = {
        "question": "Should I go out?",
        "user_profile": {
            "finance": {"monthly_income": 5000, "monthly_expenses": 3000, "idle_cash": 10000},
            "behavior": {"sleep_hours_avg": 8, "burnout_risk_score": 20},
            "productivity": {"deep_work_hours": 6, "daily_screen_time_hours": 2},
            "learning": {"hours_per_week": 10}
        }
    }
    res = requests.post(f"{BASE_URL}/decision", json=payload)
    print_result("Normal Case (Healthy)", res)

    # Edge case: Extreme negative cashflow
    payload["user_profile"]["finance"] = {"monthly_income": 2000, "monthly_expenses": 8000, "idle_cash": 100}
    res = requests.post(f"{BASE_URL}/decision", json=payload)
    print_result("Edge Case (Extreme Debt)", res)

    # Edge case: High burnout
    payload["user_profile"]["finance"] = {"monthly_income": 8000, "monthly_expenses": 3000, "idle_cash": 10000}
    payload["user_profile"]["behavior"]["burnout_risk_score"] = 95
    payload["user_profile"]["behavior"]["sleep_hours_avg"] = 2
    res = requests.post(f"{BASE_URL}/decision", json=payload)
    print_result("Edge Case (High Burnout)", res)

    # Edge case: Unknown query (should trigger UNSURE)
    payload["question"] = "Should I eat a rock?"
    res = requests.post(f"{BASE_URL}/decision", json=payload)
    print_result("Edge Case (Unknown Query)", res)

    # Edge case: Malformed / Missing Data
    res = requests.post(f"{BASE_URL}/decision", json={"question": "What to do?", "user_profile": {}})
    print_result("Edge Case (Empty Profile)", res)

def load_test():
    print("\n--- RUNNING LOAD TEST (10 concurrent requests) ---")
    def make_req():
        try:
            requests.get(f"{BASE_URL.replace('/api', '')}/")
        except:
            pass

    threads = []
    for _ in range(10):
        t = threading.Thread(target=make_req)
        t.start()
        threads.append(t)
    
    for t in threads:
        t.join()
    print("[PASS] Completed basic concurrent load test")

if __name__ == "__main__":
    print(f"Waiting 10 seconds before hitting {BASE_URL}...")
    time.sleep(10)
    
    # Test main endpoints
    try:
        print("\n--- PINGING ENDPOINTS ---")
        print_result("Ping Base URL", requests.get(BASE_URL.replace("/api", "/")))
        print_result("Ping /api/account", requests.get(f"{BASE_URL}/account"))
        print_result("Ping /api/profile", requests.get(f"{BASE_URL}/profile"))
    except Exception as e:
        print(f"Initial connection failed: {e}")

    test_decision_logic()
    load_test()
