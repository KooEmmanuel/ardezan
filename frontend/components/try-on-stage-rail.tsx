"use client";

import type { ReactNode } from "react";

// Five stages of the try-on orchestration. We don't render labels — the
// progress bar alone is enough customer signal — but keep the type so
// callers continue to pass meaningful values for telemetry.
type StageId =
  | "validating_upload"
  | "analyzing_photo"
  | "building_catalog_context"
  | "recommending_outfits"
  | "generating_images"
  | "completed"
  | "failed";

export function TryOnStageRail({
  progress,
  terminal,
}: {
  current: StageId;
  progress: number;
  terminal: null | "completed" | "completed_partial" | "failed";
}): ReactNode {
  const failed = terminal === "failed";

  return (
    <div className="stage-rail">
      <div className="stage-progress">
        <div
          className="stage-progress-fill"
          style={{
            width: `${terminal ? 100 : Math.max(4, progress)}%`,
            background: failed ? "#8d1717" : undefined,
          }}
        />
      </div>
    </div>
  );
}
