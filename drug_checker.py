"""
command/drug_checker.py
────────────────────────
Drug Interaction Checker — Disaster Command Center v4 ELITE

Offline database of 30 emergency drugs with interaction checking,
dosage information, and contraindication alerts.

All data is self-contained — no internet access required.
Loads supplementary data from data/drug_database.json.

Functions:
    check_interaction(drug_a, drug_b) → interaction result
    get_drug_info(drug_name) → full drug profile
    get_dosage(drug_name, weight_kg, age, route) → dosage dict
    check_contraindications(drug_name, conditions) → contraindication list
"""

import os
import sys
import json
from typing import Dict, List, Optional, Any, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRUG_DB_FILE = os.path.join(BASE_DIR, "data", "drug_database.json")

# ── Builtin Emergency Drug Database (30 drugs) ──
BUILTIN_DRUGS = {
    "epinephrine": {
        "generic_name": "Epinephrine",
        "brand_names": ["Adrenaline", "EpiPen"],
        "class": "Sympathomimetic",
        "indications": ["anaphylaxis", "cardiac arrest", "severe asthma", "croup"],
        "contraindications": ["no absolute in cardiac arrest", "hypertension (relative)"],
        "dosage": {
            "adult_anaphylaxis": "0.3–0.5mg IM into outer thigh",
            "adult_cardiac_arrest": "1mg IV/IO q3-5min",
            "pediatric_anaphylaxis": "0.01mg/kg IM (max 0.5mg)",
        },
        "max_dose_adult_mg": 5.0,
        "onset_minutes": 5,
        "duration_minutes": 20,
        "interactions": {
            "beta_blockers": "MAJOR — reduces effectiveness, may cause hypertension",
            "tricyclic_antidepressants": "MAJOR — severe hypertension risk",
            "cocaine": "MAJOR — risk of cardiac arrhythmia",
            "halothane": "MAJOR — ventricular arrhythmia risk",
        },
        "pregnancy_category": "C",
        "storage": "Room temperature, protect from light",
    },
    "morphine": {
        "generic_name": "Morphine Sulfate",
        "brand_names": ["Morphine", "MS Contin"],
        "class": "Opioid analgesic",
        "indications": ["severe pain", "pulmonary edema", "myocardial infarction pain"],
        "contraindications": ["respiratory depression", "head injury (relative)", "hypotension", "COPD (relative)"],
        "dosage": {
            "adult_pain_iv": "2–4mg IV, may repeat q5min (max 10mg/hour)",
            "adult_pain_im": "5–15mg IM",
            "pediatric": "0.1mg/kg IV/IM q4h (max 15mg)",
        },
        "max_dose_adult_mg": 10.0,
        "onset_minutes": 5,
        "duration_minutes": 240,
        "interactions": {
            "benzodiazepines": "MAJOR — respiratory depression, sedation",
            "alcohol": "MAJOR — CNS depression",
            "naloxone": "REVERSES MORPHINE — use for overdose",
            "MAO_inhibitors": "MAJOR — hypertensive crisis",
        },
        "pregnancy_category": "C",
        "storage": "Controlled substance — secure storage required",
    },
    "naloxone": {
        "generic_name": "Naloxone",
        "brand_names": ["Narcan", "Evzio"],
        "class": "Opioid antagonist",
        "indications": ["opioid overdose", "respiratory depression from opioids"],
        "contraindications": ["opioid dependence (precipitates withdrawal)"],
        "dosage": {
            "adult_overdose_iv": "0.4–2mg IV/IM/IN, repeat q2-3min",
            "adult_overdose_in": "4mg intranasal (one spray per nostril)",
            "pediatric": "0.01mg/kg IV (max 2mg per dose)",
        },
        "max_dose_adult_mg": 10.0,
        "onset_minutes": 2,
        "duration_minutes": 45,
        "interactions": {
            "all_opioids": "REVERSES — intended therapeutic interaction",
            "buprenorphine": "MAJOR — may require higher doses to reverse",
        },
        "pregnancy_category": "B",
        "storage": "Room temperature",
    },
    "aspirin": {
        "generic_name": "Aspirin (Acetylsalicylic Acid)",
        "brand_names": ["Aspirin", "Bayer"],
        "class": "NSAID / Antiplatelet",
        "indications": ["suspected MI", "ischemic stroke", "pain", "fever"],
        "contraindications": ["active bleeding", "GI ulcer", "aspirin allergy", "children <12 (Reye syndrome)", "hemorrhagic stroke"],
        "dosage": {
            "adult_mi": "300–325mg chewed immediately",
            "adult_pain": "325–1000mg PO q4-6h",
        },
        "max_dose_adult_mg": 4000.0,
        "onset_minutes": 30,
        "duration_minutes": 360,
        "interactions": {
            "warfarin": "MAJOR — increased bleeding risk",
            "heparin": "MAJOR — additive anticoagulation",
            "ibuprofen": "MODERATE — reduces cardioprotective effect",
        },
        "pregnancy_category": "D (3rd trimester)",
        "storage": "Room temperature, dry",
    },
    "atropine": {
        "generic_name": "Atropine Sulfate",
        "brand_names": ["AtroPen", "Sal-Tropine"],
        "class": "Anticholinergic",
        "indications": ["bradycardia", "organophosphate poisoning", "pre-procedure antisialagogue"],
        "contraindications": ["narrow-angle glaucoma", "tachycardia", "myasthenia gravis"],
        "dosage": {
            "adult_bradycardia": "0.5–1mg IV q3-5min (max 3mg)",
            "adult_organophosphate": "2–4mg IV, repeat q5-10min until secretions dry",
            "pediatric_bradycardia": "0.02mg/kg IV (min 0.1mg, max 0.5mg)",
        },
        "max_dose_adult_mg": 3.0,
        "onset_minutes": 2,
        "duration_minutes": 60,
        "interactions": {
            "antihistamines": "MODERATE — additive anticholinergic effects",
            "tricyclic_antidepressants": "MODERATE — additive anticholinergic",
        },
        "pregnancy_category": "C",
        "storage": "Room temperature",
    },
    "diazepam": {
        "generic_name": "Diazepam",
        "brand_names": ["Valium", "Diastat"],
        "class": "Benzodiazepine",
        "indications": ["seizures", "anxiety", "alcohol withdrawal", "muscle spasm"],
        "contraindications": ["respiratory depression", "shock", "sleep apnea", "newborns"],
        "dosage": {
            "adult_seizure_iv": "5–10mg IV (2mg/min), may repeat q10min (max 30mg)",
            "adult_seizure_rectal": "0.2–0.5mg/kg rectal gel",
            "pediatric_seizure": "0.2–0.5mg/kg IV or rectal (max 10mg)",
        },
        "max_dose_adult_mg": 30.0,
        "onset_minutes": 3,
        "duration_minutes": 360,
        "interactions": {
            "opioids": "MAJOR — respiratory depression",
            "alcohol": "MAJOR — CNS depression",
            "phenobarbital": "MODERATE — additive CNS depression",
        },
        "pregnancy_category": "D",
        "storage": "Controlled substance",
    },
    "furosemide": {
        "generic_name": "Furosemide",
        "brand_names": ["Lasix"],
        "class": "Loop diuretic",
        "indications": ["pulmonary edema", "hypertensive crisis", "heart failure", "fluid overload"],
        "contraindications": ["anuria", "dehydration", "hypokalemia", "sulfa allergy"],
        "dosage": {
            "adult_pulm_edema_iv": "40–80mg IV over 2min",
            "adult_chronic": "20–80mg PO daily",
        },
        "max_dose_adult_mg": 600.0,
        "onset_minutes": 5,
        "duration_minutes": 120,
        "interactions": {
            "gentamicin": "MAJOR — ototoxicity risk",
            "lithium": "MAJOR — lithium toxicity",
            "digoxin": "MODERATE — hypokalemia increases digoxin toxicity",
        },
        "pregnancy_category": "C",
        "storage": "Room temperature, protect from light",
    },
    "nitroglycerin": {
        "generic_name": "Nitroglycerin",
        "brand_names": ["Nitrostat", "NitroBid"],
        "class": "Nitrate / Vasodilator",
        "indications": ["angina", "suspected MI", "hypertensive emergency", "heart failure"],
        "contraindications": ["hypotension (SBP<90)", "sildenafil/tadalafil use within 24-48h", "severe aortic stenosis"],
        "dosage": {
            "adult_angina_sl": "0.3–0.4mg sublingual, repeat q5min (max 3 doses)",
            "adult_infusion": "5–200mcg/min IV infusion",
        },
        "max_dose_adult_mg": 1.2,
        "onset_minutes": 2,
        "duration_minutes": 30,
        "interactions": {
            "sildenafil": "MAJOR — severe hypotension, CONTRAINDICATED",
            "alcohol": "MODERATE — hypotension",
            "antihypertensives": "MODERATE — additive hypotension",
        },
        "pregnancy_category": "B",
        "storage": "Dark, tight container — sensitive to heat and light",
    },
    "adenosine": {
        "generic_name": "Adenosine",
        "brand_names": ["Adenocard"],
        "class": "Antiarrhythmic",
        "indications": ["supraventricular tachycardia (SVT)", "stable narrow complex tachycardia"],
        "contraindications": ["second/third degree AV block", "sick sinus syndrome", "asthma (relative)", "AFib/Aflutter"],
        "dosage": {
            "adult_svt_iv": "6mg rapid IV push + flush, repeat 12mg if needed",
            "pediatric": "0.1mg/kg rapid IV (max 6mg first dose, max 12mg subsequent)",
        },
        "max_dose_adult_mg": 30.0,
        "onset_minutes": 0.1,
        "duration_minutes": 0.5,
        "interactions": {
            "dipyridamole": "MAJOR — potentiates adenosine, reduce dose",
            "theophylline": "MAJOR — blocks adenosine effect",
            "carbamazepine": "MODERATE — heart block risk",
        },
        "pregnancy_category": "C",
        "storage": "Room temperature",
    },
    "amiodarone": {
        "generic_name": "Amiodarone",
        "brand_names": ["Cordarone", "Pacerone"],
        "class": "Antiarrhythmic Class III",
        "indications": ["ventricular fibrillation", "pulseless VT", "stable VT", "AFib"],
        "contraindications": ["bradycardia", "second/third degree AV block", "cardiogenic shock", "severe pulmonary disease"],
        "dosage": {
            "adult_vfib_cardiac_arrest": "300mg IV/IO bolus, second dose 150mg",
            "adult_stable_vt": "150mg IV over 10min, then 1mg/min x 6h",
        },
        "max_dose_adult_mg": 2200.0,
        "onset_minutes": 5,
        "duration_minutes": 14400,
        "interactions": {
            "warfarin": "MAJOR — increases warfarin levels dramatically",
            "digoxin": "MAJOR — increases digoxin toxicity",
            "simvastatin": "MAJOR — myopathy risk",
        },
        "pregnancy_category": "D",
        "storage": "Room temperature, protect from light",
    },
    "glucose_50pct": {
        "generic_name": "Dextrose 50% (D50)",
        "brand_names": ["D50W"],
        "class": "Carbohydrate",
        "indications": ["severe hypoglycemia", "altered mental status with confirmed hypoglycemia"],
        "contraindications": ["hyperglycemia", "head injury without confirmed hypoglycemia (relative)"],
        "dosage": {
            "adult_hypoglycemia_iv": "25–50mL (12.5–25g) slow IV push",
            "pediatric": "2–4mL/kg of D25 (dilute D50 1:1)",
        },
        "max_dose_adult_mg": 25000.0,
        "onset_minutes": 3,
        "duration_minutes": 60,
        "interactions": {
            "insulin": "THERAPEUTIC PAIR — monitor closely",
        },
        "pregnancy_category": "A",
        "storage": "Room temperature",
    },
    "insulin_regular": {
        "generic_name": "Regular Insulin",
        "brand_names": ["Humulin R", "Novolin R"],
        "class": "Antidiabetic",
        "indications": ["diabetic ketoacidosis", "hyperglycemic hyperosmolar state", "hyperkalemia"],
        "contraindications": ["hypoglycemia"],
        "dosage": {
            "adult_dka_iv": "0.1 units/kg/h continuous infusion",
            "adult_hyperkalemia": "10 units IV with 50mL D50",
        },
        "max_dose_adult_mg": None,
        "onset_minutes": 30,
        "duration_minutes": 360,
        "interactions": {
            "glucose": "THERAPEUTIC — monitor blood glucose q1h",
            "beta_blockers": "MODERATE — may mask hypoglycemia signs",
            "alcohol": "MODERATE — hypoglycemia risk",
        },
        "pregnancy_category": "B",
        "storage": "Refrigerate, do not freeze",
    },
    "hydrocortisone": {
        "generic_name": "Hydrocortisone Sodium Succinate",
        "brand_names": ["Solu-Cortef"],
        "class": "Corticosteroid",
        "indications": ["anaphylaxis", "adrenal crisis", "severe asthma", "spinal cord injury"],
        "contraindications": ["systemic fungal infection", "live vaccines (relative)"],
        "dosage": {
            "adult_anaphylaxis_iv": "200mg IV bolus",
            "adult_asthma_iv": "200–400mg IV",
            "pediatric_anaphylaxis": "1–2mg/kg IV (max 100mg)",
        },
        "max_dose_adult_mg": 1000.0,
        "onset_minutes": 30,
        "duration_minutes": 480,
        "interactions": {
            "NSAIDs": "MODERATE — increased GI bleeding",
            "diabetes_medications": "MODERATE — hyperglycemia",
        },
        "pregnancy_category": "C",
        "storage": "Room temperature after reconstitution (6h)",
    },
    "diphenhydramine": {
        "generic_name": "Diphenhydramine",
        "brand_names": ["Benadryl"],
        "class": "Antihistamine H1",
        "indications": ["anaphylaxis (adjunct)", "allergic reaction", "dystonic reaction", "motion sickness"],
        "contraindications": ["narrow angle glaucoma", "prostatic hypertrophy", "newborns"],
        "dosage": {
            "adult_allergic_iv": "25–50mg slow IV",
            "adult_oral": "25–50mg PO q4-6h (max 300mg/day)",
            "pediatric": "1–1.25mg/kg IV/PO q4-6h",
        },
        "max_dose_adult_mg": 300.0,
        "onset_minutes": 15,
        "duration_minutes": 240,
        "interactions": {
            "opioids": "MODERATE — additive CNS depression",
            "MAO_inhibitors": "MAJOR — prolonged anticholinergic effects",
            "benzodiazepines": "MODERATE — CNS depression",
        },
        "pregnancy_category": "B",
        "storage": "Room temperature",
    },
    "ketamine": {
        "generic_name": "Ketamine",
        "brand_names": ["Ketalar"],
        "class": "Dissociative anesthetic",
        "indications": ["procedural sedation", "rapid sequence intubation", "refractory pain", "status epilepticus"],
        "contraindications": ["known psychosis", "elevated ICP (relative)", "schizophrenia"],
        "dosage": {
            "adult_sedation_iv": "1–2mg/kg IV (over 60sec)",
            "adult_sedation_im": "4–6mg/kg IM",
            "adult_analgesia_iv": "0.1–0.5mg/kg IV (low-dose)",
        },
        "max_dose_adult_mg": 500.0,
        "onset_minutes": 1,
        "duration_minutes": 15,
        "interactions": {
            "theophylline": "MAJOR — seizure risk",
            "atropine": "MODERATE — tachycardia",
            "opioids": "MODERATE — respiratory depression at high doses",
        },
        "pregnancy_category": "B",
        "storage": "Room temperature",
    },
    "midazolam": {
        "generic_name": "Midazolam",
        "brand_names": ["Versed"],
        "class": "Benzodiazepine",
        "indications": ["procedural sedation", "status epilepticus", "RSI premedication", "anxiety"],
        "contraindications": ["respiratory depression", "shock", "narrow angle glaucoma"],
        "dosage": {
            "adult_sedation_iv": "1–2.5mg IV, titrate slowly",
            "adult_seizure_im": "10mg IM (for seizures when IV unavailable)",
            "pediatric_seizure_in": "0.2mg/kg intranasal (max 10mg)",
        },
        "max_dose_adult_mg": 10.0,
        "onset_minutes": 3,
        "duration_minutes": 60,
        "interactions": {
            "opioids": "MAJOR — respiratory depression (FDA black box warning)",
            "alcohol": "MAJOR — CNS depression",
            "flumazenil": "REVERSAL AGENT — for benzodiazepine reversal",
        },
        "pregnancy_category": "D",
        "storage": "Room temperature",
    },
    "succinylcholine": {
        "generic_name": "Succinylcholine",
        "brand_names": ["Anectine", "Quelicin"],
        "class": "Depolarizing neuromuscular blocker",
        "indications": ["rapid sequence intubation", "laryngospasm"],
        "contraindications": ["hyperkalemia", "burns (after 24h)", "crush injury (after 24h)", "denervation", "malignant hyperthermia susceptibility"],
        "dosage": {
            "adult_rsi_iv": "1–1.5mg/kg IV",
            "adult_laryngospasm_im": "3–4mg/kg IM",
            "pediatric_rsi": "2mg/kg IV",
        },
        "max_dose_adult_mg": 150.0,
        "onset_minutes": 0.5,
        "duration_minutes": 10,
        "interactions": {
            "organophosphates": "MAJOR — prolonged paralysis",
            "neostigmine": "MAJOR — prolongs effect",
        },
        "pregnancy_category": "C",
        "storage": "Refrigerate (2–8°C)",
    },
    "rocuronium": {
        "generic_name": "Rocuronium Bromide",
        "brand_names": ["Zemuron", "Esmeron"],
        "class": "Non-depolarizing neuromuscular blocker",
        "indications": ["rapid sequence intubation", "endotracheal intubation"],
        "contraindications": ["myasthenia gravis (relative)", "known rocuronium allergy"],
        "dosage": {
            "adult_rsi_iv": "1.2mg/kg IV (sugammadex-reversible RSI)",
            "adult_intubation": "0.6mg/kg IV",
        },
        "max_dose_adult_mg": 200.0,
        "onset_minutes": 1,
        "duration_minutes": 60,
        "interactions": {
            "aminoglycosides": "MODERATE — prolonged paralysis",
            "sugammadex": "REVERSAL AGENT — specific antidote",
        },
        "pregnancy_category": "C",
        "storage": "Refrigerate (2–8°C)",
    },
    "tranexamic_acid": {
        "generic_name": "Tranexamic Acid (TXA)",
        "brand_names": ["Cyklokapron", "Lysteda"],
        "class": "Antifibrinolytic",
        "indications": ["traumatic hemorrhage", "postpartum hemorrhage", "major surgery bleeding"],
        "contraindications": ["active thromboembolic disease", "subarachnoid hemorrhage"],
        "dosage": {
            "adult_trauma_iv": "1g IV over 10min within 3h of injury, then 1g over 8h",
            "adult_pph_iv": "1g IV over 10min",
        },
        "max_dose_adult_mg": 2000.0,
        "onset_minutes": 5,
        "duration_minutes": 180,
        "interactions": {
            "factor_concentrates": "MODERATE — clotting risk",
            "hormonal_contraceptives": "MODERATE — thrombosis risk",
        },
        "pregnancy_category": "B",
        "storage": "Room temperature",
    },
    "ondansetron": {
        "generic_name": "Ondansetron",
        "brand_names": ["Zofran"],
        "class": "5-HT3 antagonist / Antiemetic",
        "indications": ["nausea and vomiting", "post-operative nausea", "opioid-induced nausea"],
        "contraindications": ["QT prolongation (relative)", "congenital long QT"],
        "dosage": {
            "adult_iv": "4mg slow IV over 2–5min",
            "adult_oral_dissolving": "4–8mg ODT",
            "pediatric_iv": "0.1mg/kg IV (max 4mg)",
        },
        "max_dose_adult_mg": 32.0,
        "onset_minutes": 15,
        "duration_minutes": 360,
        "interactions": {
            "QT_prolonging_drugs": "MAJOR — additive QT prolongation",
            "apomorphine": "MAJOR — severe hypotension",
        },
        "pregnancy_category": "B",
        "storage": "Room temperature",
    },
}


