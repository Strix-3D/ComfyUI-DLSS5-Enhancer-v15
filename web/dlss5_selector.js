import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

api.addEventListener("dlss5_preview", (e) => {
    const detail = e.detail || {};
    let node = app.graph.getNodeById(Number(detail.node_id));
    if (!node) node = app.graph.getNodeById(detail.node_id);
    if (node && node.__dlss5SetPreview) node.__dlss5SetPreview(detail.path);
});

app.registerExtension({
    name: "DLSS5.VideoPathSelector",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "DLSS5_Video_Path_Selector") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            const node = this;

            // Fixed default size
            node.size = [400, 360];
            node.setSize([400, 360]);

            // Simple video element
            const videoEl = document.createElement("video");
            videoEl.controls = true;
            videoEl.style.width = "380px";
            videoEl.style.height = "214px";
            videoEl.style.background = "#000";
            videoEl.style.display = "none";
            videoEl.style.objectFit = "contain";
            
            const domWidget = node.addDOMWidget("video_preview", "video", videoEl);
            domWidget.serialize = false;

            // Simple placeholder
            const placeholderEl = document.createElement("div");
            placeholderEl.textContent = "Select or upload a video to preview";
            placeholderEl.style.padding = "40px 20px";
            placeholderEl.style.textAlign = "center";
            placeholderEl.style.color = "#666";
            placeholderEl.style.fontSize = "12px";
            placeholderEl.style.fontStyle = "italic";
            
            const placeholderWidget = node.addDOMWidget("video_placeholder", "div", placeholderEl);
            placeholderWidget.serialize = false;

            const setPreview = (path) => {
                if (!path) {
                    videoEl.style.display = "none";
                    placeholderEl.style.display = "block";
                    videoEl.removeAttribute("src");
                    videoEl.load();
                    return;
                }
                placeholderEl.style.display = "none";
                videoEl.style.display = "block";
                videoEl.src = "/dlss5/view?path=" + encodeURIComponent(path) + "&t=" + Date.now();
                videoEl.load();
            };
            node.__dlss5SetPreview = setPreview;

            const btn = node.addWidget("button", "Choose file to upload...", null, () => {
                const input = document.createElement("input");
                input.type = "file";
                input.accept = "video/*";
                input.onchange = async () => {
                    const file = input.files[0];
                    if (!file) return;
                    const fd = new FormData();
                    fd.append("file", file);
                    try {
                        const resp = await fetch("/dlss5/upload", { method: "POST", body: fd });
                        if (!resp.ok) { alert("Upload failed: " + (await resp.text())); return; }
                        const data = await resp.json();
                        const w = node.widgets.find((x) => x.name === "video_path");
                        if (w) {
                            w.value = data.path;
                            if (w.callback) w.callback(data.path);
                        }
                        setPreview(data.path);
                    } catch (e) {
                        alert("Upload error: " + e);
                    }
                };
                input.click();
            });
            btn.serialize = false;

            const pathWidget = node.widgets.find((x) => x.name === "video_path");
            if (pathWidget) {
                const origCb = pathWidget.callback;
                pathWidget.callback = (v) => {
                    if (origCb) origCb(v);
                    setPreview(v);
                };
            }

            return r;
        };
    },
});