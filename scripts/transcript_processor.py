import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────
# Groq API  (primary path)
# ─────────────────────────────────────────────────────────────

def _groq_extract(transcript: str, account_id: str, call_type: str) -> Optional[Dict]:
    """Use Groq API for fast accurate extraction. Falls back to rules if key not set."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return None
    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        system = (
            "You are a data extraction assistant for a voice AI platform. "
            "Extract structured information from the call transcript. "
            "Return ONLY valid JSON — no markdown fences, no explanation. "
            "Never invent data not explicitly stated. "
            "Use empty string or empty array for missing fields. "
            "Put genuinely unclear or absent fields in questions_or_unknowns."
        )

        if call_type == "demo":
            user = f"""Extract ALL account information from this demo call transcript.

TRANSCRIPT:
{transcript}

Return exactly this JSON (fill every field you can find):
{{
  "account_id": "{account_id}",
  "company_name": "exact company name as stated",
  "business_hours": {{
    "days": ["Monday","Tuesday",...],
    "start_time": "HH:MM",
    "end_time": "HH:MM",
    "timezone": "MST / PST / EST / CST"
  }},
  "office_address": "full address if mentioned",
  "services_supported": ["service1","service2"],
  "emergency_definition": ["trigger1","trigger2"],
  "emergency_routing_rules": {{
    "primary_contact": "phone number",
    "secondary_contacts": [],
    "fallback_protocol": "what happens if no answer"
  }},
  "non_emergency_routing_rules": {{
    "primary_contact": "phone number",
    "secondary_contacts": [],
    "message_protocol": "how messages are handled"
  }},
  "call_transfer_rules": {{
    "timeout_seconds": 30,
    "max_retries": 3,
    "failure_message": "what to say if transfer fails"
  }},
  "integration_constraints": ["constraint1","constraint2"],
  "after_hours_flow_summary": "brief description",
  "office_hours_flow_summary": "brief description",
  "questions_or_unknowns": ["anything missing or unclear"],
  "notes": "one-line extraction note"
}}"""
        else:
            user = f"""Extract ONLY the NEW or UPDATED information from this onboarding call.
Do NOT include fields that were not mentioned or changed.

TRANSCRIPT:
{transcript}

Return a JSON object with only updated/new fields:
{{
  "account_id": "{account_id}",
  "company_name": "only if changed",
  "business_hours": {{"only if confirmed or updated"}},
  "office_address": "only if confirmed or updated",
  "services_supported": ["ONLY NEW services to add"],
  "emergency_definition": ["only if updated"],
  "emergency_routing_rules": {{"only if contacts changed"}},
  "non_emergency_routing_rules": {{"only if changed"}},
  "call_transfer_rules": {{"only if changed"}},
  "integration_constraints": ["ONLY NEW constraints to add"],
  "after_hours_flow_summary": "only if clarified",
  "office_hours_flow_summary": "only if clarified",
  "questions_or_unknowns": []
}}"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",   # fast + accurate, free tier available
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0,        # deterministic outputs
            max_tokens=2000,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"^```\s*",     "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```$",        "", raw)
        data = json.loads(raw.strip())
        data["_method"] = "groq_api"
        return data

    except Exception as exc:
        print(f"  [INFO] Groq API unavailable ({type(exc).__name__}: {exc}). Using rule-based fallback.")
        return None


# ─────────────────────────────────────────────────────────────
# Rule-based extraction  (fallback — zero cost, no API needed)
# ─────────────────────────────────────────────────────────────

