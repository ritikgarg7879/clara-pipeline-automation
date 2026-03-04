# Clara Answers — Automation Pipeline

> **Demo Call → Retell Agent Draft → Onboarding Updates → Agent Revision**
> Zero-cost, fully automated, version-controlled, production-ready.

---

## What This Project Does

This pipeline automates the Clara Answers client onboarding workflow:

1. **Pipeline A** — Takes a demo call transcript → extracts structured account data → generates a preliminary Retell agent configuration (v1)
2. **Pipeline B** — Takes an onboarding call transcript → extracts updates → merges with v1 → produces updated agent configuration (v2) with full changelog

Runs on all 10 files (5 demo + 5 onboarding) in one command. Zero cost. No manual steps.

---

## Architecture and Data Flow

```
data/demo_calls/*.txt
        │
        ▼
transcript_processor.py       ← Groq API (llama-3.3-70b) or rule-based fallback
        │
        ▼
account_memo.json (v1)         ← Structured extraction: hours, services, routing, constraints
        │
        ▼
agent_prompt_generator.py     ← Builds full Retell agent system prompt + config
        │
        ▼
outputs/accounts/ACC_XXX/v1/  ← account_memo.json + agent_config.json saved
        │
        ▼
task_tracker.py               ← Task logged to task_log.json (+ Trello/Notion optional)


data/onboarding_calls/*.txt
        │
        ▼
transcript_processor.py       ← Extracts only NEW or UPDATED fields
        │
        ▼
batch_processor._merge()      ← Smart merge: lists = union, dicts = deep merge, scalars = update if non-empty
        │
        ▼
account_memo.json (v2)         ← Updated memo, no unrelated fields overwritten
        │
        ▼
agent_prompt_generator.py     ← Regenerates full agent config for v2
        │
        ▼
outputs/accounts/ACC_XXX/v2/  ← account_memo.json + agent_config.json saved
        │
        ▼
version_manager.py            ← Diff generated, changelog written, diff report saved
        │
        ▼
changelog/                    ← ACC_XXX_changelog.json + ACC_XXX_v1_to_v2_diff.md
```

---

## Folder Structure

```
clara_assignment/
│
├── scripts/                          ← All Python code
│   ├── transcript_processor.py       ← Extracts data from transcripts (Groq API + rule-based)
│   ├── agent_prompt_generator.py     ← Generates Retell agent system prompt and config
│   ├── version_manager.py            ← Saves versions, diffs, changelogs
│   ├── batch_processor.py            ← Orchestrates full pipeline (main entry point)
│   ├── api_server.py                 ← Flask REST API for n8n integration
│   ├── task_tracker.py               ← Logs tasks to JSON (+ optional Trello/Notion)
│   └── test_pipeline.py              ← 77 tests covering all components
│
├── data/
│   ├── demo_calls/                   ← Input: 5 demo call transcripts
│   └── onboarding_calls/             ← Input: 5 onboarding call transcripts
│
├── outputs/
│   └── accounts/
│       └── ACC_001/
│           ├── v1/
│           │   ├── account_memo.json ← Extracted from demo call
│           │   └── agent_config.json ← Retell agent config v1
│           └── v2/
│               ├── account_memo.json ← Updated after onboarding
│               └── agent_config.json ← Retell agent config v2
│
├── changelog/
│   ├── ACC_001_changelog.json        ← What changed v1 → v2
│   ├── ACC_001_v1_to_v2_diff.md      ← Human-readable diff report
│   └── ...                           ← Same for ACC_002 through ACC_005
│
├── workflows/
│   ├── demo_call_pipeline.json       ← n8n workflow: demo call → v1
│   └── onboarding_pipeline.json      ← n8n workflow: onboarding → v2
│
├── schemas/
│   ├── account_memo_schema.json      ← JSON schema for account memo validation
│   └── retell_agent_schema.json      ← JSON schema for agent config validation
│
├── dashboard/
│   └── index.html                    ← Browser dashboard: v1 vs v2 diff viewer
│
├── .github/
│   └── workflows/
│       └── test.yml                  ← GitHub Actions: runs tests on every push
│
├── task_log.json                     ← Auto-generated task log (all pipeline runs)
├── batch_processing_summary.json     ← Auto-generated pipeline run summary
├── docker-compose.yml                ← Starts n8n locally (optional)
├── requirements.txt                  ← Python dependencies
├── .env.example                      ← Environment variable template
└── .gitignore                        ← Keeps secrets and generated files off GitHub
```

