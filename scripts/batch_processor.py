
from dotenv import load_dotenv
load_dotenv()

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.transcript_processor   import TranscriptProcessor
from scripts.agent_prompt_generator import AgentPromptGenerator
from scripts.version_manager        import VersionManager
from scripts.task_tracker           import TaskTracker


class BatchProcessor:

    def __init__(self, base_dir: str = "."):
        self.base_dir  = Path(base_dir).resolve()
        self.processor = TranscriptProcessor()
        self.generator = AgentPromptGenerator()
        self.vm        = VersionManager(str(self.base_dir))
        self.tracker   = TaskTracker(str(self.base_dir))

    # ─────────────────────────────────────────────
    # Pipeline A — demo calls → v1
    # ─────────────────────────────────────────────

    def run_demo_pipeline(self, force: bool = False) -> Dict[str, Any]:
        demo_dir = self.base_dir / "data" / "demo_calls"
        if not demo_dir.exists():
            return {"error": f"Not found: {demo_dir}"}

        files = sorted(demo_dir.glob("*.txt"))
        if not files:
            return {"error": f"No .txt files in {demo_dir}"}

        ok = skipped = errors = 0
        results: List[Dict] = []

        print(f"\n{'='*60}")
        print(f"PIPELINE A  —  Demo Calls → v1")
        print(f"Found {len(files)} file(s)")
        print(f"{'='*60}")

        for fp in files:
            account_id = fp.stem.replace("_demo", "").upper()
            print(f"\n  [{account_id}]  {fp.name}")

            if not force and self.vm.version_exists(account_id, "v1", "account_memo"):
                print("  ⏩  v1 already exists — skipping  (--force to reprocess)")
                skipped += 1
                results.append({"account_id": account_id, "status": "skipped", "reason": "v1 already exists"})
                continue

            try:
                print("  📋  Extracting account information …")
                info = self.processor.process_file(str(fp), account_id, "demo")
                info.pop("_method", None)

                print("  🤖  Generating agent config …")
                cfg = self.generator.generate_agent_config(info, "v1")

                print("  💾  Saving …")
                self.vm.save_version(account_id, info, "account_memo", "v1")
                self.vm.save_version(account_id, cfg,  "agent_config",  "v1")

                print(f"  ✅  Done — {info.get('company_name', '(unknown)')}")
                self.tracker.create_task(
                    account_id=account_id,
                    company_name=info.get("company_name", account_id),
                    task_type="demo_processing",
                    details={
                        "version": "v1",
                        "services": info.get("services_supported", []),
                        "unknowns": info.get("questions_or_unknowns", []),
                        "outputs": {
                            "account_memo": f"outputs/accounts/{account_id}/v1/account_memo.json",
                            "agent_config": f"outputs/accounts/{account_id}/v1/agent_config.json",
                        }
                    }
                )
                ok += 1
                results.append({
                    "account_id":   account_id,
                    "status":       "success",
                    "version":      "v1",
                    "company_name": info.get("company_name", ""),
                    "services":     info.get("services_supported", []),
                    "unknowns":     info.get("questions_or_unknowns", []),
                    "outputs": {
                        "account_memo": f"outputs/accounts/{account_id}/v1/account_memo.json",
                        "agent_config": f"outputs/accounts/{account_id}/v1/agent_config.json",
                    },
                })

            except Exception as exc:
                print(f"  ❌  Error: {exc}")
                errors += 1
                results.append({"account_id": account_id, "status": "error",
                                 "error": str(exc), "traceback": traceback.format_exc()})

        print(f"\n{'='*60}")
        print(f"Pipeline A — ✅ {ok} processed  ⏩ {skipped} skipped  ❌ {errors} errors")
        print(f"{'='*60}")
        return {"pipeline":"A_demo","processed":ok,"skipped":skipped,"errors":errors,
                "total":len(files),"results":results,"timestamp":datetime.now().isoformat()}

    # ─────────────────────────────────────────────
    # Pipeline B — onboarding calls → v2
    # ─────────────────────────────────────────────

    def run_onboarding_pipeline(self, force: bool = False) -> Dict[str, Any]:
        onb_dir = self.base_dir / "data" / "onboarding_calls"
        if not onb_dir.exists():
            return {"error": f"Not found: {onb_dir}"}

        files = sorted(onb_dir.glob("*.txt"))
        if not files:
            return {"error": f"No .txt files in {onb_dir}"}

        ok = skipped = errors = 0
        results: List[Dict] = []

        print(f"\n{'='*60}")
        print(f"PIPELINE B  —  Onboarding Calls → v2")
        print(f"Found {len(files)} file(s)")
        print(f"{'='*60}")

        for fp in files:
            account_id = fp.stem.replace("_onboarding", "").upper()
            print(f"\n  [{account_id}]  {fp.name}")

            if not force and self.vm.version_exists(account_id, "v2", "account_memo"):
                print("  ⏩  v2 already exists — skipping  (--force to reprocess)")
                skipped += 1
                results.append({"account_id": account_id, "status": "skipped", "reason": "v2 already exists"})
                continue

            try:
                v1_memo  = self.vm.load_version(account_id, "v1", "account_memo")
                v1_agent = self.vm.load_version(account_id, "v1", "agent_config")
                if v1_memo is None:
                    raise ValueError(f"No v1 account_memo for {account_id} — run Pipeline A first")
                if v1_agent is None:
                    raise ValueError(f"No v1 agent_config for {account_id} — run Pipeline A first")

                print("  📋  Extracting onboarding updates …")
                updates = self.processor.extract_updates(fp.read_text(encoding="utf-8"), account_id)
                updates.pop("_method", None)

                print("  🔀  Merging updates into v1 …")
                v2_memo = self._merge(v1_memo, updates)
                v2_memo["version"]      = "v2"
                v2_memo["last_updated"] = datetime.now().isoformat()

                print("  🤖  Regenerating agent config for v2 …")
                v2_agent = self.generator.update_agent_config(v1_agent, v2_memo, "v2")

                print("  💾  Saving …")
                self.vm.save_version(account_id, v2_memo,  "account_memo", "v2")
                self.vm.save_version(account_id, v2_agent, "agent_config",  "v2")

                diff    = self.vm.compare_versions(account_id, "v1", "v2", "account_memo")
                changes = diff.get("changes_summary", ["Updated from onboarding call"])
                self.vm.record_changelog(account_id, "v1", "v2", "account_memo", changes)
                self.vm.write_diff_report(account_id, "v1", "v2")

                print(f"  ✅  Done — {len(changes)} change(s) logged")
                self.tracker.create_task(
                    account_id=account_id,
                    company_name=v2_memo.get("company_name", account_id),
                    task_type="onboarding_update",
                    details={
                        "version": "v2",
                        "changes": changes,
                        "outputs": {
                            "account_memo": f"outputs/accounts/{account_id}/v2/account_memo.json",
                            "agent_config": f"outputs/accounts/{account_id}/v2/agent_config.json",
                            "changelog":    f"changelog/{account_id}_changelog.json",
                        }
                    }
                )
                ok += 1
                results.append({
                    "account_id": account_id,
                    "status":     "success",
                    "version":    "v2",
                    "changes":    changes,
                    "outputs": {
                        "account_memo": f"outputs/accounts/{account_id}/v2/account_memo.json",
                        "agent_config": f"outputs/accounts/{account_id}/v2/agent_config.json",
                        "changelog":    f"changelog/{account_id}_changelog.json",
                        "diff_report":  f"changelog/{account_id}_v1_to_v2_diff.md",
                    },
                })

            except Exception as exc:
                print(f"  ❌  Error: {exc}")
                errors += 1
                results.append({"account_id": account_id, "status": "error",
                                 "error": str(exc), "traceback": traceback.format_exc()})

        print(f"\n{'='*60}")
        print(f"Pipeline B — ✅ {ok} processed  ⏩ {skipped} skipped  ❌ {errors} errors")
        print(f"{'='*60}")
        return {"pipeline":"B_onboarding","processed":ok,"skipped":skipped,"errors":errors,
                "total":len(files),"results":results,"timestamp":datetime.now().isoformat()}

    # ─────────────────────────────────────────────
    # Full pipeline
    # ─────────────────────────────────────────────

    def run_all(self, force: bool = False) -> Dict[str, Any]:
        print("\n🚀  Clara Assignment — Full Pipeline")
        print(f"    Base dir: {self.base_dir}")

        res_a = self.run_demo_pipeline(force=force)
        if "error" in res_a:
            print(f"\n❌  Pipeline A failed: {res_a['error']}")
            return res_a

        res_b = self.run_onboarding_pipeline(force=force)
        if "error" in res_b:
            print(f"\n❌  Pipeline B failed: {res_b['error']}")
            return res_b

        summary = {
            "pipeline_a": res_a, "pipeline_b": res_b,
            "total_errors": res_a["errors"] + res_b["errors"],
            "timestamp": datetime.now().isoformat(),
        }
        summary_path = self.base_dir / "batch_processing_summary.json"
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)

        print(f"\n✅  All done!  Summary → {summary_path}")
        self._print_table()
        self.tracker.print_summary()
        return summary

    def _print_table(self) -> None:
        s = self.vm.all_accounts_summary()
        print(f"\n  {'ID':<12} {'Company':<35} Versions")
        print(f"  {'-'*12} {'-'*35} {'-'*15}")
        for aid, info in sorted(s.get("accounts", {}).items()):
            print(f"  {aid:<12} {info['company_name']:<35} {', '.join(info['versions'])}")

    # ─────────────────────────────────────────────
    # Smart merge  (v1 + onboarding updates → v2)
    # ─────────────────────────────────────────────

    @staticmethod
    def _merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge onboarding updates into v1.
        - Lists  → union (no near-duplicates)
        - Dicts  → deep merge (empty values never overwrite)
        - Scalars → update only if new value is non-empty
        - account_id is never changed
        - Protected fields keep their v1 values always
        """
        merged = dict(base)
        list_fields = ["services_supported", "emergency_definition",
                       "integration_constraints", "questions_or_unknowns"]
        dict_fields = ["business_hours", "emergency_routing_rules",
                       "non_emergency_routing_rules", "call_transfer_rules"]
        skip_fields = {"account_id", "version", "last_updated", "notes", "_method"}

        # These keys inside dicts must NEVER be overwritten if they already have a value
        protected_keys = {
            "timeout_seconds", "max_retries", "failure_message",  # call_transfer_rules
            "start_time", "end_time", "timezone",  # business_hours
        }

        # These extra keys Groq sometimes adds — never allow them
        rejected_keys = {
            "time_zone", "monday", "tuesday", "wednesday",
            "thursday", "friday", "saturday", "sunday",
            "emergency_transfer", "non_emergency_transfer",
            "phone", "message_details", "transfer_timeout",
            "callback_timeout", "backup_contact",
        }

        for key, value in updates.items():
            if key in skip_fields:
                continue
            if value in (None, "", [], {}):
                continue

            if key in list_fields and isinstance(value, list):
                existing = list(merged.get(key, []))
                for item in value:
                    if not item:
                        continue
                    # Skip near-duplicates
                    item_norm = item.lower().strip().rstrip("s")
                    already_exists = any(
                        item_norm in ex.lower().strip().rstrip("s") or
                        ex.lower().strip().rstrip("s") in item_norm
                        for ex in existing
                    )
                    if not already_exists:
                        existing.append(item)
                merged[key] = existing

            elif key in dict_fields and isinstance(value, dict):
                existing = dict(merged.get(key, {}))
                for k, v in value.items():
                    # Reject keys Groq should never add
                    if k in rejected_keys:
                        # Special case: backup_contact goes into secondary_contacts
                        if k == "backup_contact" and v:
                            sc = existing.get("secondary_contacts", [])
                            if v not in sc:
                                sc.append(v)
                            existing["secondary_contacts"] = sc
                        continue
                    if v in (None, "", [], {}):
                        continue
                    # Protected keys — only set if currently empty/missing in v1
                    if k in protected_keys:
                        if not existing.get(k):
                            existing[k] = v
                        # else keep v1 value — never overwrite
                    else:
                        existing[k] = v
                merged[key] = existing

            else:
                merged[key] = value

        # Clean questions_or_unknowns — remove bare field names
        known_field_names = {
            "account_id", "company_name", "business_hours", "office_address",
            "services_supported", "emergency_definition", "emergency_routing_rules",
            "non_emergency_routing_rules", "call_transfer_rules", "integration_constraints",
            "after_hours_flow_summary", "office_hours_flow_summary", "questions_or_unknowns",
            "notes", "version", "last_updated", "timeout_seconds", "max_retries",
            "failure_message", "primary_contact", "secondary_contacts", "fallback_protocol",
            "call_transfer_rules details",
        }
        merged["questions_or_unknowns"] = [
            q for q in merged.get("questions_or_unknowns", [])
            if q.lower().strip() not in known_field_names and len(q.strip()) > 10
        ]

        return merged


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Clara Assignment — Batch Processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/batch_processor.py
  python scripts/batch_processor.py --demo-only
  python scripts/batch_processor.py --onboarding-only
  python scripts/batch_processor.py --force
  python scripts/batch_processor.py --summary
        """,
    )
    parser.add_argument("--base-dir", default=".", help="Project root (default: current dir)")
    parser.add_argument("--demo-only",        action="store_true", help="Run Pipeline A only")
    parser.add_argument("--onboarding-only",  action="store_true", help="Run Pipeline B only")
    parser.add_argument("--force",            action="store_true", help="Reprocess even if outputs exist")
    parser.add_argument("--summary",          action="store_true", help="Print accounts table and exit")
    args = parser.parse_args()

    bp = BatchProcessor(args.base_dir)

    if args.summary:
        print(json.dumps(bp.vm.all_accounts_summary(), indent=2))
        return

    if args.demo_only:
        result = bp.run_demo_pipeline(force=args.force)
    elif args.onboarding_only:
        result = bp.run_onboarding_pipeline(force=args.force)
    else:
        result = bp.run_all(force=args.force)

    if "error" in result:
        print(f"\n❌  {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
