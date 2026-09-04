/**
 * Sounds that belong to the cut rather than to anything on screen: a tick
 * at every hard cut, a whoosh at every act change (not the kill; the stamp
 * carries its own hit), and the one-frame flash on shots that ask for it.
 * Driven by TIMELINE, so the gate has already checked every frame here.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { TIMELINE } from "../timeline";
import { T } from "../theme";
import { Sfx } from "./Sfx";

const SELF_SOUNDING = new Set(["stamp"]);

export const CutTrack: React.FC = () => {
  const frame = useCurrentFrame();
  const flashing = TIMELINE.shots.some((s) => s.shot.kind === "shot" && s.shot.flash && frame === s.from);
  return (
    <>
      {TIMELINE.shots.map((s, i) => {
        const prev = TIMELINE.shots[i - 1];
        const actChange = prev && prev.shot.act !== s.shot.act && s.shot.act !== "killed";
        const skipTick = SELF_SOUNDING.has(s.shot.kind) || (s.shot.kind === "shot" && s.shot.flash) || s.shot.sfx?.cut === false;
        return (
          <React.Fragment key={s.shot.id}>
            {actChange ? <Sfx src="whoosh" at={s.from - 4} gain={0.8} /> : null}
            {!skipTick && i > 0 ? <Sfx src="tick" at={s.from} gain={0.6} /> : null}
          </React.Fragment>
        );
      })}
      {flashing ? <AbsoluteFill style={{ background: T.plate, opacity: 0.9, pointerEvents: "none" }} /> : null}
    </>
  );
};