---

## How to Run Locally

### Step 1 — Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/clara-assignment.git
cd clara-assignment
```

### Step 2 — Create virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Set up environment variables

```bash
cp .env.example .env
```

Open `.env` and add your Groq API key:
```
GROQ_API_KEY=your_key_here
```

Get a free key at https://console.groq.com — no credit card required.

> **Note:** If you leave `GROQ_API_KEY` blank, the pipeline automatically falls back to rule-based regex extraction. It still works completely — just slightly less accurate on complex transcripts.

### Step 5 — Add your transcript files

Place transcript `.txt` files in:
- `data/demo_calls/` — named `acc_001_demo.txt`, `acc_002_demo.txt`, etc.
- `data/onboarding_calls/` — named `acc_001_onboarding.txt`, `acc_002_onboarding.txt`, etc.

The account ID is automatically derived from the filename prefix (`acc_001` → `ACC_001`).

### Step 6 — Run the full pipeline

```bash
python scripts/batch_processor.py
```

That's it. All 10 files are processed automatically.

---

## CLI Options

```bash
# Run full pipeline (Pipeline A + B)
python scripts/batch_processor.py

# Run Pipeline A only (demo calls → v1)
python scripts/batch_processor.py --demo-only

# Run Pipeline B only (onboarding → v2)
python scripts/batch_processor.py --onboarding-only

# Force reprocess even if outputs already exist
python scripts/batch_processor.py --force

# Show accounts summary table only
python scripts/batch_processor.py --summary
```

---

## Run the Tests

```bash
python scripts/test_pipeline.py
```

Expected output:
```
77/77 passed 🎉 All tests passed!
```

Tests cover: extraction accuracy, agent config generation, versioning, smart merge logic, idempotency, and full end-to-end pipeline integration.

---

## Where Outputs Are Stored

| Output | Location |
|--------|----------|
| Account memo v1 | `outputs/accounts/ACC_XXX/v1/account_memo.json` |
| Agent config v1 | `outputs/accounts/ACC_XXX/v1/agent_config.json` |
| Account memo v2 | `outputs/accounts/ACC_XXX/v2/account_memo.json` |
| Agent config v2 | `outputs/accounts/ACC_XXX/v2/agent_config.json` |
| Changelog | `changelog/ACC_XXX_changelog.json` |
| Diff report | `changelog/ACC_XXX_v1_to_v2_diff.md` |
| Task log | `task_log.json` |
| Pipeline summary | `batch_processing_summary.json` |

---

## Output Format

### Account Memo JSON (v1 example)

```json
{
  "account_id": "ACC_001",
  "company_name": "Ben's Electric Solutions",
  "business_hours": {
    "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "start_time": "07:00",
    "end_time": "17:00",
    "timezone": "MST"
  },
  "office_address": "4710 17 Ave SW, Calgary, AB T3E 0E4",
  "services_supported": ["Residential Wiring", "Panel Upgrades", "EV Charger Installation"],
  "emergency_definition": ["complete power outage", "sparking panel", "electrical fire"],
  "emergency_routing_rules": {
    "primary_contact": "403-870-8494",
    "secondary_contacts": [],
    "fallback_protocol": "Take message, callback within 15 minutes"
  },
  "non_emergency_routing_rules": {
    "primary_contact": "403-870-8494",
    "secondary_contacts": [],
    "message_protocol": "Take message, callback within 2 hours"
  },
  "call_transfer_rules": {
    "timeout_seconds": 30,
    "max_retries": 3,
    "failure_message": "I'm unable to connect you right now..."
  },
  "integration_constraints": [
    "Never schedule jobs without customer confirmation",
    "Never take on jobs outside Calgary"
  ],
  "after_hours_flow_summary": "Screen for emergencies, transfer if emergency, take message if not",
  "office_hours_flow_summary": "Greet, identify need, collect info, route to 403-870-8494",
  "questions_or_unknowns": [],
  "version": "v1"
}
```

### Retell Agent Config

The generated agent config includes:
- `agent_name` — company-specific agent name
- `voice_style` — gender, tone, pace
- `system_prompt` — full multi-section prompt (see Prompt Structure below)
- `key_variables` — timezone, hours, routing contacts
- `tool_invocation_placeholders` — transfer, message, schedule tools
- `call_transfer_protocol` — timeout, retries, failure message
- `fallback_protocol` — what to say when transfer fails
- `conversation_flows` — scripted office hours and after-hours flows
- `version` + `changelog` — full version history

### Prompt Structure

Every generated system prompt follows this exact structure:

**Business Hours Call Flow:**
1. Greeting
2. Identify purpose
3. Collect caller name and number
4. Route the call (transfer)
5. If transfer fails — take message and assure callback
6. Ask if they need anything else
7. Close

**After-Hours Call Flow:**
1. Greeting — inform office is closed
2. Identify if emergency
3a. If emergency — collect name, number, address immediately → attempt transfer → fallback if fails
3b. If non-emergency — collect details → confirm next-business-day callback
4. Close

**Emergency Handling (any time):**
- Immediate transfer attempt to primary contact
- Backup contacts if primary fails
- Assure callback within 15 minutes if all transfers fail

---

## Versioning Logic

### What v1 Contains
Only data explicitly stated in the demo call. Missing fields are left blank or flagged in `questions_or_unknowns`. Nothing is assumed or invented.

### What v2 Contains
v1 data merged with onboarding call updates using these rules:
- **Lists** (services, constraints, emergency definitions) → union, no duplicates
- **Dicts** (routing rules, business hours) → deep merge, only non-empty fields updated
- **Scalars** (company name, address) → updated only if new value is non-empty
- **account_id** → never changed under any circumstance

### Changelog Example
```json
{
  "from_version": "v1",
  "to_version": "v2",
  "changes": [
    "Added to Emergency definition: carbon monoxide alarm triggered by electrical fault",
    "Updated Emergency routing",
    "Added to Integration constraints: Never create a job in Jobber without verbal confirmation"
  ]
}
```

---

## n8n Workflow Setup (Optional)

The project includes n8n workflow exports for webhook-based automation.

### Start n8n locally

```bash
docker-compose up -d
```

n8n runs at `http://localhost:5678`
Default login: `admin` / `change_me_please`

