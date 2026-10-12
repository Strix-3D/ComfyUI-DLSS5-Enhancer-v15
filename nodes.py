"""ComfyUI Nodes for DLSS 5 Visual Enhancer v15.0 - RTX Image & Video File (Full Options)"""
import subprocess
import tempfile
import torch
import numpy as np
from PIL import Image
from pathlib import Path
import re
import folder_paths
import datetime
import shutil

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


class DLSS5_Video_File_Enhance_v15:
    """Neural Rendering + RTX Upscaling for Video Files.
    Accepts a file path string, processes the video natively via CLI, 
    and saves the result to the ComfyUI output directory."""
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "video_path": ("STRING", {"default": "", "multiline": False, "tooltip": "Absolute path to the source video file"}),
                "style": (["Default", "Natural", "Cinematic"], {"default": "Default"}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "scale": ("FLOAT", {"default": 1.0, "min": 1.0, "max": 4.0, "step": 0.5}),
                "codec": (["HEVC", "H264", "AV1", "ProRes Proxy"], {"default": "HEVC"}),
                "container": (["MKV", "MP4", "MOV"], {"default": "MKV"}),
                "quality": (["Auto", "Good", "Best", "Max"], {"default": "Auto"}),
                "filename_prefix": ("STRING", {"default": "DLSS5", "multiline": False}),
                "output_directory": ("STRING", {"default": "", "multiline": False, "tooltip": "Empty writes to ComfyUI output directory"}),
                "max_frames": ("INT", {"default": 0, "min": 0, "max": 1000000, "step": 1, "tooltip": "0 renders everything, any other value renders a preview"}),
                "copy_audio": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("output_path", "frames")
    FUNCTION = "process_video_file"
    CATEGORY = "DLSS5_v15"

    def process_video_file(self, video_path, style, strength, scale, codec, container, 
                          quality, filename_prefix, output_directory, max_frames, copy_audio):
        cli_path = find_cli()
        cli_style = STYLE_MAP.get(style, "0")
        
        input_path = Path(video_path.strip().strip('"'))
        if not input_path.is_file():
            raise Exception(f"Video file not found: {input_path}")

        # Determine output path
        if output_directory.strip():
            out_dir = Path(output_directory.strip().strip('"'))
            if not out_dir.is_absolute():
                out_dir = Path(folder_paths.get_output_directory()) / out_dir
        else:
            out_dir = Path(folder_paths.get_output_directory())
        
        out_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        container_ext = container.lower()
        final_filename = f"{filename_prefix}_{timestamp}.{container_ext}"
        final_output_path = out_dir / final_filename

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            render_path = tmpdir / f"render_out.{container_ext}"
            upscale_path = tmpdir / f"upscale_out.{container_ext}"

            # Build CLI command
            cmd = [
                str(cli_path), "render", str(input_path),
                "-o", str(render_path),
                "--style", cli_style,
                "--strength", str(strength),
                "--gpu", "auto",
                "--quiet", "--json"
            ]
            
            # Add codec and container options
            codec_map = {"HEVC": "hevc", "H264": "h264", "AV1": "av1", "ProRes Proxy": "prores"}
            cmd.extend(["--codec", codec_map.get(codec, "hevc")])
            cmd.extend(["--container", container_ext])
            
            # Add quality option
            quality_map = {"Auto": "auto", "Good": "good", "Best": "best", "Max": "max"}
            cmd.extend(["--quality", quality_map.get(quality, "auto")])
            
            # Add max_frames if specified
            if max_frames > 0:
                cmd.extend(["--max-frames", str(max_frames)])
            
            # Add copy_audio option
            if not copy_audio:
                cmd.append("--no-audio")

            # Step 1: Neural Render
            print(f"[Video File] Processing: {input_path}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"DLSS5 Video Render failed: {result.stderr}")

            # Step 2: RTX Upscale
            current_path = render_path
            if scale > 1.0:
                print(f"[Video File] Upscaling...")
                cmd_upscale = [
                    str(cli_path), "upscale", str(render_path),
                    "-o", str(upscale_path),
                    "--engine", "rtx",
                    "--scale", str(scale),
                    "--codec", codec_map.get(codec, "hevc"),
                    "--container", container_ext,
                    "--quality", quality_map.get(quality, "auto"),
                    "--gpu", "auto",
                    "--quiet", "--json"
                ]
                if max_frames > 0:
                    cmd_upscale.extend(["--max-frames", str(max_frames)])
                if not copy_audio:
                    cmd_upscale.append("--no-audio")
                    
                result = subprocess.run(cmd_upscale, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"DLSS5 Video Upscale failed: {result.stderr}")
                current_path = upscale_path

            # Move final file to output directory
            shutil.move(str(current_path), str(final_output_path))
            print(f"[Video File] Saved to: {final_output_path}")

            # Estimate frame count (simplified - CLI output or ffprobe would be more accurate)
            frame_count = max_frames if max_frames > 0 else 0  # 0 means unknown/all frames

        return (str(final_output_path), frame_count)


NODE_CLASS_MAPPINGS = {
    "DLSS5_RTX_Enhance_v15": DLSS5_RTX_Enhance_v15,
    "DLSS5_Video_File_Enhance_v15": DLSS5_Video_File_Enhance_v15,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DLSS5_RTX_Enhance_v15": "DLSS 5 RTX Enhance (Image)",
    "DLSS5_Video_File_Enhance_v15": "DLSS5 Enhance Video File (v15)",
}
