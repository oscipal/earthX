// The panel's reading of a results document and of a failed job's problem
// (M4-11b-2, plan §3.3, K8), without mounting anything.

import { describe, expect, it } from 'vitest';

import { HttpError } from './api';
import { archiveOf, failureText, refusalMessage } from './processingStore';

const link = (name: string) => ({ href: `/processing/jobs/x/results/${name}` });

describe('archiveOf', () => {
  it('is the archive where the document names one', () => {
    expect(archiveOf({ result: link('result.tif'), bundle: link('result.zip') })).toBe('result.zip');
    expect(archiveOf({ export: link('export.zip'), recipe: link('recipe.json') })).toBe('export.zip');
  });

  it('is the archive even where the document links the methods text beside it', () => {
    expect(archiveOf({ result: link('result.tif'), bundle: link('result.zip'), methods: link('methods.txt') })).toBe('result.zip');
  });

  it('is nothing for a result from before the archives: the single files are not offered any more', () => {
    expect(archiveOf({ result: link('result.tif'), methods: link('methods.txt'), recipe: link('recipe.json') })).toBeNull();
  });

  it('skips a link that is no text and a name the job API does not serve', () => {
    expect(archiveOf({ broken: { href: 7 }, other: link('evil.zip'), again: link('result.zip') })).toBe('result.zip');
    expect(archiveOf({ broken: { href: 7 }, other: link('evil.zip') })).toBeNull();
  });

  it('is nothing for an empty document', () => {
    expect(archiveOf({})).toBeNull();
  });
});

describe('failureText', () => {
  const problem = (type: string | undefined, title?: string) => new HttpError(500, 'x', 'x', undefined, title, { type });

  it('words a job over its time limit as what to do', () => {
    expect(failureText(problem('urn:earthx:job-failed:runtime_exceeded', 'The job took longer than allowed'), 'f')).toBe(
      'The job took longer than allowed. Choose a smaller area or fewer assets.',
    );
  });

  it("keeps the backend's title for every other kind, the disk space included", () => {
    expect(failureText(problem('urn:earthx:job-failed:disk_space', 'too little disk space; try later'), 'f')).toBe(
      'too little disk space; try later',
    );
    expect(failureText(problem('urn:earthx:job-failed:source_5xx', 'The source failed'), 'f')).toBe('The source failed');
  });

  it('falls back where there is no title or no HttpError', () => {
    expect(failureText(problem('urn:earthx:job-failed:runtime_exceeded_soon'), 'fallback')).toBe('fallback');
    expect(failureText(problem(undefined), 'fallback')).toBe('fallback');
    expect(failureText(new TypeError('Failed to fetch'), 'fallback')).toBe('fallback');
  });
});

describe('refusalMessage', () => {
  const retired = 'dataset was retired on 2026-10-25; use another one instead';

  it('names a retired dataset, with the reason of the problem document', () => {
    const error = new HttpError(410, 'Gone', retired, undefined, 'Gone', { type: 'urn:earthx:gone' });
    expect(refusalMessage(error)).toBe(`Dataset retired: ${retired}`);
  });

  it('does not call a 410 without a problem document a retired dataset', () => {
    expect(refusalMessage(new HttpError(410, 'Gone'))).toBe('Gone');
  });

  it('words every other status by the detail of the server', () => {
    expect(refusalMessage(new HttpError(422, 'x', 'step 0: no good'))).toBe('step 0: no good');
    expect(refusalMessage(new TypeError('Failed to fetch'))).toBe('Failed to fetch');
  });
});
