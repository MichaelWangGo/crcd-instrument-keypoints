"""Build a public showcase from measured CRCD predictions; no new inference."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import cv2
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
DOCS = PROJECT / "docs"
ROOT = Path("/workspace/CRCD")
RUN = ROOT / "runs/vitpose_plus_base"
ANALYSIS = RUN / "analysis"
COLORS = {"FBF": (180, 220, 25), "PCH": (255, 171, 98)}


def render(image, records, index, history):
    canvas = image.copy()
    for tool, record in records.items():
        points = np.asarray(record["predicted_xy"])
        color = COLORS[tool]
        for start, end in history["categories"][tool]["skeleton"]:
            cv2.line(canvas, tuple(np.rint(points[start - 1]).astype(int)),
                     tuple(np.rint(points[end - 1]).astype(int)), color, 3, cv2.LINE_AA)
        for point in points:
            cv2.circle(canvas, tuple(np.rint(point).astype(int)), 5, color, -1, cv2.LINE_AA)
        for x, y, visibility in record["ground_truth_xyv"]:
            if visibility > 0:
                cv2.drawMarker(canvas, (round(x), round(y)), (105, 118, 255), cv2.MARKER_CROSS, 14, 2)
        for keypoint in ([3, 4] if tool == "FBF" else [5]):
            trail = [history["frames"][j]["instruments"][tool]["predicted_xy"][keypoint]
                     for j in range(max(0, index - 14), index + 1)]
            if len(trail) > 1:
                cv2.polylines(canvas, [np.rint(trail).astype(np.int32)], False, color, 2, cv2.LINE_AA)
    return canvas


def encode(images, target):
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", "960x540", "-r", "12", "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium",
            "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-threads", "2", str(target)]
    process = subprocess.Popen(args, stdin=subprocess.PIPE)
    for image in images:
        process.stdin.write(cv2.resize(image, (960, 540), interpolation=cv2.INTER_AREA).tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError(f"Video encoding failed: {target}")


def main():
    for directory in ("assets/video", "assets/images", "assets/charts", "data", "downloads"):
        (DOCS / directory).mkdir(parents=True, exist_ok=True)
    data = json.loads((ROOT / "annotations/crcd_test.json").read_text())
    annotations = {a["id"]: a for a in data["annotations"]}
    categories = {c["name"]: c for c in data["categories"]}
    predictions = json.loads((ANALYSIS / "best_test/predictions.json").read_text())
    by_tool = {t: {} for t in categories}
    for prediction in predictions:
        frame = int(re.search(r"\d+$", Path(prediction["file_name"]).stem)[0])
        ann = annotations[prediction["annotation_id"]]
        gt = np.asarray(ann["keypoints"]).reshape(-1, 3)
        xy = np.asarray(prediction["keypoints_xy"])
        visible = gt[:, 2] == 2
        error = float(np.linalg.norm(xy[visible] - gt[visible, :2], axis=-1).mean()) if visible.any() else None
        by_tool[prediction["tool"]][frame] = {
            "predicted_xy": xy.round(3).tolist(), "ground_truth_xyv": gt.tolist(),
            "mean_visible_error_px": error, "visible_count": int(visible.sum()),
            "bbox": ann["bbox"], "source_file": prediction["file_name"],
        }
    common = sorted(set(by_tool["FBF"]) & set(by_tool["PCH"]))
    runs = []
    for frame in common:
        if not runs or frame != runs[-1][-1] + 1:
            runs.append([])
        runs[-1].append(frame)
    candidates = []
    for frames in runs:
        for offset in range(0, len(frames) - 119, 24):
            window = frames[offset:offset + 120]
            values = [by_tool[t][f]["mean_visible_error_px"] for f in window for t in categories]
            if any(v is None for v in values):
                continue
            candidates.append({"frames": window, "score": float(np.mean(values))})
    selected = []
    for quantile, slug, label in ((0.2, "steady", "相对稳定片段"), (0.5, "typical", "典型片段"),
                                  (0.9, "challenging", "困难片段")):
        target = float(np.quantile([c["score"] for c in candidates], quantile))
        choices = sorted(candidates, key=lambda c: abs(c["score"] - target))
        chosen = next((c for c in choices if all(not set(c["frames"]) & set(s["frames"]) for s in selected)), choices[0])
        selected.append({**chosen, "slug": slug, "label": label})
    manifest = {"image_width": 1280, "image_height": 720, "playback_fps": 12,
                "scope": "Framewise predictions with GT boxes and annotation-assisted identities; not an evaluated temporal tracker.",
                "source_fps_verified": False, "categories": categories, "clips": []}
    for clip in selected:
        payload = {"categories": categories, "frames": []}
        originals = []
        for frame in clip["frames"]:
            records = {t: by_tool[t][frame] for t in categories}
            a = ROOT / records["FBF"]["source_file"]
            b = ROOT / records["PCH"]["source_file"]
            with a.open("rb") as handle:
                ah = hashlib.file_digest(handle, "sha256").digest()
            with b.open("rb") as handle:
                bh = hashlib.file_digest(handle, "sha256").digest()
            if ah != bh:
                raise RuntimeError(f"Two tools do not refer to the same image at frame {frame}")
            image = cv2.imread(str(a))
            if image is None:
                raise RuntimeError(a)
            originals.append(image)
            payload["frames"].append({"source_frame": frame, "instruments": records})
        slug = clip["slug"]
        (DOCS / f"data/{slug}.json").write_text(json.dumps(payload, separators=(",", ":")))
        encode(originals, DOCS / f"assets/video/{slug}-raw.mp4")
        overlays = [render(image, payload["frames"][i]["instruments"], i, payload) for i, image in enumerate(originals)]
        encode(overlays, DOCS / f"assets/video/{slug}-overlay.mp4")
        cv2.imwrite(str(DOCS / f"assets/images/{slug}-poster.jpg"), overlays[0], [cv2.IMWRITE_JPEG_QUALITY, 90])
        manifest["clips"].append({"id": slug, "label": clip["label"], "frame_count": len(payload["frames"]),
                                  "first_source_frame": clip["frames"][0], "last_source_frame": clip["frames"][-1],
                                  "mean_visible_error_px": clip["score"], "selection_window_quantile":
                                  {"steady": 0.2, "typical": 0.5, "challenging": 0.9}[slug],
                                  "raw_video": f"assets/video/{slug}-raw.mp4",
                                  "overlay_video": f"assets/video/{slug}-overlay.mp4",
                                  "poster": f"assets/images/{slug}-poster.jpg", "data": f"data/{slug}.json"})
        print(slug, clip["frames"][0], clip["frames"][-1], "mean error", clip["score"], flush=True)
    (DOCS / "data/clips.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    summary = json.loads((ANALYSIS / "summary.json").read_text())
    (DOCS / "data/results.json").write_text(json.dumps(summary))
    history = [json.loads(line) for line in (RUN / "metrics.jsonl").read_text().splitlines()]
    (DOCS / "data/history.json").write_text(json.dumps([{
        "epoch": r["epoch"], "train_loss": r["train_heatmap_mse"], "val_loss": r["validation"]["heatmap_mse"],
        "FBF": r["validation"]["FBF/visible"]["mean_px"], "PCH": r["validation"]["PCH/visible"]["mean_px"],
        "macro": r["validation"]["macro_visible_mean_px"]} for r in history]))
    for name in ("learning_curves.png", "per_joint_errors.png", "test_error_cdf.png"):
        shutil.copy2(ANALYSIS / name, DOCS / "assets/charts" / name)
    shutil.copy2(ANALYSIS / "qualitative_test.jpg", DOCS / "assets/images/qualitative_test.jpg")
    for name in ("report_zh.md", "summary.json", "per_joint.csv", "crop_audit.json"):
        shutil.copy2(ANALYSIS / name, DOCS / "downloads" / name)
    shutil.copy2(ROOT / "LICENSE-DS", PROJECT / "LICENSE-CRCD")
    (DOCS / ".nojekyll").touch()
    print("Public assets ready:", DOCS, flush=True)


if __name__ == "__main__":
    main()
