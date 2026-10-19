"""Product families: the same Sentry product under its TrueSight, BMC Helix and OnPrem names."""
import re

FAMILIES = [  # first match wins: bundles before their components
    ("Bundle (BMC Helix Operations Mgmt)", r"bundle.*operations management"),
    ("Bundle (BMC Helix Continuous Optimization)", r"bundle.*continuous optimization"),
    ("Storage Plus (Capacity Optimization)", r"storage plus|capacity optimi[sz]er for storage"),
    ("Converged Infrastructure", r"converged"),
    ("Hardware", r"hardware"),
    ("Storage", r"storage"),
    ("Monitoring Studio", r"monitoring studio"),
    ("Backup", r"backup"),
    ("High Availability", r"high availability"),
    ("Microsoft Applications", r"microsoft applications"),
    ("Data Streams", r"data streams"),
    ("Integrator", r"integrator"),
    ("Sentry for TrueSight (platform)", r"^sentry for truesight"),
]


def family(product: str) -> str:
    p = (product or "").lower()
    return next((name for name, rx in FAMILIES if re.search(rx, p)), product)
