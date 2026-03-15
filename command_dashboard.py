# REFRESH TOUCH: 2026-03-14 18:25
"""
ui/command_dashboard.py
────────────────────────────────────────────────────────────────
Offline Disaster Response Command Center — v4 ELITE Dashboard

Tabs:
  1.  🚨 Active Response      — incident processing + photo upload
  2.  📋 Incident Queue       — priority-sorted incident table
  3.  👥 Responder Status     — team availability and assignments
  4.  🗺️  Incident Map         — offline plotted incident markers
  5.  📊 Situation Report     — sitrep + resource predictions
  6.  💊 Vitals & Drugs       — vitals tracker + drug checker
  7.  📡 Hotspots             — hotspot heatmap + top-5 list
  8.  🏷️  QR Triage Tags       — generate printable tags
  9.  🎓 Simulation Mode      — training scenarios
  10. 🌐 LAN Sync             — multi-laptop peer sync
  11. 🔧 Agent Logs           — execution timeline
  12. ⚙️  Settings & Access    — roles, modes, profiles

Run: streamlit run ui/command_dashboard.py
"""

import sys, os, time, json, io, importlib
from dotenv import load_dotenv

# ── Load environment variables ──
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="Disaster Command Center v4 ELITE",
    page_icon="🚨", layout="wide",
    initial_sidebar_state="expanded"
)

# ── High-Contrast Emergency Mode CSS ──
st.markdown("""
<style>
    /* Full Dark Background */
    .stApp, [data-testid="stAppViewContainer"], .main {
        background-color: #000000 !important;
    }
    
    /* Edge-to-Edge Layout */
    .block-container {
        padding-top: 0rem !important;
        padding-bottom: 2rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }
    
    /* Hide standard header */
    [data-testid="stHeader"] {
        background: rgba(0,0,0,0);
        color: white;
    }

    /* Force Grid and Text Contrast */
    h1, h2, h3, h4, h5, h6, p, label, .stMarkdown, .stText {
        color: #FFFFFF !important;
        font-family: 'Courier New', Courier, monospace !important;
    }
    
    /* Input Fields */
    .stTextArea textarea, .stTextInput input, .stSelectbox [data-baseweb="select"] {
        background-color: #050505 !important;
        color: #FFFFFF !important;
        border: 1px solid #444 !important;
        border-radius: 0px !important;
    }
    
    /* Tactical Buttons */
    .stButton>button {
        border-radius: 0px !important;
        background-color: #000 !important;
        color: #FFFF00 !important;
        border: 2px solid #FFFF00 !important;
        font-weight: bold !important;
        width: 100%;
        text-transform: uppercase;
    }
    .stButton>button:hover {
        background-color: #FFFF00 !important;
        color: #000 !important;
    }
    
    /* Metrics High-Contrast */
    [data-testid="stMetricValue"] {
        color: #FFFF00 !important;
        font-weight: 900 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #AAAAAA !important;
        text-transform: uppercase;
        font-size: 0.8em !important;
    }
    
    /* Remove rounding from everything */
    div, button, input, textarea {
        border-radius: 0px !important;
    }
    
    /* Vertical line for separation */
    [data-testid="column"] {
        border-right: 1px solid #222;
        padding-right: 1rem;
    }

    /* Expander Styling */
    .streamlit-expanderHeader {
        background-color: #000 !important;
        color: #FFF !important;
        border: 1px solid #333 !important;
        border-radius: 0px !important;
    }
    .streamlit-expanderContent {
        background-color: #000 !important;
        color: #FFF !important;
        border: 1px solid #333 !important;
        border-top: none !important;
        border-radius: 0px !important;
    }
</style>
""", unsafe_allow_html=True)

# ── Core imports ──
import command_center
importlib.reload(command_center)
from command_center           import process_emergency, build_command_pipeline
from command.incident_manager import get_sorted_queue, get_stats, resolve_incident, assign_incident
from command.responder_manager import get_all_teams, get_available_teams, seed_default_teams
from command.sitrep_generator  import generate_sitrep, predict_resource_depletion
from command.triage_assistant  import get_triage_steps
from modes.disaster_profiles   import all_profiles_summary, activate_profile, get_active_profile
from utils.system_state        import (get_state, activate_panic_mode, deactivate_panic_mode,
                                        set_battery_level, is_panic_mode, is_low_power_mode,
                                        should_show_incident)
# ── v4 imports ──
from command.vitals_tracker    import log_vitals, get_patient_vitals, get_all_critical_patients, get_vitals_summary
from command.drug_checker      import get_drug_info, check_interaction, get_dosage, check_contraindications, list_all_drugs, search_drugs_by_indication
from command.hotspot_predictor import analyze_hotspots, build_hour_day_heatmap, get_hotspot_risk_level
from command.qr_triage         import generate_qr_tag, list_generated_tags
from command.report_generator  import generate_incident_report, generate_mass_report
from utils.simulation_mode     import get_all_scenarios, start_simulation, score_simulation, get_simulation_leaderboard, get_simulation_stats
from utils.lan_sync            import start_sync_server, sync_with_peer, ping_peer, get_sync_status, get_sync_log
from utils.access_control      import login, logout, get_current_session, has_permission, get_role_badge_html, list_roles, initialize_access_config

seed_default_teams()
initialize_access_config()

# ── Theme constants (High-Contrast) ──
SEV_COLOR  = {"CRITICAL":"#FF0000","HIGH":"#FF8800","MEDIUM":"#FFFF00","LOW":"#00FF00"}
SEV_BG     = {"CRITICAL":"#000000","HIGH":"#000000","MEDIUM":"#000000","LOW":"#000000"}
SEV_EMOJI  = {"CRITICAL":"🛑","HIGH":"⚠️","MEDIUM":"ℹ️","LOW":"✅"}
STATUS_COLOR = {"pending":"#FFFFFF","assigned":"#FFFF00","resolved":"#00FF00"}


