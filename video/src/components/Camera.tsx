/**
 * One camera, one move. The six beats are stacked one screen-height apart on a
 * single tall surface; the camera translates down it as an unbroken eased shove
 * at each boundary — a receipt feeding through a printer, never a cut.
 *
 * `cameraY(frame)` is the sum of the moves that have started by `frame`. Each
 * move runs over the last `SCENE_OVERLAP` frames of its beat, so the beat is
 * fully read before the surface slides.
 */
import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { HEIGHT, from, scenes } from "../manifest";
import { MOTION } from "../theme";

/** Frames of camera travel between two stations. Also the premount lead. */
export const SCENE_OVERLAP = 22;

const CURVE = Easing.bezier(MOTION.snap[0], MOTION.snap[1], MOTION.snap[2], MOTION.snap[3]);

export const cameraY = (frame: number): number => {
  let y = 0;
  for (let i = 0; i < scenes.length - 1; i++) {
    const boundary = from(i + 1);
    y += interpolate(frame, [boundary - SCENE_OVERLAP, boundary], [0, HEIGHT], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: CURVE,
    });
  }
  return y;
};

/**
 * Positions each cell at `top: i * HEIGHT` inside a fill translated by
 * `-cameraY`. Children are the per-beat nodes in scene order; anything that
 * should stay locked to the frame (status strip, captions, audio) lives
 * outside `<Tape>`.
 */
export const Tape: React.FC<{ children: React.ReactNode[] }> = ({ children }) => {
  const y = cameraY(useCurrentFrame());
  return (
    <AbsoluteFill style={{ transform: `translateY(${-y}px)`, willChange: "transform" }}>
      {children.map((cell, i) => (
        <div
          key={i}
          style={{ position: "absolute", top: i * HEIGHT, left: 0, width: "100%", height: HEIGHT }}
        >
          {cell}
        </div>
      ))}
    </AbsoluteFill>
  );
};
