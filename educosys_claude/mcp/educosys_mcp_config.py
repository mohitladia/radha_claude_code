import os
import re
import json
from pathlib import Path


_CONFIG_PATH = Path(__file__).parent.parent / "educosys_mcp_servers.json"




def _resolve_env(value: str) -> str:
   return re.sub(r"\$\{(\w+)\}", lambda m: os.getenv(m.group(1), ""), value)




def _resolve_envs(obj):
   if isinstance(obj, dict):
       return {k: _resolve_envs(v) for k, v in obj.items()}
   if isinstance(obj, list):
       return [_resolve_envs(i) for i in obj]
   if isinstance(obj, str):
       return _resolve_env(obj)
   return obj




def load_educosys_mcp_configs() -> dict:
   """Return mcp_servers dict from educosys_mcp_servers.json with env vars resolved."""
   with open(_CONFIG_PATH, "r") as f:
       raw = json.load(f)
   return _resolve_envs(raw.get("mcp_servers", {}))
