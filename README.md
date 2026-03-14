# 🚨 Offline Disaster Response Command Center

**Multi-Agent AI Command Center for Emergency First Responders**

> 100% Offline · CPU-Only · LangGraph Orchestration · 17 Advanced Modules

---

## What It Does

Processes spoken or typed emergency descriptions and in **3–6 seconds** produces:

- **Severity classification** with confidence score
- **Step-by-step triage instructions** with timers
- **Inventory check** with low-stock warnings
- **Multi-victim detection** and resource estimation
- **Risk escalation prediction** (toxic gas, secondary drowning, etc.)
- **Survival probability** based on response delay
- **Auto team assignment** to incidents
- **Equipment dispatch** tracking
- **Situation reports** and resource depletion forecasting
- **Disaster mode profiles** (Flood / Earthquake / Fire / Chemical)

---

## Architecture

```
Voice/Text Input
      │
      ▼
┌─────────────────────────────────────────────────────┐
│              LangGraph Pipeline (12 nodes)           │
│                                                      │
│  Intake → Multi-Victim → Triage → Risk              │
│     → Knowledge Graph → Protocol RAG → Resource     │
│     → Triage Steps → Response                       │
│     → Incident Register → Assignment → Dispatch     │
└─────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────┐    ┌──────────────────────┐
│  Streamlit Dashboard │    │  Persistent Storage  │
│  7 tabs, panic mode  │    │  JSON + CSV files    │
└─────────────────────┘    └──────────────────────┘
```

### Agent Pipeline Stages

| Stage | Module | Description |
|-------|--------|-------------|
| 1 | `intake_agent.py` | Extracts victim, injury, location, keywords |
| 2 | `multi_victim_detector.py` | Counts victims, detects mass casualties |
| 3 | `triage_agent.py` | CRITICAL/HIGH/MEDIUM/LOW with confidence |
| 4 | `risk_predictor.py` | Escalation risks + survival probability |
| 5 | `knowledge_graph_agent.py` | NetworkX KG: injury→treatment→resources |
| 6 | `protocol_agent.py` | FAISS RAG over emergency medical manual |
| 7 | `resource_agent.py` | CSV inventory check + low-stock alerts |
| 8 | `triage_assistant.py` | Step-by-step instructions with timers |
| 9 | `response_agent.py` | Final report synthesis |
| 10 | `incident_manager.py` | ID assignment, priority queue |
| 11 | `responder_manager.py` | Auto team assignment algorithm |
| 12 | `equipment_dispatch.py` | Dispatch tracking, inventory deduction |

---

## Folder Structure

