import { Config } from "@remotion/cli/config";

// 1080p, transparent disabled (we render an opaque hero loop).
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setConcurrency(null); // let Remotion pick based on cores
Config.setChromiumOpenGlRenderer("angle");
