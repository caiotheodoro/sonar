/**
 * The frame every beat wears until its scene is built: eyebrow, the beat's
 * claim from the manifest, its target length, and whatever bound numbers the
 * beat will eventually show, so the binding is exercised from the first
 * render. Nothing here is typed; the caller passes values it read through
 * `RESULTS`.
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { FPS, Scene, SceneId, scenes } from "../manifest";
import { Eyebrow, GridGround, Title } from "./GridGround";
import { T } from "../theme";

export const sceneById = (id: SceneId): Scene => {
  const scene = scenes.find((s) => s.id === id);
  if (!scene) throw new Error(`no scene "${id}" in the manifest`);
  return scene;
};

export const BeatPlaceholder: React.FC<{
  id: SceneId;
  children?: React.ReactNode;
}> = ({ id, children }) => {
  const scene = sceneById(id);
  const index = scenes.indexOf(scene) + 1;
  return (
    <GridGround>
      <AbsoluteFill style={{ padding: "80px 120px 210px", justifyContent: "center" }}>
        <Eyebrow style={{ color: T.textFaint }}>
          beat {index} · {id} · {(scene.durationInFrames / FPS).toFixed(0)}s
        </Eyebrow>
        <Title style={{ marginTop: 14, marginBottom: 46, maxWidth: 1500 }}>{scene.claim}</Title>
        {children}
        {scene.cast ? (
          <div style={{ marginTop: 40, fontFamily: T.mono, fontSize: 22, color: T.textFaint }}>
            plays public/casts/{scene.cast.src}.cast once recorded
          </div>
        ) : null}
      </AbsoluteFill>
    </GridGround>
  );
};
