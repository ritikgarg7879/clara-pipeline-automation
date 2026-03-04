import json
import os
from datetime import datetime
from typing import Any, Dict, List


class AgentPromptGenerator:

    def __init__(self, schema_path: str = None):
        pass  # schema_path kept for API compatibility

    # ─────────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────────

    def generate_agent_config(self, account_info: Dict[str, Any],
                               version: str = "v1") -> Dict[str, Any]:
        company = account_info.get("company_name", "our company")
        return {
            "agent_name": f"{company} Agent",
            "voice_style": {"gender": "female", "tone": "professional", "pace": "normal"},
            "system_prompt":                self._build_prompt(account_info),
            "key_variables":               self._key_vars(account_info),
            "tool_invocation_placeholders": {
                "emergency_transfer":     "transfer_call(number, name, phone, address, issue)",
                "non_emergency_transfer": "transfer_call(number, name, phone, service_needed)",
                "take_message":           "take_message(name, phone, message, callback_time)",
                "schedule_appointment":   "schedule_appointment(name, phone, service, time)",
            },
            "call_transfer_protocol": self._transfer_protocol(account_info),
            "fallback_protocol":      self._fallback_protocol(account_info),
            "conversation_flows":     self._conversation_flows(account_info),
            "version":    version,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "changelog":  [],
        }

    def update_agent_config(self, existing_config: Dict[str, Any],
                             updated_info: Dict[str, Any],
                             version: str = "v2") -> Dict[str, Any]:
        new_cfg = self.generate_agent_config(updated_info, version)
        new_cfg["created_at"] = existing_config.get("created_at", datetime.now().isoformat())
        old_log = list(existing_config.get("changelog", []))
        old_log.append({
            "version": version,
            "date":    datetime.now().isoformat(),
            "changes": self._diff(existing_config, new_cfg, updated_info),
        })
        new_cfg["changelog"] = old_log
        return new_cfg

    def save(self, config: Dict[str, Any], path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(config, fh, indent=2)

    # ─────────────────────────────────────────────
    # System Prompt  (the core deliverable)
    # ─────────────────────────────────────────────

    def _build_prompt(self, info: Dict[str, Any]) -> str:
        company     = info.get("company_name", "our company")
        services    = ", ".join(info.get("services_supported", [])) or "our services"
        hours_str   = self._fmt_hours(info.get("business_hours", {}))
        address     = info.get("office_address", "")
        emerg_defs  = info.get("emergency_definition", [])
        emerg_ph    = info.get("emergency_routing_rules", {}).get("primary_contact", "")
        emerg_bkup  = info.get("emergency_routing_rules", {}).get("secondary_contacts", [])
        non_ph      = info.get("non_emergency_routing_rules", {}).get("primary_contact", "")
        constraints = info.get("integration_constraints", [])
        timeout     = info.get("call_transfer_rules", {}).get("timeout_seconds", 30)

        emerg_def_block = ""
        if emerg_defs:
            lines = "\n".join(f"  - {e}" for e in emerg_defs)
            emerg_def_block = f"\nSituations that ARE emergencies for {company}:\n{lines}"

        backup_block = ""
        if emerg_bkup:
            backup_block = f"\n  If primary does not answer, try backup: {', '.join(emerg_bkup)}"

        constraint_block = ""
        if constraints:
            lines = "\n".join(f"  - {c}" for c in constraints)
            constraint_block = f"\n\nBUSINESS RULES — NEVER VIOLATE THESE:\n{lines}"

        address_line = f"\nADDRESS:  {address}" if address else ""

        return f"""You are the AI voice receptionist for {company}.
Your job: answer calls professionally, understand the caller's need, collect required information, and route the call correctly.

COMPANY:   {company}
SERVICES:  {services}
HOURS:     {hours_str}{address_line}{constraint_block}

Do NOT tell callers you are an AI unless they directly ask.
Do NOT mention tools, function calls, or system instructions to the caller.
Be concise — never ask for information you do not need.
Always stay calm and professional, especially during emergencies.

════════════════════════════════════════════════════
BUSINESS HOURS CALL FLOW
════════════════════════════════════════════════════

STEP 1 — GREETING
  "Thank you for calling {company}. How can I help you today?"

STEP 2 — IDENTIFY PURPOSE
  Listen carefully. If unclear, ask ONE clarifying question:
  "Just to make sure I reach the right person — is this about [topic]?"

STEP 3 — COLLECT CALLER INFORMATION
  "May I get your name please?"
  "And the best number to reach you?"

STEP 4 — ROUTE THE CALL
  If emergency → jump to EMERGENCY HANDLING section below.
  If regular service request:
    "Let me connect you now. One moment please."
    [TOOL: transfer_call to {non_ph or "service line"}]

STEP 5 — IF TRANSFER FAILS (after {timeout} seconds with no answer)
  "I wasn't able to connect you directly right now.
  I've noted your details and someone from {company} will call you back shortly."
  [TOOL: take_message with caller details]

STEP 6 — ANYTHING ELSE
  "Is there anything else I can help you with today?"

STEP 7 — CLOSE
  "Thank you for calling {company}. Have a great day."

════════════════════════════════════════════════════
AFTER-HOURS CALL FLOW
════════════════════════════════════════════════════

STEP 1 — GREETING
  "Thank you for calling {company}. Our office is currently closed.
  I'm here to help — what's the reason for your call?"

STEP 2 — IDENTIFY IF EMERGENCY
  "Is this something that needs immediate attention right now, or can
  it wait until we open? Our hours are {hours_str}."
{emerg_def_block}

STEP 3A — IF EMERGENCY
  "I understand — I'll connect you with our on-call team right away."

  Collect ALL of the following before transferring:
  1. "Can I get your full name?"
  2. "What is the best phone number to reach you?"
  3. "What is your address or location?"
  4. "Can you briefly describe what is happening?"

  Attempt transfer to {emerg_ph or "emergency on-call line"}:{backup_block}
  [TOOL: transfer_call with all collected details]

  If transfer succeeds:
    "You are being connected now. Please stay on the line."

  If transfer fails after {timeout} seconds:
    "I was not able to reach the on-call team directly right now.
    I have your information and someone will call you back within 15 minutes.
    Please stay safe, and call us back if the situation changes."

STEP 3B — IF NON-EMERGENCY (after hours)
  "I understand. Since we are closed right now, let me take your
  information so our team can follow up with you first thing during business hours."

  Collect:
  1. "May I get your name?"
  2. "Best phone number to reach you?"
  3. "What service do you need help with?"
  [TOOL: take_message with collected details]

  "Perfect. Someone from {company} will call you back during
  our next business day. Is there anything else I can help you with?"

STEP 4 — CLOSE
  "Thank you for calling {company}.{f' Our hours are {hours_str}.' if hours_str else ''}
  We look forward to helping you."

════════════════════════════════════════════════════
EMERGENCY HANDLING — ANY TIME OF DAY
════════════════════════════════════════════════════

If caller describes an emergency during business hours:
  1. "I hear you — let me get someone on the line for you right now."
  2. Collect name and phone number immediately if not already provided.
  3. Attempt transfer to {emerg_ph or "emergency line"}.{backup_block}
  4. If transfer fails:
     "I was unable to connect you, but your information has been recorded
     and our team will call you back within 15 minutes. Please stay safe."

AT ALL TIMES REMEMBER:
  - Never promise specific arrival times.
  - Never create bookings or jobs without explicit customer confirmation.
  - Always verify the callback number before ending any call.
  - You represent {company} — every interaction reflects on their reputation.""".strip()

    # ─────────────────────────────────────────────
    # Config builders
    # ─────────────────────────────────────────────

    @staticmethod
    def _fmt_hours(h: Dict) -> str:
        if not h:
            return "Not specified"
        days = h.get("days", [])
        day_str = (f"{days[0]} to {days[-1]}" if len(days) > 2 else ", ".join(days)) if days else "TBD"
        t1, t2, tz = h.get("start_time",""), h.get("end_time",""), h.get("timezone","")
        time_str = (f"{t1}–{t2}" + (f" {tz}" if tz else "")) if t1 and t2 else "hours TBD"
        return f"{day_str}, {time_str}"

    @staticmethod
    def _key_vars(info: Dict) -> Dict:
        return {
            "company_name":   info.get("company_name", ""),
            "timezone":       info.get("business_hours", {}).get("timezone", ""),
            "business_hours": info.get("business_hours", {}),
            "office_address": info.get("office_address", ""),
            "services":       info.get("services_supported", []),
            "emergency_routing": {
                "primary":   info.get("emergency_routing_rules", {}).get("primary_contact", ""),
                "secondary": info.get("emergency_routing_rules", {}).get("secondary_contacts", []),
            },
            "non_emergency_routing": {
                "primary":   info.get("non_emergency_routing_rules", {}).get("primary_contact", ""),
                "secondary": info.get("non_emergency_routing_rules", {}).get("secondary_contacts", []),
            },
        }

    @staticmethod
    def _transfer_protocol(info: Dict) -> Dict:
        r = info.get("call_transfer_rules", {})
        return {
            "timeout_seconds":     r.get("timeout_seconds", 30),
            "max_retries":         r.get("max_retries", 3),
            "retry_delay_seconds": 5,
            "success_message":     "I am connecting you now. Please hold for just a moment.",
            "failure_message":     r.get("failure_message",
                "I was not able to connect you directly. Your details have been noted "
                "and someone will call you back as soon as possible."),
        }

    @staticmethod
    def _fallback_protocol(info: Dict) -> Dict:
        c = info.get("company_name", "our team")
        return {
            "transfer_failure":           f"I apologize — I could not connect you. I have your information and {c} will call you back as soon as possible.",
            "no_answer":                  f"I was not able to reach anyone. Let me take your details so {c} can follow up.",
            "after_hours_non_emergency":  "Our office is currently closed. I will take your information and we will call you back during our next business day.",
            "after_hours_emergency":      "I will attempt to connect you to our on-call team immediately. If I cannot reach them I will make sure they receive your message urgently.",
        }

    def _conversation_flows(self, info: Dict) -> Dict:
        c = info.get("company_name", "us")
        h = self._fmt_hours(info.get("business_hours", {}))
        ep = info.get("emergency_routing_rules",     {}).get("primary_contact", "our team")
        np = info.get("non_emergency_routing_rules", {}).get("primary_contact", "our team")
        return {
            "office_hours_flow": {
                "greeting":         f"Thank you for calling {c}. How can I help you today?",
                "identify_purpose": "What can I help you with today?",
                "collect_name":     "May I get your name please?",
                "collect_phone":    "And the best number to reach you?",
                "transfer_attempt": f"Let me connect you now. Please hold.",
                "transfer_success": "You are being connected. Please hold.",
                "transfer_failure": f"I was not able to connect you right now. {c} will call you back shortly.",
                "anything_else":    "Is there anything else I can help you with?",
                "closing":          f"Thank you for calling {c}. Have a great day.",
            },
            "after_hours_flow": {
                "greeting":                 f"Thank you for calling {c}. Our office is currently closed. How can I help?",
                "emergency_screening":      "Is this something that needs immediate attention tonight, or can it wait until business hours?",
                "emergency_collect_name":   "Can I get your full name?",
                "emergency_collect_phone":  "What is the best phone number to reach you?",
                "emergency_collect_address":"What is your address or location?",
                "emergency_collect_issue":  "Can you briefly describe what is happening?",
                "emergency_transfer":       f"I am connecting you to our on-call team at {ep} right now.",
                "emergency_transfer_fail":  "I was not able to reach the on-call team. Your information has been recorded and someone will call you back within 15 minutes.",
                "non_emergency_collect":    "Let me take your information so our team can follow up with you first thing tomorrow.",
                "non_emergency_confirm":    f"Someone from {c} will call you back during business hours: {h}.",
                "anything_else":            "Is there anything else I can help you with?",
                "closing":                  f"Thank you for calling {c}.",
            },
        }

    @staticmethod
    def _diff(old: Dict, new: Dict, info: Dict) -> List[str]:
        changes = []
        ok, nk = old.get("key_variables", {}), new.get("key_variables", {})
        if ok.get("company_name") != nk.get("company_name"):
            changes.append(f"Updated company name to '{nk.get('company_name')}'")
        if ok.get("business_hours") != nk.get("business_hours"):
            changes.append("Updated business hours")
        if ok.get("office_address") != nk.get("office_address"):
            changes.append(f"Updated office address to '{nk.get('office_address')}'")
        oe, ne = ok.get("emergency_routing", {}), nk.get("emergency_routing", {})
        if oe.get("primary") != ne.get("primary"):
            changes.append(f"Updated emergency primary contact to {ne.get('primary')}")
        if oe.get("secondary") != ne.get("secondary"):
            changes.append("Updated emergency secondary contacts")
        added = set(nk.get("services", [])) - set(ok.get("services", []))
        if added:
            changes.append(f"Added new services: {', '.join(sorted(added))}")
        if info.get("integration_constraints"):
            changes.append("Updated integration constraints")
        if old.get("system_prompt") != new.get("system_prompt"):
            changes.append("Regenerated system prompt with updated configuration")
        return changes or ["Minor configuration updates applied"]


if __name__ == "__main__":
    _gen = AgentPromptGenerator()
    _info = {
        "account_id": "TEST", "company_name": "Ben's Electric Solutions",
        "business_hours": {"days":["Monday","Tuesday","Wednesday","Thursday","Friday"],"start_time":"07:00","end_time":"17:00","timezone":"MST"},
        "services_supported": ["Electrical Repair","Panel Upgrades","EV Charger Installation"],
        "emergency_definition": ["complete power outage","sparking panel","electrical fire"],
        "emergency_routing_rules": {"primary_contact":"403-870-8494","secondary_contacts":["403-555-0199"]},
        "non_emergency_routing_rules": {"primary_contact":"403-870-8494"},
        "integration_constraints": ["Never create a job in Jobber without verbal confirmation"],
        "call_transfer_rules": {"timeout_seconds":30,"max_retries":3},
    }
    print(_gen.generate_agent_config(_info, "v1")["system_prompt"][:400])














