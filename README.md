# ComfyUI-DLSS5-Enhancer

Run NVIDIA DLSS 5 Neural Rendering over your frames and videos, directly inside ComfyUI.

DLSS 5 is NVIDIA's neural rendering pass. In a game, it reconstructs the material and lighting detail that real-time rendering has to leave out, such as skin subsurface scattering, light transmission through hair, and contact shadows. This node pack drives that same native renderer over video frames and image batches, with optional 1x to 16x RTX upscaling, DLSS Ray Reconstruction, and DLSS Frame Generation.

It is not a filter that imitates a look. Frames go to the native renderer and come back reconstructed. The model reconstructs materials and recovers structure (skin, hair, fabric) that the source only implied, rather than just sharpening edges.

Unlike older community implementations that relied on ReShade injection, this pack drives the official **v17.5** headless CLI (`VE_CLI.exe`), providing a stable, native, and highly optimized pipeline.

> **Acknowledgment:** This node pack acts as a bridge to the excellent [DLSS 5 Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer) project by Merserk. All underlying AI rendering, upscaling, and frame generation capabilities are powered by their work and the official NVIDIA runtime. This project simply makes that powerful technology accessible directly within ComfyUI workflows.

## 🚀 What's New in v1.1.0

This update brings the node pack up to date with the official **DLSS 5 Visual Enhancer v17.5** runtime, featuring the latest **NVIDIA NGX Core version 310.9.16.0** (as of October 2026).

### Component Version
* **NVIDIA NGX Core:** `310.9.16.0`
* **Release Date:** October 2026

### What This Update Is
This update delivers a major model optimization for **DLSS 5 Neural Rendering**. It uses advanced AI to replace traditional hand-tuned pipelines with photorealistic, AI-generated lighting, materials, and subsurface scattering, directly within your ComfyUI workflows.

### Core Improvements for ComfyUI

* **Reduced VRAM Consumption:** The optimized neural rendering model slashes the parameter count by **24%** and drops VRAM consumption by **20%**. This significantly reduces the chance of Out-Of-Memory errors when processing high-resolution images or long videos.
* **Faster Render Times:** Neural workloads process up to **2x faster**, drastically lowering the time it takes to render frames and export videos.
* **Greater Temporal Stability:** Operates on a refined single-frame-in, single-frame-out model that ensures rock-solid temporal stability, entirely eliminating AI shimmering, ghosting, or drifting in generated videos.
* **Expanded Hardware Support:** Officially broadens support across the **NVIDIA GeForce RTX 50 Series** desktop GPUs and laptops.
* **New Features:** Added native 1x resolution Ray Reconstruction, NVIDIA Optical Flow for video, and expanded upscaling up to 16x (1600%).

## How it Works

This pack acts as a bridge between ComfyUI and the native DLSS 5 Visual Enhancer CLI.

1. **Neural Rendering & Ray Reconstruction:** The node exports your frames or passes your video file path to `VE_CLI.exe`. The CLI handles the D3D12 process, hosting the native NVIDIA runtime to reconstruct high-frequency material details. In v17.5, the dedicated `reconstruct` command is used for native-resolution (1x) Ray Reconstruction with high-precision color handling.
2. **RTX Upscaling:** If requested, the reconstructed frames are passed through NVIDIA's RTX Super Resolution engine to intelligently enlarge the image up to 16x its original size.
3. **NVIDIA Optical Flow:** Adds temporal stability and quality options (High, Medium, Low) for Ray Reconstruction video workflows.
4. **DLSS Frame Generation:** Optionally interpolates video to a target FPS using DLSS Frame Generation for ultra-smooth playback. (Requires RTX 40 or 50 Series GPU).
5. **Video Pipeline:** For video files, the CLI processes the entire file natively in a single pass. This allows the AI to maintain temporal consistency, preventing the flickering and jitter common in frame-by-frame upscaling, while efficiently handling audio and metadata.

## Requirements

