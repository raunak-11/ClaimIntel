from typing import Any

import storage
from agents.base_agent import BaseAgent
from services.gemini_client import ask_json
from services.rag_client import get_similar_cases_context

BASE_PROMPT = """You are an accident reconstruction expert with access to a database of historical claim cases.
Analyze the vehicle damage images and claim narrative to reconstruct the incident.
Use historical precedents from the knowledge base to calibrate your confidence assessment.

{kb_context}

Claim description: {description}
Vehicle: {vehicle}
Claim type: {claim_type}
Damage map (from Agent 1): {damage_map}

Instructions:
- The damage map shows parts damaged and their severity from the AI damage assessment
- Historical precedents (if provided above) show how similar damage patterns were classified
- Assess whether the physical damage pattern is consistent with the described incident
- For reconstruction_bullets: distil the reconstruction narrative into exactly 3 concise, specific bullet points
- For storyboard_panels: produce exactly 4 sequential panels covering the lifecycle of the incident.
  Each panel needs a single relevant emoji, a short title, and a 1-2 sentence plain-English description.
  Suggested titles: "Pre-Incident", "Point of Impact", "Immediate Aftermath", "Evidence Summary"
  (adjust titles to suit the claim — e.g. "Alleged Scenario" if the story is suspect)
- Return ONLY valid JSON with no markdown fences or extra text

Return a JSON object with exactly these fields:
{{
  "collision_type": "Front impact|Rear impact|Left-side impact|Right-side impact|Rollover|Multi-point|Parking/Low-speed|Underbody|Weather damage",
  "impact_direction": "Brief description of primary impact direction and angle",
  "reconstruction": "2-4 sentence narrative of what most likely happened based on damage evidence",
  "reconstruction_bullets": [
    "First key physical finding from the damage evidence",
    "Second key finding linking damage to the claimed scenario",
    "Third finding — overall story consistency verdict"
  ],
  "storyboard_panels": [
    {{"panel": 1, "title": "Pre-Incident", "emoji": "🚗", "description": "What was happening immediately before the incident — vehicle state, location, time, conditions."}},
    {{"panel": 2, "title": "Point of Impact", "emoji": "💥", "description": "The moment of collision — direction, speed estimate, what struck what."}},
    {{"panel": 3, "title": "Immediate Aftermath", "emoji": "🔧", "description": "Post-impact scene — which parts failed, airbag state, vehicle drivability."}},
    {{"panel": 4, "title": "Evidence Summary", "emoji": "🔍", "description": "What the physical evidence conclusively tells us — consistency verdict."}}
  ],
  "damage_matches_story": true or false,
  "confidence": <integer 0-100>,
  "similar_historical_cases": ["any matching case IDs from KB precedents, e.g. HIST-003"],
  "inconsistencies": ["specific inconsistencies found between damage and description, if any"],
  "status": "completed",
  "summary": "Most Probable: {{collision_type}} | Confidence: X% | Story Match: Yes/No"
}}
"""


class IncidentReconstructionAgent(BaseAgent):
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        claim = context["claim"]
        damage = context["agents"].get("damage_assessment", {})
        image_paths = storage.get_claim_images(claim["claim_id"])

        damage_map = [
            {"part": p.get("part"), "severity": p.get("severity")}
            for p in damage.get("damaged_parts", [])
        ]
        damaged_part_names = [p.get("part", "") for p in damage.get("damaged_parts", [])]

        # RAG: fetch similar historical cases
        claim_type = claim.get("claim_type", "")
        kb_context = get_similar_cases_context(claim_type, damaged_part_names)

        prompt = BASE_PROMPT.format(
            kb_context=kb_context,
            description=claim.get("description", ""),
            vehicle=claim.get("vehicle", ""),
            claim_type=claim_type,
            damage_map=str(damage_map),
        )
        result = ask_json(prompt, image_paths if image_paths else None)
        result.setdefault("status", "completed")
        return result
