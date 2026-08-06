# Aurora AI — Decision Intelligence System

![Aurora AI demo](demos/aurora-ai-demo.gif)

Aurora AI helps you make better life choices using data from across your daily life. Instead of just tracking information, it analyzes your finances, productivity, and behavior to determine whether a decision is actually beneficial long-term.

**Live demo:** [https://aurora-ai-o2f6.onrender.com/](https://aurora-ai-o2f6.onrender.com/)

---

## What Aurora does

Users input their current state through manual entry or by uploading documents (bank statements, expense reports, habit logs), then ask real-world questions like:

- "Should I buy this $40,000 car?"
- "Can I afford to take a pay cut for my dream job?"
- "Should I work tonight or take a break?"

Aurora performs structured reasoning by:

- Extracting financial and behavioral signals from user data
- Evaluating stability using a custom Life Instability Index
- Simulating short-term outcomes of decisions
- Identifying risks such as financial strain, burnout, or loss of progress

The system outputs a clear **Yes / No / Caution** decision, plus reasoning, risks, and suggested alternatives. It can also ask follow-up clarification questions when input is incomplete.

---

## How it works — multi-agent decision system

Aurora uses specialized AI agents that evaluate decisions from different perspectives:

| Agent | Role |
|-------|------|
| **Finance Agent** | Analyzes income, expenses, savings, and financial risk |
| **Productivity Agent** | Evaluates focus, workload, and consistency toward goals |
| **Bio-Behavior Agent** | Tracks energy levels, recovery, and burnout risk |

Each agent contributes an independent perspective. A central orchestrator combines them into a final structured output — more like a decision engine than a chatbot.

---

## Tech stack

| Layer | Tools |
|-------|-------|
| Frontend | HTML, CSS, Tailwind CSS, JavaScript |
| Backend | FastAPI, Python, Pydantic, Uvicorn |
| AI | Gemini API (multi-agent orchestration) |
| Data | NumPy, OpenCV, RapidOCR, PyPDF |
| Deploy | Render |

---

## Setup

### Option 1 — Quick start (Windows)

1. Run `start_aurora.bat`
2. Add your Gemini API key to `backend/.env`

### Option 2 — Manual setup

**Backend**

```bash
cd backend
pip install -r requirements.txt
python main.py
```

**Frontend**

Open `frontend/index.html` in your browser.

---

## Why Aurora is different

Most tools track isolated metrics like money, habits, or productivity. Aurora connects those domains and answers a harder question:

> What should I actually do next?

It turns raw data into structured decisions — a personal decision engine, not just a dashboard.

---

## Future improvements

- Integration with real-time data (calendars, banking, wearables)
- Improved long-term prediction and scenario simulation
- Personalized learning based on user behavior over time
