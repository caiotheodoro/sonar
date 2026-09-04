import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile } from "remotion";
import { CaptionOverlay } from "./components/CaptionOverlay";
import { SCENE_OVERLAP, Tape } from "./components/Camera";
import { StatusStrip } from "./components/StatusStrip";
import { TapeGround } from "./components/TapeGround";
import { SceneAsk } from "./scenes/SceneAsk";
import { SceneEmptyRun } from "./scenes/SceneEmptyRun";
import { SceneLiveTrace } from "./scenes/SceneLiveTrace";
import { SceneOutro } from "./scenes/SceneOutro";
import { ScenePriceDied } from "./scenes/ScenePriceDied";
import { SceneReceipt } from "./scenes/SceneReceipt";
import {
  Scene,
  TOTAL_FRAMES,
  captions,
  from,
  musicSrc,
  musicVolume,
  narrationSrc,
  scenes,
  voiceOffset,
} from "./manifest";
import { sansFamily } from "./fonts";
import { T } from "./theme";

const sceneContent = (scene: Scene): React.ReactNode => {
  switch (scene.id) {
    case "price-died":
      return <ScenePriceDied />;
    case "live-trace":
      return <SceneLiveTrace />;
    case "receipt":
      return <SceneReceipt />;
    case "ask":
      return <SceneAsk />;
    case "empty-run":
      return <SceneEmptyRun />;
    case "outro":
      return <SceneOutro />;
  }
};

export const Main: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: T.bg, fontFamily: sansFamily }}>
    <TapeGround />

    <Tape>
      {scenes.map((scene, i) => {
        const last = i === scenes.length - 1;
        return (
          <Sequence
            key={scene.id}
            from={from(i)}
            durationInFrames={scene.durationInFrames + (last ? 0 : SCENE_OVERLAP)}
            premountFor={SCENE_OVERLAP}
            styleWhilePremounted={{ opacity: 1 }}
            name={scene.id}
          >
            {sceneContent(scene)}
          </Sequence>
        );
      })}
    </Tape>

    <StatusStrip />
    <CaptionOverlay cues={captions} />

    {narrationSrc ? (
      <Sequence from={voiceOffset} name="narration">
        <Audio src={staticFile(narrationSrc)} />
      </Sequence>
    ) : null}

    {musicSrc ? (
      <Audio
        src={staticFile(musicSrc)}
        volume={(f) =>
          musicVolume *
          interpolate(f, [0, 45, TOTAL_FRAMES - 90, TOTAL_FRAMES - 10], [0, 1, 1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          })
        }
      />
    ) : null}
  </AbsoluteFill>
);
