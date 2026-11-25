import { ChevronLeftIcon, ChevronRightIcon } from './icons';

// The pages of a list that must not scroll (UI-05, "Datasets"; UI-12, "Quick processing"): small at the right of its heading, "‹ 1 / n ›",
// also with one page; an arrow at the end is locked with the reason.
export default function Pager({ label, className, page, pages, onPage }: { label: string; className: string; page: number; pages: number; onPage: (page: number) => void }) {
  const first = page === 0;
  const last = page >= pages - 1;
  return (
    <span className={`${className} pager`} role="group" aria-label={label}>
      <button
        type="button"
        className="icon-btn sm"
        aria-label="Previous page"
        aria-disabled={first || undefined}
        data-tip-level="advanced"
        data-tip={first ? 'Already on the first page' : 'Previous page'}
        onClick={() => {
          if (!first) onPage(page - 1);
        }}
      >
        <ChevronLeftIcon size={14} />
      </button>
      <span className="dataset-page-count">
        {page + 1} / {pages}
      </span>
      <button
        type="button"
        className="icon-btn sm"
        aria-label="Next page"
        aria-disabled={last || undefined}
        data-tip-level="advanced"
        data-tip={last ? 'Already on the last page' : 'Next page'}
        onClick={() => {
          if (!last) onPage(page + 1);
        }}
      >
        <ChevronRightIcon size={14} />
      </button>
    </span>
  );
}