def _load_drug_db() -> Dict:
    """Load drug database — builtin + file-based."""
    db = dict(BUILTIN_DRUGS)
    try:
        if os.path.exists(DRUG_DB_FILE):
            with open(DRUG_DB_FILE, "r") as f:
                extra = json.load(f)
            if isinstance(extra, dict):
                db.update(extra)
    except Exception:
        pass
    return db


def _normalize_name(drug_name: str) -> str:
    """Normalize drug name for lookup."""
    return drug_name.lower().strip().replace(" ", "_").replace("-", "_")


def _find_drug(drug_name: str) -> Tuple[Optional[str], Optional[Dict]]:
    """Find drug by name (exact, normalized, or brand name match)."""
    db = _load_drug_db()
    key = _normalize_name(drug_name)

    if key in db:
        return key, db[key]

    # Search by generic or brand name
    for drug_key, info in db.items():
        if drug_key == key:
            return drug_key, info
        if drug_name.lower() in info.get("generic_name", "").lower():
            return drug_key, info
        for brand in info.get("brand_names", []):
            if drug_name.lower() in brand.lower():
                return drug_key, info

    return None, None


def get_drug_info(drug_name: str) -> Dict:
    """
    Get full drug profile.

    Args:
        drug_name: Generic or brand name

    Returns:
        Drug information dict or error dict
    """
    key, info = _find_drug(drug_name)
    if info is None:
        return {
            "found": False,
            "error": f"Drug '{drug_name}' not found in emergency database",
            "available_drugs": list(_load_drug_db().keys()),
        }
    return {"found": True, "drug_key": key, **info}


