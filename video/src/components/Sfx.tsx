/**
 * One sound at one shot-local frame. A component that draws something at
 * frame N sounds it at frame N through this, so there is no second clock.
 * `at` values before 0 are dropped; past the shot, the Sequence clips them.
 */
import React from "react";
import { Audio, Sequence, staticFile } from "remotion";
import { SFX_BUS, type SfxName } from "../sfx";

export const Sfx: React.FC<{ src: SfxName; at: number; gain?: number }> = ({ src, at, gain = 1 }) => {
  if (at < 0) return null;
  return (
    <Sequence from={Math.round(at)} name={`sfx/${src}`}>
      <Audio src={staticFile(`sfx/${src}.wav`)} volume={gain * SFX_BUS} />
    </Sequence>
  );
};

/** Several of the same sound at several frames, capped so a long list cannot flood the mix. */
export const SfxAt: React.FC<{ src: SfxName; frames: number[]; gain?: number; cap?: number }> = ({ src, frames, gain = 1, cap = 48 }) => (
  <>
    {frames.slice(0, cap).map((f, i) => (
      <Sfx key={`${src}-${i}`} src={src} at={f} gain={gain} />
    ))}
  </>
);
