"use client";

import { useEffect, useRef, useState } from "react";
import { profileCrop } from "@/lib/profile-crop";

export default function ProfilePhotoCropper({ file, onSave, onCancel }: {
  file: File;
  onSave: (file: File) => Promise<boolean>;
  onCancel: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const drag = useRef<{ x: number; y: number; cropX: number; cropY: number } | null>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const [x, setX] = useState(0);
  const [y, setY] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const clamp = (value: number) => Math.max(-1, Math.min(1, value));

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const url = URL.createObjectURL(file);
    const photo = new window.Image();
    let active = true;
    photo.onload = () => { if (active) setImage(photo); };
    photo.onerror = () => { if (active) setError("This photo could not be opened. Choose another image."); };
    photo.src = url;
    return () => {
      active = false;
      URL.revokeObjectURL(url);
      element?.close();
      document.body.style.overflow = previousOverflow;
    };
  }, [file]);

  useEffect(() => {
    const context = canvas.current?.getContext("2d");
    if (!context || !image) return;
    const crop = profileCrop(image.naturalWidth, image.naturalHeight, zoom, x, y);
    context.clearRect(0, 0, 512, 512);
    context.drawImage(image, crop.left, crop.top, crop.side, crop.side, 0, 0, 512, 512);
  }, [image, zoom, x, y]);

  const save = async () => {
    if (!image || saving) return;
    setSaving(true);
    setError("");
    try {
      const output = document.createElement("canvas");
      output.width = output.height = 512;
      const context = output.getContext("2d");
      if (!context) throw new Error("Canvas unavailable");
      const crop = profileCrop(image.naturalWidth, image.naturalHeight, zoom, x, y);
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, 512, 512);
      context.drawImage(image, crop.left, crop.top, crop.side, crop.side, 0, 0, 512, 512);
      const blob = await new Promise<Blob>((resolve, reject) => output.toBlob(
        (result) => result ? resolve(result) : reject(new Error("Crop failed")), "image/jpeg", .9,
      ));
      const saved = await onSave(new File([blob], "profile.jpg", { type: "image/jpeg" }));
      if (!saved) setError("Your photo could not be saved. Please try again.");
    } catch {
      setError("Your photo could not be saved. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <dialog ref={dialog} className="profile-crop-dialog" aria-labelledby="profile-crop-title" aria-describedby="profile-crop-help"
      onCancel={(event) => { event.preventDefault(); if (!saving) onCancel(); }}>
      <h2 id="profile-crop-title">Crop profile photo</h2>
      <p id="profile-crop-help">Drag the photo or use the sliders to position it. Everything inside the circle will appear on your profile.</p>
      <canvas ref={canvas} width={512} height={512} className="profile-crop-preview" aria-label="Circular profile photo preview"
        onPointerDown={(event) => {
          if (!image || saving) return;
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { x: event.clientX, y: event.clientY, cropX: x, cropY: y };
        }}
        onPointerMove={(event) => {
          if (!drag.current || !image || saving) return;
          const crop = profileCrop(image.naturalWidth, image.naturalHeight, zoom, x, y);
          const scale = event.currentTarget.getBoundingClientRect().width / crop.side;
          const overflowX = (image.naturalWidth - crop.side) * scale;
          const overflowY = (image.naturalHeight - crop.side) * scale;
          if (overflowX > 0) setX(clamp(drag.current.cropX - 2 * (event.clientX - drag.current.x) / overflowX));
          if (overflowY > 0) setY(clamp(drag.current.cropY - 2 * (event.clientY - drag.current.y) / overflowY));
        }}
        onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onLostPointerCapture={() => { drag.current = null; }} />
      {!image && !error && <p role="status">Loading photo…</p>}
      <fieldset className="profile-crop-sliders" disabled={!image || saving}>
        <label htmlFor="profile-crop-zoom">Zoom</label>
        <input id="profile-crop-zoom" type="range" min="1" max="4" step="0.01" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} />
        <label htmlFor="profile-crop-x">Horizontal position</label>
        <input id="profile-crop-x" type="range" min="-1" max="1" step="0.01" value={x} onChange={(event) => setX(Number(event.target.value))} />
        <label htmlFor="profile-crop-y">Vertical position</label>
        <input id="profile-crop-y" type="range" min="-1" max="1" step="0.01" value={y} onChange={(event) => setY(Number(event.target.value))} />
      </fieldset>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="form-actions">
        <button type="button" className="button button-secondary" disabled={saving} onClick={onCancel}>Cancel</button>
        <button type="button" className="button button-primary" disabled={!image || saving} onClick={() => void save()}>{saving ? "Saving…" : "Save photo"}</button>
      </div>
    </dialog>
  );
}
