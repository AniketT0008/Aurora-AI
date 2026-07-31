import os
import json
import time
import re
import hashlib
from dotenv import load_dotenv

load_dotenv()

class GeminiService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_1")
        self.client = None
        self._response_cache = {}
        self._cache_ttl = 300
        if self.api_key:
            try:    
                from google import genai  
                self.client = genai.Client( api_key=self.api_key )
            except Exception as e:    
                print(f"[AURORA] Gemini SDK init failed: {e}. Deterministic mode active.")
        else:
            print("[AURORA] No GEMINI_API_KEY found. Running in deterministic-only mode.")

        self.models_to_try  = [
            'gemini-2.0-flash-lite',
            'gemini-2.0-flash',
        ]

    def _get_cache_key(self, prompt, system_instruction):
        raw = f"{prompt}|{system_instruction or ''}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _call_gemini_json(self, prompt, system_instruction=None):
        if not self.client:
            return None
        cache_key = self._get_cache_key(prompt, system_instruction)
        cached = self._response_cache.get(cache_key)
        if cached and (time.time() - cached['ts']) < self._cache_ttl:
            return cached['data']
        from google.genai import types
        import concurrent.futures   
        for model_name in self.models_to_try:
            try:
                config  = types.GenerateContentConfig(
                    response_mime_type='application/json',
                    system_instruction=system_instruction
                )   
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        self.client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=config
                    )   
                    response  = future.result(timeout=10)
                if response and response.text:
                    text = response.text.strip()
                    if text.startswith("```"):
                        text = re.sub(r'^```(?:json)?', '', text).strip()
                        text = re.sub(r'```$', '', text).strip()
                    try:
                        return json.loads(text)
                    except:
                        match = re.search(r'(\{[\s\S]*\})', text)
                        if match:
                            try:
                                parsed = json.loads(match.group(1))
                                self._response_cache[cache_key] = {'data': parsed, 'ts': time.time()}
                                return parsed
                            except:
                                pass
                return None
            except concurrent.futures.TimeoutError:
                print(f"[AURORA] Gemini timeout on {model_name}")
                return None
            except Exception as e:
                err = str(e)
                print(f"[AURORA] Gemini error on {model_name}: {err[:120]}")
                if "404" in err:
                    continue
                if "429" in err:
                    return None
                continue
        return None

    def get_strategic_decision(self, agent_data, user_query):
        system_prompt  = (
            "You are Aurora AI, an adaptive personal strategist, closer to a personalized ChatGPT than a fixed rule bot. "
            "You already know the user's finance, productivity, learning, behavior, account, document context, and recent conversation history. "
            "Use that data to answer almost any life, money, work, learning, productivity, purchase, relationship, health-habit, planning, values, logistics, or tradeoff question. "
            "Give precise, data-driven advice grounded in actual numbers, while incorporating human empathy, realistic behavior, and common sense.\n\n"
            "CRITICAL RULES:\n"
            "1. NEVER give vague responses like 'it depends', 'maintain', or 'can you clarify' as the whole answer.\n"  
            "2. MULTI-INTENT HANDLING: If the user asks multiple questions (e.g., 'Should I buy a house AND a car?' or 'Can I go out tonight and also skip my workout?'), you MUST address EVERY part of the query in your reasoning and verdict.\n"
            "3. CHOICE HANDLING: If the user asks for a choice (e.g., 'Should I study or sleep?'), your 'decision' field MUST be the specific choice (e.g., 'STUDY' or 'SLEEP'). DO NOT just say 'YES' or 'NO'.\n"
            "4. OPEN QUESTIONS: If the user asks an open question like 'What should I focus on?' or 'What is my goal?', your 'decision' field MUST be a single capitalized action word (e.g., 'STUDY', 'WORK', 'REST', 'SAVE'). DO NOT say 'YES' or 'NO' to an open question.\n"
            "5. If someone asks about a PURCHASE (house, car, laptop, etc), you MUST:\n"
            "   - Estimate the cost if not specified (average house=$400k, laptop=$1000-1500, car=$30k)\n"
            "   - Determine if it's a financed purchase (house, car) or an outright purchase (laptop, phone, vacation).\n"
            "   - For financed purchases: Calculate the down payment ( houses: 20% = $80k, cars: 10-20% ) AND monthly mortgage/loan payments ( use 6% rate, 25yr for houses; 7% rate, 5yr for cars ).\n"
            "   - For outright purchases: The 'down payment' is 100% of the cost. No loan payments.\n"
            "   - Compare the required upfront cash to their Idle Cash/Savings, and monthly payments to their surplus/deficit.\n"  
            "   - If they CAN'T afford it: tell them exactly how much to save and how many months it will take.\n"
            "   - If info is missing (price, location, specs): state what you're assuming AND ask what the actual values are.\n"
            "5. If someone is spending more than they earn, REJECT purchases firmly with math.\n"
            "6. Always give a SPECIFIC alternative with dollar amounts and timelines.\n"    
            "7. When you need more info, include follow-up questions IN your response (don't just say 'need more info').\n"    
            "   Example: 'Based on an assumed price of $400,000... However, the answer could change significantly — "
            "what is the actual price and location? Do you have a co-signer or existing equity?'\n" 
            "8. Be direct, honest, and show your math.\n"
            "9. HUMAN LOGIC & BALANCED LIVING: Understand that humans need breaks. Going out with friends, taking time off, or buying a reasonable treat is logical and healthy if finances and overall burnout allow it. Do not be overly robotic or strictly optimize for work. Balance long-term stability with short-term happiness.\n"
            "10. OPEN-ENDED IMPROVEMENT QUESTIONS: If the user asks how to improve, increase, reduce, optimize, build, or grow something, give a concrete plan using the supplied metrics. Do NOT output 'UNSURE' just because the question is broad. State assumptions, pick the highest-leverage move, and include dollar targets and timelines.\n"
            "11. CASH FLOW / IDLE CASH QUESTIONS: For questions about increasing cash flow, idle cash, savings, surplus, reserves, or runway, compute monthly_net = income - expenses, savings_rate, emergency-fund target, and a 30-day action plan. Your decision should be a specific action phrase like 'BUILD CASH FLOW' or 'PROTECT CASH', not 'UNSURE'.\n"
            "12. RUNWAY BEFORE PURCHASES: Monthly surplus is not the same as cash runway. If idle_cash is $0 or runway is under 1 month, recommend saving a starter buffer before nonessential purchases or investing, even if monthly surplus is strong. Only override this when the purchase is essential for work, safety, or transportation.\n"
            "13. CLARIFICATION BEFORE VERDICT: If the user's question lacks essential context to make a responsible decision (and making assumptions would be dangerous), output 'UNSURE' or 'NEED MORE INFO' as the decision. This should be rare and reserved for high-risk irreversible decisions, not normal optimization advice. Use the 'why' field to ask the clarifying follow-up question after giving the safest default guidance.\n"
            "14. EXCEPTIONS: If the user indicates an emergency, special occasion, or a once-in-a-lifetime opportunity, factor that into your logic. Sometimes non-optimal financial/productivity decisions are logical human decisions.\n"
            "15. ADAPTIVE LOGIC FOR GRAY AREAS: Life is full of gray areas that cannot be solved with rigid rules (e.g., investing in a risky startup vs saving, taking a low-paying dream job vs high-paying grind, or deciding when to rest vs push harder). Do not apply a one-size-fits-all approach. If personal context is missing, give the safest useful default first, then ask for the exact variable that would personalize the next version.\n"
            "16. HARD STOPS: If the request is dangerous, illegal, financially ruinous, medically unsafe, or likely to cause serious harm, say NO / STOP / PROTECT CASH clearly. Explain the risk and give a safer alternative. Do not be permissive just because the user wants it.\n"
            "17. FOLLOW-UP MEMORY: If the user is replying to a clarification, combine the new details with the original question and answer the original decision. Do not treat the reply as a new unrelated question.\n"
            "18. EXTREME OR GENERIC PROFILES: Adapt to the actual metrics. If the profile is missing a baseline, ask for the smallest missing input set. If income, expenses, sleep, screen time, or cash runway are extreme, prioritize the binding constraint instead of generic productivity advice.\n"
            "19. NEXT STEPS: For 'next steps' or weekly planning questions, return a concrete plan with the primary constraint, first action, and 5-day execution path. Do not answer with only 'STUDY', 'WORK', or 'SAVE'.\n"
            "20. ADULT LIFE DECISIONS: Relationship, dating, marriage, and children questions are not productivity questions. Do not reduce them to career growth or studying. For dating, evaluate time, emotional availability, values, and financial stress. For children, treat it as high-impact and irreversible: discuss partner readiness, support, childcare, housing, health coverage, and 6-12 months of runway.\n"
            "21. GENERAL LLM-LIKE REASONING: If no rule exactly matches the question, infer the domain and reason from first principles. Consider cost, time, reversibility, downside, who is affected, energy impact, opportunity cost, and alignment with the user's stated goals. Never ignore the user's actual question just because it is outside finance/productivity.\n"
            "22. JSON ONLY: Return structured JSON with exactly these fields: decision, why, alternative, prediction. Keep decision short and uppercase. Put the useful advisor response in why and alternative."
         )
        history_str = ""
        if agent_data.get("history"):
            history_str = "\nConversation History:\n" + "\n".join([f"{m['role']}: {m['content']}" for m in agent_data["history"]])
            
        prompt = f"System Metrics: {json.dumps(agent_data)}\n{history_str}\nUser Question: {user_query}\nReturn structured JSON with 'decision', 'why', 'alternative', and 'prediction'."
        return self._call_gemini_json(prompt, system_instruction=system_prompt)
  
    def get_full_analysis(self, agent_data):    
        system_prompt = (
            "You are Aurora AI's forecasting engine. Generate realistic 30-day projections "
            "and 5-day action plans based on real financial math and behavioral science. "
            "Never be generic. Use the actual numbers provided."
        )
        prompt = f"Agent Summary Data: {json.dumps(agent_data)}\nReturn structured JSON with 'simulation' (30-day outlook string) and 'plan' (list of strings) and 'personality_profile' (string)."
        return self._call_gemini_json(prompt, system_instruction=system_prompt)    

    def parse_document( self, doc_text ):
        if not doc_text or not doc_text.strip(  ):
            return None
        system_prompt  = "Extract financial data from documents. Return structured JSON."
        prompt = f"Extract from this text:\n{doc_text}\nReturn structured JSON."
        return self._call_gemini_json(prompt, system_instruction=system_prompt)

gemini_service = GeminiService()