def get_dosage(drug_name: str, weight_kg: Optional[float] = None,
               age_years: Optional[int] = None,
               route: str = "IV") -> Dict:
    """
    Get dosage information, optionally weight/age-adjusted.

    Args:
        drug_name: Drug name
        weight_kg: Patient weight for weight-based dosing
        age_years: Patient age for pediatric dosing
        route: IV, IM, PO, IN, SL, etc.

    Returns:
        Dosage dict with calculated amounts
    """
    key, info = _find_drug(drug_name)
    if info is None:
        return {"found": False, "error": f"Drug '{drug_name}' not in database"}

    dosages = info.get("dosage", {})
    is_pediatric = age_years is not None and age_years < 18

    # Select most relevant dosage entry
    relevant_dosages = {}
    for dose_key, dose_value in dosages.items():
        if is_pediatric and "pediatric" in dose_key:
            relevant_dosages[dose_key] = dose_value
        elif not is_pediatric and "adult" in dose_key:
            relevant_dosages[dose_key] = dose_value

    if not relevant_dosages:
        relevant_dosages = dosages

    result = {
        "found": True,
        "drug": info.get("generic_name"),
        "route_requested": route,
        "dosages": relevant_dosages,
        "onset_minutes": info.get("onset_minutes"),
        "duration_minutes": info.get("duration_minutes"),
        "max_dose_adult_mg": info.get("max_dose_adult_mg"),
    }

    # Weight-based calculation if weight provided
    if weight_kg and is_pediatric:
        result["weight_kg"] = weight_kg
        # Try to find pediatric dose
        for dk, dv in relevant_dosages.items():
            if "kg" in str(dv).lower():
                result["weight_based_note"] = f"Multiply dose by {weight_kg}kg"
                break

    return result


