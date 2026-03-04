import difflib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class VersionManager:

    def __init__(self, base_dir: str):
        self.base_dir      = Path(base_dir).resolve()
        self.accounts_dir  = self.base_dir / "outputs" / "accounts"
        self.changelog_dir = self.base_dir / "changelog"
        self.accounts_dir.mkdir(parents=True, exist_ok=True)
        self.changelog_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────
    # Core CRUD
    # ─────────────────────────────────────────────

    def save_version(self, account_id: str, data: Dict[str, Any],
                     data_type: str, version: str) -> str:
        """
        Save to outputs/accounts/<account_id>/<version>/<data_type>.json
        Returns path string.
        data_type: 'account_memo' or 'agent_config'
        """
        dest = self.accounts_dir / account_id / version
        dest.mkdir(parents=True, exist_ok=True)
        filepath = dest / f"{data_type}.json"
        payload = dict(data)
        payload["version"]      = version
        payload["last_updated"] = datetime.now().isoformat()
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        return str(filepath)

    def load_version(self, account_id: str, version: str,
                     data_type: str) -> Optional[Dict[str, Any]]:
        filepath = self.accounts_dir / account_id / version / f"{data_type}.json"
        if not filepath.exists():
            return None
        with open(filepath, encoding="utf-8") as fh:
            return json.load(fh)

    def version_exists(self, account_id: str, version: str, data_type: str) -> bool:
        return (self.accounts_dir / account_id / version / f"{data_type}.json").exists()

    def list_versions(self, account_id: str) -> List[str]:
        d = self.accounts_dir / account_id
        if not d.exists():
            return []
        vs = [x.name for x in d.iterdir() if x.is_dir() and x.name.startswith("v")]
        vs.sort(key=lambda x: int(x[1:]))
        return vs

    def list_accounts(self) -> List[str]:
        if not self.accounts_dir.exists():
            return []
        return sorted(d.name for d in self.accounts_dir.iterdir() if d.is_dir())

    # ─────────────────────────────────────────────
    # Diff & Changelog
    # ─────────────────────────────────────────────

    def compare_versions(self, account_id: str, v1: str, v2: str,
                         data_type: str) -> Dict[str, Any]:
        old = self.load_version(account_id, v1, data_type)
        new = self.load_version(account_id, v2, data_type)
        if old is None:
            return {"error": f"Version {v1} not found for {account_id}/{data_type}"}
        if new is None:
            return {"error": f"Version {v2} not found for {account_id}/{data_type}"}

        old_txt = json.dumps(old, indent=2, sort_keys=True)
        new_txt = json.dumps(new, indent=2, sort_keys=True)
        diff = "".join(difflib.unified_diff(
            old_txt.splitlines(keepends=True),
            new_txt.splitlines(keepends=True),
            fromfile=f"{data_type}_{v1}.json",
            tofile=f"{data_type}_{v2}.json",
        ))
        return {
            "account_id":      account_id,
            "data_type":       data_type,
            "from_version":    v1,
            "to_version":      v2,
            "changes_summary": self._summarise(old, new, data_type),
            "diff":            diff,
            "compared_at":     datetime.now().isoformat(),
        }

    @staticmethod
    def _summarise(old: Dict, new: Dict, data_type: str) -> List[str]:
        if data_type != "account_memo":
            return ["Agent configuration updated"] if old != new else []
        changes = []
        checks = [
            ("company_name",               "Company name"),
            ("office_address",             "Office address"),
            ("business_hours",             "Business hours"),
            ("services_supported",         "Services"),
            ("emergency_definition",       "Emergency definition"),
            ("emergency_routing_rules",    "Emergency routing"),
            ("non_emergency_routing_rules","Non-emergency routing"),
            ("integration_constraints",    "Integration constraints"),
        ]
        for field, label in checks:
            ov, nv = old.get(field), new.get(field)
            if ov == nv:
                continue
            if isinstance(ov, list) and isinstance(nv, list):
                added   = [x for x in nv if x not in ov]
                removed = [x for x in ov if x not in nv]
                if added:
                    changes.append(f"Added to {label}: {', '.join(str(x) for x in added)}")
                if removed:
                    changes.append(f"Removed from {label}: {', '.join(str(x) for x in removed)}")
            elif isinstance(ov, dict) and isinstance(nv, dict):
                if ov != nv:
                    changes.append(f"Updated {label}")
            else:
                if nv and not ov:
                    changes.append(f"Set {label} to '{nv}'")
                elif ov and nv and ov != nv:
                    changes.append(f"Changed {label} from '{ov}' to '{nv}'")
        return changes or ["No significant field changes detected"]

    def record_changelog(self, account_id: str, from_v: str, to_v: str,
                         data_type: str, changes: List[str]) -> str:
        """Append entry. IDEMPOTENT — same from→to pair never written twice."""
        cl_file = self.changelog_dir / f"{account_id}_changelog.json"
        log = json.load(open(cl_file, encoding="utf-8")) if cl_file.exists() else []

        existing = {(e.get("from_version"), e.get("to_version"), e.get("data_type")) for e in log}
        if (from_v, to_v, data_type) in existing:
            return str(cl_file)   # already recorded — skip

        log.append({
            "account_id":   account_id,
            "data_type":    data_type,
            "from_version": from_v,
            "to_version":   to_v,
            "changes":      changes,
            "timestamp":    datetime.now().isoformat(),
        })
        with open(cl_file, "w", encoding="utf-8") as fh:
            json.dump(log, fh, indent=2)
        return str(cl_file)

    def write_diff_report(self, account_id: str, v1: str, v2: str) -> str:
        lines = [
            "# Version Diff Report",
            f"**Account:** {account_id}",
            f"**Comparing:** {v1} → {v2}",
            f"**Generated:** {datetime.now().isoformat()}",
            "",
        ]
        for dtype in ["account_memo", "agent_config"]:
            diff = self.compare_versions(account_id, v1, v2, dtype)
            if "error" in diff:
                continue
            lines += [f"## {dtype.replace('_',' ').title()}", ""]
            for c in diff["changes_summary"]:
                lines.append(f"- {c}")
            lines += ["", "```diff", diff["diff"] or "(no diff)", "```", ""]
        report_path = self.changelog_dir / f"{account_id}_{v1}_to_{v2}_diff.md"
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        return str(report_path)

    # ─────────────────────────────────────────────
    # Summaries
    # ─────────────────────────────────────────────

    def account_history(self, account_id: str) -> Dict[str, Any]:
        versions = self.list_versions(account_id)
        history: Dict[str, Any] = {"account_id": account_id, "versions": [], "changelog": []}
        for v in versions:
            memo  = self.load_version(account_id, v, "account_memo")
            agent = self.load_version(account_id, v, "agent_config")
            entry = {"version": v, "has_account_memo": memo is not None, "has_agent_config": agent is not None}
            if memo:
                entry["company_name"] = memo.get("company_name", "")
                entry["last_updated"] = memo.get("last_updated", "")
            history["versions"].append(entry)
        cl_file = self.changelog_dir / f"{account_id}_changelog.json"
        if cl_file.exists():
            history["changelog"] = json.load(open(cl_file))
        return history

    def all_accounts_summary(self) -> Dict[str, Any]:
        accounts = self.list_accounts()
        summary: Dict[str, Any] = {"total_accounts": len(accounts), "accounts": {}, "generated_at": datetime.now().isoformat()}
        for aid in accounts:
            versions = self.list_versions(aid)
            latest   = self.load_version(aid, versions[-1], "account_memo") if versions else None
            summary["accounts"][aid] = {
                "versions":       versions,
                "latest_version": versions[-1] if versions else None,
                "company_name":   latest.get("company_name", "") if latest else "",
                "version_count":  len(versions),
            }
        return summary


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        vm = VersionManager(td)
        vm.save_version("ACC_T", {"account_id":"ACC_T","company_name":"Test Co"}, "account_memo", "v1")
        vm.save_version("ACC_T", {"account_id":"ACC_T","company_name":"Test Co v2"}, "account_memo", "v2")
        diff = vm.compare_versions("ACC_T","v1","v2","account_memo")
        print("Changes:", diff["changes_summary"])
        vm.record_changelog("ACC_T","v1","v2","account_memo",diff["changes_summary"])
        vm.record_changelog("ACC_T","v1","v2","account_memo",diff["changes_summary"])  # idempotent
        import json as _j
        log = _j.load(open(str(Path(td)/"changelog"/"ACC_T_changelog.json")))
        print(f"Changelog entries (expect 1): {len(log)} — {'PASS' if len(log)==1 else 'FAIL'}")














