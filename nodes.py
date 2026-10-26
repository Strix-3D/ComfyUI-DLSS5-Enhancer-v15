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
import json
import os
import hashlib
import wave
from server import PromptServer
from aiohttp import web
from skimage.color import rgb2lab, lab2rgb
from .paths import find_cli

# Map friendly names to CLI arguments
STYLE_MAP = {
    "Default": "0",
    "Natural": "1",
    "Cinematic": "2"
}

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}

# NVENC hardware encoder maximum widths per codec
ENCODER_WIDTH_LIMITS = {"H264": 4096, "HEVC": 8192, "AV1": 8192, "ProRes Proxy": 32768}

# Display label -> value stored in the preset
DLSS_MODE_MAP = {
    "1x (DLAA / native)": "DLAA",
    "1.5x (Quality)": "Quality",
    "1.724x (Balanced)": "Balanced",
    "2x (Performance)": "Performance",
    "3x (Ultra Performance)": "Ultra Performance",
}

DLSS_PRESETS = ["Default", "J", "K", "L", "M"]


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
    """Validate video path is within ComfyUI input or output folder.
    Supports both input-relative paths and ComfyUI-root-relative paths."""
    path_str = video_path.strip().strip('"')
    if not path_str:
        raise Exception("Video path cannot be empty")

    input_dir = Path(folder_paths.get_input_directory()).resolve()
    output_dir = Path(folder_paths.get_output_directory()).resolve()
    comfyui_root = Path(folder_paths.base_path).resolve()
    comfyui_parent = comfyui_root.parent

    if path_str.startswith('/') or path_str.startswith('\\') or path_str.startswith('\\\\') or (len(path_str) > 1 and path_str[1] == ':'):
        full_path = Path(path_str).resolve()
        if not (str(full_path).startswith(str(input_dir)) or str(full_path).startswith(str(output_dir))):
            raise Exception("Absolute video paths must be inside the ComfyUI input or output folder.")
        if not full_path.is_file():
            raise Exception(f"Video file not found: {full_path}")
        return full_path

    if '..' in path_str.split('/') or '..' in path_str.split('\\'):
        raise Exception("Video path cannot contain '..'")

    # Try relative to ComfyUI parent (VideoHelperSuite format)
    candidate = (comfyui_parent / path_str).resolve()
    if (str(candidate).startswith(str(input_dir)) or str(candidate).startswith(str(output_dir))) and candidate.is_file():
        return candidate

    # Try relative to input/output directories
    for base in (input_dir, output_dir):
        candidate = (base / path_str).resolve()
        if str(candidate).startswith(str(base)) and candidate.is_file():
            return candidate

    # Try relative to ComfyUI root
    candidate = (comfyui_root / path_str).resolve()
    if (str(candidate).startswith(str(input_dir)) or str(candidate).startswith(str(output_dir))) and candidate.is_file():
        return candidate

    raise Exception(f"Video file not found in input or output folder: {path_str}")


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


def find_ffmpeg_tools():
    """Locate ffprobe (preferred) and ffmpeg (fallback)."""
    ffprobe_exe = shutil.which("ffprobe")
    ffmpeg_exe = None
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    if not ffmpeg_exe:
        ffmpeg_exe = shutil.which("ffmpeg")
    if not ffprobe_exe and ffmpeg_exe:
        sibling = Path(ffmpeg_exe).parent / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if sibling.is_file():
            ffprobe_exe = str(sibling)
    return ffmpeg_exe, ffprobe_exe


def probe_video_info(video_path: Path) -> dict:
    """Return fps, frame_count, duration, width and height as a dict."""
    info = {"fps": 0.0, "frame_count": 0, "duration": 0.0, "width": 0, "height": 0}
    ffmpeg_exe, ffprobe_exe = find_ffmpeg_tools()

    if ffprobe_exe:
        try:
            result = subprocess.run(
                [ffprobe_exe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height,avg_frame_rate,nb_frames",
                 "-show_entries", "format=duration",
                 "-of", "json", str(video_path)],
                capture_output=True, text=True)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                stream = (data.get("streams") or [{}])[0]
                fmt = data.get("format", {})
                fps = 0.0
                fr = str(stream.get("avg_frame_rate", "0/1"))
                if "/" in fr:
                    num, den = fr.split("/")
                    if float(den) > 0:
                        fps = float(num) / float(den)
                else:
                    fps = float(fr)
                duration = float(fmt.get("duration") or 0.0)
                nb = stream.get("nb_frames")
                if nb and nb != "N/A":
                    frame_count = int(nb)
                else:
                    frame_count = round(duration * fps) if fps > 0 else 0
                info.update({
                    "fps": round(fps, 3),
                    "frame_count": frame_count,
                    "duration": round(duration, 3),
                    "width": int(stream.get("width", 0)),
                    "height": int(stream.get("height", 0)),
                })
                return info
        except Exception:
            pass

    if ffmpeg_exe:
        try:
            result = subprocess.run([ffmpeg_exe, "-hide_banner", "-i", str(video_path)],
                                    capture_output=True, text=True)
            err = result.stderr
            dur_m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
            if dur_m:
                h, m, s = dur_m.groups()
                info["duration"] = round(int(h) * 3600 + int(m) * 60 + float(s), 3)
            size_m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
            if size_m:
                info["width"], info["height"] = int(size_m.group(1)), int(size_m.group(2))
            fps_m = re.search(r"(\d+(?:\.\d+)?)\s*fps", err)
            if fps_m:
                info["fps"] = round(float(fps_m.group(1)), 3)
            count = subprocess.run(
                [ffmpeg_exe, "-i", str(video_path), "-map", "0:v:0", "-c", "copy", "-f", "null", "-"],
                capture_output=True, text=True)
            frames = re.findall(r"frame=\s*(\d+)", count.stderr)
            if frames:
                info["frame_count"] = int(frames[-1])
            elif info["fps"] > 0 and info["duration"] > 0:
                info["frame_count"] = round(info["fps"] * info["duration"])
        except Exception:
            pass
    return info


