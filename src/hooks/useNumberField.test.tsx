/**
 * `useNumberField` drops the draft on every commit, so the field shows the
 * stored value afterwards whether or not the commit changed it.
 */

import { act, fireEvent, render } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { useNumberField } from "./useNumberField";

/** A field over a store that clamps to [1, 10] and rounds, like the KURO setters. */
function Harness({
  initial,
  parse,
  onCommit,
}: {
  initial: number;
  parse: (text: string) => number | undefined;
  onCommit?: (next: number) => void;
}) {
  const [stored, setStored] = useState(initial);
  const field = useNumberField({
    value: stored,
    parse,
    commit: (next) => {
      onCommit?.(next);
      setStored(Math.max(1, Math.min(10, Math.round(next))));
    },
  });
  return (
    <>
      <input type="number" aria-label="field" {...field.inputProps} />
      <output data-testid="stored">{stored}</output>
    </>
  );
}

const strictInt = (text: string) => {
  const n = Number.parseInt(text, 10);
  return Number.isNaN(n) ? undefined : n;
};
const withFallback = (text: string) => {
  const n = parseFloat(text);
  return Number.isFinite(n) ? n : 5;
};

function setup(initial: number, parse: (text: string) => number | undefined) {
  const onCommit = vi.fn();
  const view = render(<Harness initial={initial} parse={parse} onCommit={onCommit} />);
  const input = view.getByLabelText("field") as HTMLInputElement;
  const stored = () => view.getByTestId("stored").textContent;
  return { input, stored, onCommit };
}

function type(input: HTMLInputElement, text: string) {
  fireEvent.change(input, { target: { value: text } });
}

describe("useNumberField", () => {
  it("blank commits nothing and shows the stored value again", () => {
    const { input, stored, onCommit } = setup(7, strictInt);
    type(input, "");
    fireEvent.blur(input);
    expect(onCommit).not.toHaveBeenCalled();
    expect(stored()).toBe("7");
    expect(input.value).toBe("7");
  });

  it("blank commits the fallback a field declares, and shows it", () => {
    const { input, stored } = setup(5, withFallback);
    type(input, "");
    fireEvent.blur(input);
    expect(stored()).toBe("5");
    expect(input.value).toBe("5");
  });

  it("0 below the floor shows the floor even when the store already held it", () => {
    const { input, stored, onCommit } = setup(1, strictInt);
    type(input, "0");
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalledWith(0);
    expect(stored()).toBe("1");
    expect(input.value).toBe("1");
  });

  it("a negative entry shows the floor", () => {
    const { input, stored } = setup(4, strictInt);
    type(input, "-3");
    fireEvent.blur(input);
    expect(stored()).toBe("1");
    expect(input.value).toBe("1");
  });

  it("text that is not a number commits nothing", () => {
    // jsdom sanitizes a number input's non-numeric value to "", as browsers do.
    const { input, stored, onCommit } = setup(6, strictInt);
    type(input, "abc");
    fireEvent.blur(input);
    expect(onCommit).not.toHaveBeenCalled();
    expect(stored()).toBe("6");
    expect(input.value).toBe("6");
  });

  it("an entry above the ceiling shows the ceiling the store already held", () => {
    const { input, stored } = setup(10, strictInt);
    type(input, "40");
    fireEvent.blur(input);
    expect(stored()).toBe("10");
    expect(input.value).toBe("10");
  });

  it("a fraction shows the rounded value the store kept", () => {
    const { input, stored } = setup(3, withFallback);
    type(input, "3.4");
    fireEvent.blur(input);
    expect(stored()).toBe("3");
    expect(input.value).toBe("3");
  });

  it("Enter commits like blur", () => {
    const { input, stored } = setup(3, strictInt);
    input.focus();
    type(input, "8");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(stored()).toBe("8");
    expect(input.value).toBe("8");
  });

  it("keeps a draft across re-renders that leave the stored value alone", () => {
    function Rerender() {
      const [stored] = useState(3);
      const [, bump] = useState(0);
      const field = useNumberField({ value: stored, parse: strictInt, commit: () => {} });
      return (
        <>
          <input type="number" aria-label="field" {...field.inputProps} />
          <button type="button" onClick={() => bump((n) => n + 1)}>bump</button>
        </>
      );
    }
    const view = render(<Rerender />);
    const input = view.getByLabelText("field") as HTMLInputElement;
    type(input, "");
    act(() => {
      fireEvent.click(view.getByText("bump"));
    });
    expect(input.value).toBe("");
  });

  it("formats the stored value with the field's format", () => {
    function Seed() {
      const [seed, setSeed] = useState<number | null>(null);
      const field = useNumberField<number | null>({
        value: seed,
        parse: (text) => (text.trim() === "" ? null : strictInt(text)),
        commit: setSeed,
        format: (value) => (value === null ? "" : String(value)),
      });
      return <input type="number" aria-label="field" {...field.inputProps} />;
    }
    const view = render(<Seed />);
    const input = view.getByLabelText("field") as HTMLInputElement;
    expect(input.value).toBe("");
    type(input, "12");
    fireEvent.blur(input);
    expect(input.value).toBe("12");
    type(input, "");
    fireEvent.blur(input);
    expect(input.value).toBe("");
  });
});