### Start the API server

```bash
python scripts/api_server.py
```

API runs at `http://localhost:8000`

### Import workflows into n8n

1. Open n8n at `http://localhost:5678`
2. Go to **Workflows → Import**
3. Import `workflows/demo_call_pipeline.json`
4. Import `workflows/onboarding_pipeline.json`

### Trigger via webhook

```bash
# Pipeline A — demo call
curl -X POST http://localhost:5678/webhook/demo-call-webhook \
  -H "Content-Type: application/json" \
  -d '{"account_id": "ACC_001", "transcript": "Your transcript text here..."}'

# Pipeline B — onboarding
curl -X POST http://localhost:5678/webhook/onboarding-webhook \
  -H "Content-Type: application/json" \
  -d '{"account_id": "ACC_001", "transcript": "Your onboarding transcript here..."}'
```

---

## Dashboard — Diff Viewer

Open `dashboard/index.html` in your browser while the API server is running:

```bash
python scripts/api_server.py
# then open dashboard/index.html in browser
```

Shows:
- All 5 accounts with version badges
- v1 vs v2 account memo side by side
- v1 vs v2 agent system prompt side by side
- Changelog entries per account
- Summary stats (total accounts, upgrades, flags, changes)

---

## Task Tracker

Every pipeline run automatically logs a task to `task_log.json`:

```json
{
  "task_id": "ACC_001_demo_processing_20260304",
  "account_id": "ACC_001",
  "company_name": "Ben's Electric Solutions",
  "task_type": "demo_processing",
  "status": "completed",
  "details": {
    "version": "v1",
    "outputs": {
      "account_memo": "outputs/accounts/ACC_001/v1/account_memo.json",
      "agent_config": "outputs/accounts/ACC_001/v1/agent_config.json"
    }
  }
}
```

**Optional integrations** — add keys to `.env` to sync tasks automatically:
- **Trello** free tier — `TRELLO_API_KEY` + `TRELLO_TOKEN` + `TRELLO_LIST_ID`
- **Notion** free tier — `NOTION_API_KEY` + `NOTION_DATABASE_ID`

---

## Zero-Cost Compliance

| Component | Tool Used | Cost |
|-----------|-----------|------|
| LLM extraction | Groq API free tier (llama-3.3-70b-versatile) | $0 |
| Fallback extraction | Rule-based regex (no API) | $0 |
| Storage | Local JSON files in GitHub repo | $0 |
| Automation orchestrator | n8n self-hosted via Docker | $0 |
| Task tracker | Local JSON (+ Trello/Notion free tier) | $0 |
| CI/CD | GitHub Actions free tier | $0 |
| **Total** | | **$0** |

