import type { CSSProperties, SVGProps } from "react";

/* Icon glyph data: Lucide (https://lucide.dev), ISC licence. Copied verbatim
   from lucide-icons/lucide@main icons/*.svg. */

export const GLYPHS = {
  "arrow-left": '<path d="m12 19-7-7 7-7"></path> <path d="M19 12H5"></path>',
  "arrow-right": '<path d="M5 12h14"></path> <path d="m12 5 7 7-7 7"></path>',
  battery: '<path d="M 22 14 L 22 10"></path> <rect x="2" y="6" width="16" height="12" rx="2"></rect>',
  cable:
    '<path d="M17 19a1 1 0 0 1-1-1v-2a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2a1 1 0 0 1-1 1z"></path> <path d="M17 21v-2"></path> <path d="M19 14V6.5a1 1 0 0 0-7 0v11a1 1 0 0 1-7 0V10"></path> <path d="M21 21v-2"></path> <path d="M3 5V3"></path> <path d="M4 10a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2a2 2 0 0 1-2 2z"></path> <path d="M7 5V3"></path>',
  camera:
    '<path d="M13.997 4a2 2 0 0 1 1.76 1.05l.486.9A2 2 0 0 0 18.003 7H20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h1.997a2 2 0 0 0 1.759-1.048l.489-.904A2 2 0 0 1 10.004 4z"></path> <circle cx="12" cy="13" r="3"></circle>',
  "camera-off":
    '<path d="M14.564 14.558a3 3 0 1 1-4.122-4.121"></path> <path d="m2 2 20 20"></path> <path d="M20 20H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h1.997a2 2 0 0 0 .819-.175"></path> <path d="M9.695 4.024A2 2 0 0 1 10.004 4h3.993a2 2 0 0 1 1.76 1.05l.486.9A2 2 0 0 0 18.003 7H20a2 2 0 0 1 2 2v7.344"></path>',
  carrot:
    '<path d="M15 16a1 1 0 0 0-7-7q-4 4-5.987 12.385a.5.5 0 0 0 .602.602Q11 20 15 16l-3-3"></path> <path d="M15 9q4 4 7 0-3-4-7 0 4-4 0-7-4 3 0 7"></path> <path d="m8 15-2.58-2.58"></path>',
  check: '<path d="M20 6 9 17l-5-5"></path>',
  "chevron-down": '<path d="m6 9 6 6 6-6"></path>',
  "chevron-left": '<path d="m15 18-6-6 6-6"></path>',
  "chevron-right": '<path d="m9 18 6-6-6-6"></path>',
  cigarette:
    '<path d="M17 12H3a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1h14"></path> <path d="M18 8c0-2.5-2-2.5-2-5"></path> <path d="M21 16a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"></path> <path d="M22 8c0-2.5-2-2.5-2-5"></path> <path d="M7 12v4"></path>',
  "circle-alert":
    '<circle cx="12" cy="12" r="10"></circle> <line x1="12" x2="12" y1="8" y2="12"></line> <line x1="12" x2="12.01" y1="16" y2="16"></line>',
  "circle-question-mark":
    '<circle cx="12" cy="12" r="10"></circle> <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path> <path d="M12 17h.01"></path>',
  clock: '<circle cx="12" cy="12" r="10"></circle> <path d="M12 6v6l4 2"></path>',
  coins:
    '<path d="M13.744 17.736a6 6 0 1 1-7.48-7.48"></path> <path d="M15 6h1v4"></path> <path d="m6.134 14.768.866-.5 2 3.464"></path> <circle cx="16" cy="8" r="6"></circle>',
  cylinder: '<ellipse cx="12" cy="5" rx="9" ry="3"></ellipse> <path d="M3 5v14a9 3 0 0 0 18 0V5"></path>',
  dog: '<path d="M11.25 16.25h1.5L12 17z"></path> <path d="M16 14v.5"></path> <path d="M4.42 11.247A13.152 13.152 0 0 0 4 14.556C4 18.728 7.582 21 12 21s8-2.272 8-6.444a11.702 11.702 0 0 0-.493-3.309"></path> <path d="M8 14v.5"></path> <path d="M8.5 8.5c-.384 1.05-1.083 2.028-2.344 2.5-1.931.722-3.576-.297-3.656-1-.113-.994 1.177-6.53 4-7 1.923-.321 3.651.845 3.651 2.235A7.497 7.497 0 0 1 14 5.277c0-1.39 1.844-2.598 3.767-2.277 2.823.47 4.113 6.006 4 7-.08.703-1.725 1.722-3.656 1-1.261-.472-1.855-1.45-2.239-2.5"></path>',
  droplet:
    '<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"></path>',
  flag: '<path d="M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.333 2q2 0 3.067-.8A1 1 0 0 1 20 4v10a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2-8-2a6 6 0 0 0-4 1.528"></path>',
  globe:
    '<circle cx="12" cy="12" r="10"></circle> <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"></path> <path d="M2 12h20"></path>',
  image:
    '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"></rect> <circle cx="9" cy="9" r="2"></circle> <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"></path>',
  info: '<circle cx="12" cy="12" r="10"></circle> <path d="M12 16v-4"></path> <path d="M12 8h.01"></path>',
  layers:
    '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z"></path> <path d="M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12"></path> <path d="M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17"></path>',
  list: '<path d="M3 5h.01"></path> <path d="M3 12h.01"></path> <path d="M3 19h.01"></path> <path d="M8 5h13"></path> <path d="M8 12h13"></path> <path d="M8 19h13"></path>',
  "loader-circle": '<path d="M21 12a9 9 0 1 1-6.219-8.56"></path>',
  map: '<path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"></path> <path d="M15 5.764v15"></path> <path d="M9 3.236v15"></path>',
  "map-pin":
    '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"></path> <circle cx="12" cy="10" r="3"></circle>',
  menu: '<path d="M4 5h16"></path> <path d="M4 12h16"></path> <path d="M4 19h16"></path>',
  minus: '<path d="M5 12h14"></path>',
  moon: '<path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"></path>',
  newspaper:
    '<path d="M15 18h-5"></path> <path d="M18 14h-8"></path> <path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-4 0v-9a2 2 0 0 1 2-2h2"></path> <rect width="8" height="4" x="10" y="6" rx="1"></rect>',
  package:
    '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"></path> <path d="M12 22V12"></path> <polyline points="3.29 7 12 12 20.71 7"></polyline> <path d="m7.5 4.27 9 5.15"></path>',
  pill: '<path d="m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z"></path> <path d="m8.5 8.5 7 7"></path>',
  plus: '<path d="M5 12h14"></path> <path d="M12 5v14"></path>',
  search: '<path d="m21 21-4.34-4.34"></path> <circle cx="11" cy="11" r="8"></circle>',
  send: '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"></path> <path d="m21.854 2.147-10.94 10.939"></path>',
  settings:
    '<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"></path> <circle cx="12" cy="12" r="3"></circle>',
  "shield-check":
    '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"></path> <path d="m9 12 2 2 4-4"></path>',
  shirt:
    '<path d="M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"></path>',
  shrub:
    '<path d="M12 22v-5.172a2 2 0 0 0-.586-1.414L9.5 13.5"></path> <path d="M14.5 14.5 12 17"></path> <path d="M17 8.8A6 6 0 0 1 13.8 20H10A6.5 6.5 0 0 1 7 8a5 5 0 0 1 10 0z"></path>',
  sofa: '<path d="M20 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v3"></path> <path d="M2 16a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5a2 2 0 0 0-4 0v1.5a.5.5 0 0 1-.5.5h-11a.5.5 0 0 1-.5-.5V11a2 2 0 0 0-4 0z"></path> <path d="M4 18v2"></path> <path d="M20 18v2"></path> <path d="M12 4v9"></path>',
  sun: '<circle cx="12" cy="12" r="4"></circle> <path d="M12 2v2"></path> <path d="M12 20v2"></path> <path d="m4.93 4.93 1.41 1.41"></path> <path d="m17.66 17.66 1.41 1.41"></path> <path d="M2 12h2"></path> <path d="M20 12h2"></path> <path d="m6.34 17.66-1.41 1.41"></path> <path d="m19.07 4.93-1.41 1.41"></path>',
  trash:
    '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"></path> <path d="M3 6h18"></path> <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>',
  "trash-2":
    '<path d="M10 11v6"></path> <path d="M14 11v6"></path> <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"></path> <path d="M3 6h18"></path> <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>',
  "triangle-alert":
    '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"></path> <path d="M12 9v4"></path> <path d="M12 17h.01"></path>',
  upload:
    '<path d="M12 3v12"></path> <path d="m17 8-5-5-5 5"></path> <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>',
  "wifi-off":
    '<path d="M12 20h.01"></path> <path d="M8.5 16.429a5 5 0 0 1 7 0"></path> <path d="M5 12.859a10 10 0 0 1 5.17-2.69"></path> <path d="M19 12.859a10 10 0 0 0-2.007-1.523"></path> <path d="M2 8.82a15 15 0 0 1 4.177-2.643"></path> <path d="M22 8.82a15 15 0 0 0-11.288-3.764"></path> <path d="m2 2 20 20"></path>',
  wine: '<path d="M8 22h8"></path> <path d="M7 10h10"></path> <path d="M12 15v7"></path> <path d="M12 15a5 5 0 0 0 5-5c0-2-.5-4-2-8H9c-1.5 4-2 6-2 8a5 5 0 0 0 5 5Z"></path>',
  x: '<path d="M18 6 6 18"></path> <path d="m6 6 12 12"></path>',
} as const;

export type GlyphName = keyof typeof GLYPHS;

/* Waste-stream id -> glyph. Deliberately avoids the recycling triangle and leaf
   motifs (anti-references in the brief); every stream has a literal object glyph. */
export const STREAM_GLYPH: Record<string, GlyphName> = {
  residual: "trash-2",
  street_litter: "trash",
  cigarette: "cigarette",
  dog_waste: "dog",
  paper: "newspaper",
  packaging: "package",
  metal: "cylinder",
  glass_clear: "wine",
  glass_green: "wine",
  glass_brown: "wine",
  glass_mixed: "wine",
  bio: "carrot",
  garden: "shrub",
  ewaste: "cable",
  batteries: "battery",
  bulky: "sofa",
  hazardous: "triangle-alert",
  cooking_oil: "droplet",
  medicines: "pill",
  textiles: "shirt",
  deposit_return: "coins",
  unknown: "circle-question-mark",
};

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name" | "stroke"> {
  name: GlyphName | string;
  size?: number;
  stroke?: number;
  label?: string;
  style?: CSSProperties;
}

export function Icon({ name, size = 24, stroke = 2, label, style, className, ...rest }: IconProps) {
  const d = GLYPHS[name as GlyphName] ?? GLYPHS["circle-question-mark"];
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : "presentation"}
      aria-label={label || undefined}
      aria-hidden={label ? undefined : "true"}
      focusable="false"
      className={className}
      style={{ display: "block", flex: "none", ...style }}
      dangerouslySetInnerHTML={{ __html: (label ? "<title>" + label + "</title>" : "") + d }}
      {...rest}
    />
  );
}
