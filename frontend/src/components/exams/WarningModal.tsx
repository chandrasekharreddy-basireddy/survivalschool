"use client";

interface Props {
  warningNumber: number;
  maxWarnings: number;
  reason: string;
  onAcknowledge: () => void;
}

export function WarningModal({ warningNumber, maxWarnings, reason, onAcknowledge }: Props) {
  const remaining = maxWarnings - warningNumber;
  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <div className="mx-4 max-w-md rounded-xl border border-red-500/40 bg-ink-950 p-8 text-center shadow-2xl">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10 text-3xl text-red-400">
          {remaining > 0 ? "⚠" : "✕"}
        </div>
        <h2 className="text-xl font-bold text-fg">
          Warning {warningNumber} of {maxWarnings}
        </h2>
        <p className="mt-3 text-sm text-fg-muted">
          {reason === "tab_blur" && "You switched away from the exam tab."}
          {reason === "fullscreen_exit" && "You exited fullscreen mode."}
          {reason === "copy" && "Copy attempt detected."}
          {reason === "paste" && "Paste attempt detected."}
          {reason === "right_click" && "Restricted action detected."}
          {!["tab_blur", "fullscreen_exit", "copy", "paste", "right_click"].includes(reason) &&
            "An integrity violation was detected."}
        </p>
        {remaining > 0 ? (
          <p className="mt-2 text-sm font-medium text-red-400">
            {remaining === 1
              ? "This is your final warning. One more violation will terminate your exam."
              : `You have ${remaining} warning${remaining === 1 ? "" : "s"} remaining.`}
          </p>
        ) : (
          <p className="mt-2 text-sm font-medium text-red-400">
            Your exam has been terminated due to repeated violations.
          </p>
        )}
        <button
          type="button"
          onClick={onAcknowledge}
          className="btn-primary mt-6 w-full"
        >
          {remaining > 0 ? "I understand, continue exam" : "Close"}
        </button>
      </div>
    </div>
  );
}
