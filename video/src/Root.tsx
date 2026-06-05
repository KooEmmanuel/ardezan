import React from "react";
import { Composition } from "remotion";
import { HeroVideo } from "./HeroVideo";
import { Act2Flow } from "./acts/Act2Flow";
import { Act1Studio } from "./acts/Act1Studio";
import { act1Total, act2Total, HERO_DURATION, VIDEO } from "./theme";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="HeroVideo"
        component={HeroVideo}
        durationInFrames={HERO_DURATION}
        fps={VIDEO.fps}
        width={VIDEO.width}
        height={VIDEO.height}
      />
      {/* Standalone compositions for fast iteration in the studio. */}
      <Composition
        id="Act2Flow"
        component={Act2Flow}
        durationInFrames={act2Total}
        fps={VIDEO.fps}
        width={VIDEO.width}
        height={VIDEO.height}
      />
      <Composition
        id="Act1Studio"
        component={Act1Studio}
        durationInFrames={act1Total}
        fps={VIDEO.fps}
        width={VIDEO.width}
        height={VIDEO.height}
      />
    </>
  );
};
