# ComfyUI-DLSS5-Enhancer-v15

Run NVIDIA DLSS 5 Neural Rendering over your frames and videos, directly inside ComfyUI.

DLSS 5 is NVIDIA's neural rendering pass. In a game, it reconstructs the material and lighting detail that real-time rendering has to leave out, such as skin subsurface scattering, light transmission through hair, and contact shadows. This node pack drives that same native renderer over video frames and image batches, with optional 1x to 4x RTX upscaling.

It is not a filter that imitates a look. Frames go to the native renderer and come back reconstructed. The model reconstructs materials and recovers structure (skin, hair, fabric) that the source only implied, rather than just sharpening edges.

Unlike older community implementations that relied on ReShade injection, this pack drives the official **v15.0 headless CLI** (`VE_CLI.exe`), providing a stable, native, and highly optimized pipeline.

---

## How it Works

In games, DLSS 5 runs as "3D-Guided" Neural Rendering: the engine hands the model its rendered frame together with geometry, texture, and lighting buffers. Video has none of that. What reaches the model here is the decoded frame plus motion vectors estimated from the footage itself, so the guidance is weaker than in a game, and the reconstruction is correspondingly more conservative.

This pack acts as a bridge between ComfyUI and the native CLI:

1. **Neural Rendering:** The node exports your frames and passes them to `VE_CLI.exe`. The CLI handles the D3D12 process, hosting the native NVIDIA runtime to reconstruct high-frequency material details.
2. **RTX Upscaling:** If requested, the reconstructed frames are passed through NVIDIA's RTX Super Resolution engine to intelligently enlarge the image up to 4x its original size.
3. **Video Pipeline:** For video, the entire batch of frames is processed together in a single CLI pass. This allows the AI to maintain temporal consistency, preventing the flickering and jitter common in frame-by-frame upscaling.

---

## Requirements

| Item | Requirement |
| --- | --- |
| **GPU** | **NVIDIA RTX 20, 30, 40, or 50 Series.** (GTX, AMD, and Intel GPUs are not supported as they lack the required Tensor Cores). |
| **Driver** | A recent NVIDIA Game Ready or Studio Driver (560.xx or newer recommended). |
| **OS** | Windows only. |
| **ComfyUI** | A recent build supporting standard `IMAGE` and `VIDEO` tensor types. |

---

## Installation

### Step 1: Install the Node Pack
Clone this repository into your `ComfyUI/custom_nodes/` folder:

`git clone https://github.com/YourUsername/ComfyUI-DLSS5-Enhancer-v15.git`

*(Alternatively, if published to ComfyUI Manager, search for `DLSS5-Enhancer-v15` and click Install).*

### Step 2: Download the Runtime & Accept the License
**This node pack does not include the proprietary NVIDIA binaries.** You must download them using the included installer script.

1. Open a PowerShell window in your main ComfyUI folder (the one containing `python_embeded`).
2. Run the following command:

   `.\python_embeded\python.exe ComfyUI\custom_nodes\ComfyUI-DLSS5-Enhancer-v15\install.py`

3. **Read the License Notice:** The script will display a list of third-party components (NVIDIA, FFmpeg, mpv, etc.) and their respective licenses.
4. **Accept the Terms:** Type `y` and press **Enter** to confirm you accept the terms and wish to proceed.
5. Wait for the ~693MB runtime to download and extract into the `runtime/` folder.

### Step 3: Restart ComfyUI
Once the installation is complete, restart ComfyUI. The nodes will now appear in your menu under the `DLSS5_v15` category.

---

## Nodes & Controls

This pack includes two highly optimized nodes:

### 1. DLSS 5 RTX Enhance (Image)
Takes an `IMAGE` batch, applies Neural Rendering, and optionally upscales it. Outputs an `IMAGE` batch.

### 2. DLSS 5 RTX Enhance (Video)
Takes a native `VIDEO` input, processes the entire sequence for temporal consistency, and outputs a native `VIDEO` type (preserving audio and metadata for direct connection to `Save Video` nodes).

### Shared Controls

