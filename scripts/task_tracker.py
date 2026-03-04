import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskTracker:

    def __init__(self, base_dir: str = "."):
        self.base_dir   = Path(base_dir).resolve()
        self.tasks_file = self.base_dir / "task_log.json"

        # Optional integrations — only used if keys are set in .env
        self._trello_key    = os.environ.get("TRELLO_API_KEY", "")
        self._trello_token  = os.environ.get("TRELLO_TOKEN", "")
        self._trello_list   = os.environ.get("TRELLO_LIST_ID", "")
        self._notion_key    = os.environ.get("NOTION_API_KEY", "")
        self._notion_db     = os.environ.get("NOTION_DATABASE_ID", "")

    # ─────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────

    def create_task(self, account_id: str, company_name: str,
                    task_type: str, details: Dict[str, Any] = None) -> Dict:
        """
        Create a new task entry for an account.
        task_type: 'demo_processing' or 'onboarding_update'
        Returns the created task dict.
        """
        task = {
            "task_id":      f"{account_id}_{task_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "account_id":   account_id,
            "company_name": company_name,
            "task_type":    task_type,
            "status":       "completed",
            "created_at":   datetime.now().isoformat(),
            "updated_at":   datetime.now().isoformat(),
            "details":      details or {},
        }

        # Save locally (always)
        self._save_local(task)

        # Try Trello if configured
        if self._trello_key and self._trello_token and self._trello_list:
            try:
                self._post_trello(task)
                task["trello_synced"] = True
            except Exception as e:
                task["trello_error"] = str(e)

        # Try Notion if configured
        if self._notion_key and self._notion_db:
            try:
                self._post_notion(task)
                task["notion_synced"] = True
            except Exception as e:
                task["notion_error"] = str(e)

        return task

    def get_tasks(self, account_id: str = None) -> List[Dict]:
        """Return all tasks, optionally filtered by account_id."""
        all_tasks = self._load_all()
        if account_id:
            return [t for t in all_tasks if t.get("account_id") == account_id]
        return all_tasks

    def get_summary(self) -> Dict:
        """Return summary stats of all tasks."""
        tasks = self._load_all()
        return {
            "total_tasks":       len(tasks),
            "demo_tasks":        len([t for t in tasks if t.get("task_type") == "demo_processing"]),
            "onboarding_tasks":  len([t for t in tasks if t.get("task_type") == "onboarding_update"]),
            "completed":         len([t for t in tasks if t.get("status") == "completed"]),
            "failed":            len([t for t in tasks if t.get("status") == "failed"]),
            "accounts_processed": list({t["account_id"] for t in tasks}),
            "generated_at":      datetime.now().isoformat(),
        }

    def print_summary(self) -> None:
        s = self.get_summary()
        print(f"\n  📋  Task Tracker Summary")
        print(f"  {'─'*40}")
        print(f"  Total tasks:      {s['total_tasks']}")
        print(f"  Demo tasks:       {s['demo_tasks']}")
        print(f"  Onboarding tasks: {s['onboarding_tasks']}")
        print(f"  Completed:        {s['completed']}")
        print(f"  Failed:           {s['failed']}")
        print(f"  Accounts:         {', '.join(sorted(s['accounts_processed']))}")
        print(f"  Log file:         task_log.json")
        if self._trello_key:
            print(f"  Trello:           connected")
        if self._notion_key:
            print(f"  Notion:           connected")

    # ─────────────────────────────────────────────
    # Local JSON storage
    # ─────────────────────────────────────────────

    def _load_all(self) -> List[Dict]:
        if not self.tasks_file.exists():
            return []
        try:
            with open(self.tasks_file, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return []

    def _save_local(self, task: Dict) -> None:
        tasks = self._load_all()

        # Idempotent — update if same task_id exists
        existing_ids = {t.get("task_id") for t in tasks}
        if task["task_id"] in existing_ids:
            tasks = [task if t.get("task_id") == task["task_id"] else t for t in tasks]
        else:
            tasks.append(task)

        with open(self.tasks_file, "w", encoding="utf-8") as fh:
            json.dump(tasks, fh, indent=2)

    # ─────────────────────────────────────────────
    # Trello integration (optional free tier)
    # ─────────────────────────────────────────────

    def _post_trello(self, task: Dict) -> None:
        """Post task as a Trello card. Only called if TRELLO keys are set."""
        import urllib.request
        import urllib.parse

        desc_lines = [
            f"Account ID: {task['account_id']}",
            f"Company: {task['company_name']}",
            f"Task Type: {task['task_type']}",
            f"Status: {task['status']}",
            f"Created: {task['created_at']}",
            "",
            "Details:",
        ]
        details = task.get("details", {})
        if details.get("outputs"):
            desc_lines.append("Outputs generated:")
            for k, v in details["outputs"].items():
                desc_lines.append(f"  - {k}: {v}")
        if details.get("changes"):
            desc_lines.append("Changes:")
            for c in details["changes"]:
                desc_lines.append(f"  - {c}")

        params = urllib.parse.urlencode({
            "key":    self._trello_key,
            "token":  self._trello_token,
            "idList": self._trello_list,
            "name":   f"[{task['account_id']}] {task['company_name']} — {task['task_type'].replace('_',' ').title()}",
            "desc":   "\n".join(desc_lines),
        }).encode()

        req = urllib.request.Request(
            "https://api.trello.com/1/cards",
            data=params, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            print(f"  📌  Trello card created: {result.get('shortUrl', '')}")

    # ─────────────────────────────────────────────
    # Notion integration (optional free tier)
    # ─────────────────────────────────────────────

    def _post_notion(self, task: Dict) -> None:
        """Post task as a Notion database row. Only called if NOTION keys are set."""
        import urllib.request

        payload = json.dumps({
            "parent": {"database_id": self._notion_db},
            "properties": {
                "Name": {
                    "title": [{"text": {"content": f"[{task['account_id']}] {task['company_name']} — {task['task_type']}"}}]
                },
                "Account ID":   {"rich_text": [{"text": {"content": task["account_id"]}}]},
                "Company":      {"rich_text": [{"text": {"content": task["company_name"]}}]},
                "Task Type":    {"select":    {"name": task["task_type"]}},
                "Status":       {"select":    {"name": task["status"]}},
                "Created":      {"date":      {"start": task["created_at"]}},
            }
        }).encode()

        req = urllib.request.Request(
            "https://api.notion.com/v1/pages",
            data=payload,
            headers={
                "Authorization":  f"Bearer {self._notion_key}",
                "Content-Type":   "application/json",
                "Notion-Version": "2022-06-28",
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            print(f"  📓  Notion page created: {result.get('id', '')}")


if __name__ == "__main__":
    tracker = TaskTracker(".")
    tracker.create_task(
        account_id="ACC_001",
        company_name="Ben's Electric Solutions",
        task_type="demo_processing",
        details={
            "outputs": {
                "account_memo": "outputs/accounts/ACC_001/v1/account_memo.json",
                "agent_config": "outputs/accounts/ACC_001/v1/agent_config.json",
            },
            "services_extracted": ["Residential Wiring", "Panel Upgrades"],
            "unknowns": [],
        }
    )
    tracker.print_summary()