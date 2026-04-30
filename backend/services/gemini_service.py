import os
import json
import time
import re
from dotenv import load_dotenv

load_dotenv()

class GeminiService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_1")
        self.client = None
        if self.api_key:
            try:    
                from google import genai  
                self.client = genai.Client( api_key=self.api_key )
            except Exception as e:    
                print(f"[AURORA] Gemini SDK init failed: {e}. Deterministic mode active.")
        else:
            print("[AURORA] No GEMINI_API_KEY found. Running in deterministic-only mode.")

        self.models_to_try  = [
            'gemini-1.5-flash',
            'gemini-1.5-pro',
        ]

    def _call_gemini_json(self, prompt, system_instruction=None):
        if not self.client:
            return None
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
                    response  = future.result(timeout=15)
                if response and response.text:
                    text = response.text.strip()
                    if text.startswith("```"):
                        text = re.sub(r'^```(?:json)?', '', text).strip()
                        text = re.sub(r'```$', '', text).strip()
                    try:
                        return json.loads(text)
                    except:
                        # Fallback: Find first { and last }
                        match = re.search(r'(\{[\s\S]*\})', text)
                        if match:
                            try:
                                return json.loads(match.group(1))
                            except:
                                pass
                return None
            except concurrent.futures.TimeoutError:
                return None
            except Exception as e:
                err = str(e)
                if "404" in err:
                    continue
                if "429" in err:
                    continue
                continue
        return None

    def get_strategic_decision(self, agent_data, user_query):
        system_prompt  = (
            "You are Aurora AI, an elite financial and life strategist. "
            "You give precise, data-driven advice grounded in actual numbers, while incorporating human empathy, realistic behavior, and common sense.\n\n"
            "CRITICAL RULES:\n"
            "1. NEVER give vague responses like 'it depends' or 'maintain'.\n"  
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
            "10. CLARIFICATION BEFORE VERDICT: If the user's question lacks essential context to make a responsible decision (and making assumptions would be dangerous), output 'UNSURE' or 'NEED MORE INFO' as the decision. Use the 'why' field to ask the clarifying follow-up question before giving a verdict.\n"
            "11. EXCEPTIONS: If the user indicates an emergency, special occasion, or a once-in-a-lifetime opportunity, factor that into your logic. Sometimes non-optimal financial/productivity decisions are logical human decisions.\n"
            "12. REWARDING HIGH PERFORMERS: If a user has incredibly healthy metrics (e.g., high savings, high deep work hours like 6-8+ hours, low burnout), they have earned a break. In these cases, actively encourage them to 'REST', 'SOCIALIZE', or 'GO OUT' instead of blindly telling them to study or work more. A well-balanced life requires enjoying the fruits of their labor."
         )
        prompt = f"System Metrics: {json.dumps(agent_data)}\nUser Question: {user_query}\nReturn structured JSON with 'decision', 'why', 'alternative', and 'prediction'."
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