/**
 * A real page, framed as a specimen. The PNG under public/shots was captured
 * by capture/shoot.mjs; its intrinsic size comes from src/data/shots.json
 * (capture/collect-shots.mjs) so the crop and the moves are exact without
 * waiting on the image to load.
 *
 *   hold      — static
 *   push      — 1.00 → 1.03 scale over the shot
 *   pan-down  — translate across the crop's vertical overflow over the shot
 *   zoom      — scale zoom[0] → zoom[1] toward `focus` over the shot
 *   punch     — instant scale `zoom` toward `focus` from frame `at`
 *   flash     — one-frame plate flash + shutter on the first frame, scale settles 1.06 → 1
 */
import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import shotsJson from "../data/shots.json";
import { FactChip } from "./FactChip";
import { Sfx } from "./Sfx";
import { SPECIMEN, Specimen } from "./Specimen";
import { MOTION, T } from "../theme";
import type { Crop, Move } from "../timeline/types";

interface ShotMeta {
  width: number;
  height: number;
  url: string;
  captured_at: string;
}
const SHOTS = shotsJson as Record<string, ShotMeta>;

export interface ScreenshotProps {
  shot: {
    src: string;
    crop?: Crop;
    move?: Move;
    facts?: string[];
    plate?: string[];
    highlight?: Crop;
    focus?: { x: number; y: number };
    zoom?: [number, number] | number;
    at?: number;
    flash?: boolean;
  };
  durationInFrames: number;
}

export const Screenshot: React.FC<ScreenshotProps> = ({ shot, durationInFrames }) => {
  const frame = useCurrentFrame();
  const meta = SHOTS[shot.src];
  if (!meta) throw new Error(`src/data/shots.json has no "${shot.src}"; run capture/collect-shots.mjs`);

  const crop: Crop = shot.crop ?? { x: 0, y: 0, w: meta.width, h: meta.height };
  const scale = SPECIMEN.w / crop.w;
  const imgW = meta.width * scale;
  const imgH = meta.height * scale;
  const cropH = crop.h * scale;
  const overflow = Math.max(0, cropH - SPECIMEN.h);
  const progress = interpolate(frame, [0, Math.max(1, durationInFrames - 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const move: Move = shot.move ?? "hold";
  const pan = move === "pan-down" ? overflow * progress : 0;

  let zoom = 1;
  if (move === "push") zoom = 1 + 0.03 * progress;
  if (move === "zoom" && Array.isArray(shot.zoom)) {
    const eased = 1 - Math.pow(1 - progress, 2);
    zoom = shot.zoom[0] + (shot.zoom[1] - shot.zoom[0]) * eased;
  }
  if (move === "punch" && typeof shot.zoom === "number" && frame >= (shot.at ?? 0)) zoom = shot.zoom;
  if (shot.flash) zoom *= interpolate(frame, [0, MOTION.slamFrames], [1.06, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  // transform origin: the focus point in specimen px, else upper-centre
  const originX = shot.focus ? (shot.focus.x - crop.x) * scale : SPECIMEN.w / 2;
  const originY = shot.focus ? (shot.focus.y - crop.y) * scale - pan : SPECIMEN.h * 0.3;

  const hl = shot.highlight;
  const hlAt = 10;
  const hlOn = interpolate(frame, [hlAt, hlAt + 4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <Specimen
      plate={shot.plate}
      scan={!shot.flash}
      aside={
        shot.facts && shot.facts.length ? (
          <div style={{ display: "flex", gap: 40 }}>
            {shot.facts.map((id) => (
              <FactChip key={id} id={id} signal={id.includes("price")} />
            ))}
          </div>
        ) : undefined
      }
    >
      {shot.flash ? <Sfx src="shutter" at={0} gain={0.9} /> : null}
      {hl ? <Sfx src="click" at={hlAt} gain={0.6} /> : null}
      {move === "punch" ? <Sfx src="tick" at={shot.at ?? 0} gain={0.7} /> : null}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: SPECIMEN.w,
          height: SPECIMEN.h,
          overflow: "hidden",
          transform: `scale(${zoom})`,
          transformOrigin: `${originX}px ${originY}px`,
        }}
      >
        <Img
          src={staticFile(`shots/${shot.src}.png`)}
          pauseWhenLoading
          delayRenderTimeoutInMilliseconds={60000}
          style={{
            position: "absolute",
            left: -crop.x * scale,
            top: -crop.y * scale - pan,
            width: imgW,
            height: imgH,
            display: "block",
          }}
        />
        {hl ? (
          <div
            style={{
              position: "absolute",
              left: (hl.x - crop.x) * scale,
              top: (hl.y - crop.y) * scale - pan,
              width: hl.w * scale,
              height: hl.h * scale,
              border: `3px solid ${T.signal}`,
              opacity: hlOn,
              boxSizing: "border-box",
            }}
          />
        ) : null}
      </div>
    </Specimen>
  );
};
