import type { BinColor, FormFactor, Observation } from "@/domain";

/* What the camera has in view, as observations the resolver has not seen yet.

   FRAME DENSITY IS EVIDENCE, NOT DECORATION. Of 466 labelled photographs in the
   predecessor's archive, 430 hold exactly one bin, 30 hold two, 6 hold three,
   and none holds four or more. There is no photograph of a container bank in
   existence for this project.

   So: one bin is the common case, three touching containers is the densest
   verified case and leads, and six is a probe that says so on screen. Nothing
   here pretends a layout has been seen when it has not.

   These carry no answers. Each bin is an Observation – a form factor and the
   colours measured off the pixels – and what it means is the region pack's job.
   That is the whole architecture in one file: the device sees shape and colour;
   only the pack knows meaning. */

export interface FrameBin {
  n: number;
  observation: Observation;
  /** Percentage of the camera surface. */
  rect: { x: number; y: number; w: number; h: number };
  /** Which measured colours to quote, and on which part. */
  quoted: { color: BinColor; part: "lid" | "body" }[];
}

export interface Frame {
  count: 1 | 3 | 6;
  photo: string | null;
  /** False when no photograph of this density exists. Said on screen. */
  verified: boolean;
  noteKey: string;
  /** Media box aspect, so a marker sits over the object and not over a crop. */
  aspect: string;
  bins: FrameBin[];
}

const bin = (
  n: number,
  form_factor: FormFactor,
  rect: FrameBin["rect"],
  quoted: FrameBin["quoted"],
  measured?: Partial<Observation>,
): FrameBin => ({
  n,
  rect,
  quoted,
  observation: {
    form_factor,
    body_color: quoted.find((q) => q.part === "body")?.color ?? null,
    lid_color: quoted.find((q) => q.part === "lid")?.color ?? null,
    ...measured,
  },
});

export const FRAMES: Record<number, Frame> = {
  /* One bin: 92% of the archive.
     A uniform green shell whose body colour could not be measured with
     confidence – common, because the apertures carry the colour coding and the
     shell does not. Only the pack's generic igloo rule matches, and that rule
     requires a question. This is the disambiguation case as it actually
     arises. */
  1: {
    count: 1,
    photo: null,
    verified: true,
    aspect: "3 / 4",
    noteKey: "frame.singleNote",
    bins: [
      bin(1, "igloo", { x: 16, y: 20, w: 66, h: 62 }, [{ color: "metal", part: "lid" }], { body_color: null }),
    ],
  },

  /* Three touching containers. A real archive photograph, and the densest
     frame anybody on this project has ever had. Two of the three are visually
     identical grey-on-black wheelie bins and resolve identically – which is
     the honest outcome, not a bug in the fixture. */
  3: {
    count: 3,
    photo: "/photos/bank-3bins-brown-grey-touching.jpg",
    verified: true,
    aspect: "1 / 1",
    noteKey: "frame.threeNote",
    bins: [
      bin(1, "wheelie_small", { x: 0, y: 21, w: 14, h: 73 }, [
        { color: "brown", part: "lid" },
        { color: "brown", part: "body" },
      ]),
      bin(2, "wheelie_small", { x: 13, y: 17, w: 44, h: 75 }, [
        { color: "grey", part: "lid" },
        { color: "black", part: "body" },
      ]),
      bin(3, "wheelie_small", { x: 56, y: 13, w: 41, h: 76 }, [
        { color: "grey", part: "lid" },
        { color: "black", part: "body" },
      ]),
    ],
  },

  /* Six. No photograph of a container bank exists in the archive, so this
     layout is extrapolation and the sheet says so rather than letting it pass
     as evidence. The last container is orange: no rule in any pack matches it,
     so it comes back unknown even in a covered city. That happens. */
  6: {
    count: 6,
    photo: null,
    verified: false,
    aspect: "3 / 4",
    noteKey: "frame.sixNote",
    bins: [
      bin(1, "wheelie_large", { x: 2, y: 30, w: 15, h: 52 }, [
        { color: "blue", part: "lid" },
        { color: "grey", part: "body" },
      ]),
      bin(2, "wheelie_large", { x: 18, y: 32, w: 14, h: 50 }, [
        { color: "yellow", part: "lid" },
        { color: "yellow", part: "body" },
      ]),
      bin(3, "igloo", { x: 33, y: 26, w: 17, h: 56 }, [{ color: "green", part: "body" }]),
      bin(4, "textile_bank", { x: 51, y: 24, w: 15, h: 58 }, [{ color: "white", part: "body" }]),
      bin(5, "wheelie_large", { x: 67, y: 31, w: 14, h: 51 }, [
        { color: "grey", part: "lid" },
        { color: "black", part: "body" },
      ]),
      bin(6, "wheelie_large", { x: 82, y: 33, w: 15, h: 49 }, [{ color: "orange", part: "body" }]),
    ],
  },
};

/* Which bins in each frame are old enough that the card asks for a
   confirmation. Freshness is a registry fact, not an observation – it belongs
   to the place, not to the pixels. Dates are relative to the build so the
   demonstration does not rot. */
const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);

export const LAST_CONFIRMED: Record<number, Record<number, string | null>> = {
  1: { 1: daysAgo(3) },
  3: { 1: daysAgo(2), 2: daysAgo(45), 3: daysAgo(2) },
  6: { 1: daysAgo(2), 2: daysAgo(20), 3: daysAgo(1), 4: daysAgo(150), 5: daysAgo(2), 6: null },
};
