import { Button, EmptyState, TopBar } from "@/components";
import type { Region } from "@/data/regions";
import { REGION_ID } from "@/data/regions";
import type { T } from "@/i18n";

/* No camera is not a broken app. The whole rules half of the product is here,
   and the contribute form is a camera-free way to identify a bin. */

export function CameraOff({
  t,
  region,
  onBrowse,
  onAllow,
  onContribute,
}: {
  t: T;
  region: Region;
  onBrowse: () => void;
  onAllow: () => void;
  onContribute: () => void;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateRows: "auto 1fr auto",
        blockSize: "100%",
        background: "var(--surface-page)",
        overflow: "hidden",
      }}
    >
      <TopBar title={t("camera.deniedTitle")} register={REGION_ID[region.key].toUpperCase()} />

      <div
        style={{
          overflowY: "auto",
          padding: "var(--gutter-phone)",
          display: "grid",
          gap: "var(--space-5)",
          alignContent: "start",
        }}
      >
        <EmptyState icon="camera-off" title={t("camera.deniedTitle")} hatched>
          {t("camera.deniedBody")}
        </EmptyState>
        <div style={{ display: "grid", gap: "var(--space-2)" }}>
          <Button variant="secondary" size="outdoor" block icon="search" onClick={onBrowse}>
            {t("unknown.search")}
          </Button>
          <Button variant="secondary" size="outdoor" block icon="package" onClick={onContribute}>
            {t("camera.describe")}
          </Button>
        </div>
      </div>

      <div style={{ padding: "var(--gutter-phone)", borderBlockStart: "var(--border-hair) solid var(--line-hair)" }}>
        <Button size="outdoor" block icon="camera" onClick={onAllow}>
          {t("camera.enable")}
        </Button>
      </div>
    </div>
  );
}
