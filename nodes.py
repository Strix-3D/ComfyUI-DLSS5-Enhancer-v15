"""ComfyUI Nodes for DLSS 5 Visual Enhancer v17.5 - RTX Image & Video (Ray Reconstruction + Optical Flow + 16x Scale)"""
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
import imageio_ffmpeg

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

def is_safe_path(path_str: str, base_dir: Path) -> bool:
    """Check if a path is safe (no traversal, no absolute, no UNC)."""
    if not path_str:
        return True
    if path_str.startswith('/') or path_str.startswith('\\') or path_str.startswith('\\\\') or (len(path_str) > 1 and path_str[1] == ':'):
        return False
    if '..' in path_str.split('/') or '..' in path_str.split('\\'):
        return False
    try:
        resolved = (base_dir / path_str).resolve()
        return str(resolved).startswith(str(base_dir.resolve()))
    except Exception:
        return False

def validate_video_path(video_path: str) -> Path:
    """Validate video path is within ComfyUI input folder."""
    path_str = video_path.strip().strip('"')
    if not path_str:
        raise Exception("Video path cannot be empty")
    if path_str.startswith('/') or path_str.startswith('\\') or path_str.startswith('\\\\') or (len(path_str) > 1 and path_str[1] == ':'):
        raise Exception("Video path must be relative to ComfyUI input folder.")
    if '..' in path_str.split('/') or '..' in path_str.split('\\'):
        raise Exception("Video path cannot contain '..'")

    input_dir = Path(folder_paths.get_input_directory())
    full_path = (input_dir / path_str).resolve()
    if not str(full_path).startswith(str(input_dir.resolve())):
        raise Exception("Video path must be within ComfyUI input folder")
    if not full_path.is_file():
        raise Exception(f"Video file not found: {full_path}")
    return full_path

def validate_output_path(output_directory: str, filename_prefix: str) -> Path:
    """Validate and construct safe output path within ComfyUI output folder."""
    output_dir = Path(folder_paths.get_output_directory())
    if output_directory.strip():
        dir_str = output_directory.strip().strip('"')
        if not is_safe_path(dir_str, output_dir):
            raise Exception("output_directory must be relative to ComfyUI output folder.")
        output_dir = (output_dir / dir_str).resolve()
    if '..' in filename_prefix or filename_prefix.startswith('/') or filename_prefix.startswith('\\') or filename_prefix.startswith('\\\\') or (len(filename_prefix) > 1 and filename_prefix[1] == ':'):
        raise Exception("filename_prefix cannot contain path separators, drive letters, or '..'")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