```
disaster_command_center/
│
├── command_center.py              # Master orchestrator (run this)
│
├── agents/
│   ├── intake_agent.py            # Context extraction (NLP)
│   ├── triage_agent.py            # Severity classification
│   ├── knowledge_graph_agent.py   # NetworkX KG (53 nodes, 60 edges)
│   ├── protocol_agent.py          # RAG retrieval (FAISS)
│   ├── resource_agent.py          # Inventory matching
│   ├── response_agent.py          # Final report synthesis
│   └── multi_victim_detector.py   # NEW: victim count detection
│
├── command/
│   ├── incident_manager.py        # NEW §1  — Incident queue
│   ├── responder_manager.py       # NEW §3  — Team assignment
│   ├── equipment_dispatch.py      # NEW §4  — Equipment tracking
│   ├── location_cluster.py        # NEW §5  — Incident clustering
│   ├── triage_assistant.py        # NEW §9  — Step-by-step + timers
│   ├── risk_predictor.py          # NEW §10/11 — Risk + survival
│   └── sitrep_generator.py        # NEW §14/16 — Sitrep + depletion forecast
│
├── maps/
│   └── offline_routing.py         # NEW §6  — OSM road routing
│
├── modes/
│   └── disaster_profiles.py       # NEW §17 — Flood/EQ/Fire/Chemical
│
├── speech/
│   ├── speech_to_text.py          # Whisper INT8 voice input
│   └── voice_commands.py          # NEW §13 — Voice commands
│
├── utils/
│   └── system_state.py            # NEW §7/8 — Battery saver + Panic mode
│
├── rag/
│   ├── embeddings.py              # sentence-transformers / TF-IDF fallback
│   ├── vector_store.py            # FAISS IndexFlatIP
│   └── pdf_loader.py              # Protocol document chunker
│
├── ui/
│   └── command_dashboard.py       # NEW — Full 7-tab Streamlit dashboard
│
├── data/
│   ├── inventory.csv              # 20-item medical supply inventory
│   ├── emergency_protocols.txt    # 8-section emergency medical manual
│   ├── incident_table.json        # Auto-generated incident queue
│   ├── responders.json            # Auto-generated team registry
│   ├── assignments.json           # Auto-generated assignment log
│   ├── dispatched_equipment.csv   # Auto-generated dispatch log
│   ├── clusters.json              # Auto-generated location clusters
│   ├── active_profile.json        # Active disaster mode profile
│   ├── system_state.json          # Battery/panic mode state
│   └── incident_logger.py         # Legacy incident logger (v1)
│
├── logs/
│   └── agent_logs.json
│
└── requirements.txt
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

**Windows:**
```bash
pip install -r requirements.txt --only-binary=:all:
```

### 2. Run text mode

```bash
python command_center.py --text "Elderly man with leg fracture trapped in flooded building"
```

### 3. Run voice mode

```bash
python command_center.py --voice --duration 7
```

### 4. Launch dashboard

```bash
streamlit run ui/command_dashboard.py
```

### 5. Generate situation report

```bash
python command_center.py --sitrep
```

---

## Dashboard Tabs

| Tab | Contents |
|-----|----------|
| 🚨 Active Response | Current incident: severity, survival prob, risks, protocol, resources |
| 📋 Incident Queue | Priority-sorted queue, filter by severity, resolve/assign actions |
| 👥 Responders | Team availability, deployment status |
| 🗺️ Incident Map | Plotted incident markers (GPS if available) |
| 📊 Situation Report | Auto sitrep + resource depletion forecast |
| 🔧 Agent Logs | Step-by-step pipeline execution log |
| ⚙️ Settings | Disaster profile, battery level, power mode, chat assistant |

---

## Key Features

### Panic Mode
Click **🔴 PANIC** in sidebar → full-screen red UI showing only CRITICAL incidents.

### Battery Saver Mode
Set battery below 30% in Settings → auto-activates:
- Speech disabled
- UI refresh slowed to 60s
- Only HIGH + CRITICAL shown

### Disaster Mode Profiles
Activate in Settings → modifies severity rules, resource bundles, triage protocols:

| Profile | Focus |
|---------|-------|
| 🌊 Flood | Hypothermia, drowning, water rescue |
| 🏚️ Earthquake | Spinal, crush syndrome, USAR |
| 🔥 Fire | Burns, smoke inhalation, CO poisoning |
| ☣️ Chemical | HAZMAT, decontamination, toxic exposure |

### Voice Commands
Speak commands while voice mode is active:
```
"activate panic mode"
"show critical incidents"
"mark incident 003 resolved"
"assign team alpha to incident 001"
"situation report"
```

### Survival Probability
Real-time model: `P(t) = P_base × exp(-λ × delay_minutes)`

| Injury | Golden Time | Decay Rate |
|--------|-------------|------------|
| Cardiac Arrest | 4 min | High (λ=0.10) |
| Severe Bleeding | 10 min | Medium (λ=0.05) |
| Burns | 20 min | Low (λ=0.02) |
| Fracture | 60 min | Very Low (λ=0.005) |

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | Dual-core 2.0GHz | Quad-core 2.5GHz |
| RAM | 4 GB | 8 GB |
| Storage | 2 GB | 4 GB |
| OS | Windows 10 / Ubuntu 20 / macOS 11 | Any |
| Python | 3.9+ | 3.11 |
| Internet | Not required at runtime | Required for initial model download |

---

## Data Schemas

### Incident Table (`data/incident_table.json`)
```json
{
  "incident_id": "INC-A1B2C3",
  "timestamp": "2024-01-15T14:32:00",
  "victim": "elderly",
  "victim_count": 1,
  "injury": "fracture",
  "situation": "flood",
  "location": "school building",
  "severity": "HIGH",
  "confidence": 0.99,
  "status": "assigned",
  "assigned_team": "TEAM-ALPHA",
  "priority_score": 118.9,
  "resources_needed": []
}
```

### Responder Table (`data/responders.json`)
```json
{
  "team_id": "TEAM-ALPHA",
  "name": "Alpha Rescue Unit",
  "type": "rescue",
  "members": 4,
  "status": "available",
  "lat": 0.0,
  "lon": 0.0,
  "skills": ["fracture", "trapped", "flood"]
}
```

### Dispatch Log (`data/dispatched_equipment.csv`)
```
dispatch_id,incident_id,item,quantity,status,dispatched_at,returned_at
DISP-00001,INC-A1B2C3,splint,1,dispatched,2024-01-15T14:32:05,
DISP-00002,INC-A1B2C3,cold_pack,1,dispatched,2024-01-15T14:32:05,
```

---

## AI Techniques Used

| Technique | Implementation | Purpose |
|-----------|---------------|---------|
| Automatic Speech Recognition | faster-whisper tiny INT8 | Voice → text (offline) |
| RAG | FAISS + sentence-transformers | Protocol retrieval |
| Knowledge Graph | NetworkX DiGraph | Injury → resource mapping |
| Multi-Agent Pipeline | LangGraph StateGraph | Orchestration |
| Survival Model | Exponential decay P(t)=P₀e^(-λt) | Response urgency |
| Location Clustering | Union-Find + Jaccard similarity | Merge nearby incidents |
| Team Assignment | Weighted scoring algorithm | Auto-dispatch |

---

## CLI Reference

```bash
# Process emergency (text)
python command_center.py --text "EMERGENCY DESCRIPTION"

# Process emergency (voice, 7 second recording)
python command_center.py --voice --duration 7

# Save output to JSON file
python command_center.py --text "..." --output result.json

# Print situation report
python command_center.py --sitrep

# Launch dashboard
streamlit run ui/command_dashboard.py
```

---

*Built for disaster environments. No cloud dependency. No GPU required. Works on a laptop in a flood.*
