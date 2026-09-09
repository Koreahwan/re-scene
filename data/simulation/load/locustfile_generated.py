"""
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
