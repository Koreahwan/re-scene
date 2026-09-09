"""
Reframe V7 Nemotron Persona Adapter
Safely parses, validates, pseudonymizes, and categorizes Nemotron-Personas-USA records.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import hashlib
import re
from typing import Dict, Any, Optional, List, Tuple
from src.reframe.simulation.schemas import DerivedPersonaProfile, PersonaLens
from src.reframe.shared.config import settings

# Census Regions Mapping for US States
US_CENSUS_REGIONS = {
    # Northeast
    "CT": "Northeast", "ME": "Northeast", "MA": "Northeast", "NH": "Northeast",
    "RI": "Northeast", "VT": "Northeast", "NJ": "Northeast", "NY": "Northeast",
    "PA": "Northeast",
    # Midwest
    "IL": "Midwest", "IN": "Midwest", "MI": "Midwest", "OH": "Midwest",
    "WI": "Midwest", "IA": "Midwest", "KS": "Midwest", "MN": "Midwest",
    "MO": "Midwest", "NE": "Midwest", "ND": "Midwest", "SD": "Midwest",
    # South
    "DE": "South", "FL": "South", "GA": "South", "MD": "South", "NC": "South",
    "SC": "South", "VA": "South", "DC": "South", "WV": "South", "AL": "South",
    "KY": "South", "MS": "South", "TN": "South", "AR": "South", "LA": "South",
    "OK": "South", "TX": "South",
    # West
    "AZ": "West", "CO": "West", "ID": "West", "MT": "West", "NV": "West",
    "NM": "West", "UT": "West", "WY": "West", "AK": "West", "CA": "West",
    "HI": "West", "OR": "West", "WA": "West",
}

STATE_FULL_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC"
}

SAFE_CINEMA_INTEREST_KEYWORDS = {
    "mystery": "mystery_puzzles",
    "detective": "mystery_puzzles",
    "puzzle": "mystery_puzzles",
    "riddle": "mystery_puzzles",
    "noir": "film_noir_classic",
    "cinema": "classic_cinema",
    "film": "classic_cinema",
    "movie": "classic_cinema",
    "theater": "arts_performing",
    "theatre": "arts_performing",
    "acting": "arts_performing",
    "photography": "visual_arts",
    "painting": "visual_arts",
    "writing": "creative_writing",
    "literature": "creative_writing",
    "reading": "creative_writing",
    "history": "historical_narrative",
    "vintage": "historical_narrative",
    "retro": "historical_narrative",
    "crime": "crime_investigation",
    "investigation": "crime_investigation",
    "thriller": "suspense_thriller",
    "suspense": "suspense_thriller",
}


class NemotronPersonaAdapter:
    def __init__(self, salt: Optional[str] = None):
        self.salt = salt or settings.SIMULATION_SALT
        self.dataset_id = settings.NEMOTRON_DATASET_ID
        self.dataset_revision = settings.NEMOTRON_DATASET_REVISION

    def compute_persona_hash(self, source_uuid: str) -> str:
        data = f"{self.dataset_id}:{self.dataset_revision}:{source_uuid}:{self.salt}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def normalize_state(self, raw_state: Optional[str]) -> str:
        if not raw_state:
            return "UNKNOWN"
        cleaned = raw_state.strip().upper()
        if cleaned in US_CENSUS_REGIONS:
            return cleaned
        lower_cleaned = raw_state.strip().lower()
        if lower_cleaned in STATE_FULL_TO_ABBR:
            return STATE_FULL_TO_ABBR[lower_cleaned]
        return "UNKNOWN"

    def get_census_region(self, state_abbr: str) -> str:
        return US_CENSUS_REGIONS.get(state_abbr, "National")


    def normalize_age_band(self, age: int) -> str:
        if age < 18:
            return "UNDER_18"
        elif age <= 24:
            return "18-24"
        elif age <= 34:
            return "25-34"
        elif age <= 44:
            return "35-44"
        elif age <= 54:
            return "45-54"
        elif age <= 64:
            return "55-64"
        else:
            return "65+"

    def categorize_occupation(self, occ: Optional[str]) -> str:
        if not occ:
            return "Other / Undisclosed"
        occ_lower = occ.lower().replace("_", " ")
        if any(k in occ_lower for k in ["not in workforce", "no occupation", "unemployed", "retired", "student"]):
            return "Other / Undisclosed"
        elif any(k in occ_lower for k in ["software", "developer", "engineer", "scientist", "database", "computer", "information", "data", "analyst", "tech", "systems", "programmer"]):
            return "Tech & Engineering"
        elif any(k in occ_lower for k in ["nurse", "physician", "doctor", "health", "medical", "dental", "pharma", "therapy", "therapist", "aide", "paramedic"]):
            return "Healthcare & Medical"
        elif any(k in occ_lower for k in ["teacher", "professor", "educat", "school", "academic", "researcher", "instructor"]):
            return "Education & Research"
        elif any(k in occ_lower for k in ["artist", "writer", "designer", "music", "actor", "producer", "photograph", "media", "journalist"]):
            return "Arts & Entertainment"
        elif any(k in occ_lower for k in ["account", "finance", "manager", "bank", "consult", "executive", "sales", "marketing", "business", "secretary", "administrative", "clerk"]):
            return "Business & Finance"
        elif any(k in occ_lower for k in ["food", "worker", "counter", "cook", "chef", "driver", "retail", "electric", "plumb", "mechanic", "construction", "laborer", "assembler", "repair", "service", "customer", "fabricat", "cleaner", "janitor"]):
            return "Trades & Services"
        elif any(k in occ_lower for k in ["legal", "lawyer", "judge", "attorney", "government", "military", "police", "officer", "firefighter", "postal", "non-profit"]):
            return "Public Sector & Legal"
        return "General Professional / Other"

    def categorize_education(self, edu: Optional[str]) -> str:
        if not edu:
            return "Other"
        edu_lower = edu.lower().replace("_", " ")
        if any(k in edu_lower for k in ["high school", "ged", "secondary", "diploma", "9th 12th no diploma"]):
            return "High School / GED"
        elif any(k in edu_lower for k in ["phd", "doctor", "md", "jd", "doctorate"]):
            return "Doctorate / Professional"
        elif any(k in edu_lower for k in ["master", "graduate", "m.s.", "m.a.", "mba", "msc", "m.ed", "m.eng"]) or re.search(r"\b(ms|ma)\b", edu_lower):
            return "Master's"
        elif any(k in edu_lower for k in ["bachelor", "bachelors", "b.a.", "b.s.", "undergraduate"]) or re.search(r"\b(ba|bs|bsc)\b", edu_lower):
            return "Bachelor's"
        elif any(k in edu_lower for k in ["associate", "associates", "some college", "community college", "vocational", "technical"]):
            return "Some College / Associate"
        return "Other"



    def categorize_location_context(self, city: Optional[str], state: str, zipcode: Optional[str]) -> str:
        # Broad deterministic categorization
        if not city:
            return "Suburban"
        city_lower = city.lower()
        major_metros = [
            "new york", "los angeles", "chicago", "houston", "phoenix", "philadelphia", "san antonio",
            "san diego", "dallas", "san jose", "austin", "jacksonville", "fort worth", "columbus",
            "san francisco", "charlotte", "indianapolis", "seattle", "denver", "washington", "boston",
            "el paso", "nashville", "detroit", "portland", "las vegas", "memphis", "louisville", "baltimore",
            "milwaukee", "albuquerque", "tucson", "fresno", "mesa", "sacramento", "atlanta", "kansas city",
            "miami", "raleigh", "omaha", "oakland", "minneapolis", "tulsa", "tampa", "arlington", "new orleans"
        ]
        if any(metro in city_lower for metro in major_metros):
            return "Urban"
        elif any(k in city_lower for k in ["county", "township", "junction", "village", "hollow", "creek", "prairie", "rural"]):
            return "Rural"
        return "Suburban"

    def extract_safe_interest_tags(self, arts_text: Optional[str], hobbies_text: Optional[str]) -> List[str]:
        combined = f"{arts_text or ''} {hobbies_text or ''}".lower()
        tags = set()
        for kw, tag in SAFE_CINEMA_INTEREST_KEYWORDS.items():
            if re.search(r'\b' + re.escape(kw) + r'\b', combined):
                tags.add(tag)
        return sorted(list(tags))

    def extract_available_lenses(self, row: Dict[str, Any]) -> List[PersonaLens]:
        lenses = [PersonaLens.GENERAL]
        if row.get("professional_persona") and len(str(row.get("professional_persona")).strip()) > 10:
            lenses.append(PersonaLens.PROFESSIONAL)
        if row.get("arts_persona") and len(str(row.get("arts_persona")).strip()) > 10:
            lenses.append(PersonaLens.ARTS)
        if row.get("sports_persona") and len(str(row.get("sports_persona")).strip()) > 10:
            lenses.append(PersonaLens.SPORTS)
        if row.get("travel_persona") and len(str(row.get("travel_persona")).strip()) > 10:
            lenses.append(PersonaLens.TRAVEL)
        if row.get("culinary_persona") and len(str(row.get("culinary_persona")).strip()) > 10:
            lenses.append(PersonaLens.CULINARY)
        return lenses

    def adapt_row(
        self,
        row: Dict[str, Any],
        alias_index: int = 1
    ) -> Tuple[Optional[DerivedPersonaProfile], Optional[str]]:
        """
        Validates and adapts a source row.
        Returns (profile, None) on success, or (None, rejection_reason) on rejection.
        """
        if "persona_id" in row and "source_persona_id_hash" in row:
            try:
                p = DerivedPersonaProfile(**row)
                return p, None
            except Exception as e:
                return None, f"INVALID_PROFILE_DATA: {e}"

        # Validate uuid
        source_uuid = row.get("uuid")
        if not source_uuid:
            return None, "MISSING_UUID"

        # Validate country (USA context)
        country = str(row.get("country", "")).strip().lower()
        if country and country not in ["united states", "usa", "us", "u.s.a.", "u.s."]:
            return None, "NON_US_COUNTRY"

        # Validate age >= 18
        raw_age = row.get("age")
        if raw_age is None:
            return None, "INVALID_SCHEMA_AGE"
        try:
            age = int(raw_age)
        except (ValueError, TypeError):
            return None, "INVALID_SCHEMA_AGE"

        if age < 18:
            return None, "UNDER_18"

        # Normalize demographic fields
        state_abbr = self.normalize_state(row.get("state"))
        census_region = self.get_census_region(state_abbr)
        age_band = self.normalize_age_band(age)
        occupation_group = self.categorize_occupation(row.get("occupation"))
        education_group = self.categorize_education(row.get("education_level"))
        location_context = self.categorize_location_context(row.get("city"), state_abbr, row.get("zipcode"))

        persona_hash = self.compute_persona_hash(str(source_uuid))
        persona_id = f"us_pers_{persona_hash[:16]}"
        display_alias = f"Synthetic Fan US-{alias_index:06d}"

        safe_interest_tags = self.extract_safe_interest_tags(
            row.get("arts_persona"),
            row.get("hobbies_and_interests") or row.get("hobbies_and_interests_list")
        )
        available_lenses = self.extract_available_lenses(row)

        profile = DerivedPersonaProfile(
            persona_id=persona_id,
            source_persona_id_hash=persona_hash,
            locale="en_US",
            display_alias=display_alias,
            age_band=age_band,
            state=state_abbr,
            census_region=census_region,
            location_context=location_context,
            education_group=education_group,
            occupation_group=occupation_group,
            sampling_weight=1.0,
            safe_interest_tags=safe_interest_tags,
            available_persona_lenses=available_lenses,
            source_dataset=self.dataset_id,
            source_revision=self.dataset_revision,
        )

        return profile, None


persona_adapter = NemotronPersonaAdapter()
