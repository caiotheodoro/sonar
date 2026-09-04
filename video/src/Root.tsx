import React from "react";
import { Composition } from "remotion";
import { Main } from "./Main";
import { SocialCard } from "./scenes/SocialCard";
import { FPS, HEIGHT, WIDTH } from "./manifest";
import { TIMELINE } from "./timeline";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="Sonar"
      component={Main}
      durationInFrames={TIMELINE.totalFrames}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
    <Composition
      id="SocialCard"
      component={SocialCard}
      durationInFrames={1}
      fps={FPS}
      width={1200}
      height={630}
    />
  </>
);