def _hash_file(path: Path, algo="sha1"):
    """Fast content hash used for upload deduplication."""
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024 * 8), b""):
            h.update(chunk)
    return h.hexdigest()


def write_preset_file(preset_json: str, tmpdir: Path):
    """Validate preset JSON content, sanitize conflicting export settings, and write to tmpdir."""
    if not preset_json or not preset_json.strip():
        return None
    try:
        data = json.loads(preset_json)
    except Exception as e:
        raise Exception(f"Invalid preset JSON: {e}")
    if not isinstance(data, dict):
        raise Exception("Preset JSON must be a top-level object.")

    # Force the schema version the CLI accepts (38).
    data["schema_version"] = 38

    settings = data.get("settings", {})
    if isinstance(settings, dict):
        keys_to_strip = [
            "codec", "container", "quality",
            "frame_interpolation_codec", "frame_interpolation_container", "frame_interpolation_quality",
            "vfx_frame_generation_enabled", "vfx_frame_multiplier", "vfx_target_fps",
            "upscale_vsr_enabled", "upscale_engine", "upscale_image_engine",
            "upscale_aspect_lock", "upscale_codec", "upscale_container",
            "upscale_custom_suffix",
            "upscale_height", "upscale_image_aspect_lock", "upscale_image_custom_suffix",
            "upscale_image_height", "upscale_image_output_format", "upscale_image_quality",
            "upscale_image_rename_mode", "upscale_image_scale_factor", "upscale_image_size_mode",
            "upscale_image_vsr_quality", "upscale_image_width", "upscale_mode",
            "upscale_optical_flow_quality", "upscale_preview_length", "upscale_quality",
            "upscale_rename_mode", "upscale_scale_factor", "upscale_size_mode",
            "upscale_vsr_quality", "upscale_width",
            "upscale_hdr_precision", "upscale_hdr_enabled", "upscale_hdr_contrast",
            "upscale_hdr_middle_gray", "upscale_hdr_peak_luminance", "upscale_hdr_saturation",
            "hdr_mode", "frame_interpolation_hdr_mode",
        ]
        for k in keys_to_strip:
            settings.pop(k, None)
        data["settings"] = settings

    path = tmpdir / "dlss5_preset.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def ensure_preset_stages(preset_json: str, stages_key: str, required_stages) -> str:
    """Ensure required pipeline stages are enabled in a preset's settings."""
    if not preset_json or not preset_json.strip():
        return preset_json
    try:
        data = json.loads(preset_json)
    except Exception:
        return preset_json
    if not isinstance(data, dict):
        return preset_json
    settings = data.get("settings")
    if not isinstance(settings, dict):
        settings = {}
        data["settings"] = settings
    enabled = settings.get(stages_key)
    if not isinstance(enabled, list):
        enabled = []
    changed = False
    for st in required_stages:
        if st not in enabled:
            enabled.append(st)
            changed = True
    if changed:
        settings[stages_key] = enabled
        return json.dumps(data)
    return preset_json


def inject_nr_passes(preset_json: str, passes: int) -> str:
    """Inject NR Passes into the preset JSON settings."""
    if preset_json and preset_json.strip():
        try:
            data = json.loads(preset_json)
        except Exception:
            data = {"format": "dlss5-visual-enhancer-settings-preset", "name": "comfyui", "schema_version": 38, "settings": {}}
    else:
        data = {"format": "dlss5-visual-enhancer-settings-preset", "name": "comfyui", "schema_version": 38, "settings": {}}

    if not isinstance(data, dict):
        data = {"format": "dlss5-visual-enhancer-settings-preset", "name": "comfyui", "schema_version": 38, "settings": {}}

    settings = data.setdefault("settings", {})
    settings["nr_passes"] = passes

    return json.dumps(data)