class DLSS5_RTX_Enhance_v17:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE",),
                "style": (["Default", "Natural", "Cinematic"], {"default": "Default"}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "scale": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 16.0, "step": 0.5, "tooltip": "Scale factor. Up to 16.0 (1600%) supported in v17.5+"}),
                "ray_reconstruction": ("BOOLEAN", {"default": False, "tooltip": "Enable DLSS Ray Reconstruction at native resolution (1x) for high-precision color handling."}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "process"
    CATEGORY = "DLSS5_v17"

    def process(self, images, style, strength, scale, ray_reconstruction):
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

                # Step 1: Render or Reconstruct
                if ray_reconstruction:
                    # Use the dedicated 'reconstruct' command for Ray Reconstruction
                    cmd_render = [str(cli_path), "reconstruct", str(input_path), "-o", str(render_path), "--format", fmt, "--gpu", "auto", "--quiet", "--json"]
                else:
                    # Use standard 'render' command
                    cmd_render = [str(cli_path), "render", str(input_path), "-o", str(render_path), "--style", cli_style, "--strength", str(strength), "--format", fmt, "--gpu", "auto", "--quiet", "--json"]
                
                subprocess.run(cmd_render, capture_output=True, text=True, check=True)

                # Step 2: Upscale (Optional)
                final_path = render_path
                if scale > 1.0:
                    cmd_upscale = [str(cli_path), "upscale", str(render_path), "-o", str(upscale_path), "--engine", "rtx", "--scale", str(scale), "--format", fmt, "--gpu", "auto", "--quiet", "--json"]
                    subprocess.run(cmd_upscale, capture_output=True, text=True, check=True)
                    final_path = upscale_path

                out_img = Image.open(final_path).convert("RGB")
                out_tensor = torch.from_numpy(np.array(out_img).astype(np.float32) / 255.0).unsqueeze(0)
                output_images.append(out_tensor)
        return (torch.cat(output_images, dim=0),)


class DLSS5_Video_File_Enhance_v17:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "video_path": ("STRING", {"default": "", "multiline": False, "tooltip": "Relative path to video file within ComfyUI input folder"}),
                "style": (["Default", "Natural", "Cinematic"], {"default": "Default"}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "scale": ("FLOAT", {"default": 1.0, "min": 1.0, "max": 16.0, "step": 0.5, "tooltip": "Scale factor. Up to 16.0 (1600%) supported in v17.5+"}),
                "codec": (["HEVC", "H264", "AV1", "ProRes Proxy"], {"default": "HEVC"}),
                "container": (["MKV", "MP4", "MOV"], {"default": "MKV"}),
                "quality": (["Auto", "Good", "Best", "Max"], {"default": "Auto"}),
                "target_fps": ("INT", {"default": 0, "min": 0, "max": 120, "step": 1, "tooltip": "0 = disabled. Target FPS for DLSS Frame Generation (Requires RTX 40/50 Series)."}),
                "ray_reconstruction": ("BOOLEAN", {"default": False, "tooltip": "Enable DLSS Ray Reconstruction for video."}),
                "optical_flow_quality": (["Disabled", "High", "Medium", "Low"], {"default": "Disabled", "tooltip": "NVIDIA Optical Flow quality for Ray Reconstruction video."}),
                "filename_prefix": ("STRING", {"default": "DLSS5", "multiline": False}),
                "output_directory": ("STRING", {"default": "", "multiline": False, "tooltip": "Relative path within ComfyUI output directory"}),
                "copy_audio": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("output_path", "frames")
    FUNCTION = "process_video_file"
    CATEGORY = "DLSS5_v17"

    def process_video_file(self, video_path, style, strength, scale, codec, container, quality, target_fps, ray_reconstruction, optical_flow_quality, filename_prefix, output_directory, copy_audio):
        cli_path = find_cli()
        cli_style = STYLE_MAP.get(style, "0")

        input_path = validate_video_path(video_path)
        out_dir = validate_output_path(output_directory, filename_prefix)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        container_ext = container.lower()
        final_filename = f"{filename_prefix}_{timestamp}.{container_ext}"
        final_output_path = out_dir / final_filename

        codec_map = {"HEVC": "hevc", "H264": "h264", "AV1": "av1", "ProRes Proxy": "prores"}
        quality_map = {"Auto": "auto", "Good": "good", "Best": "best", "Max": "max"}

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            render_path = tmpdir / f"render_out.{container_ext}"
            upscale_path = tmpdir / f"upscale_out.{container_ext}"

            # Step 1: Render or Reconstruct
            if ray_reconstruction:
                print(f"[Video File] Processing with Ray Reconstruction...")
                cmd = [str(cli_path), "reconstruct", str(input_path), "-o", str(render_path), "--gpu", "auto", "--quiet", "--json"]
                cmd.extend(["--codec", codec_map.get(codec, "hevc")])
                cmd.extend(["--container", container_ext])
                cmd.extend(["--quality", quality_map.get(quality, "auto")])
                
                if optical_flow_quality != "Disabled":
                    cmd.extend(["--flow-quality", optical_flow_quality.lower()])
            else:
                print(f"[Video File] Processing with Neural Render...")
                cmd = [str(cli_path), "render", str(input_path), "-o", str(render_path), "--style", cli_style, "--strength", str(strength), "--gpu", "auto", "--quiet", "--json"]
                cmd.extend(["--codec", codec_map.get(codec, "hevc")])
                cmd.extend(["--container", container_ext])
                cmd.extend(["--quality", quality_map.get(quality, "auto")])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"DLSS5 Video Process failed: {result.stderr}")

            current_path = render_path

            # Step 2: RTX Upscale (Optional)
            if scale > 1.0:
                print(f"[Video File] Upscaling...")
                cmd_upscale = [str(cli_path), "upscale", str(render_path), "-o", str(upscale_path), "--engine", "rtx", "--scale", str(scale), "--codec", codec_map.get(codec, "hevc"), "--container", container_ext, "--quality", quality_map.get(quality, "auto"), "--gpu", "auto", "--quiet", "--json"]
                result = subprocess.run(cmd_upscale, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"DLSS5 Video Upscale failed: {result.stderr}")
                current_path = upscale_path

            # Step 3: DLSS Frame Generation Interpolation (Optional)
            if target_fps > 0:
                print(f"[Video File] Interpolating to {target_fps} FPS via DLSS Frame Generation...")
                interpolate_path = tmpdir / f"interpolated_out.{container_ext}"

                cmd_interpolate = [
                    str(cli_path), "interpolate", str(current_path),
                    "--fps", str(target_fps),
                    "-o", str(interpolate_path),
                    "--quiet", "--json"
                ]

                result = subprocess.run(cmd_interpolate, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"DLSS5 Video Interpolation failed: {result.stderr}")

                current_path = interpolate_path
                print(f"[Video File] Interpolation complete.")

            # Step 4: Audio Preservation Fix (Uses imageio-ffmpeg)
            if copy_audio:
                print(f"[Video File] Preserving audio from source...")
                ffmpeg_exe = None
                try:
                    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                except Exception:
                    pass

                if not ffmpeg_exe:
                    ffmpeg_exe = shutil.which("ffmpeg")

                if not ffmpeg_exe:
                    print(f"[Warning] ffmpeg not found. Saving video without audio.")
                    shutil.move(str(current_path), str(final_output_path))
                else:
                    ffmpeg_cmd = [
                        ffmpeg_exe, "-y",
                        "-i", str(current_path),
                        "-i", str(input_path),
                        "-c:v", "copy",
                        "-c:a", "copy",
                        "-map", "0:v:0",
                        "-map", "1:a:0?",
                        str(final_output_path)
                    ]
                    try:
                        subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)
                        print(f"[Video File] Audio successfully merged.")
                    except subprocess.CalledProcessError as e:
                        print(f"[Warning] FFmpeg audio merge failed: {e.stderr}. Saving video without audio.")
                        shutil.move(str(current_path), str(final_output_path))
            else:
                shutil.move(str(current_path), str(final_output_path))

            print(f"[Video File] Saved to: {final_output_path}")
            frame_count = 0

        return (str(final_output_path), frame_count)


NODE_CLASS_MAPPINGS = {
    "DLSS5_Enhance_Image": DLSS5_RTX_Enhance_v17,
    "DLSS5_Enhance_Video": DLSS5_Video_File_Enhance_v17,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DLSS5_Enhance_Image": "DLSS5 Enhance (Image)",
    "DLSS5_Enhance_Video": "DLSS5 Enhance (Video)",
}
