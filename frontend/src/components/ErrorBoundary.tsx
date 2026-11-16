// A part of the page that fails while it renders or in an effect shows a short note with "Reload" instead of a white page (UI-10). The
// whole app has one boundary, the map one of its own, so that the panels stay usable when only the map fails.

import { Component, type ErrorInfo, type ReactNode } from 'react';

import { useAppStore } from '../store';

interface Props {
  // What failed, said in the note: "The map" or "The page".
  what: string;
  // Outside the app (`main.tsx`) the note brings its own theme; inside, it takes the one of the app.
  themed?: boolean;
  children: ReactNode;
}

interface State {
  failed: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error(`${this.props.what} failed`, error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    const note = (
      <div className="error-note" role="alert">
        <p>{this.props.what} ran into an error.</p>
        <button type="button" className="btn primary" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    );
    return this.props.themed ? (
      <div className="app error-page" data-theme={useAppStore.getState().theme}>
        {note}
      </div>
    ) : (
      note
    );
  }
}
