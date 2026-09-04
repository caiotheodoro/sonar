import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile } from "remotion";
import { StatusStrip } from "./components/StatusStrip";
import { ShotView } from "./shots/ShotView";
import { STORYBOARD, TIMELINE, msToFrame } from "./timeline";
import { monoFamily } from "./fonts";
import { T } from "./theme";

const { music, narration } = STORYBOARD;
const duckFrames = msToFrame(music.duckMs);
const fadeOutFrames = msToFrame(music.fadeOutMs);

/** Music gain at frame f: ducked under any cue, faded over the tail. Pure. */
const musicGain = (f: number): number => {
  let duck = 1;
  if (TIMELINE.narrationMeasured) {
    for (const c of TIMELINE.cues) {
      const g = interpolate(f, [c.from - duckFrames, c.from, c.to, c.to + duckFrames], [1, music.duckTo, music.duckTo, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
      duck = Math.min(duck, g);
    }
  }
  const tail = interpolate(f, [TIMELINE.totalFrames - fadeOutFrames, TIMELINE.totalFrames - 2], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return music.volume * duck * tail;
};

export const Main: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: T.ink, fontFamily: monoFamily }}>
    {TIMELINE.shots.map((s) => (
      <Sequence
        key={s.shot.id}
        from={s.from}
        durationInFrames={s.durationInFrames}
        premountFor={15}
        name={`${s.shot.act}/${s.shot.id}`}
      >
        <ShotView shot={s} />
      </Sequence>
    ))}

    <StatusStrip />

    <Sequence from={TIMELINE.narrationFrom} name="narration">
      <Audio src={staticFile(narration.src)} />
    </Sequence>

    <Audio src={staticFile(music.src)} volume={musicGain} />
  </AbsoluteFill>
);