# ════════════════════════════════════════════════════════════
# PANIC MODE override
# ════════════════════════════════════════════════════════════
sys_state = get_state()
if sys_state.get("panic_active"):
    st.markdown("""
    <div style="background:#1a0000;border:4px solid #FF0000;border-radius:12px;
         padding:24px;text-align:center;margin-bottom:16px">
      <div style="font-size:3em;font-weight:bold;color:#FF0000">
        🔴  PANIC MODE ACTIVE  🔴
      </div>
      <div style="color:#FF8888;font-size:1.1em;margin-top:8px">
        Only CRITICAL incidents shown
      </div>
    </div>""", unsafe_allow_html=True)
    critical_incs = [i for i in get_sorted_queue() if i.get("severity") == "CRITICAL"]
    if not critical_incs:
        st.info("No CRITICAL incidents at this time.")
    for inc in critical_incs:
        st.markdown(
            f'<div style="background:#2d0000;border:2px solid #FF0000;border-radius:8px;'
            f'padding:14px;margin:8px 0">'
            f'<b style="color:#FF0000;font-size:1.3em">🔴 {inc["incident_id"]}</b> — '
            f'{inc["victim"]} | {inc["injury"]} | 📍 {inc["location"]}<br>'
            f'<span style="color:#aaa">Status: {inc["status"]} | Team: {inc.get("assigned_team","Unassigned")}</span></div>',
            unsafe_allow_html=True)
    if st.button("🔕 DEACTIVATE PANIC MODE", type="primary"):
        deactivate_panic_mode(); st.rerun()
    st.stop()


# ════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════
active_profile = get_active_profile()
profile_badge  = active_profile.get("name", "⚙️ Normal")
battery_level  = sys_state.get("battery_level", 100)
lp_badge       = "⚡ LOW POWER" if is_low_power_mode() else ""

# Role badge
session = get_current_session()
role_html = get_role_badge_html(session)

