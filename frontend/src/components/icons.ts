// The one source of the icons of the interface (UI-04 part 2, `docs/ui/leitfaden.md` §3): Lucide, one stroke, three sizes. Nothing else imports
// `lucide-react`, and no character of the text stands for an icon. A new icon gets its line here and a row in the table of the guide.

import { createElement, type ComponentType } from 'react';

import {
  ArchiveRestore,
  ArrowDown,
  ArrowLeft,
  ArrowLeftRight,
  ArrowUp,
  ArrowUpDown,
  ArrowUpToLine,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleX,
  Cog,
  Copy,
  Download,
  Ellipsis,
  Eye,
  EyeOff,
  GripHorizontal,
  GripVertical,
  History,
  Info,
  LayoutGrid,
  List,
  ClipboardList,
  Layers,
  MapPin,
  Monitor,
  Moon,
  Pause,
  Pencil,
  Pentagon,
  Play,
  Plus,
  RotateCw,
  Scan,
  Search,
  Square,
  Sun,
  Trash2,
  TriangleAlert,
  Upload,
  X,
  createLucideIcon,
  type LucideIcon,
} from 'lucide-react';

import { ICON_SIZES } from './iconSizes';
import { SETTINGS_ICON_NODE } from './settingsIconNode';

// 16 px is the standard; 14 px stands in the rows of a list; 20 px is the rail at the left (Otto, 4.11.2026). The same numbers are the tokens
// `--icon-size`, `--icon-size-sm` and `--icon-size-rail` of `tokens.css`; `icons.test.tsx` keeps the two together.
export type IconSize = (typeof ICON_SIZES)[keyof typeof ICON_SIZES];
export interface IconProps {
  size?: IconSize;
  // Stands in front of a text: keeps its distance from it (`.icon-lead`).
  lead?: boolean;
  className?: string;
}

// A stroke of 1.5 px at every size (`absoluteStrokeWidth`), in the colour of the text around it.
const STROKE = 1.5;

function icon(name: string, Glyph: LucideIcon): ComponentType<IconProps> {
  const Icon = ({ size = ICON_SIZES.standard, lead = false, className }: IconProps) =>
    createElement(Glyph, {
      size,
      strokeWidth: STROKE,
      absoluteStrokeWidth: true,
      className: [lead ? 'icon-lead' : '', className ?? ''].filter(Boolean).join(' ') || undefined,
      'aria-hidden': true,
      focusable: false,
    });
  Icon.displayName = name;
  return Icon;
}

export const ArchiveRestoreIcon = icon('ArchiveRestoreIcon', ArchiveRestore);
export const ArrowDownIcon = icon('ArrowDownIcon', ArrowDown);
export const ArrowLeftIcon = icon('ArrowLeftIcon', ArrowLeft);
export const ArrowLeftRightIcon = icon('ArrowLeftRightIcon', ArrowLeftRight);
export const ArrowUpIcon = icon('ArrowUpIcon', ArrowUp);
export const ArrowUpDownIcon = icon('ArrowUpDownIcon', ArrowUpDown);
export const ArrowUpToLineIcon = icon('ArrowUpToLineIcon', ArrowUpToLine);
export const CheckIcon = icon('CheckIcon', Check);
export const ChevronDownIcon = icon('ChevronDownIcon', ChevronDown);
export const ChevronLeftIcon = icon('ChevronLeftIcon', ChevronLeft);
export const ChevronRightIcon = icon('ChevronRightIcon', ChevronRight);
export const ChevronUpIcon = icon('ChevronUpIcon', ChevronUp);
export const ClearIcon = icon('ClearIcon', CircleX);
export const CogIcon = icon('CogIcon', Cog);
export const CopyIcon = icon('CopyIcon', Copy);
export const CoverageIcon = icon('CoverageIcon', LayoutGrid);
export const DownloadIcon = icon('DownloadIcon', Download);
export const EllipsisIcon = icon('EllipsisIcon', Ellipsis);
export const EyeIcon = icon('EyeIcon', Eye);
export const EyeOffIcon = icon('EyeOffIcon', EyeOff);
export const GripHorizontalIcon = icon('GripHorizontalIcon', GripHorizontal);
export const GripVerticalIcon = icon('GripVerticalIcon', GripVertical);
export const HistoryIcon = icon('HistoryIcon', History);
export const InfoIcon = icon('InfoIcon', Info);
export const LayersIcon = icon('LayersIcon', Layers);
export const JobsIcon = icon('JobsIcon', ClipboardList);
export const MapPinIcon = icon('MapPinIcon', MapPin);
export const MonitorIcon = icon('MonitorIcon', Monitor);
export const MoonIcon = icon('MoonIcon', Moon);
export const PauseIcon = icon('PauseIcon', Pause);
export const PencilIcon = icon('PencilIcon', Pencil);
export const PentagonIcon = icon('PentagonIcon', Pentagon);
export const PlayIcon = icon('PlayIcon', Play);
export const PlusIcon = icon('PlusIcon', Plus);
export const ResultsListIcon = icon('ResultsListIcon', List);
export const RetryIcon = icon('RetryIcon', RotateCw);
export const SearchIcon = icon('SearchIcon', Search);
// "Settings 6 Line" of MingCute, redrawn as strokes (`settingsIconNode.ts`): the one icon that is not Lucide's.
export const SettingsIcon = icon('SettingsIcon', createLucideIcon('settings-6-line', SETTINGS_ICON_NODE));
export const SquareIcon = icon('SquareIcon', Square);
export const SunIcon = icon('SunIcon', Sun);
export const TrashIcon = icon('TrashIcon', Trash2);
export const UploadIcon = icon('UploadIcon', Upload);
export const WarningIcon = icon('WarningIcon', TriangleAlert);
export const XIcon = icon('XIcon', X);
export const ZoomToSelectionIcon = icon('ZoomToSelectionIcon', Scan);