| Item | Requirement |
| --- | --- |
| **GPU** | NVIDIA RTX 20, 30, 40, or 50 Series. (GTX, AMD, and Intel GPUs are not supported as they lack the required Tensor Cores). |
| **GPU (Frame Gen)** | DLSS Frame Generation requires RTX 40 or 50 Series. Enable Hardware-accelerated GPU scheduling in Windows. |
| **Driver** | A recent NVIDIA Game Ready or Studio Driver (560.xx or newer recommended). |
| **OS** | Windows only. |
| **ComfyUI** | A recent build supporting standard `IMAGE` and `VIDEO` tensor types. |

## Installation

### Step 1: Install the Node Pack
Clone this repository into your `ComfyUI/custom_nodes/` folder:
```bash
git clone https://github.com/Strix-3D/ComfyUI-DLSS5-Enhancer-v15.git
```
*(Alternatively, if published to ComfyUI Manager, search for `DLSS5-Enhancer` and click Install).*

**Important for Manual Installations:** If you cloned the repository manually (rather than using ComfyUI Manager), you must install the Python dependencies. Open a PowerShell window in your main ComfyUI folder and run:
```powershell
.\python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-DLSS5-Enhancer-v15\requirements.txt
```

### Step 2: Download the Runtime & Accept the License
This node pack does not include the proprietary NVIDIA binaries. You must download them using the included installer script.

1. Open a PowerShell window in your main ComfyUI folder (the one containing `python_embeded`).
2. Run the following command:
   ```powershell
   .\python_embeded\python.exe ComfyUI\custom_nodes\ComfyUI-DLSS5-Enhancer-v15\install.py
   ```
3. **Read the License Notice:** The script will display a list of third-party components (NVIDIA, FFmpeg, mpv, etc.) and their respective licenses.
4. **Accept the Terms:** The script will automatically proceed with the download. By installing this node pack, you accept the terms.
5. Wait for the ~700MB runtime to download and extract into the `runtime/` folder.

### Step 3: Restart ComfyUI
Once the installation is complete, restart ComfyUI. The nodes will now appear in your menu under the `DLSS5_v17` category.

---

## ⚡ Quick Reference Cheat Sheet

### 🚀 TL;DR: Common Workflows
| Goal | Settings to Use |
| --- | --- |
| **Upscale AI Image to 4K** | `scale: 2.0` or `4.0`, `style: Default`, `strength: 1.0` |
| **Fix AI Video Flicker/Boiling** | `scale: 1.0`, `style: Natural`, `strength: 0.8` |
| **Smooth 30fps Video to 60fps** | `target_fps: 60` *(Requires RTX 40/50 GPU)* |
| **High-Precision 3D/Render Cleanup** | Enable `ray_reconstruction`, `style: Default` |
| **Maximum Contrast/Punch** | `style: Cinematic`, `strength: 1.0` |
| **Pick a video without typing paths** | Use the `DLSS5 Video Path Selector` node (type, upload, or link a path) |
| **Chain a second processing pass** | Link `output_path` ➔ a second Enhance node's `video_path` |
| **Inspect fps / resolution / frame count** | Use the `DLSS5 Video Info` node |

### 🧠 Widget Pro-Tips
| Widget | What it actually does | Pro-Tip / Gotcha |
| --- | --- | --- |
| **style** | Dictates the AI's reconstruction "personality". | `Natural` is best for faces. `Cinematic` adds contrast but can crush shadows. |
| **strength** | Intensity of the neural effect. | **Never go above 1.5** unless you want AI hallucinations and weird artifacts. |
| **scale** | RTX Upscaling multiplier. | Set to `1.0` to skip upscaling entirely and just apply Neural Rendering. |
| **codec** | The hardware encoder used for output. | `H264` caps at 4096 px wide. Use `HEVC` or `AV1` for outputs wider than 4K. |
| **ray_reconstruction** | Native 1x reconstruction for ray-traced data. | **Useless for standard AI images.** Only enable this if processing 3D renders or RTX game captures. |
| **optical_flow_quality** | Temporal stability for Ray Reconstruction. | Only works if `ray_reconstruction` is enabled. Use `High` for final renders, `Low` for fast previews. |
| **target_fps** | DLSS Frame Generation interpolation. | **RTX 40/50 ONLY.** Will fail silently or throw an error on RTX 20/30 cards. |

