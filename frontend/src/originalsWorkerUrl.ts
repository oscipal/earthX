// The address of the service worker of `originalsWorker.ts`, as the bundler gives it: a file of its own in the
// build, the module served by the dev server otherwise. Kept in a file of its own so that tests can replace it.
export { default as workerUrl } from './originalsWorker.ts?worker&url';
