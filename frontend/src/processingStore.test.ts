// The panel's reading of a results document and of a failed job's problem
// (M4-11b-2, plan §3.3, K8), without mounting anything.

import { describe, expect, it } from 'vitest';

import { HttpError } from './api';
import { failureText, resultFiles, ZIP_LABEL } from './processingStore';

const link = (name: string) => ({ href: `/processing/jobs/x/results/${name}` });

describe('resultFiles', () => {
  it('is the one archive where the document names one', () => {
    expect(resultFiles({ result: link('result.tif'), bundle: link('result.zip') })).toEqual([
      { file: 'result.zip', label: ZIP_LABEL },
    ]);
    expect(resultFiles({ export: link('export.zip'), recipe: link('recipe.json') })).toEqual([
      { file: 'export.zip', label: ZIP_LABEL },
    ]);
  });

  it('is the single links, each once, without names the job API does not serve', () => {
    expect(
      resultFiles({
        result: link('result.tif'),
        again: link('result.tif'),
        other: link('evil.exe'),
        broken: { href: 7 },
        recipe: link('recipe.json'),
      }),
    ).toEqual([
      { file: 'result.tif', label: 'Result (COG)' },
      { file: 'recipe.json', label: 'Recipe' },
    ]);
  });

  it('is empty for an empty document', () => {
    expect(resultFiles({})).toEqual([]);
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
