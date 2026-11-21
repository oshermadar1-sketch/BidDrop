// The password input: show/hide toggle and the live rules checklist.
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react-native";
import PasswordField from "../app/components/PasswordField";
import { AUTH_COLORS } from "../app/ui/authStyles";

function Wrapper({ showRules }: { showRules?: boolean }) {
  const [value, setValue] = React.useState("");
  return (
    <PasswordField label="סיסמה" value={value} onChangeText={setValue} showRules={showRules} />
  );
}

// A Text's style may be an array; merge it to read one property.
function colorOf(style: any): string | undefined {
  return (Array.isArray(style) ? Object.assign({}, ...style.flat()) : style)?.color;
}

describe("PasswordField", () => {
  test("hides the password until the toggle is pressed", async () => {
    // Testing Library 14 renders asynchronously and exposes the result on `screen`.
    await render(<Wrapper />);
    const { getByPlaceholderText, getByText } = screen;
    expect(getByPlaceholderText("••••••••").props.secureTextEntry).toBe(true);

    await fireEvent.press(getByText("הצגה"));
    expect(getByPlaceholderText("••••••••").props.secureTextEntry).toBe(false);
    expect(getByText("הסתרה")).toBeTruthy();
  });

  test("ticks the rules as the user types", async () => {
    await render(<Wrapper showRules />);
    const { getByPlaceholderText, getByText } = screen;
    await fireEvent.changeText(getByPlaceholderText("••••••••"), "Abc12");
    // Upper, lower and digit are satisfied; the length rule is not.
    expect(colorOf(getByText("אות גדולה באנגלית (A-Z)").props.style)).toBe(AUTH_COLORS.good);
    expect(colorOf(getByText("אות קטנה באנגלית (a-z)").props.style)).toBe(AUTH_COLORS.good);
    expect(colorOf(getByText("ספרה אחת לפחות (0-9)").props.style)).toBe(AUTH_COLORS.good);
    expect(colorOf(getByText("לפחות 8 תווים").props.style)).toBe(AUTH_COLORS.dim);

    await fireEvent.changeText(getByPlaceholderText("••••••••"), "Abc12345");
    expect(colorOf(getByText("לפחות 8 תווים").props.style)).toBe(AUTH_COLORS.good);
  });
});
