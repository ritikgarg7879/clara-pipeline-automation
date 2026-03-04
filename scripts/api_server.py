import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, jsonify, request
from flask_cors import CORS

from scripts.transcript_processor   import TranscriptProcessor
from scripts.agent_prompt_generator import AgentPromptGenerator
from scripts.version_manager        import VersionManager
from scripts.batch_processor        import BatchProcessor

app = Flask(__name__)
CORS(app)

BASE_DIR   = Path(__file__).parent.parent
processor  = TranscriptProcessor()
generator  = AgentPromptGenerator()
vm         = VersionManager(str(BASE_DIR))
batch_proc = BatchProcessor(str(BASE_DIR))


def ok(data, message="Success"):
    return jsonify({"status": "success", "message": message, "data": data})

def err(message, code=400):
    return jsonify({"status": "error", "message": message}), code


# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

@app.route("/health")
def health():
    return ok({
        "service":   "Clara Assignment API",
        "status":    "healthy",
        "timestamp": datetime.now().isoformat(),
        "accounts":  len(vm.list_accounts()),
    })


# ─────────────────────────────────────────────
# Extraction endpoints
# ─────────────────────────────────────────────

@app.route("/extract-account-info", methods=["POST"])
def extract_account_info():
    body = request.json or {}
    transcript = body.get("transcript", "")
    account_id = body.get("account_id", "")
    if not transcript:
        return err("'transcript' field is required")
    if not account_id:
        return err("'account_id' field is required")
    try:
        info = processor.extract_account_info(transcript, account_id, "demo")
        info.pop("_method", None)
        return ok(info, f"Extracted account info for {account_id}")
    except Exception as e:
        return err(str(e), 500)


@app.route("/extract-updates", methods=["POST"])
def extract_updates():
    body = request.json or {}
    transcript = body.get("transcript", "")
    account_id = body.get("account_id", "")
    if not transcript:
        return err("'transcript' field is required")
    if not account_id:
        return err("'account_id' field is required")
    try:
        updates = processor.extract_updates(transcript, account_id)
        updates.pop("_method", None)
        return ok(updates, f"Extracted onboarding updates for {account_id}")
    except Exception as e:
        return err(str(e), 500)


# ─────────────────────────────────────────────
# Config generation endpoints
# ─────────────────────────────────────────────

@app.route("/generate-agent-config", methods=["POST"])
def generate_agent_config():
    body = request.json or {}
    account_info = body.get("account_info", {})
    account_id   = body.get("account_id", account_info.get("account_id", ""))
    version      = body.get("version", "v1")
    if not account_info:
        return err("'account_info' object is required")
    if not account_id:
        return err("'account_id' is required")
    try:
        config = generator.generate_agent_config(account_info, version)
        vm.save_version(account_id, account_info, "account_memo", version)
        vm.save_version(account_id, config,       "agent_config",  version)
        return ok({
            "account_id":   account_id,
            "version":      version,
            "agent_config": config,
            "outputs": {
                "account_memo": f"outputs/accounts/{account_id}/{version}/account_memo.json",
                "agent_config": f"outputs/accounts/{account_id}/{version}/agent_config.json",
            }
        }, f"Generated agent config {version} for {account_id}")
    except Exception as e:
        return err(str(e), 500)


@app.route("/update-agent-config", methods=["POST"])
def update_agent_config():
    body       = request.json or {}
    account_id = body.get("account_id", "")
    updates    = body.get("updates", {})
    version    = body.get("version", "v2")
    if not account_id:
        return err("'account_id' is required")
    if not updates:
        return err("'updates' object is required")

    v1_memo  = vm.load_version(account_id, "v1", "account_memo")
    v1_agent = vm.load_version(account_id, "v1", "agent_config")
    if v1_memo is None:
        return err(f"No v1 account_memo for {account_id}. Run generate-agent-config first.", 404)
    if v1_agent is None:
        return err(f"No v1 agent_config for {account_id}. Run generate-agent-config first.", 404)

    try:
        v2_memo = batch_proc._merge(v1_memo, updates)
        v2_memo["version"]      = version
        v2_memo["last_updated"] = datetime.now().isoformat()
        v2_agent = generator.update_agent_config(v1_agent, v2_memo, version)
        vm.save_version(account_id, v2_memo,  "account_memo", version)
        vm.save_version(account_id, v2_agent, "agent_config",  version)
        diff    = vm.compare_versions(account_id, "v1", version, "account_memo")
        changes = diff.get("changes_summary", [])
        vm.record_changelog(account_id, "v1", version, "account_memo", changes)
        vm.write_diff_report(account_id, "v1", version)
        return ok({
            "account_id":   account_id,
            "version":      version,
            "changes":      changes,
            "agent_config": v2_agent,
        }, f"Updated agent config to {version} for {account_id}")
    except Exception as e:
        return err(str(e), 500)


# ─────────────────────────────────────────────
# Account data endpoints
# ─────────────────────────────────────────────

@app.route("/accounts")
def list_accounts():
    return ok(vm.all_accounts_summary())


@app.route("/accounts/<account_id>")
def get_account(account_id):
    history = vm.account_history(account_id)
    if not history["versions"]:
        return err(f"Account {account_id} not found", 404)
    return ok(history)


@app.route("/accounts/<account_id>/<version>/memo")
def get_memo(account_id, version):
    data = vm.load_version(account_id, version, "account_memo")
    if data is None:
        return err(f"No account_memo for {account_id}/{version}", 404)
    return ok(data)


@app.route("/accounts/<account_id>/<version>/agent")
def get_agent(account_id, version):
    data = vm.load_version(account_id, version, "agent_config")
    if data is None:
        return err(f"No agent_config for {account_id}/{version}", 404)
    return ok(data)


@app.route("/accounts/<account_id>/diff/<v1>/<v2>")
def get_diff(account_id, v1, v2):
    diff = vm.compare_versions(account_id, v1, v2, "account_memo")
    if "error" in diff:
        return err(diff["error"], 404)
    return ok(diff)


# ─────────────────────────────────────────────
# Batch endpoint
# ─────────────────────────────────────────────

@app.route("/batch/run-all", methods=["POST"])
def run_batch():
    body  = request.json or {}
    force = body.get("force", False)
    try:
        result = batch_proc.run_all(force=force)
        return ok(result, "Batch processing complete")
    except Exception as e:
        return err(str(e), 500)


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────

if __name__ == "__main__":
    port = int(json.loads(Path(BASE_DIR / ".env").read_text().split("API_PORT=")[1].split("\n")[0])
               if (BASE_DIR / ".env").exists() and "API_PORT=" in (BASE_DIR / ".env").read_text()
               else 8000)
    print(f"\n🚀  Clara API Server starting on http://localhost:{port}")
    print(f"    Health check: http://localhost:{port}/health")
    print(f"    Accounts:     http://localhost:{port}/accounts\n")
    app.run(host="0.0.0.0", port=port, debug=True)