class DLSS5_RTX_Enhance_v17:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "Images": ("IMAGE",),
                "NR Style": (["Default", "Natural", "Cinematic"], {"default": "Default"}),
                "NR Intensity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "NR Passes": ("INT", {"default": 1, "min": 1, "max": 4, "step": 1}),
                "Scale": ("FLOAT", {"default": 2.0, "min": 1.0, "max": 16.0, "step": 0.5, "tooltip": "Scale factor. Up to 16.0 (1600%) supported in v17.5+"}),
                "Ray Reconstruction": ("BOOLEAN", {"default": False, "tooltip": "Enable DLSS Ray Reconstruction at native resolution (1x) for high-precision color handling."}),
            },
            "optional": {
                "Pro Controls": ("STRING", {"default": "", "forceInput": True, "tooltip": "Output from DLSS5 Pro Controls node."}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "process"
    CATEGORY = "DLSS5_v17"

    def process(self, **kwargs):
        images = kwargs.get("Images")
        nr_style = kwargs.get("NR Style", "Default")
        nr_intensity = kwargs.get("NR Intensity", 1.0)
        nr_passes = kwargs.get("NR Passes", 1)
        scale = kwargs.get("Scale", 2.0)
        ray_reconstruction = kwargs.get("Ray Reconstruction", False)
        pro_controls = kwargs.get("Pro Controls", "")

        cli_path = find_cli()
        output_images = []
        cli_style = STYLE_MAP.get(nr_style, "0")
        fmt = "png"
        ext = ".png"

        # Inject NR Passes into the incoming Pro Controls JSON
        preset_json = inject_nr_passes(pro_controls, nr_passes)

        for img in images:
            i = 255.0 * img.cpu().numpy()
            img_pil = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            with tempfile.TemporaryDirectory() as tmpdir:
                input_path = Path(tmpdir) / f"input{ext}"
                render_path = Path(tmpdir) / f"render_out{ext}"
                upscale_path = Path(tmpdir) / f"upscale_out{ext}"
                img_pil.save(str(input_path))

                if ray_reconstruction:
                    preset_json_eff = ensure_preset_stages(preset_json, "image_enabled_stages", ["dlss_ray_reconstruction"])
                    cmd_render = [str(cli_path), "reconstruct", str(input_path), "-o", str(render_path), "--format", fmt, "--gpu", "auto", "--quiet", "--json"]
                else:
                    preset_json_eff = ensure_preset_stages(preset_json, "image_enabled_stages", ["neural_model"])
                    cmd_render = [str(cli_path), "render", str(input_path), "-o", str(render_path), "--style", cli_style, "--strength", str(nr_intensity), "--format", fmt, "--gpu", "auto", "--quiet", "--json"]

                preset_path = write_preset_file(preset_json_eff, Path(tmpdir))
                if preset_path:
                    cmd_render.extend(["--preset", str(preset_path)])

                result = subprocess.run(cmd_render, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"DLSS5 Image Process failed: {result.stderr}")

                final_path = render_path
                if scale > 1.0:
                    cmd_upscale = [str(cli_path), "upscale", str(render_path), "-o", str(upscale_path), "--engine", "rtx", "--scale", str(scale), "--format", fmt, "--gpu", "auto", "--quiet", "--json"]
                    result = subprocess.run(cmd_upscale, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise Exception(f"DLSS5 Image Upscale failed: {result.stderr}")
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
                "Video Path": ("STRING", {"default": "", "multiline": False, "tooltip": "Relative path to video file within ComfyUI input folder, or a linked path from another node."}),
                "NR Style": (["Default", "Natural", "Cinematic"], {"default": "Default"}),
                "NR Intensity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "NR Passes": ("INT", {"default": 1, "min": 1, "max": 4, "step": 1}),
                "Scale": ("FLOAT", {"default": 1.0, "min": 1.0, "max": 16.0, "step": 0.5, "tooltip": "Scale factor. Up to 16.0 (1600%) supported in v17.5+"}),
                "Codec": (["HEVC", "H264", "AV1", "ProRes Proxy"], {"default": "H264"}),
                "Container": (["MKV", "MP4", "MOV"], {"default": "MP4"}),
                "Encoder Quality": (["Auto", "Good", "Best", "Max"], {"default": "Auto"}),
                "Target FPS": ("INT", {"default": 0, "min": 0, "max": 120, "step": 1, "tooltip": "0 = disabled. Target FPS for DLSS Frame Generation (Requires RTX 40/50 Series)."}),
                "Ray Reconstruction": ("BOOLEAN", {"default": False, "tooltip": "Enable DLSS Ray Reconstruction for video. WARNING: Mutually exclusive with 'DLSS Super Resolution' in Pro Controls."}),
                "Optical Flow Quality": (["Disabled", "High", "Medium", "Low"], {"default": "Disabled", "tooltip": "NVIDIA Optical Flow quality for Ray Reconstruction video."}),
                "Filename Prefix": ("STRING", {"default": "DLSS5", "multiline": False}),
                "Output Directory": ("STRING", {"default": "", "multiline": False, "tooltip": "Relative path within ComfyUI output directory"}),
                "Copy Audio": ("BOOLEAN", {"default": True}),
                "Input FPS": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 1.0, "tooltip": "Frame rate used ONLY when encoding an IMAGE batch into a temporary video."}),
            },
            "optional": {
                "Images": ("IMAGE", {"tooltip": "Optional: Pass an IMAGE batch (e.g. from VideoHelperSuite). The node will encode it to a temp video for flicker-free processing."}),
                "Audio": ("AUDIO", {"tooltip": "Optional: Audio track to mux into the temporary video when using an IMAGE batch."}),
                "Pro Controls": ("STRING", {"default": "", "forceInput": True, "tooltip": "Output from DLSS5 Pro Controls node."}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("output_path",)
    FUNCTION = "process_video_file"
    CATEGORY = "DLSS5_v17"

    def process_video_file(self, **kwargs):
        video_path = kwargs.get("Video Path", "")
        images = kwargs.get("Images", None)
        audio = kwargs.get("Audio", None)
        nr_style = kwargs.get("NR Style", "Default")
        nr_intensity = kwargs.get("NR Intensity", 1.0)
        nr_passes = kwargs.get("NR Passes", 1)
        scale = kwargs.get("Scale", 1.0)
        codec = kwargs.get("Codec", "H264")
        container = kwargs.get("Container", "MP4")
        encoder_quality = kwargs.get("Encoder Quality", "Auto")
        target_fps = kwargs.get("Target FPS", 0)
        ray_reconstruction = kwargs.get("Ray Reconstruction", False)
        optical_flow_quality = kwargs.get("Optical Flow Quality", "Disabled")
        filename_prefix = kwargs.get("Filename Prefix", "DLSS5")
        output_directory = kwargs.get("Output Directory", "")
        copy_audio = kwargs.get("Copy Audio", True)
        pro_controls = kwargs.get("Pro Controls", "")
        input_fps = kwargs.get("Input FPS", 24.0)

        cli_path = find_cli()
        cli_style = STYLE_MAP.get(nr_style, "0")

        # 1. Determine the input source (Images batch OR Video Path)
        input_path = None
        run_tmpdir = None
        final_audio_source = None

        if images is not None:
            print("[DLSS5 Video] Received IMAGE batch. Encoding to temporary video for temporal stability...")
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

            # Convert tensor [B, H, W, C] to numpy [B, H, W, 3] uint8
            img_np = np.clip(images.cpu().numpy() * 255.0, 0, 255).astype(np.uint8)

            # CRITICAL CHECK: The DLSS CLI requires at least 2 frames to encode a video.
            if img_np.shape[0] < 2:
                raise Exception(f"The DLSS CLI requires at least 2 frames to process video. The input batch only contains {img_np.shape[0]} frame(s). This usually happens if the video loader failed to read the file. Please check your video path or use the 'DLSS5 Enhance (Image)' node for single images.")

            run_tmpdir = Path(tempfile.mkdtemp(prefix="dlss5_hybrid_"))
            temp_silent_path = run_tmpdir / "temp_input_silent.mp4"

            try:
                writer = imageio_ffmpeg.write_frames(str(temp_silent_path), (img_np.shape[2], img_np.shape[1]), fps=input_fps)
                writer.send(None)
                for frame in img_np:
                    writer.send(frame)
                writer.close()

                if not temp_silent_path.exists() or temp_silent_path.stat().st_size == 0:
                    raise Exception("Failed to create temporary video file.")

                print(f"[DLSS5 Video] Encoded {len(img_np)} frames to silent temp video at {input_fps} FPS.")
                input_path = temp_silent_path
            except Exception as e:
                raise Exception(f"Error encoding images to temp video: {e}")

            # Handle Audio Extraction (but don't mux yet!)
            if audio is not None and copy_audio:
                print("[DLSS5 Video] Preparing audio for final muxing...")
                temp_audio_path = run_tmpdir / "temp_audio.wav"

                try:
                    waveform = None
                    sample_rate = 44100
                    audio_file_path = None

                    # Robust extraction logic
                    if hasattr(audio, 'get_audio'):
                        waveform, sample_rate = audio.get_audio()
                    elif isinstance(audio, dict):
                        waveform = audio.get('waveform')
                        sample_rate = audio.get('sample_rate', 44100)
                    else:
                        for attr in ['audio_path', 'file_path', 'path', 'source_path']:
                            if hasattr(audio, attr):
                                audio_file_path = getattr(audio, attr)
                                break
                        if audio_file_path is None:
                            try:
                                waveform = audio['waveform']
                                sample_rate = audio['sample_rate']
                            except:
                                raise Exception(f"Unsupported audio format: {type(audio)}")

                    if audio_file_path:
                        print(f"[DLSS5 Video] Using source audio file directly: {audio_file_path}")
                        final_audio_source = audio_file_path
                    else:
                        # Convert tensor to WAV using built-in wave module
                        if waveform is not None and waveform.dim() == 3:
                            waveform = waveform.squeeze(0)

                        data = np.clip(waveform.cpu().numpy() * 32767, -32768, 32767).astype(np.int16)
                        channels, samples = data.shape[0], data.shape[1]

                        with wave.open(str(temp_audio_path), 'w') as wav_file:
                            wav_file.setnchannels(channels)
                            wav_file.setsampwidth(2)
                            wav_file.setframerate(sample_rate)
                            wav_file.setnframes(samples)
                            wav_file.setcomptype('NONE', 'not compressed')
                            if channels > 1:
                                data = data.T.flatten()
                            wav_file.writeframes(data.tobytes())

                        final_audio_source = str(temp_audio_path)
                        print("[DLSS5 Video] Audio saved to temporary WAV file.")

                except Exception as e:
                    print(f"[Warning] Failed to prepare audio: {e}. Output will be silent.")
                    copy_audio = False
        else:
            if not video_path:
                raise Exception("Either 'Video Path' or 'Images' must be provided.")
            input_path = validate_video_path(video_path)
            if copy_audio:
                final_audio_source = str(input_path)

        if input_path is None:
            raise Exception("No valid input path determined.")

        out_dir = validate_output_path(output_directory, filename_prefix)

        if scale > 1.0:
            src_info = probe_video_info(input_path)
            src_w, src_h = src_info.get("width", 0), src_info.get("height", 0)
            if src_w > 0:
                out_w, out_h = int(round(src_w * scale)), int(round(src_h * scale))
                # Ensure even dimensions for NVENC hardware encoder
                if out_w % 2 != 0:
                    out_w += 1
                if out_h % 2 != 0:
                    out_h += 1
                max_w = ENCODER_WIDTH_LIMITS.get(codec, 8192)
                if out_w > max_w:
                    max_scale = max_w / src_w
                    raise Exception(
                        f"Output resolution {out_w}x{out_h} exceeds the {codec} hardware "
                        f"encoder limit ({max_w} px max width). Switch codec to HEVC/AV1, "
                        f"or lower scale to {max_scale:.1f} or below."
                    )

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        container_ext = container.lower()
        final_filename = f"{filename_prefix}_{timestamp}.{container_ext}"
        final_output_path = out_dir / final_filename

        codec_map = {"HEVC": "hevc", "H264": "h264", "AV1": "av1", "ProRes Proxy": "prores"}
        quality_map = {"Auto": "auto", "Good": "good", "Best": "best", "Max": "max"}

        # Inject NR Passes into the incoming Pro Controls JSON
        preset_json = inject_nr_passes(pro_controls, nr_passes)

        # Use a temporary directory for intermediate CLI files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            render_path = tmpdir / f"render_out.{container_ext}"
            upscale_path = tmpdir / f"upscale_out.{container_ext}"

            if ray_reconstruction:
                print(f"[Video File] Processing with Ray Reconstruction...")
                preset_json_eff = ensure_preset_stages(preset_json, "video_enabled_stages", ["dlss_ray_reconstruction"])
                cmd = [str(cli_path), "reconstruct", str(input_path), "-o", str(render_path), "--gpu", "auto", "--quiet", "--json"]
                cmd.extend(["--codec", codec_map.get(codec, "hevc")])
                cmd.extend(["--container", container_ext])
                cmd.extend(["--quality", quality_map.get(encoder_quality, "auto")])

                if optical_flow_quality != "Disabled":
                    cmd.extend(["--flow-quality", optical_flow_quality.lower()])
            else:
                print(f"[Video File] Processing with Neural Render...")
                preset_json_eff = ensure_preset_stages(preset_json, "video_enabled_stages", ["neural_model"])
                cmd = [str(cli_path), "render", str(input_path), "-o", str(render_path), "--style", cli_style, "--strength", str(nr_intensity), "--gpu", "auto", "--quiet", "--json"]
                cmd.extend(["--codec", codec_map.get(codec, "hevc")])
                cmd.extend(["--container", container_ext])
                cmd.extend(["--quality", quality_map.get(encoder_quality, "auto")])

            preset_path = write_preset_file(preset_json_eff, tmpdir)
            if preset_path:
                cmd.extend(["--preset", str(preset_path)])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"DLSS5 Video Process failed: {result.stderr}")

            current_path = render_path

            if scale > 1.0:
                print(f"[Video File] Upscaling...")
                cmd_upscale = [str(cli_path), "upscale", str(render_path), "-o", str(upscale_path), "--engine", "rtx", "--scale", str(scale), "--codec", codec_map.get(codec, "hevc"), "--container", container_ext, "--quality", quality_map.get(encoder_quality, "auto"), "--gpu", "auto", "--quiet", "--json"]
                result = subprocess.run(cmd_upscale, capture_output=True, text=True)
                if result.returncode != 0:
                    raise Exception(f"DLSS5 Video Upscale failed: {result.stderr}")
                current_path = upscale_path

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

            # Final Muxing (Combine enhanced video with audio source)
            if copy_audio and final_audio_source:
                print(f"[Video File] Muxing audio to final output...")
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
                        "-i", str(final_audio_source),
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-shortest",
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

        # Cleanup the temp input directory if we created one from an image batch
        if run_tmpdir and run_tmpdir.exists():
            shutil.rmtree(run_tmpdir, ignore_errors=True)

        return (str(final_output_path),)


class DLSS5_Video_Path_Selector:
    """Robust video path selector that also loads frames and audio using ffmpeg."""
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "Video Path": ("STRING", {"default": "", "multiline": False, "tooltip": "Relative path within the input folder. Use the button to upload."}),
                "frame_load_cap": ("INT", {"default": 0, "min": 0, "max": 10000, "step": 1, "tooltip": "0 = load all frames. Limit this to prevent memory crashes on long videos."}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("STRING", "IMAGE", "AUDIO")
    RETURN_NAMES = ("video_path", "images", "audio")
    FUNCTION = "get_path"
    CATEGORY = "DLSS5_v17"

    def get_path(self, **kwargs):
        video_path = kwargs.get("Video Path", "")
        frame_load_cap = kwargs.get("frame_load_cap", 0)
        unique_id = kwargs.get("unique_id")

        empty_img = torch.zeros(1, 64, 64, 3, device="cpu")
        empty_audio = {"waveform": torch.zeros(1, 1, device="cpu"), "sample_rate": 44100}

        if not video_path:
            return ("", empty_img, empty_audio)

        try:
            full_path = validate_video_path(video_path)
        except Exception:
            return ("", empty_img, empty_audio)

        # 1. Load Video Frames using robust ffmpeg subprocess
        img_tensor = empty_img
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            info = probe_video_info(full_path)
            w, h = info["width"], info["height"]
            
            if w == 0 or h == 0:
                raise Exception("Could not determine video resolution.")

            cmd = [ffmpeg_exe, "-i", str(full_path)]
            if frame_load_cap > 0:
                cmd.extend(["-frames:v", str(frame_load_cap)])
            # Extract raw RGB frames to pipe
            cmd.extend(["-f", "image2pipe", "-pix_fmt", "rgb24", "-vcodec", "rawvideo", "-"])
            
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            frames = []
            frame_size = w * h * 3
            
            while True:
                raw_frame = proc.stdout.read(frame_size)
                if not raw_frame:
                    break
                frame_np = np.frombuffer(raw_frame, dtype=np.uint8).reshape((h, w, 3))
                frames.append(frame_np)
            proc.wait()
            
            if frames:
                img_np = np.stack(frames, axis=0)
                img_tensor = torch.from_numpy(img_np).float() / 255.0
                print(f"[DLSS5 Selector] Successfully loaded {len(frames)} frames.")
        except Exception as e:
            print(f"[DLSS5] Warning: Could not load video frames: {e}")

        # 2. Load Audio using ffmpeg + wave module
        audio_dict = empty_audio
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            with tempfile.TemporaryDirectory() as tmpdir:
                temp_wav = Path(tmpdir) / "temp_audio.wav"
                if subprocess.run([ffmpeg_exe, "-y", "-i", str(full_path), "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", str(temp_wav)], capture_output=True).returncode == 0 and temp_wav.exists():
                    import wave
                    with wave.open(str(temp_wav), 'rb') as wav_file:
                        n_channels, sample_width, framerate, n_frames = wav_file.getnchannels(), wav_file.getsampwidth(), wav_file.getframerate(), wav_file.getnframes()
                        audio_array = np.frombuffer(wav_file.readframes(n_frames), dtype=np.int16 if sample_width == 2 else np.int32)
                        audio_array = audio_array.reshape(-1, n_channels).T if n_channels > 1 else audio_array.reshape(1, -1)
                        audio_dict = {"waveform": torch.from_numpy(audio_array.astype(np.float32) / 32768.0), "sample_rate": framerate}
        except Exception:
            pass

        # 3. Trigger Preview Update
        if unique_id is not None:
            try:
                PromptServer.instance.send_sync("dlss5_preview", {"node_id": unique_id, "path": video_path})
            except Exception:
                pass
                
        return (video_path, img_tensor, audio_dict)


# ---------------------------------------------------------------------------
# Server routes for the frontend extension (upload button + video preview)
# ---------------------------------------------------------------------------
@PromptServer.instance.routes.get("/dlss5/view")
async def dlss5_view(request):
    rel = request.query.get("path", "")
    try:
        full = validate_video_path(rel)
    except Exception as e:
        return web.Response(status=400, text=str(e))
    return web.FileResponse(full)


@PromptServer.instance.routes.post("/dlss5/upload")
async def dlss5_upload(request):
    reader = await request.multipart()
    field = await reader.next()
    if field is None:
        return web.Response(status=400, text="No file received.")
    filename = Path(field.filename or "").name
    if Path(filename).suffix.lower() not in VIDEO_EXTS:
        return web.Response(status=400, text="Unsupported file type. Video files only.")

    target_dir = Path(folder_paths.get_input_directory())
    comfyui_parent = Path(folder_paths.base_path).parent

    # Stream the upload to a temp file while computing size + hash (single pass)
    h = hashlib.sha1()
    size = 0
    tmp_path = target_dir / f".dlss5_upload_{os.getpid()}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.part"
    try:
        with tmp_path.open("wb") as sink:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                sink.write(chunk)
                h.update(chunk)
                size += len(chunk)
        new_hash = h.hexdigest()

        # Look for an identical file ANYWHERE in the input tree (incl. subfolders).
        for candidate in target_dir.rglob("*"):
            if not candidate.is_file() or candidate.suffix.lower() not in VIDEO_EXTS:
                continue
            try:
                if candidate.stat().st_size != size:
                    continue
            except OSError:
                continue
            if _hash_file(candidate) == new_hash:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
                rel_path = candidate.relative_to(comfyui_parent).as_posix()
                print(f"[DLSS5] Upload dedup: reusing existing {rel_path}")
                return web.json_response({"path": rel_path})

        # No duplicate found: move into place
        target = target_dir / filename
        counter = 1
        while target.exists():
            target = target_dir / f"{Path(filename).stem}_{counter}{Path(filename).suffix}"
            counter += 1
        shutil.move(str(tmp_path), str(target))

        rel_path = target.relative_to(comfyui_parent).as_posix()
        return web.json_response({"path": rel_path})
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


class DLSS5_Pro_Controls:
    """Advanced native render controls: Local Structure & Tone, Auto Mask + Skin detail,
    and optional in-render DLSS Super Resolution (mode + model preset)."""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "optional": {
                "Local Tone Strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Local tone intensity (local_tone_strength). Range 0.0-1.0."}),
                "Local Structure Strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Local structure intensity (local_structure_strength). Range 0.0-1.0."}),
                "Automatic Mask": ("BOOLEAN", {"default": True, "tooltip": "Mirrors the app's Auto Mask toggle. When ON, skin enhancement is targeted to detected skin regions."}),
                "Skin Structure Strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Skin structure detail (skin_structure_strength). Only active when Automatic Mask is ON."}),
                "DLSS Super Resolution": ("BOOLEAN", {"default": False, "tooltip": "Enable the in-render DLSS Super Resolution stage. Keep the Enhance node's scale at 1.0 when using it."}),
                "DLSS Mode": (list(DLSS_MODE_MAP.keys()), {"default": "1x (DLAA / native)", "tooltip": "DLSS render scale mode. Only written when DLSS Super Resolution is ON."}),
                "DLSS Preset": (DLSS_PRESETS, {"default": "M", "tooltip": "DLSS model preset. Only written when DLSS Super Resolution is ON."}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("pro_controls",)
    FUNCTION = "build"
    CATEGORY = "DLSS5_v17"

    def build(self, **kwargs):
        tone = kwargs.get("Local Tone Strength", 1.0)
        structure = kwargs.get("Local Structure Strength", 1.0)
        auto_mask = kwargs.get("Automatic Mask", True)
        skin_detail = kwargs.get("Skin Structure Strength", 1.0)
        dlss_sr = kwargs.get("DLSS Super Resolution", False)
        dlss_mode = kwargs.get("DLSS Mode", "1x (DLAA / native)")
        dlss_preset = kwargs.get("DLSS Preset", "M")

        data = {
            "format": "dlss5-visual-enhancer-settings-preset",
            "name": "comfyui_pro_controls",
            "schema_version": 38,
            "settings": {},
        }

        settings = data.setdefault("settings", {})
        settings["local_tone_strength"] = tone
        settings["local_structure_strength"] = structure
        settings["automatic_mask"] = auto_mask
        settings["skin_structure_strength"] = skin_detail

        if dlss_sr:
            mode_value = DLSS_MODE_MAP.get(dlss_mode, "DLAA")
            settings["upscale_image_dlss_mode"] = mode_value
            settings["upscale_image_dlss_preset"] = dlss_preset
            settings["upscale_dlss_mode"] = mode_value
            settings["upscale_dlss_preset"] = dlss_preset
            for key in ("image_enabled_stages", "video_enabled_stages"):
                enabled = settings.get(key)
                if not isinstance(enabled, list):
                    enabled = []
                if "dlss_super_resolution" not in enabled:
                    enabled.append("dlss_super_resolution")
                settings[key] = enabled

        return (json.dumps(data),)


class DLSS5_Video_Info:
    """Probes any video path and returns technical info as JSON plus individual values."""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "Video Path": ("STRING", {"default": "", "multiline": False, "tooltip": "Video path. Designed to accept links, e.g. from DLSS5 Enhance (Video) output_path."}),
            },
        }

    RETURN_TYPES = ("STRING", "INT", "INT", "FLOAT", "INT")
    RETURN_NAMES = ("video_info", "width", "height", "fps", "frame_count")
    FUNCTION = "probe"
    CATEGORY = "DLSS5_v17"

    def probe(self, **kwargs):
        video_path = kwargs.get("Video Path", "")
        full_path = validate_video_path(video_path)
        info = probe_video_info(full_path)
        return (json.dumps(info), info["width"], info["height"], info["fps"], info["frame_count"])


