"""The 17 modules of v2 §2.4 and who owns their data.

16 modules run on the server, each with a package under ``app.modules`` and one
PostgreSQL schema. OFF is client-owned: it lives in the React Native / PWA
client and keeps its data in device storage, so it has no package here.
"""

from typing import NamedTuple


class ServerModule(NamedTuple):
    code: str
    package: str
    schema: str


SERVER_MODULES: tuple[ServerModule, ...] = (
    ServerModule("AUTH", "app.modules.auth", "identity"),
    ServerModule("TAX", "app.modules.tax", "curriculum"),
    ServerModule("QB", "app.modules.qb", "qbank"),
    ServerModule("CMS", "app.modules.cms", "cms"),
    ServerModule("PRAC", "app.modules.prac", "practice"),
    ServerModule("EXAM", "app.modules.exam", "exam"),
    ServerModule("ANL", "app.modules.anl", "analytics"),
    ServerModule("AI", "app.modules.ai", "ai"),
    ServerModule("GAM", "app.modules.gam", "rewards"),
    ServerModule("PLAN", "app.modules.plan", "notify"),
    ServerModule("COM", "app.modules.com", "community"),
    ServerModule("PAR", "app.modules.par", "parent"),
    ServerModule("INST", "app.modules.inst", "institution"),
    ServerModule("PAY", "app.modules.pay", "commerce"),
    ServerModule("OPS", "app.modules.ops", "ops"),
    ServerModule("NFR", "app.modules.nfr", "platform"),
)

CLIENT_OWNED: dict[str, str] = {
    "OFF": "Client platform (Android, PWA, lite mode, sync engine); data in device storage. "
    "Built in the React Native + react-native-web client, not in this repository.",
}

SCHEMAS: tuple[str, ...] = tuple(m.schema for m in SERVER_MODULES)