###  Hardware Capability Cheat Sheet
| GPU Series | Neural Rendering | RTX Upscaling (up to 16x) | DLSS Frame Generation |
| --- | :---: | :---: | :---: |
| **RTX 50 Series** | ✅ | ✅ | ✅ |
| **RTX 40 Series** | ✅ | ✅ | ✅ |
| **RTX 30 Series** | ✅ | ✅ | ❌ |
| **RTX 20 Series** | ✅ | ✅ | ❌ |
| **GTX / AMD / Intel** | ❌ | ❌ | ❌ |

### ⚙️ CLI Flag Mapping (For Advanced Users)
If you are using the `VE_CLI.exe` manually via terminal, here is how the ComfyUI widgets map to the CLI flags:
| ComfyUI Widget | CLI Command / Flag |
| --- | --- |
| `style` (Default/Natural/Cinematic) | `--style 0`, `--style 1`, `--style 2` |
| `strength` | `--strength [0.0 to 2.0]` |
| `ray_reconstruction` (Enabled) | Uses `reconstruct` command instead of `render` |
| `optical_flow_quality` | `--flow-quality high`, `medium`, or `low` |
| `scale` | `--scale [1.0 to 16.0]` |
| `target_fps` | Uses `interpolate` command with `--fps [value]` |

---

## Nodes & Controls

This pack includes four highly optimized nodes:

### 1. DLSS5 Enhance (Image)
Takes an `IMAGE` batch, applies Neural Rendering (or Ray Reconstruction), and optionally upscales it. Outputs an `IMAGE` batch.

### 2. DLSS5 Enhance (Video)
Takes a file path string, processes the video natively via the CLI, and saves the result to your output directory. Outputs the new file path string (`output_path`) and the frame count (`frames`).

