import React from "react";

type Props = {
  children: React.ReactNode;
};

type State = {
  error: Error | null;
  errorInfo: string | null;
};

function formatUnknownError(err: unknown): Error {
  if (err instanceof Error) return err;
  try {
    return new Error(typeof err === "string" ? err : JSON.stringify(err));
  } catch {
    return new Error(String(err));
  }
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null, errorInfo: null };

  private onUnhandledRejection = (event: PromiseRejectionEvent) => {
    const err = formatUnknownError(event.reason);
    // eslint-disable-next-line no-console
    console.error("Unhandled promise rejection:", err);
    this.setState({ error: err, errorInfo: "unhandledrejection" });
  };

  private onWindowError = (event: ErrorEvent) => {
    const err = formatUnknownError(event.error ?? event.message);
    // eslint-disable-next-line no-console
    console.error("Window error:", err);
    this.setState({ error: err, errorInfo: "window.onerror" });
  };

  componentDidMount(): void {
    window.addEventListener("unhandledrejection", this.onUnhandledRejection);
    window.addEventListener("error", this.onWindowError);
  }

  componentWillUnmount(): void {
    window.removeEventListener("unhandledrejection", this.onUnhandledRejection);
    window.removeEventListener("error", this.onWindowError);
  }

  static getDerivedStateFromError(error: Error): State {
    return { error, errorInfo: "render" };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error("React render error:", error, info);
    this.setState({ error, errorInfo: info.componentStack || "componentDidCatch" });
  }

  private resetApp = () => {
    try {
      localStorage.removeItem("btl_session");
    } catch {
      // ignore
    }
    window.location.reload();
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div style={{ padding: "2rem", maxWidth: 900, margin: "0 auto" }}>
        <h1>Something went wrong</h1>
        <p>
          The app hit a runtime error (usually a bad API response or stale saved session) and
          stopped rendering.
        </p>
        <button onClick={this.resetApp} style={{ marginBottom: "1rem" }}>
          Reset App
        </button>
        <div
          style={{
            background: "#0f172a",
            color: "#e2e8f0",
            padding: "1rem",
            borderRadius: 12,
            overflow: "auto"
          }}
        >
          <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
            {String(this.state.errorInfo ?? "")}
            {"\n\n"}
            {this.state.error.name}: {this.state.error.message}
            {"\n\n"}
            {this.state.error.stack ?? ""}
          </pre>
        </div>
      </div>
    );
  }
}