class DLSS5_Color_Enhancement:
    """Adds Light and Color adjustments (LUT/Coloring stage) to the Pro Controls preset pipeline."""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "optional": {
                "Pro Controls": ("STRING", {"default": "", "forceInput": True, "tooltip": "Input from DLSS5 Pro Controls."}),
            },
            "required": {
                # Light Group
                "Exposure": ("FLOAT", {"default": 0.0, "min": -3.0, "max": 3.0, "step": 0.01, "tooltip": "Adjusts overall brightness (-3 to +3)."}),
                "Contrast": ("INT", {"default": 0, "min": -100, "max": 100}),
                "Highlights": ("INT", {"default": 0, "min": -100, "max": 100}),
                "Shadows": ("INT", {"default": 0, "min": -100, "max": 100}),
                "Whites": ("INT", {"default": 0, "min": -100, "max": 100}),
                "Blacks": ("INT", {"default": 0, "min": -100, "max": 100}),
                "Midtones": ("INT", {"default": 0, "min": -100, "max": 100}),
                # Color Group
                "Temperature": ("INT", {"default": 0, "min": -100, "max": 100, "tooltip": "Adjusts color temperature (-100 to +100)."}),
                "Tint": ("INT", {"default": 0, "min": -100, "max": 100}),
                "Hue Shift": ("INT", {"default": 0, "min": -180, "max": 180, "tooltip": "Adjusts hue (-180 to +180)."}),
                "Vibrance": ("INT", {"default": 0, "min": -100, "max": 100}),
                "Saturation": ("INT", {"default": 0, "min": -100, "max": 100}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("pro_controls",)
    FUNCTION = "build"
    CATEGORY = "DLSS5_v17"

    def build(self, **kwargs):
        pro_controls = kwargs.get("Pro Controls", "")

        # Parse existing JSON or create base
        if pro_controls and pro_controls.strip():
            try:
                data = json.loads(pro_controls)
            except Exception:
                data = {"format": "dlss5-visual-enhancer-settings-preset", "name": "comfyui_color", "schema_version": 38, "settings": {}}
        else:
            data = {"format": "dlss5-visual-enhancer-settings-preset", "name": "comfyui_color", "schema_version": 38, "settings": {}}

        if not isinstance(data, dict):
            data = {"format": "dlss5-visual-enhancer-settings-preset", "name": "comfyui_color", "schema_version": 38, "settings": {}}

        settings = data.setdefault("settings", {})

        # Inject Light settings (Direct mapping, 0 is neutral)
        settings["lut_exposure"] = kwargs.get("Exposure", 0.0)
        settings["lut_contrast"] = kwargs.get("Contrast", 0)
        settings["lut_highlights"] = kwargs.get("Highlights", 0)
        settings["lut_shadows"] = kwargs.get("Shadows", 0)
        settings["lut_whites"] = kwargs.get("Whites", 0)
        settings["lut_blacks"] = kwargs.get("Blacks", 0)
        settings["lut_midtones"] = kwargs.get("Midtones", 0)

        # Inject Color settings (Direct mapping, 0 is neutral)
        settings["lut_temperature"] = kwargs.get("Temperature", 0)
        settings["lut_tint"] = kwargs.get("Tint", 0)
        settings["lut_hue"] = kwargs.get("Hue Shift", 0)
        settings["lut_vibrance"] = kwargs.get("Vibrance", 0)
        settings["lut_saturation"] = kwargs.get("Saturation", 0)

        # Master mix for the stage (100 means fully applied)
        settings["lut_mix"] = 100

        # CRITICAL: Enable the "coloring" stage in the pipeline
        # The CLI ignores these settings unless the stage is in the enabled list.
        for key in ("image_enabled_stages", "video_enabled_stages"):
            enabled = settings.get(key)
            if not isinstance(enabled, list):
                enabled = []
            if "coloring" not in enabled:
                enabled.append("coloring")
            settings[key] = enabled

        return (json.dumps(data),)


class DLSS5_Sharpening_Grain:
    """Adds Sharpening and Grain adjustments to the Pro Controls preset pipeline."""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "optional": {
                "Pro Controls": ("STRING", {"default": "", "forceInput": True, "tooltip": "Input from DLSS5 Pro Controls."}),
            },
            "required": {
                # Sharpening Group
                "Sharpening": ("BOOLEAN", {"default": True, "tooltip": "Enable Sharpening."}),
                "Sharpening Method": (["NVIDIA NIS", "AMD CAS"], {"default": "NVIDIA NIS"}),
                "Sharpness": ("INT", {"default": 50, "min": 0, "max": 100, "tooltip": "Sharpness intensity (cas_sharpness)."}),
                # Grain Group
                "Grain": ("BOOLEAN", {"default": True, "tooltip": "Enable Grain."}),
                "Grain Amount": ("INT", {"default": 20, "min": 0, "max": 100}),
                "Grain Size": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 5.0, "step": 0.1}),
                "Color Grain": ("INT", {"default": 0, "min": 0, "max": 100}),
                "Tonal Response": ("INT", {"default": 70, "min": 0, "max": 100}),
                "Grain Seed": ("INT", {"default": 0, "min": 0, "max": 999999}),
                "Grain Animated": ("BOOLEAN", {"default": True, "tooltip": "Animate grain over time."}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("pro_controls",)
    FUNCTION = "build"
    CATEGORY = "DLSS5_v17"

    def build(self, **kwargs):
        pro_controls = kwargs.get("Pro Controls", "")

        # Parse existing JSON or create base
        if pro_controls and pro_controls.strip():
            try:
                data = json.loads(pro_controls)
            except Exception:
                data = {"format": "dlss5-visual-enhancer-settings-preset", "name": "comfyui_sg", "schema_version": 38, "settings": {}}
        else:
            data = {"format": "dlss5-visual-enhancer-settings-preset", "name": "comfyui_sg", "schema_version": 38, "settings": {}}

        if not isinstance(data, dict):
            data = {"format": "dlss5-visual-enhancer-settings-preset", "name": "comfyui_sg", "schema_version": 38, "settings": {}}

        settings = data.setdefault("settings", {})

        # Get toggle states
        enable_sharpening = kwargs.get("Sharpening", True)
        enable_grain = kwargs.get("Grain", True)

        # Inject Sharpening settings (Only if enabled)
        if enable_sharpening:
            settings["sharpening_method"] = kwargs.get("Sharpening Method", "NVIDIA NIS")
            settings["cas_sharpness"] = kwargs.get("Sharpness", 50)
        else:
            # Remove keys if disabled to ensure clean state
            settings.pop("sharpening_method", None)
            settings.pop("cas_sharpness", None)

        # Inject Grain settings (Only if enabled)
        if enable_grain:
            settings["grain_amount"] = kwargs.get("Grain Amount", 20)
            settings["grain_size"] = kwargs.get("Grain Size", 1.0)
            settings["grain_color"] = kwargs.get("Color Grain", 0)
            settings["grain_response"] = kwargs.get("Tonal Response", 70)
            settings["grain_seed"] = kwargs.get("Grain Seed", 0)
            settings["grain_animated"] = kwargs.get("Grain Animated", True)
        else:
            # Remove keys if disabled
            for k in ["grain_amount", "grain_size", "grain_color", "grain_response", "grain_seed", "grain_animated"]:
                settings.pop(k, None)

        # CRITICAL: Enable/Disable stages in the pipeline based on toggles
        for key in ("image_enabled_stages", "video_enabled_stages"):
            enabled = settings.get(key)
            if not isinstance(enabled, list):
                enabled = []

            # Handle Sharpening Stage
            if enable_sharpening:
                if "cas_sharpening" not in enabled:
                    enabled.append("cas_sharpening")
            else:
                if "cas_sharpening" in enabled:
                    enabled.remove("cas_sharpening")

            # Handle Grain Stage
            if enable_grain:
                if "grain" not in enabled:
                    enabled.append("grain")
            else:
                if "grain" in enabled:
                    enabled.remove("grain")

            settings[key] = enabled

        return (json.dumps(data),)


def _reinhard_transfer(source_uint8, reference_uint8):
    """Reinhard color transfer: makes 'source' adopt the color statistics of 'reference'.
    Operates in Lab space. Returns uint8 HxWx3."""
    # scikit-image expects float [0, 1]
    src = source_uint8.astype(np.float32) / 255.0
    ref = reference_uint8.astype(np.float32) / 255.0

    src_lab = rgb2lab(src)
    ref_lab = rgb2lab(ref)

    result_lab = np.empty_like(src_lab)
    for ch in range(3):
        s_mean, s_std = src_lab[..., ch].mean(), src_lab[..., ch].std()
        r_mean, r_std = ref_lab[..., ch].mean(), ref_lab[..., ch].std()
        s_std = max(s_std, 1e-5)
        r_std = max(r_std, 1e-5)
        # Map source distribution onto reference distribution
        result_lab[..., ch] = (src_lab[..., ch] - s_mean) * (r_std / s_std) + r_mean

    result_rgb = lab2rgb(result_lab)
    return np.clip(result_rgb * 255.0, 0, 255).astype(np.uint8)


class DLSS5_Color_Matcher:
    """Corrects the color drift of an enhanced image so its colors match a reference image.
    Place AFTER the Enhance node. Pure image processing — no CLI/LUT involved."""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "Source Image": ("IMAGE", {"tooltip": "The enhanced/drifted image (output of the Enhance node)."}),
                "Reference Image": ("IMAGE", {"tooltip": "The image whose colors you want (usually the original input)."}),
            },
            "optional": {
                "Match Strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                                             "tooltip": "Blend between original (0) and fully matched (1)."}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("matched_image",)
    FUNCTION = "match_colors"
    CATEGORY = "DLSS5_v17"

    def match_colors(self, **kwargs):
        source_image = kwargs.get("Source Image")
        reference_image = kwargs.get("Reference Image")
        strength = kwargs.get("Match Strength", 1.0)

        # ComfyUI tensors are [B, H, W, C] float [0, 1]
        src_uint8 = np.clip(source_image[0].cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
        ref_uint8 = np.clip(reference_image[0].cpu().numpy() * 255.0, 0, 255).astype(np.uint8)

        print("[DLSS5] Applying Reinhard color match...")
        matched_uint8 = _reinhard_transfer(src_uint8, ref_uint8)

        # Blend toward the uncorrected source based on Match Strength
        if strength < 1.0:
            matched_uint8 = (src_uint8.astype(np.float32) * (1.0 - strength)
                             + matched_uint8.astype(np.float32) * strength)
            matched_uint8 = np.clip(matched_uint8, 0, 255).astype(np.uint8)

        # Back to ComfyUI tensor [1, H, W, C] float [0, 1]
        out_tensor = torch.from_numpy(matched_uint8.astype(np.float32) / 255.0).unsqueeze(0)
        return (out_tensor,)


NODE_CLASS_MAPPINGS = {
    "DLSS5_Enhance_Image": DLSS5_RTX_Enhance_v17,
    "DLSS5_Enhance_Video": DLSS5_Video_File_Enhance_v17,
    "DLSS5_Video_Path_Selector": DLSS5_Video_Path_Selector,
    "DLSS5_Video_Info": DLSS5_Video_Info,
    "DLSS5_Pro_Controls": DLSS5_Pro_Controls,
    "DLSS5_Color_Enhancement": DLSS5_Color_Enhancement,
    "DLSS5_Sharpening_Grain": DLSS5_Sharpening_Grain,
    "DLSS5_Color_Matcher": DLSS5_Color_Matcher,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DLSS5_Enhance_Image": "DLSS5 Enhance (Image)",
    "DLSS5_Enhance_Video": "DLSS5 Enhance (Video)",
    "DLSS5_Video_Path_Selector": "DLSS5 Video Path Selector",
    "DLSS5_Video_Info": "DLSS5 Video Info",
    "DLSS5_Pro_Controls": "DLSS5 Pro Controls",
    "DLSS5_Color_Enhancement": "DLSS5 Color Enhancement",
    "DLSS5_Sharpening_Grain": "DLSS5 Sharpening & Grain",
    "DLSS5_Color_Matcher": "DLSS5 Color Matcher",
}