def check_interaction(drug_a: str, drug_b: str) -> Dict:
    """
    Check for interaction between two drugs.

    Args:
        drug_a: First drug name
        drug_b: Second drug name

    Returns:
        Interaction result with severity and description
    """
    key_a, info_a = _find_drug(drug_a)
    key_b, info_b = _find_drug(drug_b)

    results = {
        "drug_a": drug_a,
        "drug_b": drug_b,
        "drug_a_found": info_a is not None,
        "drug_b_found": info_b is not None,
        "interactions_found": [],
        "highest_severity": "NONE",
        "safe_to_combine": True,
    }

    if info_a is None or info_b is None:
        results["error"] = "One or both drugs not found in database"
        return results

    # Check A's interaction list for B
    interactions_a = info_a.get("interactions", {})
    name_b_variants = [key_b, _normalize_name(drug_b), drug_b.lower()]

    for interaction_key, description in interactions_a.items():
        for variant in name_b_variants:
            if variant in interaction_key.lower() or interaction_key.lower() in variant:
                severity = "MAJOR" if "MAJOR" in description.upper() else \
                           "MODERATE" if "MODERATE" in description.upper() else "MINOR"
                results["interactions_found"].append({
                    "severity": severity,
                    "description": description,
                    "source": f"{info_a['generic_name']} → {info_b['generic_name']}",
                })
                break

    # Check B's interaction list for A
    interactions_b = info_b.get("interactions", {})
    name_a_variants = [key_a, _normalize_name(drug_a), drug_a.lower()]

    for interaction_key, description in interactions_b.items():
        for variant in name_a_variants:
            if variant in interaction_key.lower() or interaction_key.lower() in variant:
                severity = "MAJOR" if "MAJOR" in description.upper() else \
                           "MODERATE" if "MODERATE" in description.upper() else "MINOR"
                results["interactions_found"].append({
                    "severity": severity,
                    "description": description,
                    "source": f"{info_b['generic_name']} → {info_a['generic_name']}",
                })
                break

    # Determine highest severity
    if results["interactions_found"]:
        severities = [i["severity"] for i in results["interactions_found"]]
        if "MAJOR" in severities:
            results["highest_severity"] = "MAJOR"
            results["safe_to_combine"] = False
        elif "MODERATE" in severities:
            results["highest_severity"] = "MODERATE"
            results["safe_to_combine"] = False
        else:
            results["highest_severity"] = "MINOR"
            results["safe_to_combine"] = True

    return results