> Groq's free tier provides 14,400 requests/day on llama-3.3-70b-versatile with no credit card required. The pipeline uses approximately 10 requests for a full dataset run.

---

## Known Limitations

1. **Rule-based extraction accuracy** — Without a Groq API key, the regex fallback may miss services or constraints that are phrased unusually. Groq API is strongly recommended for production use.

2. **Audio transcription not included** — The pipeline accepts transcripts as input. If only audio recordings are available, a separate transcription step (e.g. OpenAI Whisper running locally) is needed before running the pipeline.

3. **Single-language support** — Extraction is optimized for English transcripts only.

4. **Phone number disambiguation** — If the same phone number is used for both emergency and non-emergency routing (common in small businesses), the non-emergency contact may show as blank and be flagged in `questions_or_unknowns`.

5. **n8n requires Docker** — The webhook automation layer requires Docker to run n8n locally. The core Python pipeline works without Docker.

6. **No Retell API integration** — Retell's free tier does not support programmatic agent creation. The pipeline produces a `agent_config.json` that exactly matches the Retell agent spec format. This can be manually imported into the Retell UI or used directly as a spec document.

---

## Retell Integration Notes

Since Retell does not allow programmatic agent creation on free tier:

**Manual import steps:**
1. Open the generated `outputs/accounts/ACC_XXX/v1/agent_config.json`
2. Copy the `system_prompt` field
3. Log into Retell → Create New Agent
4. Paste the system prompt into the agent prompt field
5. Set voice style to match `voice_style` field (female, professional)
6. Configure transfer numbers from `key_variables.emergency_routing` and `key_variables.non_emergency_routing`

The `agent_config.json` is designed to map directly to Retell's agent configuration UI with no translation needed.

---

## What I Would Improve With Production Access

1. **Direct Retell API integration** — With a paid Retell account, `api_server.py` already has the structure to call Retell's agent creation endpoint directly. One additional function in `agent_prompt_generator.py` would complete this.

2. **Real-time audio transcription** — Add a Whisper transcription step at the start of the pipeline so it accepts `.mp3` / `.wav` files directly, not just transcripts.

3. **Supabase storage** — Replace local JSON files with Supabase (free tier) for multi-user access, better querying, and real-time updates to the dashboard.

4. **Conflict detection** — When onboarding data contradicts demo data (e.g. different phone number), flag it explicitly in the changelog rather than silently overwriting.

5. **Confidence scoring** — Add a confidence score to each extracted field so reviewers know which fields were extracted with high certainty vs. which ones are best-effort guesses.

6. **Webhook for real transcripts** — Connect to Retell's call recording webhook so transcripts flow in automatically after each call, triggering the pipeline without any manual file placement.

7. **Multi-language support** — Add language detection and extraction support for Spanish and French, which are common in the service trade markets Clara targets.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Optional | Groq API key for LLM extraction. Get free at console.groq.com |
| `API_PORT` | Optional | Port for Flask API server. Default: 8000 |
| `API_HOST` | Optional | Host for Flask API server. Default: 0.0.0.0 |
| `N8N_BASIC_AUTH_USER` | Optional | n8n login username. Default: admin |
| `N8N_BASIC_AUTH_PASSWORD` | Optional | n8n login password |
| `N8N_PORT` | Optional | n8n port. Default: 5678 |
| `TRELLO_API_KEY` | Optional | Trello integration for task tracking |
| `TRELLO_TOKEN` | Optional | Trello auth token |
| `TRELLO_LIST_ID` | Optional | Trello list ID to post cards to |
| `NOTION_API_KEY` | Optional | Notion integration for task tracking |
| `NOTION_DATABASE_ID` | Optional | Notion database ID to post rows to |

---

## Submission

Repository contains:
- `/scripts` — all pipeline code
- `/workflows` — n8n workflow exports
- `/outputs/accounts/<account_id>/v1` and `v2` — all generated outputs
- `/changelog` — per-account changelog and diff reports
- `/dashboard` — visual diff viewer
- `/schemas` — JSON schemas for validation
- `/data` — sample transcripts (5 demo + 5 onboarding)
- `task_log.json` — full task history
- `README.md` — this file

---

*Built for the Clara Answers Intern Assignment — zero cost, fully automated, production-minded.*
