import type { ButtonHTMLAttributes, CSSProperties } from "react";

/* THE FRAME BORROWS NO COLOUR AND LENDS NONE.

   The camera view is the largest colour surface in the product and the one
   surface the design does not control: it is the real object, full bleed. So
   the marker is achromatic and DOUBLE-STROKED – an outer ink casing with an
   inner paper stroke, the cartographic halo used for labels over aerial
   imagery. It resolves against a white sack, a black wheelie bin, wet tarmac
   and blown-out sky alike, without tinting any of them.

   The owned violet never appears here. It lives on chrome pinned to the screen
   edge, never over the photograph – the photograph is the evidence, and the
   interface does not write on evidence.

   THE TAB CARRIES A NUMBER AND NOTHING ELSE.
   Tested against real frames of three touching containers: a tab wide enough to
   hold a translated name overhangs its own bounding box and collides with its
   neighbour's, and a name narrow enough to fit truncates to nonsense
   ("EVERYTHING E…"). So the frame marks position and the list carries language.
   The number is the join between them – it is what lets a bank of containers be
   discussed in text. A 24px square also cannot overflow at any density, and no
   translated string ever has to survive being set over a photograph.

   Selection is carried by stroke length and tab inversion, not by hue:
     unselected  short corner arms, ink tab
     selected    arms meet to close the box, paper tab

   THE ONE PLACE PHYSICAL PROPERTIES ARE CORRECT.
   Everything else in this system uses logical properties because Arabic is a
   launch locale. This component is the exception, and deliberately: it overlays
   a photograph, and a photograph does not mirror under RTL. A box positioned
   with insetInlineStart lands on the opposite side of the image from the object
   it is meant to mark the moment the interface language changes. The rect is a
   measurement of pixels, so it is written in pixels' terms – left and top.
   Everything textual inside the marker stays logical. */

export interface DetectionRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DetectionMarkerProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  index: number;
  label: string;
  rect?: DetectionRect;
  state?: "found" | "unknown";
  selected?: boolean;
  onSelect?: () => void;
  style?: CSSProperties;
}

type Corner = "tl" | "tr" | "bl" | "br";

export function DetectionMarker({
  index,
  label,
  rect = { x: 10, y: 20, w: 30, h: 45 },
  state = "found",
  selected = false,
  onSelect,
  style,
  ...rest
}: DetectionMarkerProps) {
  const anchorEnd = rect.x + rect.w > 62;
  const arm = selected ? "50%" : 16;
  const dashed = state === "unknown";

  const corner = (pos: Corner): CSSProperties => {
    const base: CSSProperties = {
      position: "absolute",
      inlineSize: arm,
      blockSize: arm,
      borderStyle: dashed ? "dashed" : "solid",
      borderWidth: 0,
      borderColor: "#ffffff",
      // outer ink casing around the paper stroke, so the frame reads on any scene
      filter:
        "drop-shadow(1px 0 0 #16181C) drop-shadow(-1px 0 0 #16181C) drop-shadow(0 1px 0 #16181C) drop-shadow(0 -1px 0 #16181C)",
    };
    const map: Record<Corner, CSSProperties> = {
      tl: { insetBlockStart: 0, insetInlineStart: 0, borderBlockStartWidth: 3, borderInlineStartWidth: 3 },
      tr: { insetBlockStart: 0, insetInlineEnd: 0, borderBlockStartWidth: 3, borderInlineEndWidth: 3 },
      bl: { insetBlockEnd: 0, insetInlineStart: 0, borderBlockEndWidth: 3, borderInlineStartWidth: 3 },
      br: { insetBlockEnd: 0, insetInlineEnd: 0, borderBlockEndWidth: 3, borderInlineEndWidth: 3 },
    };
    return { ...base, ...map[pos] };
  };

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={index + ". " + label}
      dir="ltr"
      style={{
        position: "absolute",
        // Physical, and only here: see the note above.
        left: rect.x + "%",
        top: rect.y + "%",
        width: rect.w + "%",
        height: rect.h + "%",
        background: "transparent",
        border: 0,
        padding: 0,
        cursor: "pointer",
        ...style,
      }}
      {...rest}
    >
      <span aria-hidden="true" style={corner("tl")} />
      <span aria-hidden="true" style={corner("tr")} />
      <span aria-hidden="true" style={corner("bl")} />
      <span aria-hidden="true" style={corner("br")} />
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          insetBlockStart: 0,
          insetInlineStart: anchorEnd ? "auto" : 0,
          insetInlineEnd: anchorEnd ? 0 : "auto",
          display: "grid",
          placeItems: "center",
          inlineSize: 24,
          blockSize: 24,
          background: selected ? "#FCFBF8" : "#16181C",
          color: selected ? "#16181C" : "#FCFBF8",
          boxShadow: selected ? "0 0 0 1px #16181C" : "0 0 0 1px rgba(252,251,248,0.65)",
          font: "var(--type-register)",
          fontWeight: "var(--weight-semibold)" as unknown as number,
          fontStyle: dashed ? "italic" : "normal",
          borderRadius: "var(--radius-1)",
        }}
      >
        {index}
      </span>
    </button>
  );
}