### 3. DLSS5 Video Path Selector
Browse, upload, and chain video paths without ever typing them by hand.
* **Single linkable `video_path` field:** type a relative path, or plug in a link directly (e.g. another node's `output_path` for multi-pass chaining).
* **"Choose file to upload..." button:** uploads a video from your computer into the ComfyUI input folder and fills the path in automatically (duplicate names are auto-renamed).
* **Live video preview:** updates when you upload, when you type, and every time the node executes — including when the path arrives via a link.
* **Outputs:** `video_path` (STRING) and `video_info` (JSON with fps, frame_count, duration, width, height).

### 4. DLSS5 Video Info
A lightweight probe node designed for chaining. Plug any video path in (e.g. an Enhance node's `output_path`) and get technical metadata out.
* **Outputs:** `video_info` (JSON), plus individual `width`, `height`, `fps` and `frame_count` values you can feed into math/logic nodes.
* No dropdown and no preview — whatever path arrives on the input is exactly what gets probed on every run.

### Shared Controls
| Widget | Options / Range | Effect |
| --- | --- | --- |
| **style** | Default, Natural, Cinematic | **Default:** Balanced detail reconstruction. <br> **Natural:** Subtle enhancement, preserves original textures. <br> **Cinematic:** Aggressive contrast and micro-detail enhancement. |
| **strength** | 0.00 to 2.00 (Default: 1.0) | The intensity of the Neural Rendering effect. 1.0 is the standard NVIDIA tuning. Values > 1.5 can cause AI "hallucinations" (weird artifacts). |
| **scale** | 1.0 to 16.0 (Default: 1.0) | The RTX upscaling multiplier. Set to 1.0 to skip upscaling entirely and only apply Neural Rendering. **Up to 16x (1600%) supported in v17.5+.** |
| **ray_reconstruction** | BOOLEAN (Default: False) | Enable DLSS Ray Reconstruction at native resolution (1x) using the dedicated reconstruction runtime with high-precision color handling. |
| **optical_flow_quality** | Disabled, High, Medium, Low | NVIDIA Optical Flow quality for Ray Reconstruction video previews. Adds temporal stability. |

### Video File Specific Controls
| Widget | Options / Range | Effect |
| --- | --- | --- |
| **video_path** | STRING | Relative path to video file within ComfyUI input folder (e.g., `my_video.mp4`), or an absolute path inside the input/output folder (enables chaining from other nodes). Paths outside ComfyUI folders are blocked for security. |
| **codec** | HEVC, H264, AV1, ProRes Proxy | The video encoder to use. H264 is recommended for maximum compatibility, but caps at 4096 px wide — use HEVC/AV1 for wider outputs. |
| **container** | MKV, MP4, MOV | The output file container format. |
| **quality** | Auto, Good, Best, Max | Encoding quality/bitrate. |
| **target_fps** | INT (0-120, Default: 0) | 0 = disabled. Target FPS for DLSS Frame Generation interpolation. (Requires RTX 40/50 Series GPU). |
| **filename_prefix** | STRING | Prefix for the output filename (a timestamp is automatically appended). |
| **output_directory** | STRING | Relative subfolder path within ComfyUI output directory. Leave blank to use the default output folder. |
| **copy_audio** | BOOLEAN | Whether to mux the original audio into the output file. |

### Selector & Info Node Controls
| Widget / Output | Type | Effect |
| --- | --- | --- |
| **video_path** (Selector & Info) | STRING (linkable) | Relative path within the input folder, or absolute path inside input/output. Accepts links from other nodes. |
| **Choose file to upload...** | Button | Uploads a video from your computer into the ComfyUI input folder and sets `video_path` automatically. |
| **Live preview** (Selector) | Preview | Plays the currently resolved video. Updates on upload, on manual edits, and on every execution (including linked paths). |
| **video_info** | STRING (JSON) | `{"fps", "frame_count", "duration", "width", "height"}` of the resolved video. |
| **width / height / fps / frame_count** (Info) | INT / FLOAT | Individual metadata values, ready for math and logic nodes. |

## Recommended Settings

The defaults below are starting points based on how the v17.5 native runtime behaves:

| Goal | Settings |
| --- | --- |
| Clean up generated video, same resolution | Defaults: `scale` 1.0, `style` Default, `strength` 1.0 |
| Clean up and upscale | Same as above, with `scale` 2.0 (or up to 16.0) |
| Smooth 30fps to 60fps | Defaults plus `target_fps` 60 (RTX 40/50 only) |
| Most realistic faces | Defaults plus `style` Natural, `strength` 0.8 |
| High-precision material reconstruction | Enable `ray_reconstruction`, `style` Default |
| More contrast and punch | `style` Cinematic, `strength` 1.0 (check the shadows) |
| Output looks too strong/plastic | Drop `strength` to 0.6 or 0.7, or switch `style` to Natural |

*Note: The neural pass works on what is in the frame. It reconstructs skin and material response, but it does not restore a face that the source no longer contains. For heavily degraded footage, run a generative restoration pass first and use this node as the final cleanup.*

## Example Workflows

### Image Enhancement
Because the DLSS5 nodes focus purely on AI reconstruction and upscaling, it is highly recommended to use standard ComfyUI nodes for post-processing.

<img width="1431" height="870" alt="image_workflow" src="https://github.com/user-attachments/assets/4e41a104-b502-4c44-8440-6347c3cb9294" />

`Load Image` ➔ `DLSS5 Enhance (Image)` ➔ `Color Correction / Sharpening` ➔ `Save Image`

### Video File Enhancement
Pick your source with the **DLSS5 Video Path Selector** (type, upload, or link a path), or type a relative path straight into the Enhance node. The Enhance node outputs a new file path (`output_path`). Feed that path into a **DLSS5 Video Info** node for metadata, or into a `Load Video (Path)` node to visually preview the result and preserve audio by connecting both the `IMAGE` and `audio` outputs to `Video Combine`.

<img width="2198" height="832" alt="video_workflow" src="https://github.com/user-attachments/assets/7a3179e6-c159-402e-b972-7302e47de3c3" />

`DLSS5 Video Path Selector` ➔ `DLSS5 Enhance (Video)` ➔ (output_path) ➔ `DLSS5 Video Info` / `Load Video (Path)` ➔ `Video Combine`

## Troubleshooting

| Message / Issue | Cause and Fix |
| --- | --- |
| Windows SmartScreen blocks `VE_CLI.exe` | This is normal for unsigned community tools. Right-click the `.exe` in the `runtime` folder, select **Properties**, check **Unblock**, and click OK. |
| Runtime not found | The ~700MB runtime hasn't been downloaded. Run `install.py` manually to trigger the download. |
| Node fails on GTX / AMD cards | These GPUs lack the physical Tensor Cores required for DLSS/RTX AI processing. The nodes will not work on these cards. |
| Frame Generation fails on RTX 20/30 | DLSS Frame Generation strictly requires an **RTX 40 or 50 Series** GPU. Set `target_fps` to `0` to disable it. |
| `Width N exceeds 4096` / upscale fails with nvenc error | The H264 hardware encoder caps at **4096 px wide**. Switch `codec` to **HEVC** or **AV1** for outputs wider than 4K, or lower `scale`. |
| `Video file not found in input or output folder` | Paths must be relative to the input folder (e.g. `subfolder/video.mp4`) or absolute paths inside the ComfyUI input/output folders. External drives and other directories are blocked for security. |
| Video preview doesn't update on a linked path | The preview refreshes when the node **executes**. If it still looks stale after a run, hard-refresh the browser (**Ctrl+F5**) to reload the frontend extension. |
| Upload button rejects a file | Only video formats are accepted (`.mp4`, `.mkv`, `.mov`, `.webm`, `.avi`, `.m4v`). Duplicate filenames are automatically renamed with a `_1`, `_2` suffix. |
| Video processing is very slow | Neural Rendering is computationally heavy. Processing a long video natively through the AI pipeline takes time. Ensure no other heavy GPU tasks (like games) are running. |
| Output looks "plastic" or weird | Your `strength` is likely too high. Drop it to `0.7` or `1.0`, or switch the `style` to `Natural`. |

## Project Layout

```text
ComfyUI-DLSS5-Enhancer-v15/
   install.py             Downloads the runtime and prompts for license acceptance
   nodes.py               The ComfyUI node definitions (Image, Video, Selector & Info)
   paths.py               Runtime discovery and validation
   __init__.py            ComfyUI extension entrypoint (serves the web/ extension)
   README.md              This file
   LICENSE                MIT License for the Python source code
   requirements.txt       Python dependencies (imageio-ffmpeg)
   web/                   Frontend extension (dlss5_selector.js: upload button + live preview)
   runtime/               Native runtime (VE_CLI.exe, NVIDIA DLLs) - *Not tracked in Git*
   config.json            Local path configuration - *Not tracked in Git*
```

## Licensing and Attribution

The Python source code in this repository is licensed under the MIT License.

This repository does not host or redistribute the AI runtime binaries. The `install.py` script downloads the official **DLSS 5 Visual Enhancer v17.5** release from [Merserk/dlss5-visual-enhancer](https://github.com/Merserk/dlss5-visual-enhancer). The downloaded runtime contains proprietary components owned by their respective creators:

* **NVIDIA Corporation:** DLSS Super Resolution, Neural Rendering (updated to v310.9.16.0), Frame Generation, Ray Reconstruction, Optical Flow, and RTX Video SDKs (Proprietary).
* **Merserk:** Visual Enhancer CLI and Engine (Merserk Source License).
* **FFmpeg/mpv:** Media processing binaries (GPLv2/v3).

By installing this node pack, you agree to use these components only under the terms permitted by their respective licenses. The worker protocol was reimplemented for this pack. The runtime and the original application come from [Merserk/dlss5-visual-enhancer](https://github.com/Merserk/dlss5-visual-enhancer), which makes NVIDIA's renderer usable outside a game engine. This project is not affiliated with or endorsed by NVIDIA or that project.