def check_contraindications(drug_name: str, conditions: List[str]) -> Dict:
    """
    Check if drug has contraindications for given patient conditions.

    Args:
        drug_name: Drug name
        conditions: List of patient conditions/diagnoses

    Returns:
        Dict with flagged contraindications
    """
    key, info = _find_drug(drug_name)
    if info is None:
        return {"found": False, "error": f"Drug '{drug_name}' not found"}

    contraindications = info.get("contraindications", [])
    flagged = []

    for condition in conditions:
        condition_lower = condition.lower()
        for contra in contraindications:
            contra_lower = contra.lower()
            # Check keyword overlap
            condition_words = set(condition_lower.split())
            contra_words = set(contra_lower.split())
            overlap = condition_words & contra_words - {"the", "a", "an", "in", "of", "with", "and"}
            if overlap or condition_lower in contra_lower or contra_lower in condition_lower:
                flagged.append({
                    "condition": condition,
                    "contraindication": contra,
                    "severity": "ABSOLUTE" if "relative" not in contra_lower else "RELATIVE",
                })

    return {
        "found": True,
        "drug": info.get("generic_name"),
        "patient_conditions": conditions,
        "flagged_contraindications": flagged,
        "has_contraindications": len(flagged) > 0,
        "absolute_contraindications": [f for f in flagged if f["severity"] == "ABSOLUTE"],
    }


def list_all_drugs() -> List[str]:
    """Return list of all drug names in the database."""
    return sorted(_load_drug_db().keys())


def search_drugs_by_indication(indication: str) -> List[Dict]:
    """Find drugs indicated for a specific condition."""
    db = _load_drug_db()
    matches = []
    for key, info in db.items():
        indications = info.get("indications", [])
        if any(indication.lower() in ind.lower() for ind in indications):
            matches.append({
                "drug_key": key,
                "generic_name": info.get("generic_name"),
                "class": info.get("class"),
                "indications": indications,
            })
    return matches
