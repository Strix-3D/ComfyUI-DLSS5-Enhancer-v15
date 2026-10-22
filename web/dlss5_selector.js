import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Server pushes the real executed path straight to this node's preview
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

            // --- Live video preview (DOM widget) ---
            const videoEl = document.createElement("video");
            videoEl.controls = true;
            videoEl.style.width = "100%";
            videoEl.style.maxHeight = "220px";
            videoEl.style.background = "#000";
            const domWidget = node.addDOMWidget("video_preview", "video", videoEl);
            domWidget.serialize = false;

            const setPreview = (path) => {
                if (!path) { videoEl.removeAttribute("src"); videoEl.load(); return; }
                videoEl.src = "/dlss5/view?path=" + encodeURIComponent(path) + "&t=" + Date.now();
                videoEl.load();
            };
            node.__dlss5SetPreview = setPreview;

            // --- Upload button ---
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

            // --- Manual typing updates preview ---
            const pathWidget = node.widgets.find((x) => x.name === "video_path");
            if (pathWidget) {
                const origCb = pathWidget.callback;
                pathWidget.callback = (v) => {
                    if (origCb) origCb(v);
                    setPreview(v);
                };
            }

            // --- Show widget value on creation (only when NOT linked) ---
            const onConfigure = node.onConfigure;
            node.onConfigure = function () {
                const r2 = onConfigure ? onConfigure.apply(this, arguments) : undefined;
                const linked = node.inputs && node.inputs.some((i) => i.name === "video_path" && i.link != null);
                const w = node.widgets.find((x) => x.name === "video_path");
                if (!linked && w && w.value) setPreview(w.value);
                return r2;
            };
            return r;
        };
    },
});
