/**
 * A real page, framed as a specimen. The PNG under public/shots was captured
 * by capture/shoot.mjs; its intrinsic size comes from src/data/shots.json
 * (capture/collect-shots.mjs) so the crop and the pan are exact without
 * waiting on the image to load.
 *
 *   hold      — static
 *   push      — 1.00 → 1.03 scale over the shot
 *   pan-down  — translate across the crop's vertical overflow over the shot
 */
import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import shotsJson from "../data/shots.json";
import { FactChip } from "./FactChip";
import { SPECIMEN, Specimen } from "./Specimen";
import { T } from "../theme";
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
  const zoom = move === "push" ? 1 + 0.03 * progress : 1;

  const hl = shot.highlight;
  const hlOn = interpolate(frame, [10, 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <Specimen
      plate={shot.plate}
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
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: SPECIMEN.w,
          height: SPECIMEN.h,
          overflow: "hidden",
          transform: `scale(${zoom})`,
          transformOrigin: "50% 30%",
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
