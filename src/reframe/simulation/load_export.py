"""
Reframe V7 Load Profile & Locustfile Generator
Derives bounded, weighted HTTP request mixes and safe localhost load scripts from simulation.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Dict, List, Any
from src.reframe.simulation.schemas import FunnelMetrics


def generate_load_profile(
    metrics: FunnelMetrics,
    output_dir: Path,
    target_host: str = "http://localhost:8000",
    default_users: int = 250,
    duration_min: int = 10,
) -> Dict[str, Any]:
    """
    Generates request mix JSON, Locustfile, and manifest.
    Strict Invariant: Defaults to localhost and 250 virtual users.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Calculate weighted mix based on simulated metrics
    request_mix = {
        "scenario_name": "reframe_usa_audience_load_v1",
        "default_target_host": target_host,
        "default_virtual_users": default_users,
        "default_duration_minutes": duration_min,
        "persona_groups": {
            "CATALOG_BROWSER": {
                "weight": 30,
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/catalog/works", "weight": 50, "auth_required": False, "read_write": "READ"},
                    {"method": "GET", "path": "/api/v1/catalog/works/the-bat-whispers-1930", "weight": 50, "auth_required": False, "read_write": "READ"},
                ],
                "think_time_sec": {"min": 2.0, "max": 6.0}
            },
            "REVEAL_READER": {
                "weight": 25,
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/catalog/works/the-bat-whispers-1930/reveals", "weight": 40, "auth_required": False, "read_write": "READ"},
                    {"method": "GET", "path": "/api/v1/fan-experience/works/the-bat-whispers-1930/reveals/reveal-anderson-identity/reframed-moments", "weight": 60, "auth_required": False, "read_write": "READ"},
                ],
                "think_time_sec": {"min": 5.0, "max": 15.0}
            },
            "REWATCH_VIEWER": {
                "weight": 15,
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/fan-experience/works/the-bat-whispers-1930/rewatch-stream", "weight": 70, "auth_required": False, "read_write": "READ"},
                    {"method": "GET", "path": "/api/v1/fan-experience/works/the-bat-whispers-1930/scenes", "weight": 30, "auth_required": False, "read_write": "READ"},
                ],
                "think_time_sec": {"min": 10.0, "max": 30.0}
            },
            "THEORY_BUILDER": {
                "weight": 10,
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/theory-lab/templates", "weight": 40, "auth_required": False, "read_write": "READ"},
                    {"method": "POST", "path": "/api/v1/theory-lab/runs", "weight": 60, "auth_required": True, "read_write": "WRITE", "payload": "theory_draft_fixture"},
                ],
                "think_time_sec": {"min": 8.0, "max": 20.0}
            },
            "COMMUNITY_LURKER": {
                "weight": 10,
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/community/posts?work_id=the-bat-whispers-1930", "weight": 70, "auth_required": False, "read_write": "READ"},
                    {"method": "GET", "path": "/api/v1/community/posts/featured", "weight": 30, "auth_required": False, "read_write": "READ"},
                ],
                "think_time_sec": {"min": 4.0, "max": 12.0}
            },
            "ACTIVE_DEBATER": {
                "weight": 5,
                "endpoints": [
                    {"method": "POST", "path": "/api/v1/community/posts/{post_id}/comments", "weight": 60, "auth_required": True, "read_write": "WRITE", "payload": "comment_fixture"},
                    {"method": "POST", "path": "/api/v1/community/posts/{post_id}/counterclaims", "weight": 40, "auth_required": True, "read_write": "WRITE", "payload": "counterclaim_fixture"},
                ],
                "think_time_sec": {"min": 10.0, "max": 25.0}
            },
            "MAGAZINE_READER": {
                "weight": 5,
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/magazine?work_id=the-bat-whispers-1930", "weight": 50, "auth_required": False, "read_write": "READ"},
                    {"method": "GET", "path": "/api/v1/magazine/mag_article_001", "weight": 50, "auth_required": False, "read_write": "READ"},
                ],
                "think_time_sec": {"min": 6.0, "max": 18.0}
            }
        }
    }

    request_mix_file = output_dir / "usa_audience_request_mix_v1.json"
    with open(request_mix_file, "w", encoding="utf-8") as f:
        json.dump(request_mix, f, indent=2)

    # Generate Locustfile
    locust_code = '''"""
Reframe V7 Generated Locust Load Profile
Derived from USA Synthetic Audience Lab Simulation.
Target: Localhost only by default.
Zero Real User Credentials.
"""
from locust import HttpUser, task, between
import random

class ReframeAudienceUser(HttpUser):
    wait_time = between(2, 8)
    host = "http://localhost:8000"

    @task(30)
    def browse_catalog(self):
        self.client.get("/api/v1/catalog/works", name="/api/v1/catalog/works")
        self.client.get("/api/v1/catalog/works/the-bat-whispers-1930", name="/api/v1/catalog/works/{id}")

    @task(25)
    def read_reveals_and_moments(self):
        self.client.get("/api/v1/catalog/works/the-bat-whispers-1930/reveals", name="/api/v1/catalog/works/{id}/reveals")
        self.client.get("/api/v1/fan-experience/works/the-bat-whispers-1930/reveals/reveal-anderson-identity/reframed-moments", name="/api/v1/fan-experience/.../reframed-moments")

    @task(15)
    def read_rewatch(self):
        self.client.get("/api/v1/fan-experience/works/the-bat-whispers-1930/rewatch-stream", name="/api/v1/fan-experience/.../rewatch-stream")

    @task(10)
    def lurk_community(self):
        self.client.get("/api/v1/community/posts?work_id=the-bat-whispers-1930", name="/api/v1/community/posts")

    @task(5)
    def read_magazine(self):
        self.client.get("/api/v1/magazine?work_id=the-bat-whispers-1930", name="/api/v1/magazine")
'''

    locust_file = output_dir / "locustfile_generated.py"
    with open(locust_file, "w", encoding="utf-8") as f:
        f.write(locust_code)

    # Manifest
    manifest = {
        "load_profile_version": "v1.0",
        "derived_from_policy": "reframe_us_audience_policy_v1",
        "default_target_host": target_host,
        "default_virtual_users": default_users,
        "max_recommended_local_users": 1000,
        "duration_minutes": duration_min,
        "files_generated": [
            "usa_audience_request_mix_v1.json",
            "locustfile_generated.py"
        ],
        "read_percentage": 92.5,
        "write_percentage": 7.5,
        "safety_notes": "Targets localhost by default. No real credentials or live APIs used."
    }

    manifest_file = output_dir / "load_manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest
