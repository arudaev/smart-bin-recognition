/* The design system, imported from Claude Design and rewritten in TypeScript.
   The guidelines that justify each component live in the header comment of its
   own file; do not restyle one without reading that comment first.

   Source: Smart Bin Recognition Design System
   (claude.ai/design – design system 3b3cb5ca-7fa0-4985-95aa-c785cde0f2be) */

export { Button } from "./core/Button";
export type { ButtonProps, ButtonSize, ButtonVariant } from "./core/Button";
export { Card } from "./core/Card";
export type { CardProps } from "./core/Card";
export { GLYPHS, Icon, STREAM_GLYPH } from "./core/Icon";
export type { GlyphName, IconProps } from "./core/Icon";
export { IconButton } from "./core/IconButton";
export type { IconButtonProps } from "./core/IconButton";
export { Tag } from "./core/Tag";
export type { TagProps } from "./core/Tag";

export { ColorQuote } from "./domain/ColorQuote";
export type { ColorQuoteProps } from "./domain/ColorQuote";
export { DetectionMarker } from "./domain/DetectionMarker";
export type { DetectionMarkerProps, DetectionRect } from "./domain/DetectionMarker";
export { Freshness } from "./domain/Freshness";
export type { FreshnessProps } from "./domain/Freshness";
export { ItemRule } from "./domain/ItemRule";
export type { ItemRuleProps, Verdict } from "./domain/ItemRule";
export { LocalName } from "./domain/LocalName";
export type { LocalNameProps } from "./domain/LocalName";
export { ResultCard } from "./domain/ResultCard";
export type { QuotedColor, ResultCardProps, ResultLevel } from "./domain/ResultCard";
export { RuleGroup } from "./domain/RuleGroup";
export type { RuleGroupProps } from "./domain/RuleGroup";
export { StreamGlyph } from "./domain/StreamGlyph";
export type { StreamGlyphProps } from "./domain/StreamGlyph";

export { EmptyState } from "./feedback/EmptyState";
export type { EmptyStateProps } from "./feedback/EmptyState";
export { Notice } from "./feedback/Notice";
export type { NoticeProps } from "./feedback/Notice";
export { Sheet } from "./feedback/Sheet";
export type { SheetProps } from "./feedback/Sheet";
export { StatusStrip } from "./feedback/StatusStrip";
export type { ConnectionState, StatusStripProps } from "./feedback/StatusStrip";

export { ChoiceTile } from "./forms/ChoiceTile";
export type { ChoiceTileProps } from "./forms/ChoiceTile";
export { LanguageList } from "./forms/LanguageList";
export type { LanguageItem, LanguageListProps } from "./forms/LanguageList";
export { Stepper } from "./forms/Stepper";
export type { StepperProps } from "./forms/Stepper";
export { TextField } from "./forms/TextField";
export type { TextFieldProps } from "./forms/TextField";

export { ListRow } from "./navigation/ListRow";
export type { ListRowProps } from "./navigation/ListRow";
export { SegmentedControl } from "./navigation/SegmentedControl";
export type { SegmentedControlProps, SegmentedItem } from "./navigation/SegmentedControl";
export { TopBar } from "./navigation/TopBar";
export type { TopBarProps } from "./navigation/TopBar";