| Widget | Options / Range | Effect |
| --- | --- | --- |
| **style** | Default, Natural, Cinematic | **Default:** Balanced detail reconstruction.<br>**Natural:** Subtle enhancement, preserves original textures.<br>**Cinematic:** Aggressive contrast and micro-detail enhancement. |
| **strength** | 0.00 to 2.00 (Default: 1.0) | The intensity of the Neural Rendering effect. 1.0 is the standard NVIDIA tuning. Values > 1.5 can cause AI "hallucinations" (weird artifacts). |
| **scale** | 1.0 to 4.0 (Default: 2.0) | The RTX upscaling multiplier. **Set to 1.0 to skip upscaling entirely** and only apply Neural Rendering. |

---

## Recommended Settings

The defaults below are starting points based on how the v15.0 native runtime behaves:

| Goal | Settings |
| --- | --- |
| **Clean up generated video, same resolution** | Defaults: `scale` 1.0, `style` Default, `strength` 1.0 |
| **Clean up and upscale** | Same as above, with `scale` 2.0 |
| **Most realistic faces** | Defaults plus `style` Natural, `strength` 0.8 |
| **More contrast and punch** | `style` Cinematic, `strength` 1.0 (check the shadows) |
| **Output looks too strong/plastic** | Drop `strength` to 0.6 or 0.7, or switch `style` to Natural |

*Note: The neural pass works on what is in the frame. It reconstructs skin and material response, but it does not restore a face that the source no longer contains. For heavily degraded footage, run a generative restoration pass first and use this node as the final cleanup.*

---

## Example Workflows

### Image Enhancement
Because the DLSS5 nodes focus purely on AI reconstruction and upscaling, it is highly recommended to use standard ComfyUI nodes for post-processing.

`Load Image` -> **`DLSS 5 RTX Enhance (Image)`** -> `Color Correction / Sharpening` -> `Save Image`

### Video Enhancement
The video node accepts and outputs the native `VIDEO` type, making it seamless to drop into existing video workflows.

`Load Video` -> **`DLSS 5 RTX Enhance (Video)`** -> `Save Video`

---

## Troubleshooting

| Message / Issue | Cause and Fix |
| --- | --- |
| **Windows SmartScreen blocks `VE_CLI.exe`** | This is normal for unsigned community tools. Right-click the `.exe` in the `runtime` folder, select **Properties**, check **Unblock**, and click OK. |
| **Runtime not found** | The 693MB runtime hasn't been downloaded. Run `install.py` manually and accept the license. |
| **Node fails on GTX / AMD cards** | These GPUs lack the physical Tensor Cores required for DLSS/RTX AI processing. The nodes will not work on these cards. |
| **Video processing is very slow** | Neural Rendering is computationally heavy. Processing a 100-frame video natively through the AI pipeline takes time. Ensure no other heavy GPU tasks (like games) are running. |
| **Output looks "plastic" or weird** | Your `strength` is likely too high. Drop it to `0.7` or `1.0`, or switch the `style` to **Natural**. |
| **Worker could not be started** | Antivirus is blocking the worker. Add the `runtime` folder to your antivirus exclusion list. |

---

## Project Layout

    ComfyUI-DLSS5-Enhancer-v15/
       install.py             Downloads the runtime and prompts for license acceptance
       nodes.py               The ComfyUI node definitions (Image & Video)
       paths.py               Runtime discovery and validation
       __init__.py            ComfyUI extension entrypoint
       README.md              This file
       runtime/               Native runtime (VE_CLI.exe, NVIDIA DLLs) - *Not tracked in Git*
       config.json            Local path configuration - *Not tracked in Git*

---

## Licensing and Attribution

The Python source code in this repository is licensed under the **MIT License**. 

**This repository does not host or redistribute the AI runtime binaries.** 
The `install.py` script downloads the official **DLSS 5 Visual Enhancer v15.0** release from [Merserk/dlss5-visual-enhancer](https://github.com/Merserk/dlss5-visual-enhancer). The downloaded runtime contains proprietary components owned by their respective creators:
*   **NVIDIA Corporation:** DLSS Super Resolution, Neural Rendering, and RTX Video SDKs (Proprietary).
*   **Merserk:** Visual Enhancer CLI and Engine (Merserk Source License).
*   **FFmpeg/mpv:** Media processing binaries (GPLv2/v3).

By running the installer and typing `y`, you agree to use these components only under the terms permitted by their respective licenses. The worker protocol was reimplemented for this pack. The runtime and the original application come from [Merserk/dlss5-visual-enhancer](https://github.com/Merserk/dlss5-visual-enhancer), which makes NVIDIA's renderer usable outside a game engine. This project is not affiliated with or endorsed by NVIDIA or that project.