"""ComfyUI-DLSS5-Enhancer-v15: RTX Engine Only"""
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Tells ComfyUI to serve the custom frontend extension (web/dlss5_selector.js) to the browser
WEB_DIRECTORY = "./web"

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
