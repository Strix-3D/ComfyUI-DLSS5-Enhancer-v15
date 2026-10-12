"""ComfyUI Nodes for DLSS 5 Visual Enhancer v15.0 - RTX Image & Video (VIDEO Output)"""
import subprocess
import tempfile
import torch
import numpy as np
from PIL import Image
from pathlib import Path
import re

from .paths import find_cli

# Map friendly names to CLI arguments
STYLE_MAP = {
    "Default": "0",
    "Natural": "1",
    "Cinematic": "2"
}

def natural_sort_key(s):
    """Helper to sort filenames naturally (frame_1, frame_2, frame_10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

class DLSS5_RTX_Enhance_v15:
    """Neural Rendering + RTX Upscaling for Images. 
    Set scale to 1.0 to skip upscaling and only apply Neural Rendering."""
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE",),
                "style": (["Default", "Natural", "Cinematic"], {"default": "Default"}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "scale": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 4.0, "step": 0.5}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "process"
    CATEGORY = "DLSS5_v15"

    def process(self, images, style, strength, scale):
        cli_path = find_cli()
        output_images = []
        cli_style = STYLE_MAP.get(style, "0")
        fmt = "png"
        ext = ".png"

        for img in images:
            i = 255.0 * img.cpu().numpy()
            img_pil = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            
            with tempfile.TemporaryDirectory() as tmpdir:
                input_path = Path(tmpdir) / f"input{ext}"
                render_path = Path(tmpdir) / f"render_out{ext}"
                upscale_path = Path(tmpdir) / f"upscale_out{ext}"
                img_pil.save(str(input_path))

                # --- STEP 1: NEURAL RENDER ---
                cmd_render = [
                    str(cli_path), "render", str(input_path),
                    "-o", str(render_path),
                    "--style", cli_style,
                    "--strength", str(strength),
                    "--format", fmt,
                    "--gpu", "auto",
                    "--quiet", "--json"
                ]
                subprocess.run(cmd_render, capture_output=True, text=True, check=True)

                # --- STEP 2: RTX UPSCALE ---
                final_path = render_path
                if scale > 1.0:
                    cmd_upscale = [
                        str(cli_path), "upscale", str(render_path),
                        "-o", str(upscale_path),
                        "--engine", "rtx",
                        "--scale", str(scale),
                        "--format", fmt,
                        "--gpu", "auto",
                        "--quiet", "--json"
                    ]
                    subprocess.run(cmd_upscale, capture_output=True, text=True, check=True)
                    final_path = upscale_path

                out_img = Image.open(final_path).convert("RGB")
                out_tensor = torch.from_numpy(np.array(out_img).astype(np.float32) / 255.0).unsqueeze(0)
                output_images.append(out_tensor)

        return (torch.cat(output_images, dim=0),)


class DLSS5_Video_Enhance_v15:
    """Neural Rendering + RTX Upscaling for Video.
    Accepts native VIDEO type and outputs native VIDEO type."""
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "video": ("VIDEO",), # Accepts native VIDEO type
                "style": (["Default", "Natural", "Cinematic"], {"default": "Default"}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "scale": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 4.0, "step": 0.5}),
            }
        }

    RETURN_TYPES = ("VIDEO",) # Outputs native VIDEO type for Save Video nodes
    FUNCTION = "process_video"
    CATEGORY = "DLSS5_v15"

    def process_video(self, video, style, strength, scale):
        cli_path = find_cli()
        cli_style = STYLE_MAP.get(style, "0")
        fmt = "png"
        
        # Extract the image batch from the VIDEO dictionary
        # Native ComfyUI Load Video outputs a dict with an 'images' key
        if isinstance(video, dict):
            images = video.get("images", video.get("frames", video))
            original_audio = video.get("audio")
            original_meta = video.get("meta", {})
        else:
            images = video
            original_audio = None
            original_meta = {}
            
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            input_dir = tmpdir / "input_frames"
            render_dir = tmpdir / "render_frames"
            upscale_dir = tmpdir / "upscale_frames"
            
            input_dir.mkdir()
            
            # 1. Save the entire batch of images to the input folder
            print(f"[Video] Saving {len(images)} frames to temporary folder...")
            for i, img in enumerate(images):
                i_tensor = 255.0 * img.cpu().numpy()
                img_pil = Image.fromarray(np.clip(i_tensor, 0, 255).astype(np.uint8))
                img_pil.save(str(input_dir / f"frame_{i+1:04d}.png"))

            # 2. Run Neural Render on the whole folder
            print(f"[Video] Running Neural Render on folder...")
            cmd_render = [
                str(cli_path), "render", str(input_dir),
                "-o", str(render_dir),
                "--style", cli_style,
                "--strength", str(strength),
                "--format", fmt,
                "--gpu", "auto",
                "--quiet", "--json"
            ]
            result = subprocess.run(cmd_render, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"DLSS5 Video Render failed: {result.stderr}")

            # 3. Run RTX Upscale on the rendered folder (if scale > 1.0)
            current_dir = render_dir
            if scale > 1.0:
                print(f"[Video] Running RTX Upscale on folder...")
                cmd_upscale = [
                    str(cli_path), "upscale", str(render_dir),
                    "-o", str(upscale_dir),
                    "--engine", "rtx",
                    "--scale", str(scale),
                    "--format", fmt,
                    "--gpu", "auto",
                    "--quiet", "--json"
                ]
                result = subprocess.run(cmd_upscale, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"DLSS5 Video Upscale failed: {result.stderr}")
                current_dir = upscale_dir

            # 4. Load the processed frames back into a ComfyUI IMAGE batch
            print(f"[Video] Loading processed frames back into ComfyUI...")
            processed_files = sorted([f for f in current_dir.glob("*.png")], key=lambda x: natural_sort_key(x.name))
            
            if not processed_files:
                raise Exception("No output frames were generated by the CLI.")

            output_tensors = []
            for file_path in processed_files:
                out_img = Image.open(file_path).convert("RGB")
                out_tensor = torch.from_numpy(np.array(out_img).astype(np.float32) / 255.0).unsqueeze(0)
                output_tensors.append(out_tensor)

            # Stack all frames back into a single batch
            final_tensor = torch.cat(output_tensors, dim=0)

            # 5. Reconstruct the VIDEO dictionary to pass to Save Video
            # This preserves audio and metadata from the original load!
            output_video = {
                "images": final_tensor,
                "audio": original_audio,
                "meta": original_meta
            }

            return (output_video,)


NODE_CLASS_MAPPINGS = {
    "DLSS5_RTX_Enhance_v15": DLSS5_RTX_Enhance_v15,
    "DLSS5_Video_Enhance_v15": DLSS5_Video_Enhance_v15,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DLSS5_RTX_Enhance_v15": "DLSS 5 RTX Enhance (Image)",
    "DLSS5_Video_Enhance_v15": "DLSS 5 RTX Enhance (Video)",
}