st.markdown(f"""
<div style="background:#000000;
     padding:12px 20px;margin-bottom:10px;
     border-bottom:3px solid #FF0000;display:flex;justify-content:space-between;align-items:center">
  <div>
    <h1 style="color:#FF0000;margin:0;font-size:1.6em;font-weight:900;text-transform:uppercase;letter-spacing:2px">
      ☢️ COMMAND CENTER · EMERGENCY MODE
    </h1>
    <span style="color:#FFFFFF;font-size:0.8em;opacity:0.8;font-family:monospace">
      OS: AGENT_SYSTEM_V4 // LOC: KARNATAKA_IN // STATUS: ONLINE
    </span>
  </div>
  <div style="text-align:right">
    {role_html}
    <br>
    <span style="color:#FFFF00;font-size:0.9em;font-weight:bold;font-family:monospace">
      {profile_badge} // 🔋 {battery_level}% {lp_badge}
    </span>
  </div>
</div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════
tabs = st.tabs([
    "🚨 Active Response",
    "📋 Incident Queue",
    "👥 Responders",
    "🗺️ Incident Map",
    "📊 Situation Report",
    "💊 Vitals & Drugs",
    "📡 Hotspots",
    "🏷️ QR Tags",
    "🎓 Simulation",
    "🌐 LAN Sync",
    "🔧 Agent Logs",
    "⚙️ Settings",
])

(tab_response, tab_queue, tab_responders, tab_map,
 tab_sitrep, tab_vitals, tab_hotspots, tab_qr,
 tab_sim, tab_lan, tab_logs, tab_settings) = tabs


# ════════════════════════════════════════════════════════════
# TAB 1 — ACTIVE RESPONSE
# ════════════════════════════════════════════════════════════
with tab_response:
    st.subheader("🚨 Emergency Incident Processor")

    col_inp, col_result = st.columns([1, 1])

    with col_inp:

        # ─────────────────────────────────────────────────
        # INPUT METHOD SELECTOR
        # ─────────────────────────────────────────────────
        input_method = st.radio(
            "Input Method",
            ["📝 Text", "📸 Text + Photo", "🎤 Voice"],
            horizontal=True
        )

        transcription = ""

        if input_method in ["📝 Text", "📸 Text + Photo"]:
            transcription = st.text_area(
            "Emergency Report",
            placeholder="e.g. Bus overturned on highway. 12 injured, 3 unconscious and not breathing.",
            height=130,
        )

        location_input = st.text_input(
            "📍 Incident Location",
            placeholder="e.g. MG Road, Bengaluru or 12.97, 77.59",
            help="Enter a specific address, landmark, or GPS coordinates.",
            key="location_input_field"
        )

        photo_bytes = None
        photo_media_type = "image/jpeg"
        voice_transcription = None

        # ─────────────────────────────────────────────────
        # PHOTO INPUT
        # ─────────────────────────────────────────────────
        if input_method == "📸 Text + Photo":
            uploaded = st.file_uploader(
                "Upload Injury Photo",
                type=["jpg","jpeg","png","webp"]
            )

            if uploaded:
                photo_bytes = uploaded.read()
                photo_media_type = uploaded.type or "image/jpeg"
                st.image(photo_bytes, caption="Uploaded injury photo", width=200)

        # ─────────────────────────────────────────────────
# ─────────────────────────────────────────────────
        # VOICE INPUT
        # ─────────────────────────────────────────────────
        if input_method == "🎤 Voice":

            st.markdown("### 🎤 Emergency Voice Report")

            language_options = {
                "Auto Detect (English / Hindi)": None,
                "English (India)": "en",
                "Hindi / Hinglish": "hi"
            }

            selected_lang = st.selectbox(
                "Speech Language",
                list(language_options.keys())
            )

            forced_language = language_options[selected_lang]

            audio = st.audio_input("Record voice report")

            if audio:

                with open("temp_voice.wav", "wb") as f:
                    f.write(audio.getbuffer())

                try:
                    from speech.multilingual_stt import transcribe_multilingual

                    print(f"[UI] Calling STT with: {'temp_voice.wav'} (type: {type('temp_voice.wav')})")
                    stt_result = transcribe_multilingual(
                        "temp_voice.wav",
                        force_language=forced_language
                    )

                    st.session_state.voice_transcription = ""
                    if stt_result.get("detected_language") == "hi":
                        st.session_state.voice_transcription = stt_result.get("text_english", "")
                    else:
                        st.session_state.voice_transcription = stt_result.get("text_original", "")

                    st.success("Transcription Complete")

                    st.text_area(
                        "Recognized Speech",
                        st.session_state.voice_transcription,
                        height=120
                    )
                    
                    # Update the local variable so the processor can see it
                    voice_transcription = st.session_state.voice_transcription

                except Exception as e:
                    st.error(f"Speech recognition error: {e}")
        # ─────────────────────────────────────────────────
        # OPTIONS
        # ─────────────────────────────────────────────────
        use_llm = st.checkbox("🤖 Use LLM Triage (Claude API)", value=True)

        col_a, col_b = st.columns(2)

        process_btn = col_a.button(
            "🚀 Process Emergency",
            type="primary",
            use_container_width=True
        )

        clear_btn = col_b.button(
            "🗑️ Clear",
            use_container_width=True
        )

        # ─────────────────────────────────────────────────
        # CLEAR
        # ─────────────────────────────────────────────────
        if clear_btn:
            for k in ["last_result","last_logs"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()

    # ─────────────────────────────────────────────────
    # PROCESS INPUT
    # ─────────────────────────────────────────────────
    report_text = transcription

    if input_method == "🎤 Voice" and voice_transcription:
        report_text = voice_transcription

    if process_btn and report_text.strip():

        if not use_llm:
            os.environ["DISABLE_LLM_TRIAGE"] = "1"
        else:
            os.environ.pop("DISABLE_LLM_TRIAGE", None)

        with st.spinner("🧠 Processing through 15-node AI pipeline..."):
            try:

                final = process_emergency(
                    report_text.strip(),
                    photo_bytes,
                    photo_media_type,
                    location_hint=location_input.strip() if location_input else None
                )

                st.session_state["last_result"] = final
                st.session_state["last_logs"] = final.get("agent_logs", [])
                
                # Store latest coordinates for map centering
                coords = final.get("final_response", {}).get("coordinates")
                if coords:
                    try:
                        lat, lon = map(float, coords.split(","))
                        st.session_state["map_center"] = {"lat": lat, "lon": lon}
                    except: pass

            except Exception as e:
                st.error(f"Pipeline error: {e}")

    # ═══════════════════════════════════════════════════════
    # RESULT PANEL
    # ═══════════════════════════════════════════════════════
    with col_result:

        if "last_result" in st.session_state:

            final = st.session_state["last_result"]

            resp = final.get("final_response", {}) or {}
            sev = resp.get("severity", "MEDIUM")
            inc_id = resp.get("incident_id", "?")
            resolved_coords = resp.get("coordinates")

            surv = final.get("survival_data", {}) or {}
            va = final.get("victim_analysis", {}) or {}

            triage_method = final.get("triage_method", "rule_based")

            st.markdown(f"""
            <div style="background:#000;
                 border:2px solid {SEV_COLOR.get(sev,'#FFF')};
                 border-radius:0px;padding:14px;text-align:center;margin-bottom:12px">

              <div style="font-size:2em;color:{SEV_COLOR.get(sev,'#fff')};font-weight:900">
                {SEV_EMOJI.get(sev,'⚪')} {sev} PRIORITY
              </div>

              <div style="color:#FFF;font-size:0.9em;font-family:monospace">
                ID: {inc_id} &nbsp;|&nbsp;
                Triage: {triage_method.upper()} &nbsp;|&nbsp;
                Survival: {surv.get('survival_probability','?')}%
                {f"&nbsp;|&nbsp; 📍 {resolved_coords}" if resolved_coords else ""}
              </div>

            </div>
            """, unsafe_allow_html=True)

            lang_result = final.get("language_result")

            if lang_result and lang_result.get("detected_language","en") != "en":
                from speech.multilingual_stt import get_language_badge_html
                st.markdown(
                    get_language_badge_html(lang_result),
                    unsafe_allow_html=True
                )

            c1, c2 = st.columns(2)

            c1.metric("Victim", resp.get("victim","?"))
            c2.metric("Injury", resp.get("injury","?"))

            c1.metric("Teams Needed", va.get("required_teams","?"))
            c2.metric("Assigned Team", resp.get("assigned_team","Unassigned"))

            c1.metric("Survival %", f"{surv.get('survival_probability','?')}%")
            c2.metric("Urgency", surv.get("urgency","?"))

            photo_t = final.get("photo_triage_result")

            if photo_t and photo_t.get("injury_visible"):

                st.markdown("**📸 Photo Triage Result:**")

                p1, p2 = st.columns(2)

                p1.metric("Photo Severity", photo_t.get("severity","?"))
                p2.metric("Confidence", f"{photo_t.get('confidence',0):.0%}")

                if photo_t.get("do_not_do"):
                    st.warning("⚠️ DO NOT: " + " · ".join(photo_t["do_not_do"]))

                if photo_t.get("immediate_actions"):
                    st.info("✅ Photo Actions: " + " · ".join(photo_t["immediate_actions"]))

            # ─────────────────────────────────────────────────
            # MEDICAL PROTOCOL & EQUIPMENT LOCATOR
            # ─────────────────────────────────────────────────
            proto = final.get("protocol_data", {}) or {}
            proto_text = proto.get("protocol_text", "")
            resource_status = (final.get("resource_data", {}) or {}).get("resources", [])

            if proto_text:
                st.markdown("---")
                st.markdown("### 📋 Medical Protocol & Equipment Locator")
                
                # Format the protocol text to be cleaner (remove RAG scores if present)
                display_proto = proto_text
                if "[Relevance:" in display_proto:
                    import re
                    display_proto = re.sub(r'\[Relevance: \d+\.\d+\]', '', display_proto).strip()
                
                # Create a nice container for the protocol
                with st.expander("📍 View Treatment Steps & Item Locations", expanded=True):
                    html_proto = display_proto.replace('\n', '<br>')
                    st.markdown(f"""
                    <div style="background:#000; border: 2px solid #FFFF00; border-radius: 0px; padding: 15px; font-family: 'Courier New', Courier, monospace; color: #FFFFFF;">
                        <div style="color: #FFFF00; font-weight: bold; margin-bottom: 10px; text-transform: uppercase;">📄 RAG PROTOCOL // OFFLINE_DB</div>
                        {html_proto}
                    </div>
                    """, unsafe_allow_html=True)

                    # Scan for equipment locations
                    if resource_status:
                        st.markdown("**📦 Equipment Availability:**")
                        cols = st.columns(3)
                        for idx, res in enumerate(resource_status[:6]):
                            with cols[idx % 3]:
                                status_emoji = "✅" if res["status"] == "AVAILABLE" else "❌"
                                bin_loc = res.get('location', 'Unknown') if res.get('location') else "Contact Support"
                                st.markdown(f"""
                                <div style="background:#000; padding: 8px; border-radius: 0px; border-left: 5px solid {'#00FF00' if res['status'] == 'AVAILABLE' else '#FF0000'}; border: 1px solid #333">
                                    <b style="color: #FFF">{status_emoji} {res['item'].upper()}</b><br>
                                    <span style="font-size: 0.8em; color: #FFFF00;">LOC: {bin_loc}</span>
                                </div>
                                """, unsafe_allow_html=True)

            # ─────────────────────────────────────────────────
            # QUICK ACTIONS
            # ─────────────────────────────────────────────────
            st.markdown("---")
            col_a1, col_a2, col_a3 = st.columns(3)
            
            if col_a1.button("🏷️ QR Tag", key="quick_qr", use_container_width=True):

                res = generate_qr_tag(
                    inc_id,
                    resp.get("victim","?"),
                    sev,
                    resp.get("injury","?"),
                    resp.get("location","")
                )

                if res["success"] and res["filename"].endswith(".png"):
                    try:
                        from PIL import Image
                        img = Image.open(res["file_path"])
                        st.image(img, caption=f"Triage Tag: {inc_id}", width=260)
                    except Exception:
                        st.success(f"✅ Tag saved: {res['filename']}")

            if col_a2.button("📄 PDF Report", key="quick_report", use_container_width=True):

                r = generate_incident_report(inc_id)

                if r.get("success"):
                    st.success(f"✅ Report: {r['filename']}")
                else:
                    st.error(r.get("error","Unknown error"))

        else:
            st.info("Enter an emergency report and press **Process Emergency** to begin.")
# ════════════════════════════════════════════════════════════
# TAB 2 — INCIDENT QUEUE
# ════════════════════════════════════════════════════════════
with tab_queue:
    st.subheader("📋 Incident Queue")
    stats = get_stats()
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total",    stats.get("total",0))
    c2.metric("Pending",  stats.get("pending",0))
    c3.metric("Assigned", stats.get("assigned",0))
    c4.metric("Resolved", stats.get("resolved",0))

    col_filter, col_sort = st.columns([2,1])
    sev_filter = col_filter.multiselect("Filter severity", ["CRITICAL","HIGH","MEDIUM","LOW"], default=["CRITICAL","HIGH","MEDIUM","LOW"])
    show_resolved = col_sort.checkbox("Show resolved", value=False)

    queue = get_sorted_queue()
    for inc in queue:
        sev = inc.get("severity","MEDIUM")
        if sev not in sev_filter: continue
        if inc.get("status") == "resolved" and not show_resolved: continue

        with st.expander(f"{SEV_EMOJI.get(sev,'⚪')} {inc['incident_id']} — {inc.get('victim','?')} | {inc.get('injury','?')[:40]}"):
            ci1, ci2, ci3 = st.columns(3)
            ci1.write(f"**Severity:** {sev}")
            ci2.write(f"**Status:** {inc.get('status','?')}")
            ci3.write(f"**Priority:** {inc.get('priority_score','?')}")
            ci1.write(f"**Team:** {inc.get('assigned_team','Unassigned')}")
            ci2.write(f"**Location:** {inc.get('location','?')}")
            ci3.write(f"**Triage:** {inc.get('triage_method','rule_based')}")
            surv = inc.get("survival_data",{})
            if surv:
                ci1.write(f"**Survival:** {surv.get('survival_probability','?')}%")

            btn1, btn2, btn3 = st.columns(3)
            if btn1.button("✅ Resolve", key=f"res_{inc['incident_id']}"):
                resolve_incident(inc["incident_id"]); st.rerun()
            if btn2.button("🏷️ QR Tag", key=f"qr_{inc['incident_id']}"):
                generate_qr_tag(inc["incident_id"], inc.get("victim","?"), sev, inc.get("injury","?"), inc.get("location",""))
                st.success("Tag generated")
            if btn3.button("📄 Report", key=f"rpt_{inc['incident_id']}"):
                r = generate_incident_report(inc["incident_id"])
                st.success(r.get("filename","?") if r.get("success") else r.get("error","?"))


# ════════════════════════════════════════════════════════════
# TAB 3 — RESPONDERS
# ════════════════════════════════════════════════════════════
with tab_responders:
    st.subheader("👥 Responder Teams")
    teams = get_all_teams()
    available = get_available_teams()
    rc1, rc2 = st.columns(2)
    rc1.metric("Total Teams",     len(teams))
    rc2.metric("Available Teams", len(available))
    for team in teams:
        status = team.get("status","unknown")
        color = "#22CC44" if status == "available" else "#FF7700" if status == "busy" else "#888"
        st.markdown(
            f'<div style="background:#000;border:1px solid #333;border-left:5px solid {color};'
            f'padding:10px 14px;border-radius:0px;margin:4px 0">'
            f'<b style="color:{color}">{team.get("team_id","?")} — {status.upper()}</b> &nbsp; '
            f'<span style="color:#FFF">{team.get("specialty","General")} | {team.get("members",0)} members</span>'
            f'</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# TAB 4 — INCIDENT MAP
# ════════════════════════════════════════════════════════════
with tab_map:
    st.subheader("🗺️ Incident Map")
    try:
        import plotly.graph_objects as go
        queue_for_map = get_sorted_queue()
        
        # ── Pre-process Live Input ──
        current_input = st.session_state.get("location_input_field", "").strip()
        live_coords = None
        if current_input:
            from utils.geocoder import geocode_location
            live_coords = geocode_location(current_input)

        if queue_for_map or live_coords:
            lats, lons, texts, colors_map = [], [], [], []
            
            # 1. Add Queue Incidents
            for inc in queue_for_map:
                loc = inc.get("coordinates") or inc.get("location", "0,0")
                try:
                    parts = loc.replace("(","").replace(")","").split(",")
                    lat, lon = float(parts[0].strip()), float(parts[1].strip())
                    if lat == 0 and lon == 0: raise ValueError
                except Exception:
                    import random; lat, lon = 12.9716 + random.uniform(-0.05,0.05), 77.5946 + random.uniform(-0.05,0.05)
                lats.append(lat); lons.append(lon)
                texts.append(f"<b>{inc['incident_id']}</b><br>{inc.get('victim','?')}<br>{inc.get('severity','?')}")
                colors_map.append(SEV_COLOR.get(inc.get("severity","MEDIUM"),"#888"))
            
            # 2. Add Live Target Marker (if new)
            if live_coords:
                lat, lon = live_coords
                lats.append(lat); lons.append(lon)
                texts.append(f"<b>📍 LIVE_TARGET</b><br>{current_input}")
                colors_map.append("#00FFFF") # Cyan for Live Input

            # Determine map center: prioritize live_coords then session_state map_center
            center_lat, center_lon = 12.9716, 77.5946
            if live_coords:
                center_lat, center_lon = live_coords
            elif "map_center" in st.session_state:
                center_lat = st.session_state["map_center"]["lat"]
                center_lon = st.session_state["map_center"]["lon"]
            elif lats:
                center_lat, center_lon = lats[0], lons[0]

            fig = go.Figure(go.Scattermapbox(lat=lats, lon=lons, mode="markers",
                marker=go.scattermapbox.Marker(size=18, color=colors_map, opacity=0.8),
                text=texts, hoverinfo="text"))
            
            # Use dynamic zoom: tight if we have a specific center
            zoom_level = 15 if (live_coords or "map_center" in st.session_state) else 12
            
            fig.update_layout(mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=zoom_level),
                              margin=dict(l=0,r=0,t=0,b=0), height=450)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No incidents to map yet.")
    except ImportError:
        st.info("Install plotly for map display: `pip install plotly`")


# ════════════════════════════════════════════════════════════
# TAB 5 — SITUATION REPORT
# ════════════════════════════════════════════════════════════
with tab_sitrep:
    st.subheader("📊 Situation Report")
    if st.button("🔄 Generate Sitrep"):
        with st.spinner("Generating..."):
            sitrep = generate_sitrep()
        st.text_area("Situation Report", sitrep.get("summary",""), height=300)
    depletion = predict_resource_depletion()
    if depletion:
        st.markdown("**⚠️ Resource Depletion Predictions:**")
        for item in depletion[:5]:
            st.warning(f"🔻 {item.get('item','?')} — depletes in ~{item.get('hours_remaining','?')} hours")
    if st.button("📦 Generate Mass Report PDF"):
        r = generate_mass_report()
        if r.get("success"): st.success(f"✅ {r['filename']} ({r.get('incident_count',0)} incidents)")
        else: st.error(r.get("error","?"))


# ════════════════════════════════════════════════════════════
# TAB 6 — VITALS & DRUGS
# ════════════════════════════════════════════════════════════
with tab_vitals:
    st.subheader("💊 Vitals Tracker & Drug Checker")
    vtab1, vtab2 = st.tabs(["🩺 Vitals Tracker", "💊 Drug Reference"])

    # ── Vitals ──
    with vtab1:
        summary = get_vitals_summary()
        vc1,vc2,vc3 = st.columns(3)
        vc1.metric("Patients Monitored", summary["total_patients_monitored"])
        vc2.metric("Critical Patients",  summary["critical_patients"])
        vc3.metric("Total Readings",     summary["total_readings_logged"])

        critical_pts = get_all_critical_patients()
        if critical_pts:
            st.error(f"🔴 {len(critical_pts)} PATIENT(S) REQUIRE ATTENTION")
            for pt in critical_pts:
                latest = pt.get("latest_reading",{})
                st.markdown(f"**{pt['victim_name']}** — Pulse: {latest.get('pulse_bpm','?')} | SpO2: {latest.get('spo2_percent','?')}% | BP: {latest.get('systolic_bp','?')}/{latest.get('diastolic_bp','?')}")
                for alert in latest.get("alerts",[])[:3]:
                    color = "#FF2222" if alert["severity"]=="CRITICAL" else "#FF7700"
                    st.markdown(f'<span style="color:{color}">⚠️ {alert["message"]}</span>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("**Log Patient Vitals:**")
        vl1, vl2 = st.columns(2)
        v_incident = vl1.text_input("Incident ID")
        v_victim   = vl2.text_input("Patient Name")
        vv1, vv2, vv3 = st.columns(3)
        v_pulse = vv1.number_input("Pulse (bpm)", 0, 300, 80)
        v_spo2  = vv2.number_input("SpO2 (%)", 0, 100, 98)
        v_sbp   = vv3.number_input("Systolic BP", 0, 300, 120)
        vv4, vv5 = st.columns(2)
        v_dbp   = vv4.number_input("Diastolic BP", 0, 200, 80)
        v_rr    = vv5.number_input("Resp. Rate", 0, 60, 16)
        v_cons  = st.selectbox("Consciousness", ["Alert","Voice","Pain","Unresponsive"])
        if st.button("💾 Log Vitals", type="primary"):
            if v_incident and v_victim:
                result = log_vitals(v_incident, v_victim, {
                    "pulse_bpm": v_pulse, "spo2_percent": v_spo2,
                    "systolic_bp": v_sbp, "diastolic_bp": v_dbp,
                    "respiratory_rate": v_rr, "consciousness": v_cons,
                })
                if result.get("has_critical"):
                    st.error(f"🔴 CRITICAL ALERTS: {result['alert_count']}")
                    for a in result.get("alerts",[]):
                        st.error(a["message"])
                elif result.get("alert_count",0) > 0:
                    st.warning(f"⚠️ {result['alert_count']} alert(s) triggered")
                else:
                    st.success("✅ Vitals logged — all within normal range")
            else:
                st.warning("Please enter Incident ID and Patient Name")

    # ── Drug Checker ──
    with vtab2:
        st.markdown("**Drug Search:**")
        drug_query = st.text_input("Enter drug name (e.g. epinephrine, morphine, aspirin)")
        if drug_query:
            info = get_drug_info(drug_query)
            if info.get("found"):
                st.success(f"✅ {info['generic_name']} — {info['class']}")
                di1, di2 = st.columns(2)
                di1.markdown(f"**Indications:** {', '.join(info.get('indications',[]))}")
                di2.markdown(f"**Contraindications:** {', '.join(info.get('contraindications',[]))}")
                st.markdown("**Dosages:**")
                for k,v in info.get("dosage",{}).items():
                    st.markdown(f"- `{k}`: {v}")
                st.markdown(f"**Storage:** {info.get('storage','?')} | **Onset:** {info.get('onset_minutes','?')}min")
                ints = info.get("interactions",{})
                if ints:
                    st.markdown("**⚠️ Interactions:**")
                    for drug, desc in ints.items():
                        color = "#FF2222" if "MAJOR" in desc else "#FF7700" if "MODERATE" in desc else "#888"
                        st.markdown(f'<span style="color:{color}">⚡ {drug}: {desc}</span>', unsafe_allow_html=True)
            else:
                st.error(f"Drug not found. Available: {', '.join(list_all_drugs()[:10])}...")

        st.markdown("---")
        st.markdown("**Interaction Checker:**")
        ic1, ic2 = st.columns(2)
        drug_a = ic1.text_input("Drug A", placeholder="e.g. morphine")
        drug_b = ic2.text_input("Drug B", placeholder="e.g. benzodiazepines")
        if st.button("⚡ Check Interaction") and drug_a and drug_b:
            result = check_interaction(drug_a, drug_b)
            if result.get("interactions_found"):
                sev_int = result["highest_severity"]
                color = "#FF2222" if sev_int=="MAJOR" else "#FF7700" if sev_int=="MODERATE" else "#FFD700"
                st.markdown(f'<h3 style="color:{color}">⚠️ {sev_int} INTERACTION FOUND</h3>', unsafe_allow_html=True)
                for inter in result["interactions_found"]:
                    st.warning(f"{inter['severity']}: {inter['description']}")
                if not result["safe_to_combine"]:
                    st.error("🚫 NOT SAFE TO COMBINE — consult physician")
            else:
                st.success("✅ No known interaction found in database")

        st.markdown("---")
        st.markdown("**Search by Indication:**")
        indication = st.text_input("Indication (e.g. seizures, cardiac arrest, anaphylaxis)")
        if indication:
            matches = search_drugs_by_indication(indication)
            if matches:
                for m in matches[:6]:
                    st.markdown(f"💊 **{m['generic_name']}** ({m['class']})")
            else:
                st.info("No drugs found for that indication")


# ════════════════════════════════════════════════════════════
# TAB 7 — HOTSPOTS
# ════════════════════════════════════════════════════════════
with tab_hotspots:
    st.subheader("📡 Incident Hotspot Prediction")
    hotspots = analyze_hotspots(top_n=5)

    if hotspots:
        st.markdown("**🔥 Top 5 Hotspot Locations:**")
        for i, h in enumerate(hotspots):
            risk_level = get_hotspot_risk_level(h["risk_score"])
            risk_color = {"EXTREME":"#FF0000","HIGH":"#FF7700","MEDIUM":"#FFD700","LOW":"#22CC44"}.get(risk_level,"#888")
            st.markdown(
                f'<div style="background:#000;border:1px solid #333;border-left:5px solid {risk_color};'
                f'padding:10px 14px;border-radius:0px;margin:6px 0">'
                f'<b style="color:{risk_color}">{risk_level} // {h["hotspot_location"].upper()}</b><br>'
                f'<span style="color:#FFF;font-size:0.9em;font-family:monospace">'
                f'SCORE: {h["risk_score"]} | INC: {h["frequency"]} | '
                f'INJURY: {h["predicted_injury"]} | PEAK: {h["peak_hour_range"]}'
                f'</span></div>', unsafe_allow_html=True)
    else:
        st.info("No incident history to analyze yet.")

    st.markdown("---")
    st.markdown("**🗓️ Hour × Day Heatmap:**")
    try:
        import plotly.graph_objects as go
        heatmap_data = build_hour_day_heatmap()
        fig = go.Figure(go.Heatmap(
            z=heatmap_data["matrix"],
            x=heatmap_data["hours"][::2],  # every 2 hours
            y=heatmap_data["days"],
            colorscale="Reds",
            showscale=True,
        ))
        fig.update_layout(title="Incident Frequency by Hour & Day",
                          height=280, margin=dict(l=0,r=0,t=30,b=0))
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.info("Install plotly for heatmap: `pip install plotly`")


# ════════════════════════════════════════════════════════════
# TAB 8 — QR TRIAGE TAGS
# ════════════════════════════════════════════════════════════
with tab_qr:
    st.subheader("🏷️ QR Triage Tag Generator")
    qc1, qc2 = st.columns(2)
    qr_incident = qc1.text_input("Incident ID", value="INC-001")
    qr_victim   = qc2.text_input("Victim", value="Adult male ~40yr")
    qr_sev      = qc1.selectbox("Severity", ["CRITICAL","HIGH","MEDIUM","LOW"])
    qr_injury   = qc2.text_input("Injury", value="Multiple trauma")
    qr_location = st.text_input("Location (optional)")

    if st.button("🏷️ Generate QR Triage Tag", type="primary"):
        result = generate_qr_tag(qr_incident, qr_victim, qr_sev, qr_injury, qr_location)
        if result.get("success"):
            if result["filename"].endswith(".png"):
                try:
                    from PIL import Image
                    img = Image.open(result["file_path"])
                    st.image(img, caption=f"A6 Triage Tag — {qr_incident}", width=310)
                    with open(result["file_path"],"rb") as f:
                        st.download_button("⬇️ Download Tag PNG", f, file_name=result["filename"])
                except Exception:
                    st.success(f"✅ Tag saved: {result['filename']}")
            else:
                st.success(f"✅ QR data saved: {result['filename']}")
            st.code(result.get("qr_data",""), language="json")
        else:
            st.error(result.get("error","Generation failed"))

    st.markdown("---")
    st.markdown("**Previously Generated Tags:**")
    tags = list_generated_tags()
    if tags:
        for tag in tags[:10]:
            tc1, tc2 = st.columns([3,1])
            tc1.write(f"🏷️ {tag['filename']} — {tag['created']}")
            if tag["filename"].endswith(".png"):
                try:
                    with open(tag["file_path"],"rb") as f:
                        tc2.download_button("⬇️", f, file_name=tag["filename"], key=f"dl_{tag['filename']}")
                except Exception:
                    pass
    else:
        st.info("No tags generated yet.")


# ════════════════════════════════════════════════════════════
# TAB 9 — SIMULATION MODE
# ════════════════════════════════════════════════════════════
with tab_sim:
    st.subheader("🎓 Training Simulation Mode")

    sim_stats = get_simulation_stats()
    sc1,sc2,sc3 = st.columns(3)
    sc1.metric("Sessions Run",    sim_stats.get("total_sessions",0))
    sc2.metric("Avg Score",       f"{sim_stats.get('avg_score',0)}%")
    sc3.metric("Top Score",       f"{sim_stats.get('top_score',0)}%")

    scenarios = get_all_scenarios()
    difficulty_filter = st.selectbox("Filter Difficulty", ["ALL","EASY","MEDIUM","HARD"])
    filtered = [s for s in scenarios if difficulty_filter=="ALL" or s.get("difficulty")==difficulty_filter]

    selected_scenario = st.selectbox(
        "Select Scenario",
        options=[s["id"] for s in filtered],
        format_func=lambda sid: next((f"{s['id']} — {s['name']} [{s['difficulty']}]" for s in filtered if s["id"]==sid), sid)
    )

    if selected_scenario:
        scen = next((s for s in scenarios if s["id"]==selected_scenario), None)
        if scen:
            st.markdown(f"**{scen['name']}** — {scen['description']}")
            st.markdown(f"⏱️ Time Limit: {scen['time_limit_seconds']}s | 🏷️ Type: {scen['disaster_type']} | ⚡ Difficulty: {scen['difficulty']}")

            if st.button("▶️ Start Simulation", type="primary"):
                session_result = start_simulation(selected_scenario)
                if session_result["success"]:
                    st.session_state["sim_session"] = session_result["session"]
                    st.session_state["sim_scenario"] = scen
                    st.session_state["sim_start_time"] = time.time()
                    st.info(f"🎬 Session {session_result['session']['session_id']} started!")

            if "sim_session" in st.session_state and st.session_state.get("sim_scenario",{}).get("id") == selected_scenario:
                st.markdown("---")
                st.markdown(f"**🚨 INCIDENT:** {scen['transcription']}")
                elapsed = time.time() - st.session_state.get("sim_start_time",time.time())
                st.info(f"⏱️ Elapsed: {elapsed:.0f}s / {scen['time_limit_seconds']}s")

                sm1, sm2 = st.columns(2)
                resp_sev   = sm1.selectbox("Your Triage Decision", ["CRITICAL","HIGH","MEDIUM","LOW"], key="sim_sev")
                resp_teams = sm2.number_input("Teams Deployed", 1, 10, 2, key="sim_teams")

                if st.button("✅ Submit Response"):
                    score_result = score_simulation(
                        st.session_state["sim_session"],
                        actual_severity=resp_sev,
                        actual_teams_deployed=resp_teams,
                        response_time_seconds=elapsed,
                    )
                    grade = score_result.get("grade","?")
                    pct   = score_result.get("percentage",0)
                    color = "#22CC44" if pct >= 85 else "#FFD700" if pct >= 60 else "#FF2222"
                    st.markdown(f'<h2 style="color:{color}">Grade: {grade} — {pct:.0f}%</h2>', unsafe_allow_html=True)
                    for item in score_result.get("breakdown",[]):
                        pts = item["points"]
                        color2 = "#22CC44" if pts > 0 else "#FF2222"
                        st.markdown(f'<span style="color:{color2}">{"✅" if pts>0 else "❌"} {item["item"]}: {pts} pts</span>', unsafe_allow_html=True)
                    del st.session_state["sim_session"]

    st.markdown("---")
    st.markdown("**🏆 Leaderboard:**")
    leaders = get_simulation_leaderboard(top_n=5)
    for i, entry in enumerate(leaders):
        st.markdown(f"**#{i+1}** — {entry.get('scenario_name','?')} | Grade: **{entry.get('grade','?')}** | Score: {entry.get('percentage',0):.0f}%")


# ════════════════════════════════════════════════════════════
# TAB 10 — LAN SYNC
# ════════════════════════════════════════════════════════════
with tab_lan:
    st.subheader("🌐 LAN Sync — Multi-Laptop Collaboration")

    sync_status = get_sync_status()
    ls1,ls2,ls3 = st.columns(3)
    ls1.metric("Node ID",           sync_status["node_id"])
    ls2.metric("Server Running",    "✅ YES" if sync_status["server_running"] else "❌ NO")
    ls3.metric("Connected Peers",   sync_status["connected_peers"])

    col_sv1, col_sv2 = st.columns(2)
    if col_sv1.button("🟢 Start Sync Server", disabled=sync_status["server_running"]):
        res = start_sync_server()
        st.success(f"Server started — Node ID: {res['node_id']} on port {res['port']}")
        st.rerun()
    if col_sv2.button("🔴 Stop Server", disabled=not sync_status["server_running"]):
        from utils.lan_sync import stop_sync_server
        stop_sync_server()
        st.rerun()

    st.markdown("---")
    peer_ip = st.text_input("Peer IP Address", placeholder="192.168.1.x")
    lc1, lc2 = st.columns(2)
    if lc1.button("📡 Ping Peer") and peer_ip:
        res = ping_peer(peer_ip)
        if res.get("online"):
            st.success(f"✅ Peer {peer_ip} ONLINE | Node: {res.get('peer_node_id')} | Incidents: {res.get('peer_incident_count')}")
        else:
            st.error(f"❌ Peer offline: {res.get('error')}")

    if lc2.button("🔄 Sync with Peer") and peer_ip:
        with st.spinner(f"Syncing with {peer_ip}..."):
            res = sync_with_peer(peer_ip)
        if res.get("success"):
            st.success(f"✅ Synced! Updated {res['incidents_updated']} incident(s) from {peer_ip}")
        else:
            st.error(f"Sync failed: {res.get('error')}")

    st.markdown("---")
    st.markdown("**Sync Log:**")
    logs = get_sync_log(limit=10)
    if logs:
        for entry in reversed(logs):
            st.markdown(f"`{entry['timestamp']}` — **{entry['event']}** — {entry.get('peer_ip','local')} {entry.get('details','')}")
    else:
        st.info("No sync activity yet.")


# ════════════════════════════════════════════════════════════
# TAB 11 — AGENT LOGS
# ════════════════════════════════════════════════════════════
with tab_logs:
    st.subheader("🔧 Agent Execution Logs")
    if "last_logs" in st.session_state:
        logs_list = st.session_state["last_logs"]
        for i, log in enumerate(logs_list):
            color = "#FF4444" if "[LLM" in log else "#44AAFF" if "[Photo" in log else "#44FF88" if "[Vitals" in log else "#FFD700" if "⚠️" in log else "#cccccc"
            st.markdown(f'<div style="font-family:monospace;color:{color};padding:2px 8px;font-size:0.88em">{i+1:02d}. {log}</div>', unsafe_allow_html=True)
    else:
        st.info("Run an emergency to see execution logs here.")

    from agents.llm_triage_agent import get_llm_log_summary, get_cache_stats
    cache_stats = get_cache_stats()
    st.markdown("---")
    st.markdown(f"**LLM Cache:** {cache_stats['cached_entries']}/{cache_stats['max_cache']} entries")
    llm_logs = get_llm_log_summary()
    if llm_logs:
        recent = llm_logs[-5:]
        for entry in recent:
            icon = "✅" if entry.get("success") else "⚠️"
            st.markdown(f'`{entry["timestamp"]}` {icon} {entry["method"]} — {entry["latency_ms"]}ms {entry.get("error","")}')


# ════════════════════════════════════════════════════════════
# TAB 12 — SETTINGS & ACCESS
# ════════════════════════════════════════════════════════════
with tab_settings:
    st.subheader("⚙️ Settings & Role-Based Access")

    set_tab1, set_tab2, set_tab3 = st.tabs(["🔐 Login / Roles", "🌪️ Mode & Profile", "🔊 Audio & Features"])

    # ── Login / Roles ──
    with set_tab1:
        st.markdown("**Current Session:**")
        st.markdown(get_role_badge_html(session), unsafe_allow_html=True)

        if not session:
            st.markdown("---")
            st.markdown("**Login:**")
            pin_input = st.text_input("Enter PIN", type="password", max_chars=10)
            if st.button("🔑 Login", type="primary"):
                result = login(pin_input)
                if result["success"]:
                    st.success(f"✅ Welcome, {result['display_name']}!")
                    st.rerun()
                else:
                    st.error(result.get("error","Invalid PIN"))
        else:
            if st.button("🚪 Logout"):
                logout(); st.rerun()

        st.markdown("---")
        st.markdown("**All Roles:**")
        roles = list_roles()
        for r in roles:
            rc = {"INCIDENT_COMMANDER":"#CC0000","FIRST_RESPONDER":"#FF4400","VOLUNTEER":"#0066CC","TRAINER":"#006600"}.get(r["role"],"#888")
            st.markdown(
                f'<div style="border-left:4px solid {rc};padding:6px 12px;margin:4px 0">'
                f'{r["badge_emoji"]} <b>{r["display_name"]}</b> (Level {r["level"]}) — '
                f'{r["permission_count"]} permissions | Logins: {r["login_count"]}'
                f'</div>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("**Default PINs (change after deployment):**")
        st.code("INCIDENT_COMMANDER: 1234\nFIRST_RESPONDER: 2345\nVOLUNTEER: 3456\nTRAINER: 4567", language="text")

    # ── Mode & Profile ──
    with set_tab2:
        st.markdown("**Disaster Profile:**")
        profiles = all_profiles_summary()
        profile_names = [p["name"] for p in profiles]
        selected_profile = st.selectbox("Active Profile", profile_names)
        if st.button("✅ Activate Profile"):
            activate_profile(selected_profile.lower())
            st.success(f"Profile activated: {selected_profile}")

        st.markdown("---")
        if st.button("🔴 ACTIVATE PANIC MODE", type="primary"):
            activate_panic_mode(); st.rerun()

        battery = st.slider("Battery Level %", 0, 100, sys_state.get("battery_level",100))
        if st.button("💾 Set Battery Level"):
            set_battery_level(battery)
            st.success(f"Battery set to {battery}%")

    # ── Audio & Features ──
    with set_tab3:
        st.markdown("**Audio Alerts:**")
        from utils.audio_alerts import is_muted, mute_alerts, unmute_alerts, get_alert_registry, play_alert

        muted = is_muted()
        col_m1, col_m2 = st.columns(2)
        if col_m1.button("🔇 Mute Alerts", disabled=muted):
            mute_alerts(); st.rerun()
        if col_m2.button("🔊 Unmute Alerts", disabled=not muted):
            unmute_alerts(); st.rerun()
        st.info("🔇 Alerts muted" if muted else "🔊 Alerts active")

        st.markdown("**Test Alerts:**")
        alert_types = [a["type"] for a in get_alert_registry()]
        selected_alert = st.selectbox("Alert Type", alert_types)
        if st.button("▶️ Play Test Alert"):
            result = play_alert(selected_alert)
            if result.get("muted"):
                st.warning("Alerts are muted — unmute to hear")
            else:
                st.success(f"Playing: {result.get('description','?')}")

        st.markdown("---")
        st.markdown("**Pipeline Info:**")
        st.markdown("- 15-node LangGraph pipeline")
        st.markdown("- Nodes: intake → llm_triage → photo_triage → multi_victim → triage → risk → kg → protocol → resource → triage_steps → response → incident_register → vitals_check → assignment → dispatch")
        st.markdown("- v4 NEW: LLM triage, Photo triage, Vitals, Hotspots, QR Tags, Drug DB, Simulation, LAN Sync, RBAC, Reports, Audio Alerts")
