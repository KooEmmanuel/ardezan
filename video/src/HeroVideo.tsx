import React from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { Act1Studio } from "./acts/Act1Studio";
import { Act2Flow } from "./acts/Act2Flow";
import { Transition } from "./components/Transition";
import { act1Total, TRANSITION } from "./theme";

// Full hero loop: Act 1 (real Veo studio footage) → camera-flash Transition
// with an animated line → Act 2 (coded try-on → buy flow). Loops seamlessly.
export const HeroVideo: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <Sequence from={0} durationInFrames={act1Total}>
        <Act1Studio />
      </Sequence>

      <Sequence from={act1Total}>
        <Act2Flow />
      </Sequence>

      {/* Flash + animated text straddling the act boundary. */}
      <Sequence from={act1Total - TRANSITION.pre} durationInFrames={TRANSITION.pre + TRANSITION.post}>
        <Transition boundary={TRANSITION.pre} />
      </Sequence>
    </AbsoluteFill>
  );
};