class _RuleExtractor:
    """
    Every regex is SCOPED to the relevant sentence only.
    'Sunday' in a constraint sentence never pollutes business-hours extraction.
    """

    _DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    _DAY_ABBR = {
        "mon":"Monday","tue":"Tuesday","wed":"Wednesday",
        "thu":"Thursday","fri":"Friday","sat":"Saturday","sun":"Sunday",
    }
    _TZ = {
        "MST":"MST","MDT":"MDT","PST":"PST","PDT":"PDT",
        "EST":"EST","EDT":"EDT","CST":"CST","CDT":"CDT",
        "MT":"MST","PT":"PST","ET":"EST","CT":"CST",
    }

    @staticmethod
    def _sentences(text: str) -> List[str]:
        return [s.strip() for s in re.split(r"(?<!\d)\.\s+|\n", text) if s.strip()]

    @staticmethod
    def _phone(text: str) -> str:
        for pat in [
            r"\d{3}[-.\s]\d{3}[-.\s]\d{4,6}",
            r"\d{3}[-.\s]\d{6,7}",
            r"\d{10,12}",
        ]:
            m = re.search(pat, text)
            if m:
                return m.group(0).strip()
        return ""

    def _company(self, text: str) -> str:
        patterns = [
            r"(?:calling|call)\s+from\s+([A-Z][A-Za-z0-9\s&'.\-]+?)(?:\.|,|\n|$)",
            r"this is ([A-Z][A-Za-z0-9\s&'.\-]+?)[,.]",
            r"from ([A-Z][A-Za-z0-9\s&'.\-]+?),\s+(?:a|an|we)",
            r"I'm ([A-Z][A-Za-z0-9\s&'.\-]+?),\s+I",
        ]
        skip = {"a","an","the","our","your","this","that","hi","hello"}
        for pat in patterns:
            m = re.search(pat, text, re.MULTILINE)
            if m:
                name = m.group(1).strip().rstrip(".,")
                words = name.split()
                if 2 <= len(words) <= 7 and words[0].lower() not in skip:
                    return name
        return ""

    def _hours(self, text: str) -> Dict:
        h: Dict[str, Any] = {"days":[],"start_time":"","end_time":"","timezone":""}
        sents = [s for s in self._sentences(text)
                 if re.search(r"business hours|hours are|we operate|open from|monday to|monday through|mon.*fri", s, re.I)]
        if not sents:
            return h
        src = " ".join(sents)

        rng = re.search(
            r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
            r"\s*(?:to|through|and|-)\s*"
            r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)",
            src, re.I,
        )
        if rng:
            d1 = self._DAY_ABBR.get(rng.group(1)[:3].lower(), rng.group(1).title())
            d2 = self._DAY_ABBR.get(rng.group(2)[:3].lower(), rng.group(2).title())
            try:
                i1, i2 = self._DAYS.index(d1), self._DAYS.index(d2)
                h["days"] = self._DAYS[i1:i2+1]
            except ValueError:
                h["days"] = [d1, d2]
        else:
            h["days"] = [d for d in self._DAYS if re.search(r"\b"+d[:3]+r"\w*\b", src, re.I)]

        tm = re.search(
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*(?:to|-)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
            src, re.I,
        )
        if tm:
            h["start_time"] = self._norm_time(tm.group(1))
            h["end_time"]   = self._norm_time(tm.group(2))

        for src2 in [src, text]:
            tz = re.search(r"\b(MST|MDT|PST|PDT|EST|EDT|CST|CDT|MT|PT|ET|CT)\b", src2)
            if tz:
                h["timezone"] = self._TZ.get(tz.group(1), tz.group(1))
                break
        return h

    @staticmethod
    def _norm_time(s: str) -> str:
        s = s.strip().upper()
        pm, am = "PM" in s, "AM" in s
        s = s.replace("PM","").replace("AM","").strip()
        parts = s.split(":")
        hh = int(parts[0].strip())
        mm = parts[1].strip() if len(parts) > 1 else "00"
        if pm and hh != 12: hh += 12
        if am and hh == 12: hh = 0
        return f"{hh:02d}:{mm}"

    def _address(self, text: str) -> str:
        for s in self._sentences(text):
            if re.search(r"located at|address is|office at|based at|out of", s, re.I):
                m = re.search(r"(?:located at|address is|office at|based at|out of)\s+([^.\n]+)", s, re.I)
                if m:
                    addr = m.group(1).strip().rstrip(".,")
                    if 5 < len(addr) < 120:
                        return addr
        m = re.search(r"\d{3,5}\s+[A-Z][a-zA-Z\s]+(?:Street|Ave|Avenue|Road|Blvd|Lane|Drive|Dr|Way|Court|Ct|SW|SE|NW|NE)[^.\n]*", text)
        return m.group(0).strip().rstrip(".,") if m else ""

    def _services(self, text: str) -> List[str]:
        for s in self._sentences(text):
            if re.search(r"we offer|we provide|services include|services are|we handle|services now include", s, re.I):
                m = re.search(r"(?:we offer|we provide|services(?:\s+now)?\s+include|services are|we handle)\s+(.+)", s, re.I)
                if m:
                    raw = m.group(1).rstrip(".")
                    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", raw)
                    return [p.strip().rstrip(".,") for p in parts if 2 < len(p.strip()) < 60]
        return []

    def _emerg_def(self, text: str) -> List[str]:
        results = []
        for s in self._sentences(text):
            if re.search(r"emergenc(?:y|ies)\s+(?:for us|are|include|like|such as|definition)", s, re.I):
                m = re.search(
                    r"emergenc(?:y|ies)\s+(?:for us\s+)?(?:are|include|like|such as|definition\s*(?:is)?|means?)\s*[:\-]?\s*(.+)",
                    s, re.I,
                )
                if m:
                    for p in re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(1)):
                        p = p.strip().rstrip(".,")
                        if 3 < len(p) < 100:
                            results.append(p)
        return list(dict.fromkeys(results))

    def _emerg_routing(self, text: str) -> Dict:
        r: Dict[str, Any] = {"primary_contact":"","secondary_contacts":[],"fallback_protocol":""}
        for s in self._sentences(text):
            if re.search(r"emergenc", s, re.I):
                ph = self._phone(s)
                if ph:
                    if not r["primary_contact"]:
                        r["primary_contact"] = ph
                    elif ph != r["primary_contact"] and ph not in r["secondary_contacts"]:
                        r["secondary_contacts"].append(ph)
        for s in self._sentences(text):
            if re.search(r"if no (?:one )?answer|transfer fails|callback within|call back within", s, re.I):
                r["fallback_protocol"] = s.rstrip(".")
                break
        return r

    def _non_emerg_routing(self, text: str) -> Dict:
        r: Dict[str, Any] = {"primary_contact":"","secondary_contacts":[],"message_protocol":""}
        emerg_ph = self._emerg_routing(text)["primary_contact"]
        for s in self._sentences(text):
            if re.search(r"regular|business hours|service call|non.emergency", s, re.I):
                ph = self._phone(s)
                if ph and ph != emerg_ph and not r["primary_contact"]:
                    r["primary_contact"] = ph
        for s in self._sentences(text):
            if re.search(r"take a message|leave a message|call back|voicemail", s, re.I):
                r["message_protocol"] = s.rstrip(".")
                break
        return r

    @staticmethod
    def _transfer_rules(_text: str) -> Dict:
        return {
            "timeout_seconds": 30,
            "max_retries": 3,
            "failure_message": "I'm unable to connect you right now, but I'll make sure someone gets your message and calls you back as soon as possible.",
        }

    def _constraints(self, text: str) -> List[str]:
        skip = ["promise you can't keep","make promises","guessing","confirm understanding"]
        results = []
        for s in self._sentences(text):
            if re.search(r"\b(?:never|do not|don't|always|must not|require|no same.day)\b", s, re.I):
                s = s.strip().rstrip(".")
                if 10 < len(s) < 200 and not any(x in s.lower() for x in skip):
                    results.append(s)
        return list(dict.fromkeys(results))

    def _after_hours(self, text: str) -> str:
        for s in self._sentences(text):
            if re.search(r"after.hours|when closed|outside.*hours", s, re.I):
                if re.search(r"screen|transfer|emergency|message|flow", s, re.I):
                    return s.rstrip(".")
        return "Screen for emergencies, collect contact information, then transfer or take a detailed message for callback."

    def _office_hours(self, text: str) -> str:
        for s in self._sentences(text):
            if re.search(r"during.*hours|business hours", s, re.I):
                if re.search(r"route|transfer|handle|call|message", s, re.I):
                    return s.rstrip(".")
        return "Greet caller, identify needs, collect name and callback number, route to appropriate contact or take message."

    @staticmethod
    def _unknowns(data: Dict) -> List[str]:
        flags = []
        if not data.get("company_name"):
            flags.append("Company name could not be extracted")
        bh = data.get("business_hours", {})
        if not bh.get("days"):
            flags.append("Business hours — days not specified")
        if not bh.get("start_time"):
            flags.append("Business hours — start/end time not specified")
        if not bh.get("timezone"):
            flags.append("Timezone not specified")
        if not data.get("emergency_routing_rules", {}).get("primary_contact"):
            flags.append("Emergency contact phone number not provided")
        if not data.get("non_emergency_routing_rules", {}).get("primary_contact"):
            flags.append("Non-emergency contact phone number not provided")
        if not data.get("emergency_definition"):
            flags.append("Emergency definition not specified")
        return flags

    def extract(self, text: str, account_id: str) -> Dict:
        data = {
            "account_id":                   account_id,
            "company_name":                 self._company(text),
            "business_hours":               self._hours(text),
            "office_address":               self._address(text),
            "services_supported":           self._services(text),
            "emergency_definition":         self._emerg_def(text),
            "emergency_routing_rules":      self._emerg_routing(text),
            "non_emergency_routing_rules":  self._non_emerg_routing(text),
            "call_transfer_rules":          self._transfer_rules(text),
            "integration_constraints":      self._constraints(text),
            "after_hours_flow_summary":     self._after_hours(text),
            "office_hours_flow_summary":    self._office_hours(text),
            "questions_or_unknowns":        [],
            "notes": f"Rule-based extraction — {datetime.now().isoformat()}",
            "_method": "rule_based",
        }
        data["questions_or_unknowns"] = self._unknowns(data)
        return data


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

