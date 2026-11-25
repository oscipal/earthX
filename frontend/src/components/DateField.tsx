import { useEffect, useRef, useState } from 'react';

import { clampDay, todayUtc, type DayBounds } from '../dateBounds';
import { dayAllowed, isDay, monthAllowed, monthCells, monthToShow, shiftMonth, type Month } from '../dayCalendar';
import { formatMonth, weekdayHeads } from '../numberFormat';
import { CalendarIcon, ChevronLeftIcon, ChevronRightIcon } from './icons';
import Popover from './Popover';

// A day as "2026-12-03", whatever the language of the browser (UI-12, Otto): a text field and a calendar of its own in English, in place
// of the browser's date field, which writes the day in the browser's language. The calendar offers only the days of `bounds` (UI-05
// §3.3); a day typed outside them is moved onto the nearest one when the field is left, and a text that is no day goes back to the last
// one.
export function DateField({
  value,
  onChange,
  label,
  disabled,
  bounds,
  lockReason,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  disabled?: boolean;
  bounds: DayBounds | null;
  lockReason?: string;
}) {
  const [text, setText] = useState(value);
  const [open, setOpen] = useState(false);
  const field = useRef<HTMLDivElement>(null);
  useEffect(() => setText(value), [value]);
  const leave = () => {
    if (text === '') return;
    if (!isDay(text)) {
      setText(value);
      return;
    }
    const day = clampDay(text, bounds);
    setText(day);
    if (day !== value) onChange(day);
  };
  return (
    <div className="date-field" ref={field}>
      <input
        autoComplete="off"
        type="text"
        inputMode="numeric"
        placeholder="YYYY-MM-DD"
        maxLength={10}
        value={text}
        min={bounds?.min ?? undefined}
        max={bounds?.max ?? undefined}
        onChange={(e) => {
          const next = e.target.value;
          setText(next);
          if (next === '' || isDay(next)) onChange(next);
        }}
        onBlur={leave}
        aria-label={label}
        disabled={disabled}
        data-tip={disabled ? lockReason : undefined}
      />
      <button
        type="button"
        className="icon-btn quiet date-icon-btn"
        aria-label={`Open the ${label.toLowerCase()} calendar`}
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        <CalendarIcon />
      </button>
      {open && (
        <Popover anchorRef={field} open onClose={() => setOpen(false)} className="day-calendar-popup" role="dialog" ariaLabel={label} focusOnOpen form minWidth={CALENDAR_WIDTH}>
          <DayCalendar
            value={value}
            bounds={bounds}
            onChoose={(day) => {
              onChange(day);
              setOpen(false);
            }}
          />
        </Popover>
      )}
    </div>
  );
}

// Wide enough for seven columns of days, also with the taller controls of a touch screen.
const CALENDAR_WIDTH = 264;

function DayCalendar({ value, bounds, onChoose }: { value: string; bounds: DayBounds | null; onChoose: (day: string) => void }) {
  const [shown, setShown] = useState<Month>(() => monthToShow(value, bounds, todayUtc()));
  const before = shiftMonth(shown, -1);
  const after = shiftMonth(shown, 1);
  const cells = monthCells(shown);
  return (
    <div className="day-calendar">
      <div className="day-calendar-head">
        <MonthArrow month={before} bounds={bounds} label="Previous month" onGo={setShown} />
        <span className="day-calendar-month">{formatMonth(shown.year, shown.month)}</span>
        <MonthArrow month={after} bounds={bounds} label="Next month" onGo={setShown} />
      </div>
      <div className="day-calendar-grid" role="grid">
        {weekdayHeads().map((head) => (
          <span key={head} className="day-calendar-weekday" role="columnheader">
            {head}
          </span>
        ))}
        {cells.map((day, i) =>
          day === null ? (
            <span key={`gap-${i}`} aria-hidden="true" />
          ) : (
            <button
              key={day}
              type="button"
              className="day-calendar-day"
              aria-label={day}
              aria-pressed={day === value}
              disabled={!dayAllowed(day, bounds)}
              onClick={() => onChoose(day)}
            >
              {Number(day.slice(8))}
            </button>
          ),
        )}
      </div>
    </div>
  );
}

function MonthArrow({ month, bounds, label, onGo }: { month: Month; bounds: DayBounds | null; label: string; onGo: (m: Month) => void }) {
  const allowed = monthAllowed(month, bounds);
  return (
    <button
      type="button"
      className="icon-btn sm quiet"
      aria-label={label}
      aria-disabled={allowed ? undefined : true}
      data-tip={allowed ? label : 'No day to choose there'}
      data-tip-level={allowed ? 'advanced' : undefined}
      onClick={() => {
        if (allowed) onGo(month);
      }}
    >
      {label === 'Previous month' ? <ChevronLeftIcon size={14} /> : <ChevronRightIcon size={14} />}
    </button>
  );
}
