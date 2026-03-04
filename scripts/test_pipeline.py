import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.transcript_processor   import TranscriptProcessor, _RuleExtractor
from scripts.agent_prompt_generator import AgentPromptGenerator
from scripts.version_manager        import VersionManager
from scripts.batch_processor        import BatchProcessor


# ─────────────────────────────────────────────
# Test runner
# ─────────────────────────────────────────────

_passed = _failed = 0

def test(name: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  ✅  {name}")
    else:
        _failed += 1
        print(f"  ❌  {name}" + (f"  →  {detail}" if detail else ""))


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

DEMO_TRANSCRIPT = """
Hi, I'm calling from Ben's Electric Solutions. My name is Ben Penoyer.
Our business hours are Monday to Friday, 7 AM to 5 PM MST.
We are located at 4710 17 Ave SW, Calgary, AB T3E 0E4.
We offer Residential Wiring, Panel Upgrades, and EV Charger Installation.
Emergencies like complete power outages and sparking panels should call 403-870-8494.
For regular service calls during business hours, same number: 403-870-8494.
If no one answers, take a message and call back within 2 hours.
We never schedule jobs without customer confirmation.
We never take on jobs outside of Calgary.
After hours: screen for emergencies, transfer if emergency, take message if not.
"""

ONBOARDING_TRANSCRIPT = """
This is the onboarding call for Ben's Electric Solutions, ACC_001.
Emergency primary contact updated to 403-870-8494.
Backup emergency contact is 403-555-0199.
Our services now include Smart Panel Installation as well.
New constraint: never create a job in Jobber without verbal confirmation.
Additional constraint: never promise same-day service.
Office address confirmed: 4710 17 Ave SW, Calgary, AB T3E 0E4.
"""

ACCOUNT_INFO = {
    "account_id":   "ACC_001",
    "company_name": "Ben's Electric Solutions",
    "business_hours": {
        "days": ["Monday","Tuesday","Wednesday","Thursday","Friday"],
        "start_time": "07:00", "end_time": "17:00", "timezone": "MST",
    },
    "office_address": "4710 17 Ave SW, Calgary, AB T3E 0E4",
    "services_supported": ["Residential Wiring","Panel Upgrades","EV Charger Installation"],
    "emergency_definition": ["complete power outage","sparking panel","electrical fire"],
    "emergency_routing_rules": {
        "primary_contact": "403-870-8494",
        "secondary_contacts": ["403-555-0199"],
        "fallback_protocol": "Take message, callback within 15 minutes",
    },
    "non_emergency_routing_rules": {
        "primary_contact": "403-870-8494",
        "secondary_contacts": [],
        "message_protocol": "Take message, callback within 2 hours",
    },
    "call_transfer_rules": {"timeout_seconds": 30, "max_retries": 3},
    "integration_constraints": [
        "Never schedule jobs without customer confirmation",
        "Never take on jobs outside of Calgary",
    ],
    "after_hours_flow_summary":  "Screen for emergencies then transfer or take message",
    "office_hours_flow_summary": "Greet, identify need, collect info, route to 403-870-8494",
    "questions_or_unknowns": [],
    "notes": "Test fixture",
}


# ─────────────────────────────────────────────
# 1. Transcript extraction
# ─────────────────────────────────────────────

def test_extraction():
    print("\n── Transcript Extraction ──────────────────────────")
    ex = _RuleExtractor()
    r  = ex.extract(DEMO_TRANSCRIPT, "ACC_001")

    test("Company name extracted",
         r["company_name"] == "Ben's Electric Solutions",
         repr(r["company_name"]))

    test("Business hours — days",
         "Monday" in r["business_hours"]["days"] and "Friday" in r["business_hours"]["days"],
         repr(r["business_hours"]["days"]))

    test("Business hours — start time",
         r["business_hours"]["start_time"] == "07:00",
         repr(r["business_hours"]["start_time"]))

    test("Business hours — end time",
         r["business_hours"]["end_time"] == "17:00",
         repr(r["business_hours"]["end_time"]))

    test("Timezone extracted",
         r["business_hours"]["timezone"] == "MST",
         repr(r["business_hours"]["timezone"]))

    test("Office address extracted",
         "Calgary" in r["office_address"],
         repr(r["office_address"]))

    test("Services extracted",
         len(r["services_supported"]) >= 1,
         repr(r["services_supported"]))

    test("Emergency definition extracted",
         len(r["emergency_definition"]) >= 1,
         repr(r["emergency_definition"]))

    test("Emergency phone extracted",
         r["emergency_routing_rules"]["primary_contact"] == "403-870-8494",
         repr(r["emergency_routing_rules"]["primary_contact"]))

    test("Integration constraints extracted",
         any("confirmation" in c.lower() or "never" in c.lower()
             for c in r["integration_constraints"]),
         repr(r["integration_constraints"]))

    test("questions_or_unknowns is a list",
         isinstance(r["questions_or_unknowns"], list))

    test("No hallucinated company (not a stopword)",
         r["company_name"].lower() not in {"the","a","an","our","from",""},
         repr(r["company_name"]))


# ─────────────────────────────────────────────
# 2. TranscriptProcessor public API
# ─────────────────────────────────────────────

def test_processor():
    print("\n── TranscriptProcessor ────────────────────────────")
    proc = TranscriptProcessor()

    r1 = proc.extract_account_info(DEMO_TRANSCRIPT, "ACC_001", "demo")
    test("extract_account_info returns dict",        isinstance(r1, dict))
    test("account_id preserved",                    r1["account_id"] == "ACC_001")
    test("company_name present and non-empty",       bool(r1.get("company_name")))

    r2 = proc.extract_updates(ONBOARDING_TRANSCRIPT, "ACC_001")
    test("extract_updates returns dict",             isinstance(r2, dict))
    test("extract_updates has account_id",           r2.get("account_id") == "ACC_001")


# ─────────────────────────────────────────────
# 3. Agent config generation
# ─────────────────────────────────────────────

def test_agent_generation():
    print("\n── Agent Config Generation ────────────────────────")
    gen = AgentPromptGenerator()
    cfg = gen.generate_agent_config(ACCOUNT_INFO, "v1")

    test("Config has agent_name",     bool(cfg.get("agent_name")))
    test("Config has system_prompt",  bool(cfg.get("system_prompt")))
    test("Config has voice_style",    isinstance(cfg.get("voice_style"), dict))
    test("Config version is v1",      cfg["version"] == "v1")
    test("Config has changelog list", isinstance(cfg.get("changelog"), list))

    prompt = cfg["system_prompt"]
    test("Prompt contains company name",             "Ben's Electric Solutions" in prompt)
    test("Prompt contains BUSINESS HOURS CALL FLOW", "BUSINESS HOURS CALL FLOW" in prompt)
    test("Prompt contains AFTER-HOURS CALL FLOW",    "AFTER-HOURS CALL FLOW" in prompt)
    test("Prompt contains EMERGENCY HANDLING",       "EMERGENCY HANDLING" in prompt)
    test("Prompt contains STEP 1",                   "STEP 1" in prompt)
    test("Prompt contains STEP 7",                   "STEP 7" in prompt)
    test("Prompt contains STEP 3A (emergency)",      "STEP 3A" in prompt)
    test("Prompt contains STEP 3B (non-emergency)",  "STEP 3B" in prompt)
    test("Prompt contains transfer tool placeholder","transfer_call" in prompt or "TOOL" in prompt)
    test("Prompt contains business hours",           "07:00" in prompt or "Monday" in prompt)
    test("Prompt contains emergency phone",          "403-870-8494" in prompt)
    test("Prompt contains NEVER VIOLATE",            "NEVER VIOLATE" in prompt)

    test("Config has call_transfer_protocol",  isinstance(cfg.get("call_transfer_protocol"), dict))
    test("Config has fallback_protocol",       isinstance(cfg.get("fallback_protocol"), dict))
    test("Config has conversation_flows",      isinstance(cfg.get("conversation_flows"), dict))
    test("conversation_flows has office_hours_flow",  "office_hours_flow" in cfg["conversation_flows"])
    test("conversation_flows has after_hours_flow",   "after_hours_flow"  in cfg["conversation_flows"])


# ─────────────────────────────────────────────
# 4. Version management
# ─────────────────────────────────────────────

def test_versioning():
    print("\n── Version Management ─────────────────────────────")
    gen = AgentPromptGenerator()
    cfg = gen.generate_agent_config(ACCOUNT_INFO, "v1")

    with tempfile.TemporaryDirectory() as td:
        vm = VersionManager(td)

        path = vm.save_version("ACC_001", ACCOUNT_INFO, "account_memo", "v1")
        test("save_version returns path",   isinstance(path, str))
        test("saved file exists",           Path(path).exists())

        vm.save_version("ACC_001", cfg, "agent_config", "v1")
        test("version_exists returns True",  vm.version_exists("ACC_001","v1","account_memo"))
        test("version_exists v99 = False",   not vm.version_exists("ACC_001","v99","account_memo"))

        loaded = vm.load_version("ACC_001", "v1", "account_memo")
        test("load_version returns dict",        isinstance(loaded, dict))
        test("loaded company_name correct",      loaded["company_name"] == "Ben's Electric Solutions")

        # create v2
        info_v2 = dict(ACCOUNT_INFO)
        info_v2["services_supported"] = ACCOUNT_INFO["services_supported"] + ["Smart Panel Installation"]
        info_v2["emergency_routing_rules"] = {
            "primary_contact": "403-870-8494",
            "secondary_contacts": ["403-555-0199"],
        }
        vm.save_version("ACC_001", info_v2, "account_memo", "v2")
        vm.save_version("ACC_001", gen.generate_agent_config(info_v2,"v2"), "agent_config", "v2")

        diff = vm.compare_versions("ACC_001","v1","v2","account_memo")
        test("diff has changes_summary",     "changes_summary" in diff)
        test("diff detected service change", any("Smart Panel" in str(c) for c in diff["changes_summary"]))

        cl_path = vm.record_changelog("ACC_001","v1","v2","account_memo",diff["changes_summary"])
        test("changelog file created",       Path(cl_path).exists())
        log = json.load(open(cl_path))
        test("changelog has 1 entry",        len(log) == 1)

        # idempotency
        vm.record_changelog("ACC_001","v1","v2","account_memo",diff["changes_summary"])
        vm.record_changelog("ACC_001","v1","v2","account_memo",diff["changes_summary"])
        log2 = json.load(open(cl_path))
        test("changelog stays at 1 entry (idempotent)", len(log2) == 1)

        report = vm.write_diff_report("ACC_001","v1","v2")
        test("diff report file created",     Path(report).exists())

        history = vm.account_history("ACC_001")
        test("account_history has versions", len(history["versions"]) == 2)
        test("account_history has changelog",isinstance(history["changelog"], list))

        summary = vm.all_accounts_summary()
        test("all_accounts_summary total = 1", summary["total_accounts"] == 1)
        test("summary has ACC_001",            "ACC_001" in summary["accounts"])


# ─────────────────────────────────────────────
# 5. Smart merge
# ─────────────────────────────────────────────

def test_merge():
    print("\n── Smart Merge ────────────────────────────────────")
    bp = BatchProcessor()

    base = {
        "account_id":            "ACC_001",
        "company_name":          "Ben's Electric Solutions",
        "services_supported":    ["Electrical Repair","Panel Upgrades"],
        "integration_constraints": ["Never schedule without confirmation"],
        "business_hours":        {"days":["Monday","Friday"],"start_time":"07:00","end_time":"17:00","timezone":"MST"},
        "emergency_routing_rules": {"primary_contact":"403-870-8494","secondary_contacts":[]},
    }
    updates = {
        "services_supported":      ["EV Charger Installation"],
        "integration_constraints": ["Never create Jobber job without verbal confirmation"],
        "emergency_routing_rules": {"primary_contact":"403-870-8494","secondary_contacts":["403-555-0199"]},
        "office_address":          "4710 17 Ave SW, Calgary",
    }

    merged = bp._merge(base, updates)

    test("account_id unchanged",
         merged["account_id"] == "ACC_001")

    test("services list is union (old + new)",
         "Electrical Repair"        in merged["services_supported"] and
         "EV Charger Installation"  in merged["services_supported"])

    test("constraints list is union",
         "Never schedule without confirmation"                  in merged["integration_constraints"] and
         "Never create Jobber job without verbal confirmation"  in merged["integration_constraints"])

    test("emergency secondary contact added",
         "403-555-0199" in merged["emergency_routing_rules"]["secondary_contacts"])

    test("emergency primary preserved",
         merged["emergency_routing_rules"]["primary_contact"] == "403-870-8494")

    test("new scalar field added (office_address)",
         merged["office_address"] == "4710 17 Ave SW, Calgary")

    test("empty string update does NOT overwrite",
         bp._merge({"company_name":"Ben's Electric"}, {"company_name":""})["company_name"] == "Ben's Electric")

    test("empty list update does NOT overwrite",
         bp._merge({"services_supported":["Repair"]}, {"services_supported":[]})["services_supported"] == ["Repair"])

    test("no duplicate services after double-merge",
         len(bp._merge(
             {"services_supported":["Repair","EV Charger"]},
             {"services_supported":["EV Charger","New Service"]}
         )["services_supported"]) == 3)


# ─────────────────────────────────────────────
# 6. Full pipeline integration (file-based)
# ─────────────────────────────────────────────

def test_full_pipeline():
    print("\n── Full Pipeline Integration ──────────────────────")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base/"data"/"demo_calls").mkdir(parents=True)
        (base/"data"/"onboarding_calls").mkdir(parents=True)
        (base/"schemas").mkdir()

        (base/"data"/"demo_calls"/"acc_001_demo.txt").write_text(DEMO_TRANSCRIPT)
        (base/"data"/"onboarding_calls"/"acc_001_onboarding.txt").write_text(ONBOARDING_TRANSCRIPT)

        bp  = BatchProcessor(str(base))
        ra  = bp.run_demo_pipeline()
        test("Pipeline A — no errors",        ra["errors"] == 0)
        test("Pipeline A — 1 processed",      ra["processed"] == 1)
        test("Pipeline A — v1 files exist",   (base/"outputs"/"accounts"/"ACC_001"/"v1"/"account_memo.json").exists())

        rb  = bp.run_onboarding_pipeline()
        test("Pipeline B — no errors",        rb["errors"] == 0)
        test("Pipeline B — 1 processed",      rb["processed"] == 1)
        test("Pipeline B — v2 files exist",   (base/"outputs"/"accounts"/"ACC_001"/"v2"/"account_memo.json").exists())
        test("Changelog file created",        len(list((base/"changelog").glob("*.json"))) > 0)
        test("Diff report created",           len(list((base/"changelog").glob("*.md"))) > 0)

        # idempotency
        ra2 = bp.run_demo_pipeline()
        rb2 = bp.run_onboarding_pipeline()
        test("Pipeline A idempotent (0 processed on re-run)", ra2["processed"] == 0 and ra2["skipped"] == 1)
        test("Pipeline B idempotent (0 processed on re-run)", rb2["processed"] == 0 and rb2["skipped"] == 1)

        # v2 memo has merged services
        v2_memo = json.load(open(base/"outputs"/"accounts"/"ACC_001"/"v2"/"account_memo.json"))
        test("v2 memo has Smart Panel from onboarding",
             any("Smart Panel" in s for s in v2_memo.get("services_supported", [])))

        # v2 agent prompt has new info
        v2_agent = json.load(open(base/"outputs"/"accounts"/"ACC_001"/"v2"/"agent_config.json"))
        test("v2 agent_config has system_prompt", bool(v2_agent.get("system_prompt")))
        test("v2 agent_config has changelog",     len(v2_agent.get("changelog", [])) > 0)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  Clara Assignment — Test Suite")
    print("="*60)

    test_extraction()
    test_processor()
    test_agent_generation()
    test_versioning()
    test_merge()
    test_full_pipeline()

    total = _passed + _failed
    print(f"\n{'='*60}")
    print(f"  Results: {_passed}/{total} passed", end="")
    if _failed:
        print(f"  ({_failed} FAILED)")
    else:
        print("  🎉 All tests passed!")
    print(f"{'='*60}\n")

    if _failed:
        sys.exit(1)


if __name__ == "__main__":
    main()