class TranscriptProcessor:
    """Main entry point. Auto-selects Groq API or rule-based extraction."""

    def __init__(self, schema_path: str = None):
        self._rule = _RuleExtractor()

    def extract_account_info(self, transcript: str, account_id: str = None,
                              call_type: str = "demo") -> Dict[str, Any]:
        if not account_id:
            account_id = f"ACC_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        result = _groq_extract(transcript, account_id, call_type)
        if result:
            result["account_id"] = account_id
            result.setdefault("notes", f"Extracted via Groq API — {datetime.now().isoformat()}")
            return result
        return self._rule.extract(transcript, account_id)

    def extract_updates(self, transcript: str, account_id: str) -> Dict[str, Any]:
        return self.extract_account_info(transcript, account_id, call_type="onboarding")

    def process_file(self, filepath: str, account_id: str = None,
                     call_type: str = "demo") -> Dict[str, Any]:
        with open(filepath, encoding="utf-8") as fh:
            return self.extract_account_info(fh.read(), account_id, call_type)


if __name__ == "__main__":
    _sample = """
    Hi, calling from Sunrise Plumbing. We are based at 100 Oak Street, Chicago, IL.
    Business hours are Monday to Friday, 8 AM to 6 PM CST.
    We offer Plumbing, Drain Cleaning, and Emergency Service.
    Emergencies like burst pipes should call 312-555-0101.
    Regular service: 312-555-0102. We never schedule without confirmation.
    """
    _proc = TranscriptProcessor()
    print(json.dumps(_proc.extract_account_info(_sample, "TEST"), indent=2))














